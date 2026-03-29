"""Handlers para gestión de alertas de imágenes."""

import re
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
    query = update.callback_query
    await query.answer("🔔 Activando alerta...")

    user_id = update.effective_user.id

    try:
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
            raise Exception("API error")

    except Exception as e:
        logger.error(f"Error activating alert: {e}")
        await _safe_edit_message(query, f"❌ Error: {str(e)}")


async def alert_custom_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elegir hora personalizada."""
    query = update.callback_query
    await query.answer()

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


async def handle_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesar hora enviada por el usuario."""
    if not context.user_data.get("waiting_for_time"):
        return

    time_str = update.message.text.strip()

    # Validar formato HH:MM
    if not re.match(r"^\d{2}:\d{2}$", time_str):
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
    except ValueError:
        await update.message.reply_text(
            "❌ Hora inválida. Usa formato 24h (00:00 - 23:59)",
            parse_mode="Markdown"
        )
        return

    # Guardar en API
    user_id = update.effective_user.id

    try:
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

        if data.get("ok"):
            await update.message.reply_text(
                f"✅ *Alerta configurada!*\n\n"
                f"Recibirás la imagen diaria a las *{time_str}* (hora Cuba).\n\n"
                "Usa /toqueimg para ver la imagen ahora.",
                parse_mode="Markdown"
            )
        else:
            raise Exception("API error")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

    finally:
        # Clear state
        context.user_data["waiting_for_time"] = False
        context.user_data["alert_action"] = None


async def alert_disable_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desactivar alerta."""
    query = update.callback_query
    await query.answer("❌ Desactivando alerta...")

    user_id = update.effective_user.id

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/api/v1/images/alerts/{user_id}/disable",
                timeout=5.0
            )
            data = response.json()

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
            raise Exception("API error")

    except Exception as e:
        logger.error(f"Error disabling alert: {e}")
        await _safe_edit_message(query, f"❌ Error: {str(e)}")


async def alert_change_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cambiar hora de alerta existente."""
    query = update.callback_query
    await query.answer()

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


async def alert_change_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cambiar formato de imagen (photo/document)."""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("📷 Foto", callback_data="alert_format_photo")],
        [InlineKeyboardButton("📄 Documento", callback_data="alert_format_document")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="alert_cancel")],
    ]

    await _safe_edit_message(
        query,
        "📄 *Cambiar Formato*\n\n"
        "Elige cómo quieres recibir la imagen:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def alert_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guardar formato seleccionado."""
    query = update.callback_query
    await query.answer()

    format_type = query.data.split("_")[-1]  # "photo" or "document"
    user_id = update.effective_user.id

    # Get current alert time
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_URL}/api/v1/images/alerts/{user_id}",
            timeout=5.0
        )
        alert_data = response.json()

    current_time = alert_data.get("data", {}).get("alert_time", "07:15")

    # Update alert
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

    await _safe_edit_message(
        query,
        f"✅ *Formato Actualizado*\n\n"
        f"Recibirás la imagen como *{format_type}*.\n\n"
        "Usa /toqueimg para ver la imagen ahora.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Ver imagen", callback_data="toqueimg_refresh")
        ]])
    )


async def alert_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar estado actual de alerta."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_URL}/api/v1/images/alerts/{user_id}",
            timeout=5.0
        )
        alert_data = response.json()

    if alert_data.get("data"):
        alert = alert_data["data"]
        await _safe_edit_message(
            query,
            "✅ *Estado de Alerta*\n\n"
            f"⏰ Hora: *{alert['alert_time']}*\n"
            f"📄 Formato: *{alert['format_type']}*\n"
            f"✅ Estado: *Activa*\n\n"
            "Usa los botones para cambiar la configuración.",
            reply_markup=query.message.reply_markup
        )


async def alert_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancelar operación."""
    query = update.callback_query
    await query.answer("❌ Cancelado")

    context.user_data["waiting_for_time"] = False
    context.user_data["alert_action"] = None

    await _safe_edit_message(query, "❌ Operación cancelada.")
