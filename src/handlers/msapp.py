"""Handler para el comando /msapp — publica un mensaje en la sección Alertas de la app Android.

Solo disponible para administradores (ver src/utils/permissions.py).
Ver docs/plans/2026-10-01-app-mensajes-notificaciones-y-blog.md (en tasalo/docs/plans).

A diferencia de /ms (que envía por Telegram a los usuarios del bot), /msapp NO envía nada
por Telegram: guarda el mensaje en taso-api (POST /api/v1/app/messages) y la app Android lo
muestra en Notificaciones → Alertas. Mantenerlo separado de /ms evita publicar en el canal
equivocado por un descuido.

Uso:
    /msapp <texto>        → publica el mensaje en la app
    /msapp list           → últimos mensajes publicados (con su #id)
    /msapp del <id>       → elimina un mensaje de la app
    (reply a un mensaje de texto) + /msapp   → publica ese texto

Formato: el mismo Markdown de Telegram (legacy) que usa /ms: *negrita*, _cursiva_, `código`,
[texto](url). La PRIMERA LÍNEA es el título (lo que se ve con el mensaje contraído); el resto es
el cuerpo que se ve al expandir. Si el mensaje tiene una sola línea, esa línea es el título y
también el cuerpo.

Antes de publicar se muestra una vista previa con botones de confirmación, igual que /ms.
El estado pendiente vive en context.bot_data["msapp_pending"][admin_id] (por admin).
"""

import logging
import re
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.utils.permissions import is_admin

logger = logging.getLogger(__name__)

# La API acepta hasta 4096; aquí se deja margen para que la vista previa (cabecera + pie)
# también quepa en un mensaje de Telegram.
MAX_BODY_LENGTH = 3600
MAX_TITLE_LENGTH = 120
LIST_LIMIT = 10

_COMMAND_PREFIX_RE = re.compile(r"^/msapp(?:@\w+)?[ \t]*", re.IGNORECASE)
_DELETE_RE = re.compile(r"^del\s+(\d+)$", re.IGNORECASE)
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)\s]+\)")
_PAIRED_MARKUP_RE = re.compile(r"([*_`])(.+?)\1")


def plain_title(line: str) -> str:
    """Primera línea sin marcas de Markdown (el título se muestra como texto plano en la app)."""
    text = _LINK_RE.sub(r"\1", line)
    for _ in range(2):  # dos pasadas por si hay marcas anidadas (*_texto_*)
        text = _PAIRED_MARKUP_RE.sub(r"\2", text)
    text = " ".join(text.split())
    if len(text) > MAX_TITLE_LENGTH:
        text = text[: MAX_TITLE_LENGTH - 1].rstrip() + "…"
    return text


def split_title_body(text: str) -> tuple[str, str]:
    """Separa título (primera línea, sin Markdown) y cuerpo (el resto, con su Markdown).

    Con una sola línea, el cuerpo es el mensaje completo.
    """
    text = text.strip()
    first, _, rest = text.partition("\n")
    return plain_title(first), (rest.strip() or text)


def extract_text(update: Update) -> str:
    """Texto del mensaje: lo escrito tras /msapp (conservando los saltos de línea) o el del reply."""
    message = update.message
    raw = _COMMAND_PREFIX_RE.sub("", message.text or "", count=1).strip()
    if raw:
        return raw
    source = message.reply_to_message
    if source and source.text:
        return source.text.strip()
    return ""


def _escape_md(text: str) -> str:
    """Escapa los caracteres especiales del Markdown legacy de Telegram."""
    return re.sub(r"([_*`\[])", r"\\\1", text)


def _preview_text(title: str, body: str) -> str:
    return (
        "📱 *Vista previa en la app*\n"
        "──────────────────\n"
        f"*Título (contraído):* {_escape_md(title)}\n\n"
        f"*Al expandir:*\n{body}\n"
        "──────────────────\n"
        "Se publicará en *Alertas* de la app Android. No se envía nada por Telegram."
    )


def _confirm_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Publicar en la app", callback_data=f"msapp_confirm:{admin_id}"),
        InlineKeyboardButton("❌ Cancelar", callback_data=f"msapp_cancel:{admin_id}"),
    ]])


def _pending_store(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.bot_data.setdefault("msapp_pending", {})


def _format_created_at(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d/%m %H:%M UTC")
    except ValueError:
        return value


async def msapp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler principal de /msapp: arma la vista previa (o lista/elimina) y espera confirmación."""
    admin_id = update.effective_user.id
    username = update.effective_user.username or str(admin_id)

    if not is_admin(admin_id):
        logger.warning("⚠️ Unauthorized /msapp attempt by user %d (@%s)", admin_id, username)
        await update.message.reply_text(
            "🔑 *Acceso Denegado*\n\nEste comando es solo para administradores.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    api_client = context.bot_data.get("api_client")
    if not api_client or not api_client.admin_key:
        logger.error("❌ api_client/admin_key no disponible para /msapp (admin %d)", admin_id)
        await update.message.reply_text(
            "⚠️ *Error de Configuración*\n\nEl bot no está configurado correctamente.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    raw = extract_text(update)
    if not raw:
        await update.message.reply_text(
            "⚠️ Uso:\n"
            "`/msapp <texto>` — publica el mensaje en la sección Alertas de la app\n"
            "`/msapp list` — últimos mensajes publicados\n"
            "`/msapp del <id>` — elimina un mensaje de la app\n\n"
            "La *primera línea* es el título (se ve contraído); el resto se ve al expandir. "
            "Formato: el mismo Markdown de Telegram que /ms (`*negrita*`, `_cursiva_`).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if raw.lower() == "list":
        await _list_messages(update, api_client)
        return

    delete_match = _DELETE_RE.match(raw)
    if delete_match:
        await _delete_message(update, api_client, int(delete_match.group(1)))
        return

    title, body = split_title_body(raw)
    if not title:
        await update.message.reply_text("⚠️ El mensaje no tiene un título válido en la primera línea.")
        return
    if len(body) > MAX_BODY_LENGTH:
        await update.message.reply_text(
            f"⚠️ El texto supera los {MAX_BODY_LENGTH} caracteres ({len(body)}). "
            "Acórtalo e inténtalo de nuevo."
        )
        return

    store = _pending_store(context)
    store[admin_id] = {"title": title, "body": body, "format": "telegram"}
    logger.info("📱 /msapp preview solicitado por admin %d (@%s), título=%r", admin_id, username, title)

    try:
        await update.message.reply_text(
            _preview_text(title, body),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_confirm_keyboard(admin_id),
        )
    except BadRequest as e:
        # Markdown inválido (un * o _ sin cerrar): la app usa el mismo formato, así que se corrige aquí.
        store.pop(admin_id, None)
        logger.info("⚠️ /msapp: Markdown inválido de admin %d: %s", admin_id, e)
        await update.message.reply_text(
            "⚠️ El formato no es válido para Telegram (¿un `*` o `_` sin cerrar?). "
            "La app usa el mismo formato, así que corrígelo y vuelve a enviarlo.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def _list_messages(update: Update, api_client) -> None:
    messages = await api_client.admin_list_app_messages(limit=LIST_LIMIT)
    if not messages:
        await update.message.reply_text("📭 No hay mensajes publicados en la app (o falló la consulta a taso-api).")
        return
    lines = ["📱 Mensajes en la app (los más nuevos primero):", ""]
    for m in messages:
        estado = "✅" if m.get("is_active", True) else "⏸"
        lines.append(f"#{m.get('id')} {estado} {_format_created_at(m.get('created_at'))} — {m.get('title', '')}")
    lines += ["", "Para eliminar uno: /msapp del <id>"]
    await update.message.reply_text("\n".join(lines))  # sin parse_mode: los títulos pueden traer símbolos


async def _delete_message(update: Update, api_client, message_id: int) -> None:
    deleted = await api_client.admin_delete_app_message(message_id)
    if deleted:
        await update.message.reply_text(f"🗑 Mensaje #{message_id} eliminado de la app.")
    else:
        await update.message.reply_text(f"⚠️ No se pudo eliminar #{message_id} (¿no existe?).")


def _parse_admin_id(callback_data: str) -> int | None:
    try:
        return int(callback_data.split(":", 1)[1])
    except (IndexError, ValueError):
        return None


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback msapp_confirm:<admin_id> — publica el mensaje en la app."""
    query = update.callback_query
    owner_id = _parse_admin_id(query.data)

    if owner_id is None or query.from_user.id != owner_id:
        await query.answer("⚠️ Este mensaje no te pertenece.", show_alert=True)
        return

    pending = _pending_store(context)
    payload = pending.pop(owner_id, None)
    if payload is None:
        await query.edit_message_text("⚠️ Esta publicación ya no está disponible (expiró o ya se procesó).")
        return

    api_client = context.bot_data.get("api_client")
    result = await api_client.admin_create_app_message(
        title=payload["title"],
        body=payload["body"],
        format=payload["format"],
        created_by=owner_id,
    )
    if result and result.get("ok") and result.get("data"):
        message_id = result["data"].get("id")
        logger.info("📱 /msapp publicado por admin %d: id=%s", owner_id, message_id)
        await query.edit_message_text(
            f"✅ Publicado en la app (#{message_id}).\n\n"
            "Los usuarios lo verán al abrir la app o en su próxima actualización en segundo plano "
            "(hasta ~30 min).\n\n"
            f"Para retirarlo: /msapp del {message_id}"
        )
    else:
        logger.error("❌ /msapp: taso-api no pudo guardar el mensaje (admin %d)", owner_id)
        await query.edit_message_text(
            "⚠️ No se pudo publicar en la app. Revisa que taso-api esté desplegada con "
            "/api/v1/app/messages. El mensaje se descartó."
        )


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback msapp_cancel:<admin_id> — descarta la publicación pendiente."""
    query = update.callback_query
    owner_id = _parse_admin_id(query.data)

    if owner_id is None or query.from_user.id != owner_id:
        await query.answer("⚠️ Este mensaje no te pertenece.", show_alert=True)
        return

    _pending_store(context).pop(owner_id, None)
    await query.edit_message_text("❌ Cancelado. No se publicó nada.")
