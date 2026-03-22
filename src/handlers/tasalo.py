"""Handlers para el comando /tasalo del bot TASALO.

Módulo responsable de manejar el comando /tasalo, callbacks inline,
y comandos de administración.
"""

import asyncio
import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.api_client import TasaloApiClient
from src.formatters import build_full_message
from src.image_generator import generate_image

logger = logging.getLogger(__name__)

# Timeout para generación de imagen (segundos)
IMAGE_GENERATION_TIMEOUT = 5


def build_inline_keyboard() -> InlineKeyboardMarkup:
    """Construye el teclado inline con botones 🔄 y 🗺.

    Returns:
        InlineKeyboardMarkup con los botones de acción
    """
    keyboard = [
        [
            InlineKeyboardButton("🔄 Actualizar", callback_data="tasalo_refresh"),
            InlineKeyboardButton("🗺 Ver provincias", callback_data="tasalo_provincias"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_tasalo_response(
    update: Update,
    api_data: dict,
    message_id: Optional[int] = None,
):
    """Envía la respuesta del comando /tasalo con imagen + texto + botones.

    Args:
        update: Update de Telegram
        api_data: Datos de la API
        message_id: ID del mensaje a editar (None para enviar nuevo)
    """
    # Construir teclado inline
    keyboard = build_inline_keyboard()

    # Formatear texto (siempre se necesita)
    text = build_full_message(api_data)

    # Generar imagen en paralelo con timeout
    try:
        image_bytes = await asyncio.wait_for(
            generate_image(api_data),
            timeout=IMAGE_GENERATION_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("⚠️ Image generation timed out (>5s), sending text only")
        image_bytes = None
    except Exception as e:
        logger.error(f"❌ Error generando imagen: {e}", exc_info=True)
        image_bytes = None

    # Enviar respuesta
    if image_bytes:
        # Enviar con imagen
        if message_id:
            # Editar mensaje existente con foto
            await update.effective_message.edit_message_caption(
                caption=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            # Enviar foto como nuevo mensaje (no se puede editar a foto)
            await update.effective_message.reply_photo(
                photo=image_bytes,
                caption=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_photo(
                photo=image_bytes,
                caption=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        logger.info("✅ Imagen + texto enviados correctamente")
    else:
        # Fallback: solo texto
        if message_id:
            await update.effective_message.edit_message_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        logger.info("✅ Texto enviado (fallback sin imagen)")


async def tasalo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /tasalo.

    Comando principal que muestra las tasas de cambio actuales de todas
    las fuentes (ElToque, CADECA, BCC) con imagen, texto formateado y botones.

    Flujo:
        1. Envía mensaje "⏳ Consultando tasas..."
        2. Llama a taso-api para obtener datos
        3. Si error: muestra mensaje de error amigable
        4. Si éxito: genera imagen, formatea texto y envía con botones inline

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

    # Enviar respuesta con imagen + texto + botones
    await send_tasalo_response(update, api_data)

    # Eliminar mensaje de estado
    await status_msg.delete()


async def tasalo_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para el botón 🔄 Actualizar.

    Re-llama a la API y actualiza el mensaje existente con datos frescos.

    Args:
        update: Update de Telegram con el callback query
        context: Contexto del bot
    """
    query = update.callback_query
    await query.answer("🔄 Actualizando...")

    user_id = query.from_user.id
    logger.info(f"🔄 Refresh callback invoked by user {user_id}")

    # Obtener cliente API
    api_client: TasaloApiClient = context.bot_data.get("api_client")

    if not api_client:
        await query.edit_message_text(
            "⚠️ *Error de Configuración*\n\n"
            "El bot no está configurado correctamente.",
            parse_mode="Markdown",
        )
        return

    # Llamar a la API
    data = await api_client.get_latest()

    if data is None or not data.get("data"):
        await query.answer("⚠️ No se pudieron obtener datos", show_alert=True)
        return

    # Enviar respuesta actualizada
    await send_tasalo_response(update, data.get("data"), message_id=query.message.message_id)

    logger.info("✅ Refresh completado")


async def tasalo_provincias_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para el botón 🗺 Ver provincias.

    Muestra las tasas por provincia (stub por ahora).

    Args:
        update: Update de Telegram con el callback query
        context: Contexto del bot
    """
    query = update.callback_query
    await query.answer("🗺 Mostrando provincias...")

    user_id = query.from_user.id
    logger.info(f"🗺 Provincias callback invoked by user {user_id}")

    # Obtener cliente API
    api_client: TasaloApiClient = context.bot_data.get("api_client")

    if not api_client:
        await query.edit_message_text(
            "⚠️ *Error de Configuración*\n\n"
            "El bot no está configurado correctamente.",
            parse_mode="Markdown",
        )
        return

    # Llamar a la API para obtener datos (incluyendo provincias si existen)
    data = await api_client.get_latest()

    if data is None or not data.get("data"):
        await query.answer("⚠️ No se pudieron obtener datos", show_alert=True)
        return

    api_data = data.get("data")

    # Construir mensaje de provincias
    # Por ahora, mostrar mensaje stub - se implementará cuando la API tenga provincias
    provincias_text = build_provincias_message(api_data)

    # Teclado con botón "Volver"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Volver", callback_data="tasalo_back")],
    ])

    await query.edit_message_text(
        text=provincias_text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    logger.info("✅ Provincias mostradas")


def build_provincias_message(api_data: dict) -> str:
    """Construye el mensaje de tasas por provincia.

    Args:
        api_data: Datos de la API

    Returns:
        String formateado con las tasas por provincia
    """
    lines = []

    lines.append("🗺 *TASAS POR PROVINCIA*")
    lines.append("━" * 30)
    lines.append("")

    # Verificar si hay datos provinciales en la API
    # Por ahora, mostrar mensaje de "próximamente"
    lines.append("_Funcionalidad próximamente..._")
    lines.append("")
    lines.append("Las tasas por provincia se mostrarán aquí")
    lines.append("cuando estén disponibles en el backend.")
    lines.append("")
    lines.append("━" * 30)

    # Footer con timestamp
    from datetime import datetime
    updated_at = api_data.get("updated_at")
    if updated_at:
        try:
            updated_at = updated_at.replace("Z", "+00:00")
            if "+" in updated_at:
                updated_at = updated_at.split("+")[0]
            dt = datetime.fromisoformat(updated_at)
            timestamp = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines.append(f"📆 {timestamp}")
    lines.append("🔗 elToque.com")

    return "\n".join(lines)


async def tasalo_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para el botón 🔙 Volver.

    Vuelve a la vista principal de tasas.

    Args:
        update: Update de Telegram con el callback query
        context: Contexto del bot
    """
    query = update.callback_query
    await query.answer("🔙 Volviendo...")

    # Obtener datos frescos
    api_client: TasaloApiClient = context.bot_data.get("api_client")

    if not api_client:
        await query.edit_message_text(
            "⚠️ *Error de Configuración*\n\n"
            "El bot no está configurado correctamente.",
            parse_mode="Markdown",
        )
        return

    data = await api_client.get_latest()

    if data is None or not data.get("data"):
        await query.answer("⚠️ No se pudieron obtener datos", show_alert=True)
        return

    # Re-enviar la vista principal
    await send_tasalo_response(update, data.get("data"), message_id=query.message.message_id)

    logger.info("✅ Back callback completado")
