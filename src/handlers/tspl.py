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
import logging
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.handlers.p import get_crypto_client
from src.formatters import build_tspl_market_bullets
from src.services.tspl_digest_scheduler import (
    TSPL_DIGEST_CACHE_KEY,
    generate_and_cache_tspl_digest,
)
from src.stats_tracker import track_command_usage
from src.cache import cache

logger = logging.getLogger(__name__)

MARKET_CACHE_TTL_SECONDS = 900  # 15 min — mismo TTL que /spl
DIGEST_CACHE_TTL_SECONDS = 72000  # 20h — se regenera solo o vía el cron diario
MARKET_CACHE_KEY = "tspl_market_snapshot"


def _build_keyboard() -> InlineKeyboardMarkup:
    btn_refresh = InlineKeyboardButton("🔄 Actualizar", callback_data="tspl_refresh")
    return InlineKeyboardMarkup([[btn_refresh]])


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


def _build_message(digest: dict | None, snapshot: dict | None) -> str:
    fecha = datetime.now().strftime("%d %b %Y").lower()
    lede = (digest or {}).get("lede") or (
        "Panorama del mercado cripto de hoy — la sección de noticias no "
        "está disponible en este momento, pero los datos de mercado sí."
    )
    radar = (digest or {}).get("radar")

    partes = [
        f"📊 *TASALO Spotlight — {fecha}*",
        "",
        lede,
        "",
        "📰 *Lo más importante del día*",
        "",
        _build_news_section(digest),
        "",
        "📊 *Resumen del mercado*",
        "",
        build_tspl_market_bullets(snapshot or {}),
    ]

    if radar:
        partes.append("")
        partes.append(f"👀 *En el radar:* {radar}")

    return "\n".join(partes)


async def tspl_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback para botón 🔄 Actualizar de /tspl — refresca solo el
    snapshot de mercado (el digest de noticias sigue el ciclo de 1x/día,
    salvo que el cache esté vacío)."""
    logger.info("🔄 /tspl refresh callback by user %d", update.callback_query.from_user.id)
    cache.invalidate(MARKET_CACHE_KEY)
    await tspl_command(update, context)


async def tspl_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el TASALO Spotlight completo: lede + noticias del día
    (curadas por Groq 1x/día) + resumen de mercado + en el radar."""
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    logger.info("📊 /tspl command invoked by user %d (@%s)", user_id, username)

    if update.message:
        await update.message.reply_chat_action("typing")
    elif update.callback_query:
        await update.callback_query.answer("🔄 Actualizando...")

    try:
        digest, snapshot = await asyncio.gather(
            _get_or_build_digest(),
            _get_or_build_market_snapshot(),
        )
    except Exception as e:
        logger.error("❌ Error generando /tspl: %s", e, exc_info=True)
        digest, snapshot = None, None

    if not digest and not snapshot:
        error_msg = "⚠️ No se pudo generar el Spotlight en este momento. Intenta de nuevo en unos minutos."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        asyncio.create_task(track_command_usage(update, context, "/tspl", success=False))
        return

    mensaje = _build_message(digest, snapshot)
    keyboard = _build_keyboard()

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
