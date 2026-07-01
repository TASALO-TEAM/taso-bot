"""Handler for /toqueimg command.

Modelo (2026-06-30): bajo demanda puro. Cada invocación pide a taso-api que
intente refrescar la imagen (clic real en 'Guardar POST' en
iframe.cubanomic.com). Si la fuente no responde, taso-api devuelve la última
imagen local disponible marcada como 'stale' — el bot nunca falla solo
porque la descarga fresca no se pudo completar.
"""

import logging
import time
import os
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
CAPTURE_ENDPOINT = f"{API_URL}/api/v1/images/eltoque/capture"


async def _fetch_toqueimg_data(api: TasaloApiClient, user_id: int) -> dict:
    """Pide a taso-api que refresque la imagen y trae el estado de alerta.

    Siempre llama al endpoint de captura (bajo demanda) — taso-api decide
    internamente si sirve una imagen fresca o cae a la local existente.

    Returns:
        dict con: ok, image_path, captured_label, stale, has_alert, error
    """
    capture_data = await api._post_with_retry(CAPTURE_ENDPOINT)

    if not capture_data or not capture_data.get("ok") or not capture_data.get("data"):
        error = (capture_data or {}).get("error", {}).get("message", "Error desconocido")
        return {"ok": False, "error": error}

    image_data = capture_data["data"]
    stale = capture_data.get("stale", False)
    image_path = image_data["image_path"]
    captured_at_str = image_data.get("captured_at", "")

    try:
        captured_dt = datetime.fromisoformat(captured_at_str.replace("Z", "+00:00"))
        captured_label = captured_dt.astimezone(CUBA_TZ).strftime("%d/%m/%Y %H:%M")
    except Exception:
        captured_label = datetime.now(CUBA_TZ).strftime("%d/%m/%Y")

    alert_data = await api._get_with_retry(f"{API_URL}/api/v1/images/alerts/{user_id}")
    has_alert = (
        alert_data
        and alert_data.get("ok")
        and alert_data.get("data")
        and alert_data["data"].get("enabled", False)
    )

    return {
        "ok": True,
        "image_path": image_path,
        "captured_label": captured_label,
        "stale": stale,
        "has_alert": has_alert,
    }


def _build_toqueimg_caption(captured_label: str, stale: bool) -> str:
    """Caption del mensaje. Si stale=True, avisa que puede no ser la más reciente."""
    caption = (
        "🇨🇺 *Tasa Diaria El Toque*\n"
        f"📅 {captured_label} (Cuba)\n\n"
    )
    if stale:
        caption += "_⚠️ No se pudo actualizar ahora, mostrando última imagen disponible_\n"
    caption += "_Fuente: iframe.cubanomic.com_"
    return caption


async def toqueimg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /toqueimg - Refresca (bajo demanda) y muestra la imagen del post
    de ElToque en iframe.cubanomic.com.
    """
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"

    logger.info("📸 /toqueimg invocado por user %d (@%s)", user_id, username)

    is_callback = update.callback_query is not None
    if is_callback:
        loading_msg = await update.callback_query.message.reply_text("📸 Cargando imagen...")
    else:
        loading_msg = await update.message.reply_text("📸 Cargando imagen...")

    try:
        api = TasaloApiClient(api_url=API_URL, timeout=30)
        result = await _fetch_toqueimg_data(api, user_id)

        if not result["ok"]:
            await loading_msg.edit_text(
                "⚠️ *Imagen no disponible*\n\n"
                "No se pudo obtener la imagen en este momento.\n"
                "Intenta de nuevo más tarde.",
                parse_mode="Markdown"
            )
            return

        if not os.path.exists(result["image_path"]):
            logger.error("User %d: Archivo de imagen no encontrado: %s", user_id, result["image_path"])
            await loading_msg.edit_text(
                "❌ No se encontró el archivo de imagen.\n"
                "Intenta de nuevo más tarde."
            )
            return

        keyboard = _build_toqueimg_keyboard(result["has_alert"])
        caption = _build_toqueimg_caption(result["captured_label"], result["stale"])

        with open(result["image_path"], "rb") as f:
            await loading_msg.edit_media(
                media=InputMediaPhoto(media=f, caption=caption, parse_mode="Markdown"),
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
        keyboard = [
            [InlineKeyboardButton(
                "✅ Alerta activa",
                callback_data="alert_status",
                style="success",
            )],
            [
                InlineKeyboardButton("⏰ Cambiar hora", callback_data="alert_change_time"),
                InlineKeyboardButton("📄 Cambiar formato", callback_data="alert_change_format"),
            ],
            [InlineKeyboardButton(
                "❌ Desactivar alerta",
                callback_data="alert_disable",
                style="danger",
            )],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton(
                "🔔 Activar alerta (7:30 AM)",
                callback_data="alert_enable_default",
                style="success",
            )],
            [InlineKeyboardButton(
                "⏰ Elegir hora personalizada",
                callback_data="alert_custom_time",
            )],
        ]

    keyboard.append([InlineKeyboardButton(
        "🔄 Actualizar imagen",
        callback_data="toqueimg_refresh",
        style="primary",
    )])

    return keyboard


async def toqueimg_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para botón 🔄 Actualizar en /toqueimg.

    Edita el mensaje de imagen existente con la última captura disponible,
    sin enviar mensajes nuevos. Usa el mismo flujo on-demand que el comando.
    """
    callback_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    query = update.callback_query

    logger.info("🔄 toqueimg_refresh callback de user %d (@%s)", user_id, username)
    await query.answer("🔄 Actualizando...")

    try:
        api = TasaloApiClient(api_url=API_URL, timeout=30)
        result = await _fetch_toqueimg_data(api, user_id)

        if not result["ok"]:
            await query.answer("⚠️ No se pudo actualizar la imagen. Intenta de nuevo.", show_alert=True)
            return

        if not os.path.exists(result["image_path"]):
            await query.answer("❌ Archivo de imagen no encontrado.", show_alert=True)
            return

        keyboard = _build_toqueimg_keyboard(result["has_alert"])
        caption = _build_toqueimg_caption(result["captured_label"], result["stale"])

        with open(result["image_path"], "rb") as f:
            await query.edit_message_media(
                media=InputMediaPhoto(media=f, caption=caption, parse_mode="Markdown"),
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
