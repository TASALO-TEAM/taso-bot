"""Handler para el comando /ads — gestión del sistema de anuncios.

Solo disponible para administradores (ver src/utils/permissions.py).
Ver docs/plans/2026-07-04-sistema-anuncios.md para el diseño completo.

Uso:
    /ads                        → lista todos los anuncios
    /ads add <texto>            → crea un anuncio (Aviso, no patrocinado)
    /ads del <id>               → elimina un anuncio
    /ads on <id>  / off <id>    → activa/desactiva sin borrar
    /ads sponsor <id> / unsponsor <id> → marca/desmarca como Patrocinado
    /ads weight <id> <n>        → ajusta el peso (frecuencia relativa)
    /ads edit <id> <texto>      → edita el texto de un anuncio
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.api_client import TasaloApiClient
from src.utils.permissions import is_admin
from src.services.ads_manager import invalidate_ad_cache

logger = logging.getLogger(__name__)

MAX_AD_LENGTH = 300

HELP_TEXT = (
    "📢 *Gestión de Anuncios* — `/ads`\n\n"
    "`/ads` — lista todos los anuncios\n"
    "`/ads add <texto>` — crea un anuncio (Aviso)\n"
    "`/ads del <id>` — elimina un anuncio\n"
    "`/ads on <id>` / `/ads off <id>` — activa/desactiva\n"
    "`/ads sponsor <id>` / `/ads unsponsor <id>` — marca/desmarca Patrocinado\n"
    "`/ads weight <id> <n>` — ajusta el peso (1-100)\n"
    "`/ads edit <id> <texto>` — edita el texto"
)


def _get_api_client(context: ContextTypes.DEFAULT_TYPE) -> TasaloApiClient:
    return context.bot_data.get("api_client")


def _format_ad_line(ad: dict) -> str:
    """Formatea una línea del listado admin de /ads."""
    status = "✅" if ad.get("is_active") else "⏸️"
    kind = "📢Patrocinado" if ad.get("is_sponsored") else "📝Aviso"
    weight = ad.get("weight", 1)
    text = ad.get("text", "")
    preview = text if len(text) <= 60 else text[:57] + "..."
    return f"{status} `#{ad['id']}` {kind} (peso {weight})\n   {preview}"


def _parse_id(raw: str) -> int | None:
    """Parsea un id de anuncio desde texto. None si no es un entero válido."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def ads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal de /ads. Despacha a los subcomandos."""
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)

    if not is_admin(user_id):
        logger.warning("⚠️ Unauthorized /ads attempt by user %d (@%s)", user_id, username)
        await update.message.reply_text(
            "🔑 *Acceso Denegado*\n\nEste comando es solo para administradores.",
            parse_mode="Markdown",
        )
        return

    api_client = _get_api_client(context)
    if not api_client or not api_client.admin_key:
        logger.error("❌ api_client/admin_key no disponible para /ads (admin %d)", user_id)
        await update.message.reply_text(
            "⚠️ *Error de Configuración*\n\nEl bot no está configurado correctamente.",
            parse_mode="Markdown",
        )
        return

    args = context.args or []
    sub = args[0].lower() if args else ""

    logger.info("📢 /ads %s invoked by admin %d (@%s)", sub or "(list)", user_id, username)

    if sub == "":
        await _handle_list(update, api_client)
    elif sub == "add":
        await _handle_add(update, api_client, args[1:], user_id)
    elif sub == "del":
        await _handle_delete(update, api_client, args[1:])
    elif sub == "on":
        await _handle_toggle_active(update, api_client, args[1:], active=True)
    elif sub == "off":
        await _handle_toggle_active(update, api_client, args[1:], active=False)
    elif sub == "sponsor":
        await _handle_toggle_sponsor(update, api_client, args[1:], sponsored=True)
    elif sub == "unsponsor":
        await _handle_toggle_sponsor(update, api_client, args[1:], sponsored=False)
    elif sub == "weight":
        await _handle_weight(update, api_client, args[1:])
    elif sub == "edit":
        await _handle_edit(update, api_client, args[1:])
    else:
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def _handle_list(update: Update, api_client: TasaloApiClient) -> None:
    """`/ads` sin argumentos: lista todos los anuncios (activos e inactivos)."""
    ads = await api_client.admin_list_ads()
    if not ads:
        await update.message.reply_text(
            "📢 *Anuncios*\n\nNo hay ningún anuncio creado todavía.\n\n"
            "Usa `/ads add <texto>` para crear el primero.",
            parse_mode="Markdown",
        )
        return

    lines = ["📢 *Anuncios* (%d total)\n" % len(ads)]
    lines.extend(_format_ad_line(ad) for ad in ads)
    lines.append("\n" + HELP_TEXT)
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def _handle_add(
    update: Update, api_client: TasaloApiClient, args: list, user_id: int
) -> None:
    """`/ads add <texto>`: crea un anuncio nuevo (Aviso, no patrocinado)."""
    text = " ".join(args).strip()
    if not text:
        await update.message.reply_text(
            "⚠️ Uso: `/ads add <texto del anuncio>`", parse_mode="Markdown"
        )
        return
    if len(text) > MAX_AD_LENGTH:
        await update.message.reply_text(
            f"⚠️ El texto supera los {MAX_AD_LENGTH} caracteres "
            f"({len(text)}). Acortálo e inténtalo de nuevo."
        )
        return

    result = await api_client.admin_create_ad(text=text, created_by=user_id)
    if not result:
        await update.message.reply_text("❌ No se pudo crear el anuncio. Revisa los logs.")
        return

    invalidate_ad_cache()
    ad = result.get("data", {})
    await update.message.reply_text(
        f"✅ Anuncio `#{ad.get('id')}` creado como *Aviso*.\n\n{_format_ad_line(ad)}",
        parse_mode="Markdown",
    )


async def _handle_delete(update: Update, api_client: TasaloApiClient, args: list) -> None:
    """`/ads del <id>`: elimina un anuncio definitivamente."""
    ad_id = _parse_id(args[0]) if args else None
    if ad_id is None:
        await update.message.reply_text("⚠️ Uso: `/ads del <id>`", parse_mode="Markdown")
        return

    deleted = await api_client.admin_delete_ad(ad_id)
    if not deleted:
        await update.message.reply_text(f"❌ No existe el anuncio `#{ad_id}`.", parse_mode="Markdown")
        return

    invalidate_ad_cache()
    await update.message.reply_text(f"🗑️ Anuncio `#{ad_id}` eliminado.", parse_mode="Markdown")


async def _handle_toggle_active(
    update: Update, api_client: TasaloApiClient, args: list, active: bool
) -> None:
    """`/ads on <id>` / `/ads off <id>`: activa o desactiva sin borrar."""
    ad_id = _parse_id(args[0]) if args else None
    if ad_id is None:
        cmd = "on" if active else "off"
        await update.message.reply_text(f"⚠️ Uso: `/ads {cmd} <id>`", parse_mode="Markdown")
        return

    result = await api_client.admin_update_ad(ad_id, is_active=active)
    if not result:
        await update.message.reply_text(f"❌ No existe el anuncio `#{ad_id}`.", parse_mode="Markdown")
        return

    invalidate_ad_cache()
    ad = result.get("data", {})
    estado = "activado ✅" if active else "pausado ⏸️"
    await update.message.reply_text(
        f"Anuncio `#{ad_id}` {estado}.\n\n{_format_ad_line(ad)}", parse_mode="Markdown"
    )


async def _handle_toggle_sponsor(
    update: Update, api_client: TasaloApiClient, args: list, sponsored: bool
) -> None:
    """`/ads sponsor <id>` / `/ads unsponsor <id>`: cambia la etiqueta mostrada."""
    ad_id = _parse_id(args[0]) if args else None
    if ad_id is None:
        cmd = "sponsor" if sponsored else "unsponsor"
        await update.message.reply_text(f"⚠️ Uso: `/ads {cmd} <id>`", parse_mode="Markdown")
        return

    result = await api_client.admin_update_ad(ad_id, is_sponsored=sponsored)
    if not result:
        await update.message.reply_text(f"❌ No existe el anuncio `#{ad_id}`.", parse_mode="Markdown")
        return

    invalidate_ad_cache()
    ad = result.get("data", {})
    etiqueta = "Patrocinado 📢" if sponsored else "Aviso 📝"
    await update.message.reply_text(
        f"Anuncio `#{ad_id}` marcado como *{etiqueta}*.\n\n{_format_ad_line(ad)}",
        parse_mode="Markdown",
    )


async def _handle_weight(update: Update, api_client: TasaloApiClient, args: list) -> None:
    """`/ads weight <id> <n>`: ajusta el peso (frecuencia relativa, 1-100)."""
    if len(args) < 2:
        await update.message.reply_text("⚠️ Uso: `/ads weight <id> <n>`", parse_mode="Markdown")
        return

    ad_id = _parse_id(args[0])
    weight = _parse_id(args[1])
    if ad_id is None or weight is None:
        await update.message.reply_text("⚠️ `<id>` y `<n>` deben ser números enteros.", parse_mode="Markdown")
        return
    if not (1 <= weight <= 100):
        await update.message.reply_text("⚠️ El peso debe estar entre 1 y 100.")
        return

    result = await api_client.admin_update_ad(ad_id, weight=weight)
    if not result:
        await update.message.reply_text(f"❌ No existe el anuncio `#{ad_id}`.", parse_mode="Markdown")
        return

    invalidate_ad_cache()
    ad = result.get("data", {})
    await update.message.reply_text(
        f"Peso de `#{ad_id}` actualizado a {weight}.\n\n{_format_ad_line(ad)}",
        parse_mode="Markdown",
    )


async def _handle_edit(update: Update, api_client: TasaloApiClient, args: list) -> None:
    """`/ads edit <id> <texto nuevo>`: edita el texto sin perder el id."""
    if len(args) < 2:
        await update.message.reply_text("⚠️ Uso: `/ads edit <id> <texto nuevo>`", parse_mode="Markdown")
        return

    ad_id = _parse_id(args[0])
    text = " ".join(args[1:]).strip()
    if ad_id is None:
        await update.message.reply_text("⚠️ `<id>` debe ser un número entero.", parse_mode="Markdown")
        return
    if not text:
        await update.message.reply_text("⚠️ El texto nuevo no puede estar vacío.")
        return
    if len(text) > MAX_AD_LENGTH:
        await update.message.reply_text(
            f"⚠️ El texto supera los {MAX_AD_LENGTH} caracteres ({len(text)})."
        )
        return

    result = await api_client.admin_update_ad(ad_id, text=text)
    if not result:
        await update.message.reply_text(f"❌ No existe el anuncio `#{ad_id}`.", parse_mode="Markdown")
        return

    invalidate_ad_cache()
    ad = result.get("data", {})
    await update.message.reply_text(
        f"✏️ Anuncio `#{ad_id}` actualizado.\n\n{_format_ad_line(ad)}",
        parse_mode="Markdown",
    )
