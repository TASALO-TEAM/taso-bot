# src/main.py
"""Entry point del bot TASALO."""

import logging
import sys
import asyncio
import os
import time
from typing import Any
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.config import settings
from src.api_client import TasaloApiClient
from src.bot_profile import ensure_bot_profile_photo, create_template_with_profile
from src.handlers.tasalo import (
    tasalo_command,
    toque_command,
    bcc_command,
    cadeca_command,
    fuel_command,
)
from src.handlers.start import (
    start_command,
)
from src.handlers.admin import (
    refresh_command,
    status_command,
)
from src.handlers.toqueimg import (
    toqueimg_command,
)
from src.handlers.image_alerts import (
    handle_time_input,
)
from src.handlers.p import (
    p_command,
)
from src.handlers.ta import (
    ta_command,
)
from src.handlers.trading import (
    graf_command,
    mk_command,
)
from src.handlers.y import (
    y_command,
    handle_year_hour_input,
)
from src.handlers.alert import alert_command
from src.services.daily_image_sender import start_daily_dispatcher, stop_daily_dispatcher
from src.services.year_alert_scheduler import start_year_scheduler, stop_year_scheduler
from src.services.price_alert_checker import start_price_alert_checker, stop_price_alert_checker
from src.logger import BotLogger, LOGS_DIR, LOG_FILE_PATH

# Tipos de update que el bot realmente maneja (eficiencia)
ALLOWED_UPDATE_TYPES = [
    "message",           # comandos y texto
    "callback_query",    # botones inline (alertas, refresh)
    "my_chat_member",    # detectar cuando bot es bloqueado/añadido
]
# NO incluir: chat_member, message_reaction, poll, poll_answer, etc.

# Inicializar sistema de logging profesional con archivo
file_logger = BotLogger(enable_file_logging=True)
file_logger.logger.setLevel(getattr(logging, settings.log_level))

# Silenciar logs verbosos de httpx (evita mostrar URLs con tokens)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Logger estándar para este módulo
logger = file_logger.logger


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manejador global de errores.

    Loguea errores con contexto completo y notifica al usuario si es posible.

    Args:
        update: El update que causó el error (puede ser None)
        context: El contexto del bot con información del error
    """
    # Extraer información del error
    error = context.error
    error_type = type(error).__name__

    # Extraer contexto de usuario si está disponible
    user_id = None
    chat_id = None
    if isinstance(update, Update):
        if update.effective_user:
            user_id = update.effective_user.id
        if update.effective_chat:
            chat_id = update.effective_chat.id

    # Loguear error con stack trace completo y contexto
    user_context = f" | User:{user_id}" if user_id else ""
    chat_context = f" | Chat:{chat_id}" if chat_id else ""

    logger.error(
        "❌ Exception in update%s%s: %s: %s",
        getattr(update, "update_id", "unknown"),
        user_context,
        error_type,
        str(error),
        exc_info=error,
    )

    # Notificar al usuario si es posible
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ *Error Interno*\n\n"
                "Ha ocurrido un error procesando tu solicitud.\n"
                "Inténtalo de nuevo en unos momentos.\n\n"
                f"*Detalle:* `{error_type}`",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error("Failed to send error message to user: %s", e, exc_info=True)


# Instanciar cliente API
api_client = TasaloApiClient(
    api_url=settings.tasalo_api_url,
    admin_key=settings.tasalo_admin_key,
    timeout=settings.api_timeout_seconds,
)


async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /health.

    Verifica que el bot puede conectarse al backend.
    Solo para administradores.
    """
    user_id = update.effective_user.id
    logger.info("🔍 /health command invoked by user %s", user_id)

    # Verificar si es admin
    if user_id not in settings.get_admin_chat_ids_list():
        logger.warning("⚠️ /health denied for non-admin user %s", user_id)
        await update.message.reply_text("🔑 Este comando es solo para administradores.")
        return

    start_time = time.time()
    await update.message.reply_text("⏳ Verificando conexión con el backend...")

    data = await api_client.get_latest()
    duration_ms = (time.time() - start_time) * 1000

    if data:
        logger.info("✅ /health: Backend OK (%.0fms)", duration_ms)
        await update.message.reply_text(
            f"✅ *Backend Conectado*\n\n"
            f"*URL:* `{settings.tasalo_api_url}`\n"
            f"*Updated:* `{data.get('updated_at', 'N/A')}`\n"
            f"*Response time:* `{duration_ms:.0f}ms`",
            parse_mode="Markdown",
        )
    else:
        logger.error("❌ /health: Backend connection failed (%.0fms)", duration_ms)
        await update.message.reply_text(
            "❌ *Error de Conexión*\n\n"
            f"*URL:* `{settings.tasalo_api_url}`\n"
            f"*Response time:* `{duration_ms:.0f}ms`\n"
            "El backend no responde.",
            parse_mode="Markdown",
        )


def create_application() -> Application:
    """Crear y configurar la aplicación de python-telegram-bot."""
    logger.info("🔧 Creating bot application instance...")

    # Crear aplicación
    application = Application.builder().token(settings.telegram_bot_token).build()
    logger.debug("✅ Application instance created")

    # Registrar handlers
    command_handlers = [
        ("start", start_command),
        ("y", y_command),
        ("tasalo", tasalo_command),
        ("health", health_check),
        ("refresh", refresh_command),
        ("status", status_command),
        ("toque", toque_command),
        ("bcc", bcc_command),
        ("cadeca", cadeca_command),
        ("fuel", fuel_command),
        ("toqueimg", toqueimg_command),
        ("p", p_command),
        ("ta", ta_command),
        ("graf", graf_command),
        ("mk", mk_command),
        ("alert", alert_command),
    ]
    
    for cmd_name, handler in command_handlers:
        application.add_handler(CommandHandler(cmd_name, handler))
        logger.debug("  📌 CommandHandler registered: /%s", cmd_name)
    
    logger.info("✅ %d command handlers registered", len(command_handlers))

    # Registrar callback handler para botones del /start
    from src.handlers.callback_router import get_callback_handler
    application.add_handler(get_callback_handler())
    logger.info("✅ Callback router registered (consolidated 13+ handlers into 1)")

    # Registrar handler para input de hora personalizada del año
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_year_hour_input)
    )
    logger.debug("✅ MessageHandler registered for year hour input")

    # Registrar handler para input de hora de alertas de imágenes
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input)
    )
    logger.debug("✅ MessageHandler registered for image alert time input")

    # Registrar error handler global
    application.add_error_handler(error_handler)
    logger.info("✅ Global error handler registered")

    # Guardar api_client en bot_data para acceso desde handlers
    application.bot_data["api_client"] = api_client
    logger.debug("✅ API client stored in bot_data")

    logger.info("✅ All handlers registered: start, tasalo, health, refresh, status, callback_router (1 handler)")

    return application


async def post_init(application: Application):
    """Callback después de inicializar el bot."""
    logger.info("🤖 Bot initialized. Verifying connection to taso-api...")
    init_start = time.time()

    # Verificar conexión con el backend
    try:
        api_start = time.time()
        data = await api_client.get_latest()
        api_duration_ms = (time.time() - api_start) * 1000
        
        if data:
            logger.info(
                "✅ Backend connection OK. Updated at: %s (%.0fms)",
                data.get('updated_at'),
                api_duration_ms
            )
        else:
            logger.warning("⚠️ Backend connection: API returned None (%.0fms)", api_duration_ms)
    except Exception as e:
        logger.error("❌ Backend connection failed: %s", e, exc_info=True)

    # Iniciar dispatcher de alertas diarias de imágenes
    try:
        start_daily_dispatcher(application)
        logger.info("✅ Daily image alert dispatcher started (7:30 AM Cuba / 11:30-12:30 UTC)")
    except Exception as e:
        logger.error("❌ Failed to start daily image dispatcher: %s", e, exc_info=True)

    # Iniciar dispatcher de alertas de año
    try:
        start_year_scheduler(application)
        logger.info("✅ Year alert scheduler started")
    except Exception as e:
        logger.error("❌ Failed to start year alert scheduler: %s", e, exc_info=True)

    # Iniciar checker de alertas de precio de criptomonedas
    try:
        start_price_alert_checker(application)
        logger.info("✅ Price alert checker started (every 5 min)")
    except Exception as e:
        logger.error("❌ Failed to start price alert checker: %s", e, exc_info=True)

    # Obtener y cachear foto de perfil del bot
    try:
        logger.info("📸 Fetching bot profile photo...")
        profile_path = await ensure_bot_profile_photo(application.bot, cache_dir="data")

        if profile_path:
            logger.info("✅ Bot profile photo cached: %s", profile_path)
            
            # Crear plantilla con marca de agua
            template_base = settings.template_full_path
            template_with_watermark = os.path.join("data", "template_watermark.png")

            # Crear directorio data si no existe
            os.makedirs("data", exist_ok=True)

            if os.path.exists(template_base):
                watermark_start = time.time()
                create_template_with_profile(
                    template_base,
                    profile_path,
                    template_with_watermark,
                    position="center",
                    size=(250, 250),
                    opacity=0.12,
                )
                watermark_duration_ms = (time.time() - watermark_start) * 1000
                logger.info(
                    "✅ Watermark template created: %s (%.0fms)",
                    template_with_watermark,
                    watermark_duration_ms
                )
            else:
                logger.warning("⚠️ Template base not found: %s", template_base)
    except Exception as e:
        logger.error("⚠️ Error obteniendo foto de perfil: %s", e, exc_info=True)

    init_duration_ms = (time.time() - init_start) * 1000
    logger.info("✅ Bot post-init completed in %.0fms", init_duration_ms)


def main():
    """Entry point principal."""
    logger.info("=" * 60)
    logger.info("🚀 Starting TASALO-Bot...")
    logger.info("=" * 60)
    logger.info("📡 API URL: %s", settings.tasalo_api_url)
    logger.info("👥 Admin IDs: %s", settings.admin_chat_ids or "None configured")
    logger.info("📝 Log file: %s", LOG_FILE_PATH)
    logger.info("📂 Log directory: %s", LOGS_DIR)
    logger.info("📋 Log level: %s", settings.log_level)
    logger.info("🔄 API timeout: %ds", settings.api_timeout_seconds)
    logger.info("🤖 Bot version: 0.11.1")
    logger.info("=" * 60)

    # Crear aplicación
    app = create_application()

    # Configurar post_init
    app.post_init = post_init

    # Configurar shutdown para detener el dispatcher y cerrar cliente HTTP
    async def post_shutdown(app: Application) -> None:
        """Detener el dispatcher de alertas diarias y limpiar recursos."""
        logger.info("🛑 Bot shutting down...")
        stop_daily_dispatcher()
        logger.info("✅ Daily dispatcher stopped")

        stop_year_scheduler()
        logger.info("✅ Year alert scheduler stopped")

        stop_price_alert_checker()
        logger.info("✅ Price alert checker stopped")
        
        # Cerrar cliente HTTP para liberar conexiones
        api_client: TasaloApiClient = app.bot_data.get("api_client")
        if api_client:
            await api_client.close()
            logger.info("✅ API client closed")
        
        logger.info("✅ Shutdown complete")

    app.post_shutdown = post_shutdown

    # Check if webhook mode is enabled via environment variable
    use_webhook = os.getenv("USE_WEBHOOK", "false").lower() == "true"

    if use_webhook:
        # Webhook mode (production)
        webhook_url = os.getenv("WEBHOOK_URL", "")
        webhook_secret = os.getenv("TELEGRAM_SECRET_TOKEN", "")
        webhook_port = int(os.getenv("WEBHOOK_PORT", "8443"))

        if not webhook_url or not webhook_secret:
            logger.error("❌ WEBHOOK_URL and TELEGRAM_SECRET_TOKEN must be set when USE_WEBHOOK=true")
            sys.exit(1)

        logger.info("🌐 Starting webhook mode on port %d...", webhook_port)
        logger.info("🔗 Webhook URL: %s", webhook_url)
        logger.info("🔐 Secret token configured: %s", "YES" if webhook_secret else "NO")

        app.run_webhook(
            listen="0.0.0.0",
            port=webhook_port,
            url_path=settings.telegram_bot_token,
            webhook_url=webhook_url,
            secret_token=webhook_secret,
            allowed_updates=ALLOWED_UPDATE_TYPES,
        )
    else:
        # Polling mode (development default)
        logger.info("📡 Starting polling mode...")
        logger.info("🔄 Allowed updates: %s", ", ".join(ALLOWED_UPDATE_TYPES))
        app.run_polling(
            allowed_updates=ALLOWED_UPDATE_TYPES,
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    main()
