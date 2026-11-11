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
from src.build_info import BOT_VERSION
from src.api_client import TasaloApiClient
from src.commands import publish_menu, register_commands
from src.handlers.image_alerts import handle_time_input
from src.handlers.y import handle_year_hour_input
from src.handlers.tspl import handle_tspl_hour_input
from src.handlers.tkt import handle_tkt_message
from src.services.daily_image_sender import start_daily_dispatcher, stop_daily_dispatcher
from src.services.year_alert_scheduler import start_year_scheduler, stop_year_scheduler
from src.services.price_alert_checker import start_price_alert_checker, stop_price_alert_checker
from src.services.tspl_digest_scheduler import start_tspl_digest_scheduler, stop_tspl_digest_scheduler
from src.services.tspl_alert_dispatcher import start_tspl_alert_dispatcher, stop_tspl_alert_dispatcher
from src.logger import BotLogger, LOGS_DIR, LOG_FILE_PATH

# Tipos de update que el bot realmente maneja (eficiencia)
ALLOWED_UPDATE_TYPES = [
    "message",           # comandos y texto
    "callback_query",    # botones inline (alertas, refresh)
    "my_chat_member",    # detectar cuando bot es bloqueado/añadido
]
# NO incluir: chat_member, message_reaction, poll, poll_answer, etc.

# Inicializar sistema de logging profesional con archivo
# file_logger.logger es ahora el ROOT logger (ver src/logger.py) - se usa
# solo para fijar el nivel global. El logger propio de este modulo es
# aparte, igual que en todos los demas modulos (logging.getLogger(__name__)),
# para que "quien logueo que" quede claro en el archivo.
file_logger = BotLogger(enable_file_logging=True)
file_logger.logger.setLevel(getattr(logging, settings.log_level))

# Silenciar logs verbosos de httpx (evita mostrar URLs con tokens)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Logger estándar para este módulo
logger = logging.getLogger(__name__)


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

    # Avisar al grupo de soporte (mismo patrón que taso-gcg). Si esto
    # también falla, ya quedó registrado en el log de archivo arriba.
    if settings.log_chat_id:
        try:
            resumen = f"{error_type}: {error}"[:300]
            await context.bot.send_message(
                settings.log_chat_id,
                f"⚠️ Error no controlado en taso-bot: {resumen}",
            )
        except Exception:
            pass

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


def create_application() -> Application:
    """Crear y configurar la aplicación de python-telegram-bot."""
    logger.info("🔧 Creating bot application instance...")

    # Crear aplicación
    application = Application.builder().token(settings.telegram_bot_token).build()
    logger.debug("✅ Application instance created")

    # Registrar comandos desde el registro unico (src/commands.py)
    total = register_commands(application)
    logger.info("✅ %d command handlers registered", total)

    # Registrar callback handler para botones del /start
    from src.handlers.callback_router import get_callback_handler
    application.add_handler(get_callback_handler())
    logger.info("✅ Callback router registered (consolidated 13+ handlers into 1)")

    # Registrar handler para input de hora personalizada del año
    #
    # IMPORTANTE: los 3 MessageHandler globales de más abajo (year hour,
    # image alert time, tkt message) usan el mismo filtro amplio
    # (filters.TEXT & ~filters.COMMAND) y se auto-filtran internamente por
    # flags en user_data. python-telegram-bot solo ejecuta UN handler por
    # grupo por update (para en el primero cuyo filtro matchee) — si los
    # 3 quedan en el grupo 0 (default), el primero registrado "gana"
    # SIEMPRE y los otros dos nunca se llegan a ejecutar, sin importar el
    # flag interno. Por eso cada uno va en su propio grupo explícito.
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_year_hour_input),
        group=0,
    )
    logger.debug("✅ MessageHandler registered for year hour input (group=0)")

    # Registrar handler para input de hora de alertas de imágenes
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input),
        group=1,
    )
    logger.debug("✅ MessageHandler registered for image alert time input (group=1)")

    # Registrar handler para el mensaje de contenido de un ticket (/tkt)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tkt_message),
        group=2,
    )
    logger.debug("✅ MessageHandler registered for /tkt message capture (group=2)")

    # Registrar handler para input de hora personalizada de /tspl
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tspl_hour_input),
        group=3,
    )
    logger.debug("✅ MessageHandler registered for /tspl hour input (group=3)")

    # Registrar error handler global
    application.add_error_handler(error_handler)
    logger.info("✅ Global error handler registered")

    # Guardar api_client en bot_data para acceso desde handlers
    application.bot_data["api_client"] = api_client
    logger.debug("✅ API client stored in bot_data")

    logger.info("✅ All handlers registered")

    return application


async def post_init(application: Application):
    """Callback después de inicializar el bot."""
    logger.info("🤖 Bot initialized. Verifying connection to taso-api...")
    init_start = time.time()

    # Menú "/" de Telegram (un fallo no tumba el arranque)
    await publish_menu(application)

    # Aviso de arranque al grupo de soporte (mismo patrón que taso-gcg)
    if settings.log_chat_id:
        try:
            await application.bot.send_message(
                settings.log_chat_id, f"🚀 taso-bot v{BOT_VERSION} en línea."
            )
        except Exception as e:
            logger.warning("⚠️ No se pudo notificar el arranque al LOG_CHAT_ID: %s", e)

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

    # Iniciar scheduler del digest diario de noticias para /tspl
    try:
        start_tspl_digest_scheduler(application)
        logger.info("✅ /tspl digest scheduler started (11:00 UTC / ~7:00 AM Cuba)")
    except Exception as e:
        logger.error("❌ Failed to start /tspl digest scheduler: %s", e, exc_info=True)

    # Iniciar dispatcher de suscripciones a horarios de /tspl
    try:
        start_tspl_alert_dispatcher(application)
        logger.info("✅ /tspl subscription dispatcher started (runs at :00 UTC every hour)")
    except Exception as e:
        logger.error("❌ Failed to start /tspl subscription dispatcher: %s", e, exc_info=True)

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
    logger.info("🤖 Bot version: %s", BOT_VERSION)
    logger.info("=" * 60)

    # Crear aplicación
    app = create_application()

    # Configurar post_init
    app.post_init = post_init

    # Configurar shutdown para detener el dispatcher y cerrar cliente HTTP
    async def post_shutdown(app: Application) -> None:
        """Detener el dispatcher de alertas diarias y limpiar recursos."""
        logger.info("🛑 Bot shutting down...")

        # Aviso de apagado al grupo de soporte (mismo patrón que taso-gcg)
        if settings.log_chat_id:
            try:
                await app.bot.send_message(
                    settings.log_chat_id, "👋 taso-bot detenido."
                )
            except Exception as e:
                logger.warning("⚠️ No se pudo notificar el apagado al LOG_CHAT_ID: %s", e)

        stop_daily_dispatcher()
        logger.info("✅ Daily dispatcher stopped")

        stop_year_scheduler()
        logger.info("✅ Year alert scheduler stopped")

        stop_price_alert_checker()
        logger.info("✅ Price alert checker stopped")

        stop_tspl_digest_scheduler()
        logger.info("✅ /tspl digest scheduler stopped")

        stop_tspl_alert_dispatcher()
        logger.info("✅ /tspl subscription dispatcher stopped")
        
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
