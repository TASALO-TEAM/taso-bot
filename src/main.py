# src/main.py
"""Entry point del bot TASALO."""

import logging
import sys
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from src.config import settings
from src.api_client import TasaloApiClient

# Configurar logging
logging.basicConfig(
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    level=getattr(logging, settings.log_level),
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

# Instanciar cliente API
api_client = TasaloApiClient(
    api_url=settings.tasalo_api_url,
    admin_key=settings.tasalo_admin_key,
    timeout=settings.api_timeout_seconds,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /start."""
    user = update.effective_user
    await update.message.reply_html(
        f"👋 ¡Hola {user.mention_html()}!\n\n"
        f"Soy <b>TASALO</b>, tu bot para consultar las tasas de cambio de Cuba.\n\n"
        f"Usa /tasalo para ver las tasas actuales."
    )


async def tasalo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /tasalo.
    
    Este es el comando principal que muestra las tasas de cambio.
    Por ahora solo verifica conexión con el backend.
    """
    logger.info(f"📊 /tasalo command invoked by user {update.effective_user.id}")
    
    # Mensaje de estado
    status_msg = await update.message.reply_text("⏳ Consultando tasas...")
    
    # Llamar a la API
    data = await api_client.get_latest()
    
    if data is None:
        await status_msg.edit_text(
            "⚠️ *Error de Conexión*\n\n"
            "No se pudieron obtener datos del backend.\n"
            "Inténtalo de nuevo en unos momentos.",
            parse_mode="Markdown",
        )
        logger.warning("⚠️ /tasalo: API returned None")
        return
    
    # Por ahora, mostrar datos crudos para debugging
    response_text = (
        "✅ *Conexión Exitosa!*\n\n"
        f"*API URL:* `{settings.tasalo_api_url}`\n"
        f"*Updated at:* `{data.get('updated_at', 'N/A')}`\n\n"
        f"*Datos recibidos:*\n"
        f"```\n{data}\n```"
    )
    
    await status_msg.edit_text(response_text, parse_mode="Markdown")
    logger.info("✅ /tasalo: Response sent successfully")


async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /health.
    
    Verifica que el bot puede conectarse al backend.
    Solo para administradores.
    """
    user_id = update.effective_user.id
    
    # Verificar si es admin
    if user_id not in settings.get_admin_chat_ids_list():
        await update.message.reply_text("🔑 Este comando es solo para administradores.")
        return
    
    await update.message.reply_text("⏳ Verificando conexión con el backend...")
    
    data = await api_client.get_latest()
    
    if data:
        await update.message.reply_text(
            f"✅ *Backend Conectado*\n\n"
            f"*URL:* `{settings.tasalo_api_url}`\n"
            f"*Updated:* `{data.get('updated_at', 'N/A')}`",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "❌ *Error de Conexión*\n\n"
            f"*URL:* `{settings.tasalo_api_url}`\n"
            "El backend no responde.",
            parse_mode="Markdown",
        )


def create_application() -> Application:
    """Crear y configurar la aplicación de python-telegram-bot."""
    
    # Crear aplicación
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )
    
    # Registrar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("tasalo", tasalo_command))
    application.add_handler(CommandHandler("health", health_check))
    
    logger.info("✅ Handlers registrados: start, tasalo, health")
    
    return application


async def post_init(application: Application):
    """Callback después de inicializar el bot."""
    logger.info("🤖 Bot initialized. Verifying connection to taso-api...")
    
    # Verificar conexión con el backend
    try:
        data = await api_client.get_latest()
        if data:
            logger.info(f"✅ Backend connection OK. Updated at: {data.get('updated_at')}")
        else:
            logger.warning("⚠️ Backend connection: API returned None")
    except Exception as e:
        logger.error(f"❌ Backend connection failed: {e}")


def main():
    """Entry point principal."""
    logger.info("🚀 Starting TASALO-Bot...")
    logger.info(f"📡 API URL: {settings.tasalo_api_url}")
    logger.info(f"👥 Admin IDs: {settings.admin_chat_ids or 'None configured'}")
    
    # Crear aplicación
    app = create_application()
    
    # Configurar post_init
    app.post_init = post_init
    
    # Iniciar polling
    logger.info("📡 Starting polling...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
