"""Handler for /toqueimg command."""

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

from src.config import get_settings
from src.api_client import TasaloApiClient

settings = get_settings()
API_URL = settings.tasalo_api_url

CUBA_TZ = ZoneInfo("America/Havana")


async def toqueimg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /toqueimg - Muestra la última imagen capturada de ElToque.

    No captura en tiempo real: usa la imagen diaria capturada por el scheduler
    de taso-api a las 11:30 UTC (7:30 AM Cuba), que se actualiza automáticamente.
    """
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"

    logger.info("📸 /toqueimg invocado por user %d (@%s)", user_id, username)

    # Detectar si viene de un callback (refresh) o de un comando directo
    is_callback = update.callback_query is not None
    if is_callback:
        loading_msg = await update.callback_query.message.reply_text("📸 Cargando imagen...")
    else:
        loading_msg = await update.message.reply_text("📸 Cargando imagen...")

    try:
        api = TasaloApiClient(api_url=API_URL, timeout=15)

        # 1. Obtener última imagen ya capturada (sin lanzar Playwright/Selenium)
        latest_data = await api._get_with_retry(f"{API_URL}/api/v1/images/eltoque/latest")

        if not latest_data or not latest_data.get("ok") or not latest_data.get("data"):
            logger.warning("User %d: No hay imagen disponible todavía", user_id)
            await loading_msg.edit_text(
                "⚠️ *Imagen no disponible*\n\n"
                "Aún no se ha capturado la imagen de hoy.\n"
                "La captura automática ocurre a las *7:30 AM* hora Cuba.\n\n"
                "Intenta de nuevo más tarde.",
                parse_mode="Markdown"
            )
            return

        image_data = latest_data["data"]
        image_path = image_data["image_path"]
        captured_at_str = image_data.get("captured_at", "")

        # Formatear fecha/hora de captura en hora Cuba
        try:
            from datetime import datetime, timezone
            captured_dt = datetime.fromisoformat(captured_at_str.replace("Z", "+00:00"))
            captured_cuba = captured_dt.astimezone(CUBA_TZ)
            captured_label = captured_cuba.strftime("%d/%m/%Y %H:%M")
        except Exception:
            captured_label = datetime.now(CUBA_TZ).strftime("%d/%m/%Y")

        # 2. Verificar si usuario tiene alerta activa
        alert_data = await api._get_with_retry(f"{API_URL}/api/v1/images/alerts/{user_id}")
        has_alert = (
            alert_data
            and alert_data.get("ok")
            and alert_data.get("data")
            and alert_data["data"].get("enabled", False)
        )

        # 3. Construir teclado y caption
        keyboard = _build_toqueimg_keyboard(has_alert)
        caption = (
            "🇨🇺 *Tasa Diaria El Toque*\n"
            f"📅 {captured_label} (Cuba)\n\n"
            "_Fuente: iframe.cubanomic.com_"
        )

        # 4. Enviar imagen
        import os
        if not os.path.exists(image_path):
            logger.error("User %d: Archivo de imagen no encontrado: %s", user_id, image_path)
            await loading_msg.edit_text(
                "❌ No se encontró el archivo de imagen.\n"
                "Intenta de nuevo más tarde."
            )
            return

        with open(image_path, "rb") as f:
            await loading_msg.edit_media(
                media=InputMediaPhoto(
                    media=f,
                    caption=caption,
                    parse_mode="Markdown"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        cmd_duration_ms = (time.time() - cmd_start) * 1000
        logger.info("✅ /toqueimg completado para user %d (%.0fms)", user_id, cmd_duration_ms)

    except Exception as e:
        cmd_duration_ms = (time.time() - cmd_start) * 1000
        logger.error(
            "❌ /toqueimg falló para user %d (@%s) tras %.0fms: %s",
            user_id, username, cmd_duration_ms, e, exc_info=True
        )
        await loading_msg.edit_text(
            "❌ Error al cargar la imagen.\nIntenta de nuevo más tarde."
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
                "🔔 Activar alerta (7:30 AM)",
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
    """Callback para botón 🔄 Actualizar en /toqueimg.

    Edita el mensaje de imagen existente con la última captura disponible,
    sin enviar mensajes nuevos.
    """
    callback_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    query = update.callback_query

    logger.info("🔄 toqueimg_refresh callback de user %d (@%s)", user_id, username)
    await query.answer("🔄 Actualizando...")

    try:
        api = TasaloApiClient(api_url=API_URL, timeout=15)

        # Obtener última imagen
        latest_data = await api._get_with_retry(f"{API_URL}/api/v1/images/eltoque/latest")

        if not latest_data or not latest_data.get("ok") or not latest_data.get("data"):
            await query.answer("⚠️ Imagen no disponible aún. Intenta después de las 7:30 AM Cuba.", show_alert=True)
            return

        image_data = latest_data["data"]
        image_path = image_data["image_path"]
        captured_at_str = image_data.get("captured_at", "")

        try:
            from datetime import datetime as dt_cls, timezone as tz_mod
            captured_at = dt_cls.fromisoformat(captured_at_str.replace("Z", "+00:00"))
            captured_cuba = captured_at.astimezone(CUBA_TZ)
            captured_label = captured_cuba.strftime("%d/%m/%Y %H:%M")
        except Exception:
            from datetime import datetime as dt_cls
            captured_label = dt_cls.now(CUBA_TZ).strftime("%d/%m/%Y")

        # Estado de alerta
        alert_data = await api._get_with_retry(f"{API_URL}/api/v1/images/alerts/{user_id}")
        has_alert = (
            alert_data
            and alert_data.get("ok")
            and alert_data.get("data")
            and alert_data["data"].get("enabled", False)
        )

        keyboard = _build_toqueimg_keyboard(has_alert)
        caption = (
            "🇨🇺 *Tasa Diaria El Toque*\n"
            f"📅 {captured_label} (Cuba)\n\n"
            "_Fuente: iframe.cubanomic.com_"
        )

        import os
        if not os.path.exists(image_path):
            await query.answer("❌ Archivo de imagen no encontrado.", show_alert=True)
            return

        with open(image_path, "rb") as f:
            await query.edit_message_media(
                media=InputMediaPhoto(
                    media=f,
                    caption=caption,
                    parse_mode="Markdown"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        duration_ms = (time.time() - callback_start) * 1000
        logger.info("✅ toqueimg_refresh completado para user %d (%.0fms)", user_id, duration_ms)

    except Exception as e:
        duration_ms = (time.time() - callback_start) * 1000
        logger.error(
            "❌ toqueimg_refresh falló para user %d tras %.0fms: %s",
            user_id, duration_ms, e, exc_info=True
        )
        await query.answer("❌ Error al actualizar. Intenta de nuevo.", show_alert=True)
