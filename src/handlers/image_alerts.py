"""Handlers para gestión de alertas de imágenes."""

import re
import time
import httpx
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

from src.config import get_settings

settings = get_settings()
API_URL = settings.tasalo_api_url


async def _safe_edit_message(query, text, reply_markup=None, parse_mode="Markdown"):
    """Edit message safely - works with both text and photo messages.

    For photo messages, sends a new message instead of editing.

    Args:
        query: CallbackQuery from Telegram
        text: Text to send/edit
        reply_markup: Optional keyboard
        parse_mode: Parse mode (default: Markdown)
    """
    try:
        # Try to edit existing message
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except Exception as e:
        if "There is no text in the message to edit" in str(e):
            # Message is a photo - send new message instead
            await query.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        else:
            # Re-raise other errors
            raise


async def alert_enable_default_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activar alerta default (7:15 AM)."""
    action_start = time.time()
    query = update.callback_query
    user_id = update.effective_user.id
    callback_data = query.data

    logger.info("🔔 Alert enable-default action '%s' from user %d", callback_data, user_id)

    await query.answer("🔔 Activando alerta...")

    try:
        api_start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/api/v1/images/alerts",
                json={
                    "user_id": user_id,
                    "alert_time": "07:15",
                    "format_type": "photo",
                    "enabled": True
                },
                timeout=5.0
            )
            data = response.json()
        api_duration_ms = (time.time() - api_start) * 1000

        logger.info("📡 Alert enable-default API call completed for user %d (%.0fms) - response ok=%s",
                     user_id, api_duration_ms, data.get("ok"))
        logger.debug("Alert API response: %s", data)

        if data.get("ok"):
            await _safe_edit_message(
                query,
                "✅ *Alerta Activada!*\n\n"
                "Recibirás la imagen diaria a las *7:15 AM* (hora Cuba).\n\n"
                "Usa /toqueimg para ver la imagen ahora.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Ver imagen", callback_data="toqueimg_refresh")
                ]])
            )
        else:
            error_msg = data.get("error", "Unknown API error")
            logger.error("❌ Alert enable-default API returned ok=False for user %d: %s",
                         user_id, error_msg)
            raise Exception(f"API error: {error_msg}")

    except httpx.HTTPError as http_err:
        logger.error("❌ Alert enable-default HTTP error for user %d: %s",
                     user_id, http_err, exc_info=True)
        await _safe_edit_message(query, f"❌ Error de conexión: {str(http_err)}")
    except Exception as e:
        logger.error("❌ Alert enable-default unexpected error for user %d: %s",
                     user_id, e, exc_info=True)
        await _safe_edit_message(query, f"❌ Error: {str(e)}")
    finally:
        duration_ms = (time.time() - action_start) * 1000
        logger.info("✅ Alert enable-default action '%s' completed for user %d (%.0fms)",
                     callback_data, user_id, duration_ms)


async def alert_custom_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elegir hora personalizada."""
    action_start = time.time()
    query = update.callback_query
    user_id = update.effective_user.id
    callback_data = query.data

    logger.info("🔔 Alert custom-time action '%s' from user %d", callback_data, user_id)

    await query.answer()

    try:
        await _safe_edit_message(
            query,
            "⏰ *Elegir Hora Personalizada*\n\n"
            "Envíame la hora en formato `HH:MM` (ej: `08:30`, `22:00`)\n\n"
            "La hora es de Cuba (UTC-4).\n\n"
            "Envía /cancel para cancelar.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancelar", callback_data="alert_cancel")
            ]])
        )

        # Set state for next message
        context.user_data["waiting_for_time"] = True
        context.user_data["alert_action"] = "set_custom_time"

        logger.info("✅ Alert custom-time state set for user %d (waiting_for_time=True)", user_id)

    except Exception as e:
        logger.error("❌ Alert custom-time error for user %d: %s",
                     user_id, e, exc_info=True)
        await _safe_edit_message(query, f"❌ Error: {str(e)}")
    finally:
        duration_ms = (time.time() - action_start) * 1000
        logger.info("✅ Alert custom-time action '%s' completed for user %d (%.0fms)",
                     callback_data, user_id, duration_ms)


async def handle_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesar hora enviada por el usuario."""
    action_start = time.time()
    user_id = update.effective_user.id
    time_str = update.message.text.strip()

    logger.info("⏰ Alert time-input received '%s' from user %d", time_str, user_id)

    if not context.user_data.get("waiting_for_time"):
        logger.debug("⏰ Alert time-input ignored - not waiting for time from user %d", user_id)
        return

    # Validar formato HH:MM
    format_start = time.time()
    if not re.match(r"^\d{2}:\d{2}$", time_str):
        format_duration_ms = (time.time() - format_start) * 1000
        logger.warning("⚠️ Alert time-input format validation failed for user %d: '%s' (%.0fms)",
                       user_id, time_str, format_duration_ms)
        await update.message.reply_text(
            "❌ Formato inválido. Usa `HH:MM` (ej: `08:30`)",
            parse_mode="Markdown"
        )
        return

    # Validar hora válida
    try:
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError()
        logger.info("✅ Alert time-input validation passed for user %d: %s", user_id, time_str)
    except ValueError:
        logger.warning("⚠️ Alert time-input value validation failed for user %d: '%s'",
                       user_id, time_str)
        await update.message.reply_text(
            "❌ Hora inválida. Usa formato 24h (00:00 - 23:59)",
            parse_mode="Markdown"
        )
        return

    # Guardar en API
    try:
        api_start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/api/v1/images/alerts",
                json={
                    "user_id": user_id,
                    "alert_time": time_str,
                    "format_type": "photo",
                    "enabled": True
                },
                timeout=5.0
            )
            data = response.json()
        api_duration_ms = (time.time() - api_start) * 1000

        logger.info("📡 Alert time-input API call completed for user %d, time=%s (%.0fms) - ok=%s",
                     user_id, time_str, api_duration_ms, data.get("ok"))

        if data.get("ok"):
            await update.message.reply_text(
                f"✅ *Alerta configurada!*\n\n"
                f"Recibirás la imagen diaria a las *{time_str}* (hora Cuba).\n\n"
                "Usa /toqueimg para ver la imagen ahora.",
                parse_mode="Markdown"
            )
        else:
            error_msg = data.get("error", "Unknown API error")
            logger.error("❌ Alert time-input API returned ok=False for user %d: %s",
                         user_id, error_msg)
            raise Exception(f"API error: {error_msg}")

    except httpx.HTTPError as http_err:
        logger.error("❌ Alert time-input HTTP error for user %d: %s",
                     user_id, http_err, exc_info=True)
        await update.message.reply_text(f"❌ Error de conexión: {str(http_err)}")
    except Exception as e:
        logger.error("❌ Alert time-input error for user %d: %s",
                     user_id, e, exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        # Clear state
        context.user_data["waiting_for_time"] = False
        context.user_data["alert_action"] = None
        duration_ms = (time.time() - action_start) * 1000
        logger.info("✅ Alert time-input action completed for user %d, time=%s (%.0fms)",
                     user_id, time_str, duration_ms)


async def alert_disable_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desactivar alerta."""
    action_start = time.time()
    query = update.callback_query
    user_id = update.effective_user.id
    callback_data = query.data

    logger.info("🔔 Alert disable action '%s' from user %d", callback_data, user_id)

    await query.answer("❌ Desactivando alerta...")

    try:
        api_start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/api/v1/images/alerts/{user_id}/disable",
                timeout=5.0
            )
            data = response.json()
        api_duration_ms = (time.time() - api_start) * 1000

        logger.info("📡 Alert disable API call completed for user %d (%.0fms) - ok=%s",
                     user_id, api_duration_ms, data.get("ok"))

        if data.get("ok"):
            await _safe_edit_message(
                query,
                "❌ *Alerta Desactivada*\n\n"
                "Ya no recibirás la imagen diaria automáticamente.\n\n"
                "Usa /toqueimg para ver la imagen manualmente.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Ver imagen", callback_data="toqueimg_refresh")
                ]])
            )
        else:
            error_msg = data.get("error", "Unknown API error")
            logger.error("❌ Alert disable API returned ok=False for user %d: %s",
                         user_id, error_msg)
            raise Exception(f"API error: {error_msg}")

    except httpx.HTTPError as http_err:
        logger.error("❌ Alert disable HTTP error for user %d: %s",
                     user_id, http_err, exc_info=True)
        await _safe_edit_message(query, f"❌ Error de conexión: {str(http_err)}")
    except Exception as e:
        logger.error("❌ Alert disable error for user %d: %s",
                     user_id, e, exc_info=True)
        await _safe_edit_message(query, f"❌ Error: {str(e)}")
    finally:
        duration_ms = (time.time() - action_start) * 1000
        logger.info("✅ Alert disable action '%s' completed for user %d (%.0fms)",
                     callback_data, user_id, duration_ms)


async def alert_change_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cambiar hora de alerta existente."""
    action_start = time.time()
    query = update.callback_query
    user_id = update.effective_user.id
    callback_data = query.data

    logger.info("🔔 Alert change-time action '%s' from user %d", callback_data, user_id)

    await query.answer()

    try:
        await _safe_edit_message(
            query,
            "⏰ *Cambiar Hora de Alerta*\n\n"
            "Envíame la nueva hora en formato `HH:MM` (ej: `08:30`, `22:00`)\n\n"
            "Envía /cancel para cancelar.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancelar", callback_data="alert_cancel")
            ]])
        )

        context.user_data["waiting_for_time"] = True
        context.user_data["alert_action"] = "change_time"

        logger.info("✅ Alert change-time state set for user %d (waiting_for_time=True, action=change_time)",
                     user_id)

    except Exception as e:
        logger.error("❌ Alert change-time error for user %d: %s",
                     user_id, e, exc_info=True)
        await _safe_edit_message(query, f"❌ Error: {str(e)}")
    finally:
        duration_ms = (time.time() - action_start) * 1000
        logger.info("✅ Alert change-time action '%s' completed for user %d (%.0fms)",
                     callback_data, user_id, duration_ms)


async def alert_change_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cambiar formato de imagen (photo/document)."""
    action_start = time.time()
    query = update.callback_query
    user_id = update.effective_user.id
    callback_data = query.data

    logger.info("🔔 Alert change-format action '%s' from user %d", callback_data, user_id)

    await query.answer()

    try:
        keyboard = [
            [InlineKeyboardButton(
                "📷 Foto",
                callback_data="alert_format_photo",
                style="primary",  # Azul - opción por defecto
            )],
            [InlineKeyboardButton(
                "📄 Documento",
                callback_data="alert_format_document",
            )],
            [InlineKeyboardButton(
                "❌ Cancelar",
                callback_data="alert_cancel",
            )],
        ]

        await _safe_edit_message(
            query,
            "📄 *Cambiar Formato*\n\n"
            "Elige cómo quieres recibir la imagen:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        logger.info("✅ Alert change-format keyboard rendered for user %d", user_id)

    except Exception as e:
        logger.error("❌ Alert change-format error for user %d: %s",
                     user_id, e, exc_info=True)
        await _safe_edit_message(query, f"❌ Error: {str(e)}")
    finally:
        duration_ms = (time.time() - action_start) * 1000
        logger.info("✅ Alert change-format action '%s' completed for user %d (%.0fms)",
                     callback_data, user_id, duration_ms)


async def alert_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guardar formato seleccionado."""
    action_start = time.time()
    query = update.callback_query
    user_id = update.effective_user.id
    callback_data = query.data

    logger.info("🔔 Alert format-save action '%s' from user %d", callback_data, user_id)

    await query.answer()

    format_type = callback_data.split("_")[-1]  # "photo" or "document"
    logger.info("📄 Alert format-save parsed format_type='%s' for user %d", format_type, user_id)

    try:
        # Get current alert time
        api_get_start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/api/v1/images/alerts/{user_id}",
                timeout=5.0
            )
            alert_data = response.json()
        api_get_duration_ms = (time.time() - api_get_start) * 1000

        logger.info("📡 Alert format-save GET API completed for user %d (%.0fms)",
                     user_id, api_get_duration_ms)

        current_time = alert_data.get("data", {}).get("alert_time", "07:15")
        logger.info("📡 Alert format-save current_time='%s' for user %d", current_time, user_id)

        # Update alert
        api_post_start = time.time()
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{API_URL}/api/v1/images/alerts",
                json={
                    "user_id": user_id,
                    "alert_time": current_time,
                    "format_type": format_type,
                    "enabled": True
                },
                timeout=5.0
            )
        api_post_duration_ms = (time.time() - api_post_start) * 1000

        logger.info("📡 Alert format-save POST API completed for user %d, format=%s (%.0fms)",
                     user_id, format_type, api_post_duration_ms)

        await _safe_edit_message(
            query,
            f"✅ *Formato Actualizado*\n\n"
            f"Recibirás la imagen como *{format_type}*.\n\n"
            "Usa /toqueimg para ver la imagen ahora.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Ver imagen", callback_data="toqueimg_refresh")
            ]])
        )

    except httpx.HTTPError as http_err:
        logger.error("❌ Alert format-save HTTP error for user %d: %s",
                     user_id, http_err, exc_info=True)
        await _safe_edit_message(query, f"❌ Error de conexión: {str(http_err)}")
    except Exception as e:
        logger.error("❌ Alert format-save error for user %d: %s",
                     user_id, e, exc_info=True)
        await _safe_edit_message(query, f"❌ Error: {str(e)}")
    finally:
        duration_ms = (time.time() - action_start) * 1000
        logger.info("✅ Alert format-save action '%s' completed for user %d, format=%s (%.0fms)",
                     callback_data, user_id, format_type, duration_ms)


async def alert_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar estado actual de alerta."""
    action_start = time.time()
    query = update.callback_query
    user_id = update.effective_user.id
    callback_data = query.data

    logger.info("🔔 Alert status action '%s' from user %d", callback_data, user_id)

    await query.answer()

    try:
        api_start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/api/v1/images/alerts/{user_id}",
                timeout=5.0
            )
            alert_data = response.json()
        api_duration_ms = (time.time() - api_start) * 1000

        logger.info("📡 Alert status API call completed for user %d (%.0fms) - has_data=%s",
                     user_id, api_duration_ms, bool(alert_data.get("data")))

        if alert_data.get("data"):
            alert = alert_data["data"]
            logger.info("📊 Alert status details for user %d - time=%s, format=%s, enabled=%s",
                        user_id, alert.get("alert_time"), alert.get("format_type"),
                        alert.get("enabled"))

            await _safe_edit_message(
                query,
                "✅ *Estado de Alerta*\n\n"
                f"⏰ Hora: *{alert['alert_time']}*\n"
                f"📄 Formato: *{alert['format_type']}*\n"
                f"✅ Estado: *Activa*\n\n"
                "Usa los botones para cambiar la configuración.",
                reply_markup=query.message.reply_markup
            )
        else:
            logger.warning("⚠️ Alert status no data found for user %d", user_id)
            await _safe_edit_message(
                query,
                "⚠️ *Sin Alerta Configurada*\n\n"
                "No tienes una alerta activa. Usa /toqueimg para configurar una.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔔 Activar Alerta", callback_data="alert_enable_default")
                ]])
            )

    except httpx.HTTPError as http_err:
        logger.error("❌ Alert status HTTP error for user %d: %s",
                     user_id, http_err, exc_info=True)
        await _safe_edit_message(query, f"❌ Error de conexión: {str(http_err)}")
    except Exception as e:
        logger.error("❌ Alert status error for user %d: %s",
                     user_id, e, exc_info=True)
        await _safe_edit_message(query, f"❌ Error: {str(e)}")
    finally:
        duration_ms = (time.time() - action_start) * 1000
        logger.info("✅ Alert status action '%s' completed for user %d (%.0fms)",
                     callback_data, user_id, duration_ms)


async def alert_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancelar operación."""
    action_start = time.time()
    query = update.callback_query
    user_id = update.effective_user.id
    callback_data = query.data

    logger.info("🔔 Alert cancel action '%s' from user %d", callback_data, user_id)

    await query.answer("❌ Cancelado")

    try:
        context.user_data["waiting_for_time"] = False
        context.user_data["alert_action"] = None

        logger.info("✅ Alert cancel state cleared for user %d", user_id)

        await _safe_edit_message(query, "❌ Operación cancelada.")

    except Exception as e:
        logger.error("❌ Alert cancel error for user %d: %s",
                     user_id, e, exc_info=True)
        await _safe_edit_message(query, f"❌ Error: {str(e)}")
    finally:
        duration_ms = (time.time() - action_start) * 1000
        logger.info("✅ Alert cancel action '%s' completed for user %d (%.0fms)",
                     callback_data, user_id, duration_ms)
