"""Handlers para el comando /tasalo del bot TASALO."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.api_client import TasaloApiClient
from src.formatters import build_full_message

logger = logging.getLogger(__name__)


async def tasalo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /tasalo.

    Comando principal que muestra las tasas de cambio actuales de todas
    las fuentes (ElToque, CADECA, BCC) con formato modernizado.

    Flujo:
        1. Envía mensaje "⏳ Consultando tasas..."
        2. Llama a taso-api para obtener datos
        3. Si error: muestra mensaje de error amigable
        4. Si éxito: formatea y envía mensaje con todos los bloques

    Args:
        update: Update de Telegram con el mensaje del usuario
        context: Contexto del bot (incluye api_client)
    """
    user_id = update.effective_user.id
    logger.info(f"📊 /tasalo command invoked by user {user_id}")

    # Mensaje de estado inicial
    status_msg = await update.message.reply_text("⏳ Consultando tasas...")

    # Obtener cliente API del contexto
    api_client: TasaloApiClient = context.bot_data.get("api_client")

    if not api_client:
        logger.error("❌ api_client no está disponible en bot_data")
        await status_msg.edit_text(
            "⚠️ *Error de Configuración*\n\n"
            "El bot no está configurado correctamente.\n"
            "Contacta al administrador.",
            parse_mode="Markdown",
        )
        return

    # Llamar a la API
    data = await api_client.get_latest()

    if data is None:
        logger.warning("⚠️ /tasalo: API returned None")
        await status_msg.edit_text(
            "⚠️ *Error de Conexión*\n\n"
            "No se pudieron obtener datos del backend.\n"
            "Inténtalo de nuevo en unos momentos.",
            parse_mode="Markdown",
        )
        return

    # Verificar estructura de datos
    api_data = data.get("data")
    if not api_data:
        logger.warning("⚠️ /tasalo: API data is empty")
        await status_msg.edit_text(
            "⚠️ *Datos No Disponibles*\n\n"
            "El backend no tiene datos actualizados.\n"
            "Inténtalo de nuevo más tarde.",
            parse_mode="Markdown",
        )
        return

    # Formatear mensaje completo
    try:
        formatted_message = build_full_message(api_data)

        await status_msg.edit_text(
            formatted_message,
            parse_mode="Markdown",
        )

        logger.info("✅ /tasalo: Response sent successfully")

    except Exception as e:
        logger.error(f"❌ Error formateando mensaje: {e}", exc_info=True)
        await status_msg.edit_text(
            "⚠️ *Error de Formateo*\n\n"
            "No se pudo formatear la respuesta.\n"
            f"Detalle: `{str(e)}`\n\n"
            "Inténtalo de nuevo más tarde.",
            parse_mode="Markdown",
        )
