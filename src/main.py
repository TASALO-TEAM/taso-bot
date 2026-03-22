# src/main.py
"""Entry point del bot TASALO."""

import logging
import sys
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

from src.config import settings
from src.api_client import TasaloApiClient
from src.handlers.tasalo import (
    tasalo_command,
    tasalo_refresh_callback,
    tasalo_provincias_callback,
    tasalo_back_callback,
    history_callback,
)
from src.handlers.admin import (
    refresh_command,
    status_command,
)

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
    application.add_handler(CommandHandler("refresh", refresh_command))
    application.add_handler(CommandHandler("status", status_command))

    # Registrar callback handlers para botones inline
    application.add_handler(CallbackQueryHandler(tasalo_refresh_callback, pattern="^tasalo_refresh$"))
    application.add_handler(CallbackQueryHandler(tasalo_provincias_callback, pattern="^tasalo_provincias$"))
    application.add_handler(CallbackQueryHandler(tasalo_back_callback, pattern="^tasalo_back$"))
    application.add_handler(CallbackQueryHandler(history_callback, pattern="^tasalo_history:"))

    # Guardar api_client en bot_data para acceso desde handlers
    application.bot_data["api_client"] = api_client

    logger.info("✅ Handlers registrados: start, tasalo, health, refresh, status, callbacks (refresh, provincias, back, history)")

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
