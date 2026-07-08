"""Handler para el comando /ms — mensaje a todos los usuarios o a uno solo.

Solo disponible para administradores (ver src/utils/permissions.py).
Ver docs/plans/2026-07-07-comando-ms-broadcast.md (broadcast original) y
docs/plans/2026-07-08-ms-directo-y-tkt-mejoras.md (envío a un usuario).

Uso:
    /ms <texto>                → difunde ese texto a todos los usuarios
    /ms @usuario <texto>       → envía ese texto solo a @usuario
    (reply a foto/foto+caption) + /ms [@usuario]  → difunde/envía esa foto
        (con o sin caption) a todos los usuarios o solo a @usuario

En todos los casos se muestra un preview con botones de confirmación antes
de enviar nada — un envío (masivo o individual) no debe dispararse por
error de un solo tap/enter.

El estado del envío pendiente vive en
context.bot_data["ms_pending"][admin_id], namespaced por admin para que
dos admins puedan preparar envíos distintos sin pisarse.
"""

import asyncio
import logging
import re
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut
from telegram.ext import ContextTypes

from src.api_client import TasaloApiClient
from src.utils.permissions import is_admin

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 4096      # límite de Telegram para send_message
MAX_CAPTION_LENGTH = 1024   # límite de Telegram para caption de send_photo
CONCURRENCY = 20            # envíos simultáneos máximos
BATCH_PAUSE_SECONDS = 1.0   # pausa entre lotes (~20 msg/s, bajo el límite de Telegram)
PROGRESS_EVERY = 50         # editar el mensaje de status cada N usuarios procesados

TARGET_USERNAME_RE = re.compile(r"^@([\w]{5,32})$")


def _get_api_client(context: ContextTypes.DEFAULT_TYPE) -> TasaloApiClient:
    return context.bot_data.get("api_client")


def _pending_store(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Diccionario admin_id -> payload pendiente, vive en bot_data."""
    return context.bot_data.setdefault("ms_pending", {})


def _extract_payload(update: Update) -> dict | None:
    """Arma el payload a enviar desde /ms [@usuario] <texto> o desde un reply.

    Si el primer token del texto del comando es un @username válido, se
    guarda en payload["target_username"] y se quita del resto del texto
    antes de armar el contenido — el @usuario nunca forma parte del
    mensaje que se envía.

    Returns:
        {"kind": "text", "text": str, "target_username": str | None} o
        {"kind": "photo", "photo_file_id": str, "caption": str | None,
         "target_username": str | None}
        None si no hay contenido válido.
    """
    message = update.message
    tokens = (message.text or "").split()[1:]

    target_username = None
    if tokens and TARGET_USERNAME_RE.match(tokens[0]):
        target_username = tokens[0][1:]  # sin el "@"
        tokens = tokens[1:]

    args_text = " ".join(tokens).strip()
    source = message.reply_to_message if message.reply_to_message else None

    # Reply a una foto: prioridad sobre el texto plano del propio /ms,
    # que en ese caso actúa como reemplazo del caption si se escribió algo.
    if source and source.photo:
        photo_file_id = source.photo[-1].file_id  # mayor resolución disponible
        caption = args_text if args_text else source.caption
        return {
            "kind": "photo", "photo_file_id": photo_file_id, "caption": caption,
            "target_username": target_username,
        }

    if source and source.text:
        text = args_text if args_text else source.text
        return {"kind": "text", "text": text, "target_username": target_username} if text else None

    if args_text:
        return {"kind": "text", "text": args_text, "target_username": target_username}

    return None


def _validate_payload(payload: dict) -> str | None:
    """Valida límites de Telegram. Returns mensaje de error o None si OK."""
    if payload["kind"] == "text":
        if len(payload["text"]) > MAX_TEXT_LENGTH:
            return (
                f"⚠️ El texto supera los {MAX_TEXT_LENGTH} caracteres "
                f"({len(payload['text'])}). Acórtalo e inténtalo de nuevo."
            )
    elif payload["kind"] == "photo":
        caption = payload.get("caption") or ""
        if len(caption) > MAX_CAPTION_LENGTH:
            return (
                f"⚠️ El caption supera los {MAX_CAPTION_LENGTH} caracteres "
                f"({len(caption)}). Acórtalo e inténtalo de nuevo."
            )
    return None


def _preview_text(payload: dict, total_users: int) -> str:
    """Arma el texto de preview mostrado antes de confirmar el envío."""
    header = "📢 *Vista previa del mensaje*\n──────────────────\n"
    if payload["kind"] == "photo":
        body = payload.get("caption") or "_(foto sin texto)_"
        body += "\n\n🖼 _(se enviará también la foto adjunta)_"
    else:
        body = payload["text"]
    if payload.get("target_username"):
        footer = f"\n──────────────────\nSe enviará solo a *@{payload['target_username']}*."
    else:
        footer = f"\n──────────────────\nSe enviará a *{total_users}* usuarios."
    return header + body + footer


def _confirm_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirmar envío", callback_data=f"ms_confirm:{admin_id}"),
        InlineKeyboardButton("❌ Cancelar", callback_data=f"ms_cancel:{admin_id}"),
    ]])


async def ms_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler principal de /ms. Arma el preview y espera confirmación."""
    admin_id = update.effective_user.id
    username = update.effective_user.username or str(admin_id)

    if not is_admin(admin_id):
        logger.warning("⚠️ Unauthorized /ms attempt by user %d (@%s)", admin_id, username)
        await update.message.reply_text(
            "🔑 *Acceso Denegado*\n\nEste comando es solo para administradores.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    api_client = _get_api_client(context)
    if not api_client or not api_client.admin_key:
        logger.error("❌ api_client/admin_key no disponible para /ms (admin %d)", admin_id)
        await update.message.reply_text(
            "⚠️ *Error de Configuración*\n\nEl bot no está configurado correctamente.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    payload = _extract_payload(update)
    if payload is None:
        await update.message.reply_text(
            "⚠️ Uso:\n"
            "`/ms <texto>` — difunde ese texto a todos los usuarios\n"
            "`/ms @usuario <texto>` — envía ese texto solo a @usuario\n"
            "o responde (reply) con `/ms [@usuario]` a un mensaje con foto/texto "
            "para difundir o enviar *ese* contenido.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    error = _validate_payload(payload)
    if error:
        await update.message.reply_text(error)
        return

    target_username = payload.get("target_username")
    logger.info(
        "📢 /ms preview solicitado por admin %d (@%s), kind=%s, target=%s",
        admin_id, username, payload["kind"], target_username or "todos",
    )

    if target_username:
        target_user_id = await api_client.lookup_user_id_by_username(target_username)
        if target_user_id is None:
            await update.message.reply_text(
                f"⚠️ @{target_username} no está registrado en el bot (nunca ejecutó "
                "ningún comando, o cambió de username). Pídele que use /start primero."
            )
            return
        payload["target_user_id"] = target_user_id
        total_users = 1
    else:
        user_ids = await api_client.admin_list_user_ids()
        if not user_ids:
            await update.message.reply_text(
                "⚠️ No hay usuarios registrados todavía (o falló la consulta a taso-api). "
                "No se puede difundir nada."
            )
            return
        total_users = len(user_ids)

    payload["in_progress"] = False
    _pending_store(context)[admin_id] = payload

    await update.message.reply_text(
        _preview_text(payload, total_users),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_confirm_keyboard(admin_id),
    )


async def _send_one(bot, user_id: int, payload: dict, semaphore: asyncio.Semaphore) -> str:
    """Envía el payload a un usuario. Returns 'ok' | 'blocked' | 'error'."""
    async with semaphore:
        try:
            if payload["kind"] == "photo":
                await bot.send_photo(
                    chat_id=user_id,
                    photo=payload["photo_file_id"],
                    caption=payload.get("caption"),
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=payload["text"],
                    parse_mode=ParseMode.MARKDOWN,
                )
            return "ok"
        except Forbidden:
            # Usuario bloqueó el bot — no es un error del sistema, es esperable.
            return "blocked"
        except RetryAfter as e:
            # Telegram pide esperar por flood control: un único reintento.
            await asyncio.sleep(e.retry_after)
            try:
                if payload["kind"] == "photo":
                    await bot.send_photo(
                        chat_id=user_id, photo=payload["photo_file_id"],
                        caption=payload.get("caption"), parse_mode=ParseMode.MARKDOWN,
                    )
                else:
                    await bot.send_message(
                        chat_id=user_id, text=payload["text"], parse_mode=ParseMode.MARKDOWN,
                    )
                return "ok"
            except Exception:
                return "error"
        except (BadRequest, TimedOut):
            return "error"
        except Exception as e:
            logger.debug("⚠️ Error enviando /ms a user %d: %s", user_id, e)
            return "error"


async def _run_broadcast(bot, payload: dict, user_ids: list, status_message) -> None:
    """Envía el broadcast a todos los user_ids, editando status_message con progreso."""
    semaphore = asyncio.Semaphore(CONCURRENCY)
    counts = {"ok": 0, "blocked": 0, "error": 0}
    start = time.time()
    last_edit = start

    async def _run_one(uid: int):
        result = await _send_one(bot, uid, payload, semaphore)
        counts[result] += 1

    tasks = [asyncio.create_task(_run_one(uid)) for uid in user_ids]

    for i, task in enumerate(tasks, 1):
        await task
        now = time.time()
        if i % PROGRESS_EVERY == 0 or (now - last_edit) >= 2.0:
            last_edit = now
            try:
                await status_message.edit_text(
                    f"📤 Enviando... {i}/{len(user_ids)} "
                    f"(✅ {counts['ok']} · 🚫 {counts['blocked']} · ⚠️ {counts['error']})"
                )
            except BadRequest:
                pass  # mensaje sin cambios o editado muy seguido, no es crítico
        if i % CONCURRENCY == 0:
            await asyncio.sleep(BATCH_PAUSE_SECONDS)

    duration_s = time.time() - start
    await status_message.edit_text(
        "✅ *Broadcast completado*\n\n"
        f"✅ Enviado: {counts['ok']}\n"
        f"🚫 Bloquearon el bot: {counts['blocked']}\n"
        f"⚠️ Errores: {counts['error']}\n\n"
        f"⏱ {duration_s:.1f}s · {len(user_ids)} usuarios totales",
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(
        "✅ /ms broadcast completado: ok=%d blocked=%d error=%d (%.1fs)",
        counts["ok"], counts["blocked"], counts["error"], duration_s,
    )


def _parse_admin_id(callback_data: str) -> int | None:
    try:
        return int(callback_data.split(":", 1)[1])
    except (IndexError, ValueError):
        return None


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback ms_confirm:<admin_id> — dispara el envío (individual o masivo)."""
    query = update.callback_query
    clicker_id = query.from_user.id
    owner_id = _parse_admin_id(query.data)

    if owner_id is None or clicker_id != owner_id:
        await query.answer("⚠️ Este envío no te pertenece.", show_alert=True)
        return

    pending = _pending_store(context)
    payload = pending.get(owner_id)
    if payload is None:
        await query.edit_message_text("⚠️ Este envío ya no está disponible (expiró o ya se procesó).")
        return
    if payload.get("in_progress"):
        await query.answer("⏳ Ya está en curso, espera a que termine.", show_alert=True)
        return

    # Envío a un único usuario: se salta todo el motor de broadcast
    # (semáforo, progreso, pausa entre lotes) — no aplica para 1 solo mensaje.
    target_user_id = payload.get("target_user_id")
    if target_user_id is not None:
        payload["in_progress"] = True
        logger.info("📢 /ms confirmado por admin %d — envío directo a user %d", owner_id, target_user_id)
        semaphore = asyncio.Semaphore(1)
        try:
            result = await _send_one(context.bot, target_user_id, payload, semaphore)
        finally:
            pending.pop(owner_id, None)

        if result == "ok":
            await query.edit_message_text(f"✅ Mensaje enviado a @{payload['target_username']}.")
        elif result == "blocked":
            await query.edit_message_text(
                f"🚫 No se pudo enviar: @{payload['target_username']} bloqueó al bot."
            )
        else:
            await query.edit_message_text(
                f"⚠️ Error al enviar a @{payload['target_username']}. Intenta de nuevo."
            )
        return

    api_client = _get_api_client(context)
    user_ids = await api_client.admin_list_user_ids()
    if not user_ids:
        await query.edit_message_text("⚠️ No se pudo obtener la lista de usuarios. Cancelado.")
        pending.pop(owner_id, None)
        return

    payload["in_progress"] = True
    logger.info("📢 /ms confirmado por admin %d — enviando a %d usuarios", owner_id, len(user_ids))

    status_message = await query.edit_message_text(f"📤 Enviando... 0/{len(user_ids)}")
    try:
        await _run_broadcast(context.bot, payload, user_ids, status_message)
    finally:
        pending.pop(owner_id, None)


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback ms_cancel:<admin_id> — descarta el envío pendiente."""
    query = update.callback_query
    clicker_id = query.from_user.id
    owner_id = _parse_admin_id(query.data)

    if owner_id is None or clicker_id != owner_id:
        await query.answer("⚠️ Este envío no te pertenece.", show_alert=True)
        return

    _pending_store(context).pop(owner_id, None)
    await query.edit_message_text("❌ Cancelado. No se envió nada.")
