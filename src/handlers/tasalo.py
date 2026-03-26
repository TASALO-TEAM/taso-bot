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
from src.formatters import (
    build_full_message,
    build_history_message,
    SEPARATOR_THICK,
    parse_iso_datetime,
    build_eltoque_only_message,
    build_bcc_only_message,
    build_cadeca_only_message,
    build_toque_new_message,
)
from src.image_generator import generate_image
from src.stats_tracker import track_command_usage

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
    message: Optional[object] = None,
):
    """Envía la respuesta del comando /tasalo con imagen + texto + botones.

    Args:
        update: Update de Telegram
        api_data: Datos de la API
        message: Mensaje a editar (None para enviar nuevo desde comando)
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
        if message:
            # Editar mensaje existente con foto
            await message.edit_message_caption(
                caption=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            # Enviar foto como nuevo mensaje (no se puede editar a foto)
            await message.reply_photo(
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
        if message:
            await message.edit_message_text(
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

    # Trackear comando (fire-and-forget)
    asyncio.create_task(track_command_usage(update, context, "/tasalo"))

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
        # Trackear como fallo
        asyncio.create_task(track_command_usage(update, context, "/tasalo", success=False))
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
        # Trackear como fallo
        asyncio.create_task(track_command_usage(update, context, "/tasalo", success=False))
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
            "⚠️ *Error de Configuración*\n\nEl bot no está configurado correctamente.",
            parse_mode="Markdown",
        )
        return

    # Llamar a la API
    data = await api_client.get_latest()

    if data is None or not data.get("data"):
        await query.answer("⚠️ No se pudieron obtener datos", show_alert=True)
        return

    # Enviar respuesta actualizada
    await send_tasalo_response(
        update, data.get("data"), message=query.message
    )

    logger.info("✅ Refresh completado")


async def tasalo_provincias_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
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
            "⚠️ *Error de Configuración*\n\nEl bot no está configurado correctamente.",
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
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔙 Volver", callback_data="tasalo_back")],
        ]
    )

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
    lines.append(SEPARATOR_THICK)
    lines.append("")

    # Verificar si hay datos provinciales en la API
    # La API actual no tiene provincias, mostrar mensaje informativo
    # pero preparado para cuando se implemente

    # Por ahora, mostrar las tasas nacionales como placeholder
    eltoque_data = api_data.get("eltoque", {})

    if eltoque_data:
        lines.append("_Las tasas se muestran a nivel nacional._")
        lines.append("")
        lines.append("📍 *Tasa Nacional USD:*")

        usd_info = eltoque_data.get("USD", {})
        if isinstance(usd_info, dict):
            rate = usd_info.get("rate", 0)
            lines.append(f"   {rate:,.2f} CUP")
        else:
            lines.append(f"   {usd_info:,.2f} CUP")

        lines.append("")
        lines.append("🔜 *Próximamente:*")
        lines.append("Desglose por 15 provincias de Cuba")
        lines.append("")
    else:
        lines.append("_Datos no disponibles_")
        lines.append("")

    lines.append(SEPARATOR_THICK)

    # Footer con timestamp
    updated_at = api_data.get("updated_at")
    timestamp = parse_iso_datetime(updated_at)

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
            "⚠️ *Error de Configuración*\n\nEl bot no está configurado correctamente.",
            parse_mode="Markdown",
        )
        return

    data = await api_client.get_latest()

    if data is None or not data.get("data"):
        await query.answer("⚠️ No se pudieron obtener datos", show_alert=True)
        return

    # Re-enviar la vista principal
    await send_tasalo_response(
        update, data.get("data"), message=query.message
    )

    logger.info("✅ Back callback completado")


async def history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para ver histórico de una moneda.

    Callback data format: tasalo_history:{currency}:{source}:{days}
    Ejemplo: tasalo_history:USD:eltoque:7

    Args:
        update: Update de Telegram con el callback query
        context: Contexto del bot
    """
    query = update.callback_query
    await query.answer("📈 Cargando histórico...")

    user_id = query.from_user.id
    logger.info(f"📈 History callback invoked by user {user_id}")

    # Parsear callback data
    callback_data = query.data
    parts = callback_data.split(":")

    if len(parts) != 4:
        logger.error(f"❌ Invalid callback data format: {callback_data}")
        await query.answer("⚠️ Error cargando histórico", show_alert=True)
        return

    _, currency, source, days_str = parts

    try:
        days = int(days_str)
    except ValueError:
        logger.error(f"❌ Invalid days value: {days_str}")
        await query.answer("⚠️ Error cargando histórico", show_alert=True)
        return

    # Obtener cliente API
    api_client: TasaloApiClient = context.bot_data.get("api_client")

    if not api_client:
        await query.edit_message_text(
            "⚠️ *Error de Configuración*\n\nEl bot no está configurado correctamente.",
            parse_mode="Markdown",
        )
        return

    # Llamar a la API para histórico
    history_data = await api_client.get_history(
        source=source,
        currency=currency,
        days=days,
    )

    if history_data is None or not history_data.get("data"):
        await query.answer("⚠️ No hay datos históricos disponibles", show_alert=True)
        return

    # Construir mensaje de histórico
    history_text = build_history_message(currency, source, history_data.get("data", []))

    # Teclado con botón "Volver"
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔙 Volver", callback_data="tasalo_back")],
        ]
    )

    await query.edit_message_text(
        text=history_text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    logger.info(f"✅ Histórico mostrado para {currency}/{source}/{days}d")


# =============================================================================
# COMANDOS INDIVIDUALES POR FUENTE: /toque, /bcc, /cadeca
# =============================================================================


def _build_source_refresh_keyboard(source: str) -> InlineKeyboardMarkup:
    """Teclado simple con boton de refresh para comando individual."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Actualizar", callback_data=f"{source}_refresh")],
        ]
    )


async def _handle_source_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    source: str,
    build_message_func,
) -> None:
    """Handler genérico para comandos individuales por fuente.

    Args:
        update: Update de Telegram con el mensaje del usuario
        context: Contexto del bot con api_client en bot_data
        source: Identificador de la fuente ("toque", "bcc", "cadeca")
        build_message_func: Función formatter específica para la fuente
    """
    # Trackear comando (fire-and-forget)
    command_name = f"/{source}"
    asyncio.create_task(track_command_usage(update, context, command_name, source=source))

    api_client: TasaloApiClient = context.bot_data.get("api_client")
    if not api_client:
        logger.error("❌ api_client no está disponible en bot_data")
        await update.message.reply_text("❌ Error de configuración del bot.")
        return

    # Mensaje de carga
    loading_msg = await update.message.reply_text(f"⏳ Consultando {source.upper()}...")

    try:
        # Obtener response completo de la API
        response = await api_client.get_latest()

        # Validar respuesta
        if not response or not response.get("ok"):
            logger.warning(f"⚠️ API respondió None o ok=False para /{source}")
            await loading_msg.edit_text(
                f"⚠️ No se pudieron obtener datos de {source.upper()}."
            )
            # Trackear como fallo
            asyncio.create_task(track_command_usage(update, context, command_name, source=source, success=False))
            return

        # Extraer 'data' del response para pasar al formatter
        # Estructura: {"ok": true, "data": {"eltoque": {...}, "cadeca": {...}, ...}}
        api_data = response.get("data", {})

        if not api_data:
            logger.warning(f"⚠️ API data está vacío para /{source}")
            await loading_msg.edit_text(
                f"⚠️ Datos no disponibles de {source.upper()}."
            )
            # Trackear como fallo
            asyncio.create_task(track_command_usage(update, context, command_name, source=source, success=False))
            return

        # Construir mensaje con el formatter específico
        text = build_message_func(api_data)
        keyboard = _build_source_refresh_keyboard(source)

        await loading_msg.edit_text(
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        logger.info(f"✅ Comando /{source} ejecutado correctamente")

    except Exception as e:
        logger.error(f"❌ Error en comando /{source}: {e}", exc_info=True)
        await loading_msg.edit_text(f"❌ Error consultando {source.upper()}.")
        # Trackear como fallo
        asyncio.create_task(track_command_usage(update, context, command_name, source=source, success=False))


async def toque_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /toque — Muestra solo tasas de ElToque (nuevo formato)."""
    await _handle_source_command(update, context, "toque", build_toque_new_message)


async def bcc_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /bcc — Muestra solo tasas del BCC."""
    await _handle_source_command(update, context, "bcc", build_bcc_only_message)


async def cadeca_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /cadeca — Muestra solo tasas de CADECA."""
    await _handle_source_command(update, context, "cadeca", build_cadeca_only_message)


async def source_refresh_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Callback genérico para refresh de comandos individuales.

    Args:
        update: Update de Telegram con el callback query
        context: Contexto del bot con api_client en bot_data
    """
    query = update.callback_query
    await query.answer("🔄 Actualizando...")

    # Extraer fuente del callback_data (formato: "{source}_refresh")
    source = query.data.replace("_refresh", "")

    api_client: TasaloApiClient = context.bot_data.get("api_client")
    if not api_client:
        logger.error("❌ api_client no está disponible en source_refresh_callback")
        return

    try:
        # Obtener response completo y extraer 'data'
        response = await api_client.get_latest()
        if not response or not response.get("ok"):
            logger.warning(f"⚠️ API respondió None o ok=False en refresh /{source}")
            await query.answer("⚠️ Error actualizando datos", show_alert=True)
            return

        api_data = response.get("data", {})
        if not api_data:
            logger.warning(f"⚠️ API data está vacío en refresh /{source}")
            await query.answer("⚠️ Datos no disponibles", show_alert=True)
            return

        build_funcs = {
            "toque": build_toque_new_message,
            "bcc": build_bcc_only_message,
            "cadeca": build_cadeca_only_message,
        }
        build_func = build_funcs.get(source)
        if not build_func:
            logger.error(f"❌ Build function no encontrada para {source}")
            return

        text = build_func(api_data)
        keyboard = _build_source_refresh_keyboard(source)

        await query.edit_message_text(
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        logger.info(f"✅ Refresh /{source} completado")

    except Exception as e:
        logger.error(f"❌ Error en refresh /{source}: {e}", exc_info=True)
