# src/main.py
"""Entry point del bot TASALO."""

import logging
import sys
import asyncio
import os
from typing import Any
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from src.config import settings
from src.api_client import TasaloApiClient
from src.bot_profile import ensure_bot_profile_photo, create_template_with_profile
from src.handlers.tasalo import (
    tasalo_command,
    tasalo_refresh_callback,
    tasalo_provincias_callback,
    tasalo_back_callback,
    history_callback,
    toque_command,
    bcc_command,
    cadeca_command,
    source_refresh_callback,
)
from src.handlers.start import (
    start_command,
    start_button_callback,
)
from src.handlers.admin import (
    refresh_command,
    status_command,
)
from src.handlers.toqueimg import (
    toqueimg_command,
    toqueimg_refresh_callback,
)
from src.handlers.image_alerts import (
    alert_enable_default_callback,
    alert_custom_time_callback,
    alert_disable_callback,
    alert_change_time_callback,
    alert_change_format_callback,
    alert_format_callback,
    alert_status_callback,
    alert_cancel_callback,
    handle_time_input,
)
from src.services.daily_image_sender import start_daily_dispatcher, stop_daily_dispatcher

# Tipos de update que el bot realmente maneja (eficiencia)
ALLOWED_UPDATE_TYPES = [
    "message",           # comandos y texto
    "callback_query",    # botones inline (alertas, refresh)
    "my_chat_member",    # detectar cuando bot es bloqueado/añadido
]
# NO incluir: chat_member, message_reaction, poll, poll_answer, etc.

# Configurar logging estructurado
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(logging, settings.log_level),
    stream=sys.stdout,
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Silenciar logs verbosos de httpx (evita mostrar URLs con tokens)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manejador global de errores.

    Loguea errores y notifica al usuario si es posible.

    Args:
        update: El update que causó el error (puede ser None)
        context: El contexto del bot con información del error
    """
    # Extraer información del error
    error = context.error
    error_type = type(error).__name__

    # Loguear error con stack trace
    logger.error(
        "❌ Exception caused update %s to fail",
        getattr(update, "update_id", "unknown"),
        exc_info=error,
    )
    logger.error(f"Error type: {error_type}")
    logger.error(f"Error message: {error}")

    # Context data para debugging
    if isinstance(update, Update) and update.effective_chat:
        logger.error(f"Chat ID: {update.effective_chat.id}")
    if isinstance(update, Update) and update.effective_user:
        logger.error(f"User ID: {update.effective_user.id}")

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
            logger.error(f"❌ Failed to send error message to user: {e}")


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
    application = Application.builder().token(settings.telegram_bot_token).build()

    # Registrar handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("tasalo", tasalo_command))
    application.add_handler(CommandHandler("health", health_check))
    application.add_handler(CommandHandler("refresh", refresh_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("toque", toque_command))
    application.add_handler(CommandHandler("bcc", bcc_command))
    application.add_handler(CommandHandler("cadeca", cadeca_command))
    application.add_handler(CommandHandler("toqueimg", toqueimg_command))

    # Registrar callback handlers para botones inline
    application.add_handler(
        CallbackQueryHandler(tasalo_refresh_callback, pattern="^tasalo_refresh$")
    )
    # TODO: Habilitar cuando la API tenga datos de provincias
    # application.add_handler(
    #     CallbackQueryHandler(tasalo_provincias_callback, pattern="^tasalo_provincias$")
    # )
    application.add_handler(
        CallbackQueryHandler(tasalo_back_callback, pattern="^tasalo_back$")
    )
    application.add_handler(
        CallbackQueryHandler(history_callback, pattern="^tasalo_history:")
    )
    application.add_handler(
        CallbackQueryHandler(
            source_refresh_callback, pattern="^(toque|bcc|cadeca)_refresh$"
        )
    )
    # Registrar callback handler para botones del /start
    application.add_handler(
        CallbackQueryHandler(start_button_callback, pattern="^start_(tasalo|toque|bcc|cadeca|toqueimg)$")
    )
    
    # Registrar callbacks para /toqueimg y alertas
    application.add_handler(
        CallbackQueryHandler(toqueimg_refresh_callback, pattern="^toqueimg_refresh$")
    )
    application.add_handler(
        CallbackQueryHandler(alert_enable_default_callback, pattern="^alert_enable_default$")
    )
    application.add_handler(
        CallbackQueryHandler(alert_custom_time_callback, pattern="^alert_custom_time$")
    )
    application.add_handler(
        CallbackQueryHandler(alert_disable_callback, pattern="^alert_disable$")
    )
    application.add_handler(
        CallbackQueryHandler(alert_change_time_callback, pattern="^alert_change_time$")
    )
    application.add_handler(
        CallbackQueryHandler(alert_change_format_callback, pattern="^alert_change_format$")
    )
    application.add_handler(
        CallbackQueryHandler(alert_format_callback, pattern="^alert_format_(photo|document)$")
    )
    application.add_handler(
        CallbackQueryHandler(alert_status_callback, pattern="^alert_status$")
    )
    application.add_handler(
        CallbackQueryHandler(alert_cancel_callback, pattern="^alert_cancel$")
    )
    
    # Registrar handler para input de hora (MessageHandler para texto)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input)
    )

    # Registrar error handler global
    application.add_error_handler(error_handler)
    logger.info("✅ Global error handler registered")

    # Guardar api_client en bot_data para acceso desde handlers
    application.bot_data["api_client"] = api_client

    logger.info(
        "✅ Handlers registrados: start, tasalo, health, refresh, status, callbacks (refresh, provincias, back, history)"
    )

    return application


async def post_init(application: Application):
    """Callback después de inicializar el bot."""
    logger.info("🤖 Bot initialized. Verifying connection to taso-api...")

    # Verificar conexión con el backend
    try:
        data = await api_client.get_latest()
        if data:
            logger.info(
                f"✅ Backend connection OK. Updated at: {data.get('updated_at')}"
            )
        else:
            logger.warning("⚠️ Backend connection: API returned None")
    except Exception as e:
        logger.error(f"❌ Backend connection failed: {e}")

    # Iniciar dispatcher de alertas diarias de imágenes
    try:
        start_daily_dispatcher(application.bot_data)
        logger.info("✅ Daily image alert dispatcher started (7:15 AM Cuba / 11:15 UTC)")
    except Exception as e:
        logger.error(f"❌ Failed to start daily image dispatcher: {e}")

    # Obtener y cachear foto de perfil del bot
    try:
        logger.info("📸 Fetching bot profile photo...")
        profile_path = await ensure_bot_profile_photo(application.bot, cache_dir="data")

        if profile_path:
            # Crear plantilla con marca de agua
            template_base = settings.template_full_path
            template_with_watermark = os.path.join("data", "template_watermark.png")

            # Crear directorio data si no existe
            os.makedirs("data", exist_ok=True)

            if os.path.exists(template_base):
                create_template_with_profile(
                    template_base,
                    profile_path,
                    template_with_watermark,
                    position="center",
                    size=(250, 250),
                    opacity=0.12,
                )
                logger.info(
                    f"✅ Plantilla con marca de agua creada: {template_with_watermark}"
                )
    except Exception as e:
        logger.error(f"⚠️ Error obteniendo foto de perfil: {e}")


def main():
    """Entry point principal."""
    logger.info("🚀 Starting TASALO-Bot...")
    logger.info(f"📡 API URL: {settings.tasalo_api_url}")
    logger.info(f"👥 Admin IDs: {settings.admin_chat_ids or 'None configured'}")

    # Crear aplicación
    app = create_application()

    # Configurar post_init
    app.post_init = post_init

    # Configurar shutdown para detener el dispatcher y cerrar cliente HTTP
    async def post_shutdown(app: Application) -> None:
        """Detener el dispatcher de alertas diarias y limpiar recursos."""
        stop_daily_dispatcher()
        # Cerrar cliente HTTP para liberar conexiones
        api_client: TasaloApiClient = app.bot_data.get("api_client")
        if api_client:
            await api_client.close()

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

        logger.info(f"🌐 Starting webhook mode on port {webhook_port}...")
        logger.info(f"🔗 Webhook URL: {webhook_url}")

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
        app.run_polling(
            allowed_updates=ALLOWED_UPDATE_TYPES,
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    main()
