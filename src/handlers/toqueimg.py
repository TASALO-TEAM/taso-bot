"""Handler for /toqueimg command."""

import httpx
import logging
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

from src.config import get_settings
from src.api_client import TasaloApiClient

settings = get_settings()
API_URL = settings.tasalo_api_url  # https://tasalo.duckdns.org

api_client = TasaloApiClient(api_url=API_URL)


async def toqueimg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /toqueimg - Muestra imagen de ElToque con botones de alerta.
    """
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    first_name = update.effective_user.first_name or "Unknown"
    
    logger.info(
        "📸 /toqueimg command invoked by user %d (@%s, %s)",
        user_id, username, first_name
    )

    # 1. Mostrar "loading"
    loading_msg = await update.message.reply_text("📸 Capturando imagen...")

    try:
        # 2. Capturar imagen desde API (con retry automático 3x)
        capture_start = time.time()
        logger.debug("User %d: Starting image capture from API", user_id)
        
        capture_data = await api_client._post_with_retry(
            f"{API_URL}/api/v1/images/eltoque/capture",
            timeout=httpx.Timeout(30.0, connect=7.0)
        )

        capture_duration_ms = (time.time() - capture_start) * 1000
        logger.info(
            "User %d: Image capture completed (%.0fms)",
            user_id, capture_duration_ms
        )

        if not capture_data or not capture_data.get("ok"):
            error_detail = capture_data.get('error')
            logger.error(
                "User %d: API capture returned error: %s",
                user_id, error_detail
            )
            raise Exception(f"API error: {error_detail}")

        # 3. Obtener última imagen (file path) (con retry automático 3x)
        latest_start = time.time()
        logger.debug("User %d: Fetching latest image info", user_id)
        
        latest_data = await api_client._get_with_retry(
            f"{API_URL}/api/v1/images/eltoque/latest",
            timeout=httpx.Timeout(10.0, connect=5.0)
        )

        latest_duration_ms = (time.time() - latest_start) * 1000
        logger.info(
            "User %d: Latest image fetch completed (%.0fms)",
            user_id, latest_duration_ms
        )

        if not latest_data or not latest_data.get("ok"):
            logger.error("User %d: Failed to get latest image - response: %s", user_id, latest_data)
            raise Exception("Failed to get latest image")

        image_path = latest_data["data"]["image_path"]
        logger.debug("User %d: Image path resolved to: %s", user_id, image_path)

        # 4. Verificar si usuario tiene alerta activa (con retry automático 3x)
        alert_start = time.time()
        logger.debug("User %d: Checking alert status", user_id)
        
        alert_data = await api_client._get_with_retry(
            f"{API_URL}/api/v1/images/alerts/{user_id}",
            timeout=httpx.Timeout(5.0, connect=3.0)
        )

        alert_duration_ms = (time.time() - alert_start) * 1000
        has_alert = (
            alert_data and
            alert_data.get("ok") and
            alert_data.get("data") and
            alert_data["data"].get("enabled", False)
        )
        logger.info(
            "User %d: Alert status check completed (%.0fms, has_alert=%s)",
            user_id, alert_duration_ms, has_alert
        )

        # 5. Construir keyboard interactivo
        keyboard = _build_toqueimg_keyboard(has_alert)
        logger.debug("User %d: Keyboard built (has_alert=%s)", user_id, has_alert)

        # 6. Construir caption simple (max 1024 chars para Telegram)
        caption = (
            "🇨🇺 *Tasa Diaria El Toque*\n"
            f"📅 {datetime.now().strftime('%d/%m/%Y')}\n\n"
            "Esta es la tasa diaria de El Toque."
        )

        # Debug: log caption length
        caption_length = len(caption)
        logger.debug("User %d: Caption length: %d chars", user_id, caption_length)

        # 7. Enviar imagen
        send_start = time.time()
        logger.debug("User %d: Starting image send to Telegram", user_id)
        
        try:
            with open(image_path, "rb") as f:
                await loading_msg.edit_media(
                    media=InputMediaPhoto(
                        media=f,
                        caption=caption,
                        parse_mode="Markdown"
                    ),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            
            send_duration_ms = (time.time() - send_start) * 1000
            logger.info(
                "User %d: Image sent successfully (%.0fms)",
                user_id, send_duration_ms
            )
            
        except Exception as media_error:
            send_duration_ms = (time.time() - send_start) * 1000
            logger.error(
                "User %d: Failed to send image after %.0fms - path: %s, error: %s",
                user_id, send_duration_ms, image_path, media_error,
                exc_info=True
            )
            logger.error(
                "User %d: Caption length: %d, Image path: %s",
                user_id, caption_length, image_path
            )
            # Fallback: enviar solo texto
            await loading_msg.edit_text(
                f"❌ Error al enviar imagen: {str(media_error)}\n\nIntenta de nuevo más tarde."
            )

    except Exception as e:
        cmd_duration_ms = (time.time() - cmd_start) * 1000
        logger.error(
            "User %d (@%s): /toqueimg command failed after %.0fms - %s",
            user_id, username, cmd_duration_ms, e,
            exc_info=True
        )
        await loading_msg.edit_text(
            f"❌ Error: {str(e)}\n\nIntenta de nuevo más tarde."
        )

    cmd_duration_ms = (time.time() - cmd_start) * 1000
    logger.info(
        "✅ /toqueimg completed for user %d (%.0fms)",
        user_id, cmd_duration_ms
    )


def _build_toqueimg_keyboard(has_alert: bool) -> list:
    """Construir keyboard según estado de alerta."""
    logger.debug("Building toqueimg keyboard (has_alert=%s)", has_alert)

    if has_alert:
        # Usuario YA tiene alerta activa
        keyboard = [
            [InlineKeyboardButton(
                "✅ Alerta activa",
                callback_data="alert_status",
                style="success",  # Verde - estado activo
            )],
            [
                InlineKeyboardButton(
                    "⏰ Cambiar hora",
                    callback_data="alert_change_time",
                ),
                InlineKeyboardButton(
                    "📄 Cambiar formato",
                    callback_data="alert_change_format",
                ),
            ],
            [InlineKeyboardButton(
                "❌ Desactivar alerta",
                callback_data="alert_disable",
                style="danger",  # Rojo - acción destructiva
            )],
        ]
    else:
        # Usuario NO tiene alerta
        keyboard = [
            [InlineKeyboardButton(
                "🔔 Activar alerta (7:15 AM)",
                callback_data="alert_enable_default",
                style="success",  # Verde - acción positiva
            )],
            [InlineKeyboardButton(
                "⏰ Elegir hora personalizada",
                callback_data="alert_custom_time",
            )],
        ]

    # Botón común de refresh
    keyboard.append([InlineKeyboardButton(
        "🔄 Actualizar imagen",
        callback_data="toqueimg_refresh",
        style="primary",  # Azul - acción principal
    )])

    return keyboard


async def toqueimg_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para botón Actualizar en /toqueimg."""
    callback_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    
    logger.info(
        "🔄 /toqueimg refresh callback invoked by user %d (@%s)",
        user_id, username
    )
    
    query = update.callback_query
    await query.answer("🔄 Actualizando...")

    try:
        # Re-ejecutar el comando
        await toqueimg_command(update, context)
        
        callback_duration_ms = (time.time() - callback_start) * 1000
        logger.info(
            "✅ /toqueimg refresh callback completed for user %d (%.0fms)",
            user_id, callback_duration_ms
        )
        
    except Exception as e:
        callback_duration_ms = (time.time() - callback_start) * 1000
        logger.error(
            "User %d (@%s): /toqueimg refresh callback failed after %.0fms - %s",
            user_id, username, callback_duration_ms, e,
            exc_info=True
        )
        # Re-raise to let Telegram handle the error response
        raise
