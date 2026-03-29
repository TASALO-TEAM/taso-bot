"""Handler for /toqueimg command."""

import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes

from src.config import get_settings

settings = get_settings()
API_URL = settings.tasalo_api_url  # https://tasalo.duckdns.org


async def toqueimg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /toqueimg - Muestra imagen de ElToque con botones de alerta.
    """
    user_id = update.effective_user.id
    
    # 1. Mostrar "loading"
    loading_msg = await update.message.reply_text("📸 Capturando imagen...")
    
    try:
        # 2. Capturar imagen desde API
        async with httpx.AsyncClient() as client:
            capture_response = await client.post(
                f"{API_URL}/api/v1/images/eltoque/capture",
                timeout=30.0
            )
            capture_data = capture_response.json()
        
        if not capture_data.get("ok"):
            raise Exception(f"API error: {capture_data.get('error')}")
        
        # 3. Obtener última imagen (file path)
        async with httpx.AsyncClient() as client:
            latest_response = await client.get(
                f"{API_URL}/api/v1/images/eltoque/latest",
                timeout=10.0
            )
            latest_data = latest_response.json()
        
        if not latest_data.get("ok"):
            raise Exception("Failed to get latest image")
        
        image_path = latest_data["data"]["image_path"]
        
        # 4. Verificar si usuario tiene alerta activa
        async with httpx.AsyncClient() as client:
            alert_response = await client.get(
                f"{API_URL}/api/v1/images/alerts/{user_id}",
                timeout=5.0
            )
            alert_data = alert_response.json()
        
        has_alert = (
            alert_data.get("ok") and
            alert_data.get("data") and
            alert_data["data"].get("enabled", False)
        )
        
        # 5. Construir keyboard interactivo
        keyboard = _build_toqueimg_keyboard(has_alert)
        
        # 6. Construir caption simple
        caption = (
            "🇨🇺 *Tasa Diaria El Toque*\n"
            f"📅 {datetime.now().strftime('%d/%m/%Y')}\n\n"
            "Esta es la tasa diaria de El Toque."
        )
        
        # 7. Enviar imagen
        with open(image_path, "rb") as f:
            await loading_msg.edit_media(
                media=InputMediaPhoto(
                    media=f,
                    caption=caption,
                    parse_mode="Markdown"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ Error: {str(e)}\n\nIntenta de nuevo más tarde."
        )


def _build_toqueimg_keyboard(has_alert: bool) -> list:
    """Construir keyboard según estado de alerta."""
    
    if has_alert:
        # Usuario YA tiene alerta activa
        keyboard = [
            [InlineKeyboardButton("✅ Alerta activa", callback_data="alert_status")],
            [
                InlineKeyboardButton("⏰ Cambiar hora", callback_data="alert_change_time"),
                InlineKeyboardButton("📄 Cambiar formato", callback_data="alert_change_format")
            ],
            [InlineKeyboardButton("❌ Desactivar alerta", callback_data="alert_disable")],
        ]
    else:
        # Usuario NO tiene alerta
        keyboard = [
            [InlineKeyboardButton("🔔 Activar alerta (7:15 AM)", callback_data="alert_enable_default")],
            [InlineKeyboardButton("⏰ Elegir hora personalizada", callback_data="alert_custom_time")],
        ]
    
    # Botón común de refresh
    keyboard.append([InlineKeyboardButton("🔄 Actualizar imagen", callback_data="toqueimg_refresh")])
    
    return keyboard


async def toqueimg_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para botón Actualizar en /toqueimg."""
    query = update.callback_query
    await query.answer("🔄 Actualizando...")
    
    # Re-ejecutar el comando
    await toqueimg_command(update, context)
