# src/handlers/tspl.py
"""Handler para comando /tspl — TASALO Spotlight completo.

A diferencia de /spl (consulta rápida, datos duros + comentario corto de
IA), /tspl arma el formato completo tipo newsletter: lede + noticias del
día curadas por Groq (digest generado 1x/día por
services/tspl_digest_scheduler.py) + resumen de mercado en bullets +
sección "en el radar".

Ver docs/plans/2026-07-23-tspl-news-newsdata.md para el diseño completo.
"""

import asyncio
import html
import io
import logging
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.api_client import TasaloApiClient
from src.config import get_settings
from src.handlers.p import get_crypto_client
from src.formatters import build_tspl_market_bullets
from src.services.tspl_digest_scheduler import (
    TSPL_DIGEST_CACHE_KEY,
    generate_and_cache_tspl_digest,
)
from src.stats_tracker import track_command_usage
from src.cache import cache

logger = logging.getLogger(__name__)
settings = get_settings()

MARKET_CACHE_TTL_SECONDS = 900  # 15 min — mismo TTL que /spl
# El cron diario (tspl_digest_scheduler.py) corre a las 11:00 UTC, cada
# 24h. El TTL tiene que ser MAYOR a ese ciclo (no menor) para que el
# cache nunca se dé por "expirado" antes de que el cron vuelva a correr
# — si no, cualquier /tspl o /tspl blog que caiga en ese hueco dispara
# una regeneración bajo demanda con Groq (no determinístico), pudiendo
# quedar un digest distinto entre Telegram y el blog el mismo día.
DIGEST_CACHE_TTL_SECONDS = 90000  # 25h (24h del ciclo + 1h de margen)
MARKET_CACHE_KEY = "tspl_market_snapshot"

_tspl_api = TasaloApiClient(
    api_url=settings.tasalo_api_url,
    admin_key=settings.tasalo_admin_key,
    timeout=30,
)

MAX_SUBSCRIPTIONS = 2

# ── /tspl blog ───────────────────────────────────────────────────────────
# Plantilla fija del post de blog (imagen de cabecera + separador + firma
# de cierre) — según lo acordado, esto no cambia entre posts; lo único que
# varía de un Spotlight a otro es el contenido (lede, noticias, datos de
# mercado, radar), armado en _build_blog_content(). Todo en Markdown
# estándar, sin HTML embebido — el editor del blog acepta HTML puro por
# ahora pero ya avisa que puede dejar de ser compatible.
BLOG_HEADER_IMAGE_URL = "https://i.ecency.com/DQmZ3vUBg22bWXVqrhFt9py6s1HVdh9RzbEjcLcYzz4ZGSV/img_2286.png"
BLOG_FOOTER = (
    "---\n\n"
    "*📲 TASALO Spotlight es tomado directamente de mi bot de "
    "Telegram: [@tasalobot](https://t.me/tasalobot)*"
)

# Límite real de Telegram: 4096 caracteres (UTF-16 code units) tras el
# parseo de entidades del mensaje. Dejamos margen porque len() de Python
# cuenta codepoints, no UTF-16 code units — los emojis fuera del BMP (la
# mayoría de los que usa este post) ocupan 2 code units en Telegram pero
# 1 en len() de Python.
BLOG_MESSAGE_SAFE_LIMIT = 3500

# Horas UTC preestablecidas — 11 UTC coincide con el horario del digest
# diario (tspl_digest_scheduler.py), así el primer envío del día siempre
# tiene noticias frescas.
_HOUR_OPTIONS = [
    (11, "🌅 7 AM Cuba"),
    (17, "🌆 1 PM Cuba"),
    (23, "🌙 7 PM Cuba"),
]


def _build_keyboard(active_hours: list[int] | None = None) -> InlineKeyboardMarkup:
    """Arma el teclado de /tspl: refrescar + suscripción a horarios.

    A diferencia de /y (selección única), acá cada botón de hora es un
    toggle independiente — hasta MAX_SUBSCRIPTIONS activos a la vez.
    """
    active_hours = active_hours or []

    hour_row = []
    for hour, label in _HOUR_OPTIONS:
        prefix = "✅ " if hour in active_hours else ""
        hour_row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"tspl_sub_{hour}"))

    buttons = [
        [InlineKeyboardButton("🔄 Actualizar", callback_data="tspl_refresh")],
        hour_row,
        [InlineKeyboardButton("⏰ Personalizar hora", callback_data="tspl_sub_custom")],
    ]
    if active_hours:
        buttons.append([InlineKeyboardButton("🔕 Desactivar todo", callback_data="tspl_sub_off")])

    return InlineKeyboardMarkup(buttons)


def _build_news_section(digest: dict | None) -> str:
    """Arma el bloque "📰 Lo más importante del día" a partir del digest.

    Si no hay digest disponible (Groq/NewsData fallaron y no hay cache
    previo), retorna un aviso corto en vez de omitir la sección en
    silencio — así el usuario entiende por qué falta esa parte.
    """
    if not digest or not digest.get("items"):
        return "_(noticias no disponibles en este momento)_"

    lines = []
    for item in digest["items"]:
        emoji = item.get("emoji", "📰")
        titulo = item.get("titulo", "").strip()
        parrafo = item.get("parrafo", "").strip()
        if not titulo:
            continue
        lines.append(f"{emoji} *{titulo}*")
        if parrafo:
            lines.append(parrafo)
        lines.append("")

    return "\n".join(lines).rstrip() if lines else "_(noticias no disponibles en este momento)_"


async def _get_or_build_market_snapshot() -> dict | None:
    """Retorna el snapshot de mercado desde cache, o lo pide fresco."""
    cached = cache.get(MARKET_CACHE_KEY, ttl=MARKET_CACHE_TTL_SECONDS)
    if cached:
        return cached

    client = get_crypto_client()
    snapshot = await client.get_market_snapshot()
    if snapshot:
        cache.set(MARKET_CACHE_KEY, snapshot)
    return snapshot


async def _get_or_build_digest() -> dict | None:
    """Retorna el digest de noticias desde cache (generado por el cron
    diario), o lo genera bajo demanda si el cache está vacío/expirado
    (primer uso tras un restart, o si nadie preguntó desde ayer)."""
    cached = cache.get(TSPL_DIGEST_CACHE_KEY, ttl=DIGEST_CACHE_TTL_SECONDS)
    if cached:
        return cached
    return await generate_and_cache_tspl_digest()


def _fecha_hoy() -> str:
    """Fecha en formato corto (ej. '13 sep 2026'), compartida entre el
    mensaje de Telegram y el post de blog para que ambos queden iguales."""
    return datetime.now().strftime("%d %b %Y").lower()


def _build_message(digest: dict | None, snapshot: dict | None) -> str:
    fecha = _fecha_hoy()
    lede = (digest or {}).get("lede") or (
        "Panorama del mercado cripto de hoy — la sección de noticias no "
        "está disponible en este momento, pero los datos de mercado sí."
    )
    teaser = (digest or {}).get("teaser")
    radar = (digest or {}).get("radar")

    partes = [
        f"📊 *TASALO Spotlight — {fecha}*",
        "",
        lede,
    ]

    if teaser:
        partes.append("")
        partes.append(teaser)

    partes.extend([
        "",
        "📰 *Lo más importante del día*",
        "",
        _build_news_section(digest),
        "",
        "📊 *Resumen del mercado*",
        "",
        build_tspl_market_bullets(snapshot or {}),
    ])

    if radar:
        partes.append("")
        partes.append(f"👀 *En el radar:* {radar}")

    return "\n".join(partes)


def _build_blog_news_section(digest: dict | None) -> str:
    """Versión blog de _build_news_section(): cada noticia como encabezado
    H3 (### emoji titulo) en vez de una línea en negrita — mismo digest,
    solo cambia el marcado para Markdown estándar en vez de Telegram."""
    if not digest or not digest.get("items"):
        return "_(noticias no disponibles en este momento)_"

    lines = []
    for item in digest["items"]:
        emoji = item.get("emoji", "📰")
        titulo = item.get("titulo", "").strip()
        parrafo = item.get("parrafo", "").strip()
        if not titulo:
            continue
        lines.append(f"### {emoji} {titulo}")
        lines.append("")
        if parrafo:
            lines.append(parrafo)
        lines.append("")

    return "\n".join(lines).rstrip() if lines else "_(noticias no disponibles en este momento)_"


def _telegram_text_length(text: str) -> int:
    """Longitud en UTF-16 code units, la unidad que Telegram usa para el
    límite de 4096 caracteres — distinta de len() de Python (codepoints)
    cuando hay emojis fuera del BMP (la mayoría de los de este post)."""
    return len(text.encode("utf-16-le")) // 2


def _build_blog_content(digest: dict | None, snapshot: dict | None) -> str:
    """Arma el post de blog completo del TASALO Spotlight, para /tspl blog.

    Reutiliza el mismo digest y snapshot que la versión de Telegram
    (_build_message) — no dispara ninguna llamada nueva a Groq ni a las
    APIs de mercado. La diferencia es de formato y de cantidad de datos:
    Markdown estándar (## / ### / **negrita**) en vez de Markdown v1 de
    Telegram, y el bloque de mercado en su variante "extended" (suma
    sesgo técnico BTC, gainers/losers y tendencia — datos que ya vienen
    en el snapshot pero que no entraban en el mensaje corto de Telegram).

    La imagen de cabecera y la firma de cierre son fijos
    (BLOG_HEADER_IMAGE_URL / BLOG_FOOTER) — solo el contenido varía. Sin
    HTML embebido: todo en Markdown estándar, para que el editor del blog
    lo trate como contenido nativo en vez de "HTML puro".
    """
    fecha = _fecha_hoy()
    lede = (digest or {}).get("lede") or (
        "Panorama del mercado cripto de hoy — la sección de noticias no "
        "está disponible en este momento, pero los datos de mercado sí."
    )
    teaser = (digest or {}).get("teaser")
    radar = (digest or {}).get("radar")

    cuerpo = [
        f"# 📊 TASALO Spotlight — {fecha}",
        "",
        lede,
    ]

    if teaser:
        cuerpo.append("")
        cuerpo.append(teaser)

    cuerpo.extend([
        "",
        "## 📰 Lo más importante del día",
        "",
        _build_blog_news_section(digest),
        "",
        "## 📊 Resumen del mercado",
        "",
        build_tspl_market_bullets(snapshot or {}, extended=True, bold="**", bullet="-"),
    ])

    if radar:
        cuerpo.extend([
            "",
            "## 👀 En el radar",
            "",
            radar,
        ])

    return "\n".join([
        f"![]({BLOG_HEADER_IMAGE_URL})",
        "",
        "\n".join(cuerpo),
        "",
        BLOG_FOOTER,
    ])


async def tspl_blog_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Subcomando `/tspl blog` — arma el mismo Spotlight en Markdown
    estándar listo para pegar en el blog, con más datos de mercado que la
    versión de Telegram.

    Entrega:
    - Si el contenido entra en el límite de Telegram (4096 caracteres tras
      el parseo de entidades), lo manda como mensaje HTML envuelto en
      <pre>...</pre> — dentro de un bloque <pre> Telegram no aplica ningún
      formato, así que el markdown queda literal y se copia con un tap en
      móvil, sin la fricción de tener que abrir un archivo.
    - Si no entra, cae a un documento .txt (nunca .md: abrir un .md en el
      teléfono puede disparar un visor que lo renderice en vez de mostrarlo
      como texto plano, justo el problema que se quiere evitar)."""
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    logger.info("📊 /tspl blog invoked by user %d (@%s)", user_id, username)

    if not update.message:
        return

    await update.message.reply_chat_action("typing")

    try:
        digest, snapshot = await asyncio.gather(
            _get_or_build_digest(),
            _get_or_build_market_snapshot(),
        )
    except Exception as e:
        logger.error("❌ Error generando /tspl blog: %s", e, exc_info=True)
        digest, snapshot = None, None

    if not digest and not snapshot:
        await update.message.reply_text(
            "⚠️ No se pudo generar el Spotlight en este momento. Intenta de nuevo en unos minutos."
        )
        asyncio.create_task(track_command_usage(update, context, "/tspl", source="blog", success=False))
        return

    contenido = _build_blog_content(digest, snapshot)

    try:
        if _telegram_text_length(contenido) <= BLOG_MESSAGE_SAFE_LIMIT:
            await update.message.reply_text(
                f"<pre>{html.escape(contenido)}</pre>",
                parse_mode=ParseMode.HTML,
            )
        else:
            filename = f"tasalo-spotlight-{datetime.now().strftime('%Y-%m-%d')}.txt"
            await update.message.reply_document(
                document=io.BytesIO(contenido.encode("utf-8")),
                filename=filename,
                caption=(
                    "📄 Spotlight en Markdown — muy largo para un mensaje de "
                    "Telegram, va como archivo .txt. Ábrelo y copia el contenido."
                ),
            )
    except Exception as e:
        logger.error("❌ Error enviando /tspl blog: %s", e, exc_info=True)
        await update.message.reply_text("⚠️ No se pudo generar el post. Intenta de nuevo en unos minutos.")
        asyncio.create_task(track_command_usage(update, context, "/tspl", source="blog", success=False))
        return

    total_duration_ms = (time.time() - cmd_start) * 1000
    logger.info("✅ /tspl blog completed for user %d (%.0fms)", user_id, total_duration_ms)
    asyncio.create_task(track_command_usage(update, context, "/tspl", source="blog", success=True))


async def tspl_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback para botón 🔄 Actualizar de /tspl — refresca solo el
    snapshot de mercado (el digest de noticias sigue el ciclo de 1x/día,
    salvo que el cache esté vacío)."""
    logger.info("🔄 /tspl refresh callback by user %d", update.callback_query.from_user.id)
    cache.invalidate(MARKET_CACHE_KEY)
    await tspl_command(update, context)


async def tspl_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle tspl_sub_* callbacks (tspl_sub_<hora>, tspl_sub_custom, tspl_sub_off).

    NOTE: callback_router ya llamó a query.answer() una vez antes de
    despachar acá (mismo criterio documentado en year_sub_callback,
    handlers/y.py) — llamar de nuevo con texto/show_alert es lo que ya
    hace ese handler y funciona en producción, así que seguimos el mismo
    patrón acá.
    """
    query = update.callback_query
    user_id = query.from_user.id
    callback_data = query.data

    if callback_data == "tspl_sub_custom":
        context.user_data["awaiting_tspl_hour"] = time.time()
        await query.message.reply_text(
            "⏰ *Personalizar hora de /tspl*\n\n"
            "Responde a este mensaje con la hora (0-23) en formato UTC "
            "a la que quieres recibir el Spotlight completo.\n\n"
            f"Podés tener hasta {MAX_SUBSCRIPTIONS} horarios activos a la vez.\n"
            "Ejemplos: `9` para las 9:00 AM, `23` para las 7:00 PM Cuba.",
            parse_mode="Markdown",
        )
        return

    if callback_data == "tspl_sub_off":
        ok = await _tspl_api.delete_all_tspl_subscriptions(user_id)
        if not ok:
            await query.answer("⚠️ No se pudo desactivar", show_alert=True)
            return
        await query.answer("🔕 Suscripción a /tspl desactivada")
        try:
            await query.edit_message_reply_markup(reply_markup=_build_keyboard([]))
        except BadRequest:
            pass
        return

    if callback_data.startswith("tspl_sub_"):
        try:
            hour = int(callback_data.split("_")[-1])
        except ValueError:
            return

        current_hours = await _tspl_api.get_tspl_subscriptions(user_id)

        if hour in current_hours:
            # Toggle off: ya estaba activa, la sacamos
            await _tspl_api.delete_tspl_subscription(user_id, hour)
            await query.answer(f"🔕 Horario {hour}:00 UTC desactivado")
            new_hours = [h for h in current_hours if h != hour]
        else:
            if len(current_hours) >= MAX_SUBSCRIPTIONS:
                await query.answer(
                    f"⚠️ Máximo {MAX_SUBSCRIPTIONS} horarios — desactivá uno primero",
                    show_alert=True,
                )
                return
            result = await _tspl_api.add_tspl_subscription(user_id, hour)
            if not result or result.get("error"):
                await query.answer("❌ Error al guardar", show_alert=True)
                return
            await query.answer(f"✅ Horario {hour}:00 UTC activado")
            new_hours = current_hours + [hour]

        try:
            await query.edit_message_reply_markup(reply_markup=_build_keyboard(new_hours))
        except BadRequest:
            pass
        return

    raise ValueError(f"Unrecognised tspl callback: {callback_data}")


async def handle_tspl_hour_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """MessageHandler para la hora personalizada tras tocar '⏰ Personalizar
    hora' en /tspl. Espera un número 0-23 dentro de los 300s siguientes."""
    entry_time = context.user_data.get("awaiting_tspl_hour")
    if not entry_time:
        return
    if time.time() - entry_time > 300:
        del context.user_data["awaiting_tspl_hour"]
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not text.isdigit():
        del context.user_data["awaiting_tspl_hour"]
        await update.message.reply_text(
            "⚠️ Operación cancelada. Usa /tspl y seleccioná ⏰ Personalizar hora para intentar de nuevo.",
        )
        return

    hour = int(text)
    if not (0 <= hour <= 23):
        await update.message.reply_text(
            "❌ Hora inválida. Usa un número entre 0 y 23 (UTC).\nEjemplo: `9` para las 9:00 AM.",
            parse_mode="Markdown",
        )
        return

    del context.user_data["awaiting_tspl_hour"]

    current_hours = await _tspl_api.get_tspl_subscriptions(user_id)
    if hour in current_hours:
        await update.message.reply_text(f"ℹ️ Ya estás suscrito a las {hour}:00 UTC.")
        return
    if len(current_hours) >= MAX_SUBSCRIPTIONS:
        await update.message.reply_text(
            f"⚠️ Ya tenés {MAX_SUBSCRIPTIONS} horarios activos. Desactivá uno desde /tspl antes de agregar otro."
        )
        return

    await update.message.reply_text("⏳ Guardando horario...")
    result = await _tspl_api.add_tspl_subscription(user_id, hour)
    if not result or result.get("error"):
        await update.message.reply_text("❌ Error al guardar el horario. Intenta más tarde.")
        return

    await update.message.reply_text(
        f"✅ *Spotlight programado* a las {hour}:00 UTC.\nUsa /tspl para ver o modificar tus horarios.",
        parse_mode="Markdown",
    )


async def tspl_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el TASALO Spotlight completo: lede + noticias del día
    (curadas por Groq 1x/día) + resumen de mercado + en el radar."""
    args = context.args or []
    if args and args[0].lower() == "blog":
        await tspl_blog_command(update, context)
        return

    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    logger.info("📊 /tspl command invoked by user %d (@%s)", user_id, username)

    if update.message:
        await update.message.reply_chat_action("typing")
    elif update.callback_query:
        await update.callback_query.answer("🔄 Actualizando...")

    try:
        digest, snapshot, active_hours = await asyncio.gather(
            _get_or_build_digest(),
            _get_or_build_market_snapshot(),
            _tspl_api.get_tspl_subscriptions(user_id),
        )
    except Exception as e:
        logger.error("❌ Error generando /tspl: %s", e, exc_info=True)
        digest, snapshot, active_hours = None, None, []

    if not digest and not snapshot:
        error_msg = "⚠️ No se pudo generar el Spotlight en este momento. Intenta de nuevo en unos minutos."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        asyncio.create_task(track_command_usage(update, context, "/tspl", success=False))
        return

    mensaje = _build_message(digest, snapshot)
    keyboard = _build_keyboard(active_hours)

    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                mensaje, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        else:
            await update.message.reply_text(
                mensaje, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard,
                disable_web_page_preview=True,
            )
    except Exception as e:
        if "Message is not modified" in str(e):
            if update.callback_query:
                await update.callback_query.answer("✅ Ya actualizado")
        else:
            logger.warning("⚠️ Fallo enviando /tspl con Markdown: %s", e)
            texto_plano = mensaje.replace("*", "").replace("_", "")
            try:
                if update.callback_query:
                    await update.callback_query.edit_message_text(texto_plano, reply_markup=keyboard)
                else:
                    await update.message.reply_text(texto_plano, reply_markup=keyboard)
            except Exception as e2:
                logger.error("❌ Error enviando /tspl (fallback): %s", e2, exc_info=True)
                asyncio.create_task(track_command_usage(update, context, "/tspl", success=False))
                return

    total_duration_ms = (time.time() - cmd_start) * 1000
    logger.info("✅ /tspl completed for user %d (%.0fms)", user_id, total_duration_ms)
    asyncio.create_task(track_command_usage(update, context, "/tspl", success=True))
