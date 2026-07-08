"""Handler para el comando /tkt — tickets de contacto usuario→admin.

Disponible para cualquier usuario (a diferencia de /ms y /ads, que son
solo-admin). Ver docs/plans/2026-07-07-comando-tkt-tickets.md (diseño
original) y docs/plans/2026-07-08-ms-directo-y-tkt-mejoras.md
(notificaciones al usuario + separación bug/promo).

Flujo bug:
    /tkt → menú (🐛 Reportar bug / 📢 Pedir promoción / ❌ Cancelar)
    → el bot pide el mensaje → el usuario responde con texto
    → se crea el ticket en taso-api y se notifica a todos los admins
      con botones ✋ Tomar / ✅ Resolver. El usuario recibe un aviso
      cuando el ticket es tomado y cuando es resuelto.

Flujo promo (pedir anuncio):
    Mismo inicio, pero la notificación a los admins trae botones
    ✅ Aprobar / ❌ Rechazar en vez de Tomar/Resolver — un anuncio no se
    "toma" ni se "resuelve" como un bug, se aprueba o se rechaza
    directamente. El usuario recibe un aviso con el resultado.

El flag context.user_data["tkt_awaiting"] guarda el kind ("bug"/"promo")
mientras se espera el mensaje del usuario — a diferencia de /ms (que usa
bot_data namespaced por admin), acá SÍ es correcto usar user_data porque
quien escribe el mensaje siguiente es siempre el mismo usuario que inició
el flujo, sin riesgo de cruce entre chats distintos.
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

from src.api_client import TasaloApiClient
from src.config import settings

logger = logging.getLogger(__name__)

KIND_LABELS = {"bug": "🐛 Bug", "promo": "📢 Promoción"}
MAX_MESSAGE_LENGTH = 1000  # debe coincidir con el límite del schema en taso-api


def _get_api_client(context: ContextTypes.DEFAULT_TYPE) -> TasaloApiClient:
    return context.bot_data.get("api_client")


async def _notify_user(bot, user_id: int, text: str) -> None:
    """Envía un aviso de estado al usuario dueño de un ticket.

    Envuelto en try/except Forbidden porque el usuario puede haber
    bloqueado al bot desde que abrió el ticket — no debe interrumpir el
    flujo del admin que está tomando/resolviendo/aprobando/rechazando.
    """
    try:
        await bot.send_message(user_id, text, parse_mode=ParseMode.MARKDOWN)
    except Forbidden:
        logger.warning("⚠️ Usuario %d bloqueó el bot, no se pudo notificar el estado del ticket", user_id)
    except Exception as e:
        logger.error("❌ Error notificando estado de ticket a user %d: %s", user_id, e)


def _menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🐛 Reportar un bug", callback_data=f"tkt_bug:{user_id}")],
        [InlineKeyboardButton("📢 Pedir promoción / anuncio", callback_data=f"tkt_promo:{user_id}")],
        [InlineKeyboardButton("❌ Cancelar", callback_data=f"tkt_cancel:{user_id}")],
    ])


def _ticket_admin_keyboard(ticket_id: int, kind: str, claimed: bool = False) -> InlineKeyboardMarkup:
    """Teclado mostrado a los admins en la notificación del ticket.

    Los tickets "promo" no pasan por Tomar/Resolver: se aprueban o se
    rechazan directamente, ya que no requieren el mismo trabajo de
    diagnóstico/arreglo que un bug.
    """
    if kind == "promo":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Aprobar", callback_data=f"tkt_approve:{ticket_id}"),
            InlineKeyboardButton("❌ Rechazar", callback_data=f"tkt_reject:{ticket_id}"),
        ]])
    if claimed:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Marcar resuelto", callback_data=f"tkt_resolve:{ticket_id}"),
        ]])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✋ Tomar ticket", callback_data=f"tkt_claim:{ticket_id}"),
        InlineKeyboardButton("✅ Resolver", callback_data=f"tkt_resolve:{ticket_id}"),
    ]])


async def tkt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler principal de /tkt — muestra el menú de contacto."""
    user_id = update.effective_user.id
    logger.info("🎫 /tkt invocado por user %d", user_id)

    await update.message.reply_text(
        "🎫 *Contactar a los administradores*\n\n"
        "¿Sobre qué quieres escribirnos?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_menu_keyboard(user_id),
    )


def _parse_owner_id(callback_data: str) -> int | None:
    try:
        return int(callback_data.split(":", 1)[1])
    except (IndexError, ValueError):
        return None


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback tkt_bug:<uid> / tkt_promo:<uid> / tkt_cancel:<uid> — elección del menú."""
    query = update.callback_query
    clicker_id = query.from_user.id
    owner_id = _parse_owner_id(query.data)

    if owner_id is None or clicker_id != owner_id:
        await query.answer("⚠️ Este menú no te pertenece. Usa /tkt para abrir el tuyo.", show_alert=True)
        return

    if query.data.startswith("tkt_cancel:"):
        await query.edit_message_text("❌ Cancelado.")
        context.user_data.pop("tkt_awaiting", None)
        return

    kind = "bug" if query.data.startswith("tkt_bug:") else "promo"
    context.user_data["tkt_awaiting"] = kind

    prompt = (
        "🐛 Cuéntanos *en un solo mensaje* qué encontraste raro o qué no funciona."
        if kind == "bug"
        else "📢 Cuéntanos *en un solo mensaje* qué quieres promocionar o anunciar."
    )
    await query.edit_message_text(prompt, parse_mode=ParseMode.MARKDOWN)


async def _notify_admins(bot, ticket_id: int, kind: str, message: str, user_id: int, username: str | None) -> None:
    """Envía la notificación del ticket nuevo a todos los admins configurados."""
    label = KIND_LABELS.get(kind, kind)
    who = f"@{username}" if username else f"ID {user_id}"
    text = (
        f"🎫 *Ticket nuevo #{ticket_id}* — {label}\n\n"
        f"👤 {who}\n\n"
        f"💬 {message}"
    )
    keyboard = _ticket_admin_keyboard(ticket_id, kind, claimed=False)
    for admin_id in settings.get_admin_chat_ids_list():
        try:
            await bot.send_message(admin_id, text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        except Forbidden:
            logger.warning("⚠️ Admin %d bloqueó el bot, no se pudo notificar ticket #%d", admin_id, ticket_id)
        except Exception as e:
            logger.error("❌ Error notificando ticket #%d a admin %d: %s", ticket_id, admin_id, e)


async def handle_tkt_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """MessageHandler global: captura el mensaje siguiente a la elección del menú.

    Se auto-filtra por el flag context.user_data["tkt_awaiting"] — si no está
    presente, retorna de inmediato sin interferir con los demás MessageHandler
    globales (handle_year_hour_input, handle_time_input), siguiendo el mismo
    patrón ya usado en el bot.
    """
    kind = context.user_data.get("tkt_awaiting")
    if not kind:
        return

    context.user_data.pop("tkt_awaiting", None)

    user = update.effective_user
    message_text = (update.message.text or "").strip()

    if len(message_text) < 3:
        await update.message.reply_text(
            "⚠️ El mensaje es muy corto. Usa /tkt de nuevo para intentarlo otra vez."
        )
        return
    if len(message_text) > MAX_MESSAGE_LENGTH:
        await update.message.reply_text(
            f"⚠️ El mensaje supera los {MAX_MESSAGE_LENGTH} caracteres. "
            "Usa /tkt de nuevo con algo más corto."
        )
        return

    api_client = _get_api_client(context)
    if not api_client:
        await update.message.reply_text("⚠️ Error interno. Intenta de nuevo más tarde.")
        return

    result = await api_client.create_ticket(
        user_id=user.id, kind=kind, message=message_text, username=user.username,
    )
    if not result or not result.get("ok"):
        await update.message.reply_text(
            "❌ No se pudo crear el ticket. Intenta de nuevo más tarde con /tkt."
        )
        return

    ticket_id = result["data"]["id"]
    logger.info("🎫 Ticket #%d creado por user %d (kind=%s)", ticket_id, user.id, kind)

    await update.message.reply_text(
        "✅ Listo, un administrador te va a contactar pronto. ¡Gracias por avisarnos!"
    )
    await _notify_admins(context.bot, ticket_id, kind, message_text, user.id, user.username)


async def admin_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback tkt_claim: / tkt_resolve: / tkt_approve: / tkt_reject: — botones de admin."""
    query = update.callback_query
    admin_id = query.from_user.id

    if admin_id not in settings.get_admin_chat_ids_list():
        await query.answer("🔑 Solo administradores.", show_alert=True)
        return

    try:
        ticket_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return

    api_client = _get_api_client(context)
    if not api_client:
        return

    if query.data.startswith("tkt_claim:"):
        result = await api_client.update_ticket(ticket_id, claimed_by=admin_id)
        if not result or not result.get("ok"):
            await query.answer("⚠️ No se pudo tomar el ticket.", show_alert=True)
            return
        data = result.get("data", {})
        try:
            await query.edit_message_reply_markup(
                reply_markup=_ticket_admin_keyboard(ticket_id, data.get("kind", "bug"), claimed=True)
            )
        except BadRequest:
            pass
        await query.answer(f"✋ Ticket #{ticket_id} asignado a ti.")
        if data.get("user_id"):
            await _notify_user(
                context.bot, data["user_id"],
                f"✋ Tu ticket #{ticket_id} fue tomado por un administrador. En breve te contactará.",
            )
        return

    if query.data.startswith("tkt_resolve:"):
        result = await api_client.update_ticket(ticket_id, status="resolved")
        if not result or not result.get("ok"):
            await query.answer("⚠️ No se pudo marcar como resuelto.", show_alert=True)
            return
        data = result.get("data", {})
        label = KIND_LABELS.get(data.get("kind"), data.get("kind", "—"))
        who = f"@{data['username']}" if data.get("username") else f"ID {data.get('user_id', '—')}"
        try:
            await query.edit_message_text(
                f"🎫 *Ticket #{ticket_id}* — {label}\n\n"
                f"👤 {who}\n\n"
                f"💬 {data.get('message', '—')}\n\n"
                f"✅ *Resuelto*",
                parse_mode=ParseMode.MARKDOWN,
            )
        except BadRequest:
            pass
        await query.answer(f"✅ Ticket #{ticket_id} marcado como resuelto.")
        if data.get("user_id"):
            await _notify_user(
                context.bot, data["user_id"],
                f"✅ Tu ticket #{ticket_id} fue resuelto. ¡Gracias por avisarnos!",
            )
        return

    if query.data.startswith("tkt_approve:"):
        result = await api_client.update_ticket(ticket_id, status="approved")
        if not result or not result.get("ok"):
            await query.answer("⚠️ No se pudo aprobar el anuncio.", show_alert=True)
            return
        data = result.get("data", {})
        who = f"@{data['username']}" if data.get("username") else f"ID {data.get('user_id', '—')}"
        try:
            await query.edit_message_text(
                f"🎫 *Ticket #{ticket_id}* — {KIND_LABELS.get('promo')}\n\n"
                f"👤 {who}\n\n"
                f"💬 {data.get('message', '—')}\n\n"
                f"✅ *Aprobado*",
                parse_mode=ParseMode.MARKDOWN,
            )
        except BadRequest:
            pass
        await query.answer(f"✅ Anuncio #{ticket_id} aprobado.")
        if data.get("user_id"):
            await _notify_user(
                context.bot, data["user_id"],
                f"📢 Tu solicitud de anuncio #{ticket_id} fue aprobada. ¡Gracias!",
            )
        return

    if query.data.startswith("tkt_reject:"):
        result = await api_client.update_ticket(ticket_id, status="rejected")
        if not result or not result.get("ok"):
            await query.answer("⚠️ No se pudo rechazar el anuncio.", show_alert=True)
            return
        data = result.get("data", {})
        who = f"@{data['username']}" if data.get("username") else f"ID {data.get('user_id', '—')}"
        try:
            await query.edit_message_text(
                f"🎫 *Ticket #{ticket_id}* — {KIND_LABELS.get('promo')}\n\n"
                f"👤 {who}\n\n"
                f"💬 {data.get('message', '—')}\n\n"
                f"❌ *Rechazado*",
                parse_mode=ParseMode.MARKDOWN,
            )
        except BadRequest:
            pass
        await query.answer(f"❌ Anuncio #{ticket_id} rechazado.")
        if data.get("user_id"):
            await _notify_user(
                context.bot, data["user_id"],
                f"📢 Tu solicitud de anuncio #{ticket_id} fue rechazada. "
                "Si quieres más detalle, contacta a un administrador.",
            )
        return


async def tkts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler de /tkts (admin) — lista tickets abiertos/en progreso."""
    admin_id = update.effective_user.id
    if admin_id not in settings.get_admin_chat_ids_list():
        await update.message.reply_text("🔑 Este comando es solo para administradores.")
        return

    api_client = _get_api_client(context)
    if not api_client:
        await update.message.reply_text("⚠️ Error interno. Intenta de nuevo más tarde.")
        return

    open_tickets = await api_client.list_tickets(status="open")
    in_progress = await api_client.list_tickets(status="in_progress")
    tickets = open_tickets + in_progress

    if not tickets:
        await update.message.reply_text("✅ No hay tickets pendientes.")
        return

    lines = ["🎫 *Tickets pendientes*\n"]
    for t in tickets:
        label = KIND_LABELS.get(t["kind"], t["kind"])
        who = f"@{t['username']}" if t.get("username") else f"ID {t['user_id']}"
        status_icon = "🔵" if t["status"] == "open" else "🟡"
        claimed = f" (tomado por {t['claimed_by']})" if t.get("claimed_by") else ""
        lines.append(f"{status_icon} #{t['id']} {label} — {who}{claimed}\n   _{t['message'][:80]}_")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
