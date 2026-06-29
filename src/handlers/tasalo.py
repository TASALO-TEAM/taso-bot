"""Handlers para el comando /tasalo del bot TASALO.

Módulo responsable de manejar el comando /tasalo, callbacks inline,
y comandos de administración con logging detallado de todas las operaciones.
"""

import asyncio
import logging
import time
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.api_client import TasaloApiClient
from src.cache import cache
from src.formatters import (
    build_full_message,
    build_full_message_with_datetime,
    build_history_message,
    SEPARATOR_THICK,
    parse_iso_datetime,
    HAS_DATETIME_ENTITY,
    build_eltoque_only_message,
    build_bcc_only_message,
    build_cadeca_only_message,
    build_fuel_only_message,
    build_toque_new_message,
)
from src.stats_tracker import track_command_usage

logger = logging.getLogger(__name__)

# Cache TTL para tasas (segundos)
RATES_CACHE_TTL = 60  # 1 minuto


def build_inline_keyboard() -> InlineKeyboardMarkup:
    """Construye el teclado inline con botones 🔄 y 🗺.

    Returns:
        InlineKeyboardMarkup con los botones de acción
    """
    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 Actualizar",
                callback_data="tasalo_refresh",
                style="primary",  # Azul - acción principal
            ),
            # TODO: Habilitar cuando la API tenga datos de provincias
            # InlineKeyboardButton("🗺 Ver provincias", callback_data="tasalo_provincias"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_tasalo_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    api_data: dict,
    message_id: Optional[int] = None,
):
    """Envía la respuesta del comando /tasalo solo con texto y botones.

    Usa Bot API 9.5 DATE_TIME entities (PTB 22.7+) cuando están disponibles
    para formateo automático del timestamp según la zona horaria del usuario.

    Args:
        update: Update de Telegram
        context: Contexto del bot (necesario para métodos de edición)
        api_data: Datos de la API
        message_id: ID del mensaje a editar (None para enviar nuevo desde comando)
    """
    send_start = time.time()
    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None
    
    # Construir teclado inline
    keyboard = build_inline_keyboard()

    # Build message — use DATE_TIME entities if available (Bot API 9.5+)
    if HAS_DATETIME_ENTITY:
        # Extract timestamp from API response or use current time
        updated_at_raw = api_data.get("updated_at")
        if updated_at_raw:
            try:
                # Parse ISO datetime to Unix timestamp
                from datetime import datetime as _dt
                iso_str = updated_at_raw.replace("Z", "+00:00")
                dt = _dt.fromisoformat(iso_str)
                ts = int(dt.timestamp())
            except (ValueError, AttributeError):
                ts = int(time.time())
        else:
            ts = int(time.time())

        text, entities = build_full_message_with_datetime(api_data, ts)
        parse_mode = None  # Must be None when using entities
    else:
        # Fallback: standard Markdown
        text = build_full_message(api_data)
        entities = None
        parse_mode = "Markdown"

    # Enviar solo texto (sin generación de imagen)
    try:
        if message_id:
            await context.bot.edit_message_text(
                text=text,
                chat_id=update.effective_chat.id,
                message_id=message_id,
                reply_markup=keyboard,
                parse_mode=parse_mode,
                entities=entities,
            )
        else:
            await update.message.reply_text(
                text=text,
                reply_markup=keyboard,
                parse_mode=parse_mode,
                entities=entities,
            )
        send_duration_ms = (time.time() - send_start) * 1000
        action = "edited" if message_id else "sent"
        logger.info(
            "✅ /tasalo %s to user %d (datetime=%s, %.0fms)",
            action, user_id, HAS_DATETIME_ENTITY, send_duration_ms
        )
    except Exception as e:
        send_duration_ms = (time.time() - send_start) * 1000
        logger.error(
            "❌ Error sending /tasalo to user %d (%.0fms): %s",
            user_id, send_duration_ms, e, exc_info=True
        )
        raise


async def tasalo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /tasalo.

    Comando principal que muestra las tasas de cambio actuales de todas
    las fuentes (ElToque, CADECA, BCC) con texto formateado y botones.

    Flujo:
        1. Envía mensaje "⏳ Consultando tasas..."
        2. Llama a taso-api para obtener datos
        3. Si error: muestra mensaje de error amigable
        4. Si éxito: formatea texto y envía con botones inline

    Args:
        update: Update de Telegram con el mensaje del usuario
        context: Contexto del bot (incluye api_client)
    """
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username
    logger.info("📊 /tasalo command invoked by user %d (@%s)", user_id, username)

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

    # Check cache first
    cached_data = cache.get("rates:latest", ttl=RATES_CACHE_TTL)
    if cached_data:
        cache_duration_ms = (time.time() - cmd_start) * 1000
        logger.info("📦 /tasalo cache HIT for user %d (%.0fms)", user_id, cache_duration_ms)
        await send_tasalo_response(update, context, cached_data)
        await status_msg.delete()
        return

    # Cache miss — fetch from API
    logger.info("🌐 /tasalo cache MISS for user %d, fetching from API", user_id)
    api_start = time.time()
    data = await api_client.get_latest()
    api_duration_ms = (time.time() - api_start) * 1000

    if data is None:
        total_duration_ms = (time.time() - cmd_start) * 1000
        logger.warning("⚠️ /tasalo: API returned None for user %d (%.0fms)", user_id, total_duration_ms)
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
        total_duration_ms = (time.time() - cmd_start) * 1000
        logger.warning("⚠️ /tasalo: API data empty for user %d (%.0fms)", user_id, total_duration_ms)
        await status_msg.edit_text(
            "⚠️ *Datos No Disponibles*\n\n"
            "El backend no tiene datos actualizados.\n"
            "Inténtalo de nuevo más tarde.",
            parse_mode="Markdown",
        )
        # Trackear como fallo
        asyncio.create_task(track_command_usage(update, context, "/tasalo", success=False))
        return

    # Cache the successful response
    cache.set("rates:latest", api_data)
    logger.debug("📦 /tasalo: Cached rates for user %d (TTL=%ds)", user_id, RATES_CACHE_TTL)

    # Enviar respuesta con texto + botones
    await send_tasalo_response(update, context, api_data)

    # Eliminar mensaje de estado
    await status_msg.delete()
    
    total_duration_ms = (time.time() - cmd_start) * 1000
    logger.info("✅ /tasalo completed for user %d (API=%.0fms, total=%.0fms)", 
                user_id, api_duration_ms, total_duration_ms)


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
        update, context, data.get("data"), message_id=query.message.message_id
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
            [InlineKeyboardButton(
                "🔙 Volver",
                callback_data="tasalo_back",
            )],
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
        update, context, data.get("data"), message_id=query.message.message_id
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
            [InlineKeyboardButton(
                "🔙 Volver",
                callback_data="tasalo_back",
            )],
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
            [InlineKeyboardButton(
                "🔄 Actualizar",
                callback_data=f"{source}_refresh",
                style="primary",  # Azul - acción principal
            )],
        ]
    )


async def _handle_source_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    source: str,
    build_message_func,
) -> None:
    """Handler genérico para comandos individuales por fuente (TEXTO SOLAMENTE).

    Estos comandos son SOLO TEXTO con botones inline. La generación de imágenes
    está reservada exclusivamente para el comando /toqueimg.

    Args:
        update: Update de Telegram con el mensaje del usuario
        context: Contexto del bot con api_client en bot_data
        source: Identificador de la fuente ("toque", "bcc", "cadeca")
        build_message_func: Función formatter específica para la fuente
    """
    user_id = update.effective_user.id if update.effective_user else 0
    logger.info("📊 /%s command invoked by user %s", source, user_id)
    
    # Trackear comando (fire-and-forget)
    command_name = f"/{source}"
    asyncio.create_task(track_command_usage(update, context, command_name, source=source))

    # Guardar contra update.message None
    if not update.message:
        logger.warning("⚠️ update.message es None para /%s", source)
        return

    api_client: TasaloApiClient = context.bot_data.get("api_client")
    if not api_client:
        logger.error("❌ api_client no está disponible en bot_data")
        await update.message.reply_text("❌ Error de configuración del bot.")
        return

    # Check cache first (compartido con /tasalo)
    cached_data = cache.get("rates:latest", ttl=RATES_CACHE_TTL)
    if cached_data:
        logger.info("📦 /%s: Using cached rates", source)
        text = build_message_func(cached_data)
        keyboard = _build_source_refresh_keyboard(source)
        
        try:
            loading_msg = await update.message.reply_text(f"⏳ Consultando {source.upper()}...")
            await loading_msg.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            logger.info("✅ /%s enviado desde cache (texto)", source)
        except Exception as e:
            logger.error("❌ Error enviando /%s desde cache: %s", source, e, exc_info=True)
            await update.message.reply_text(f"❌ Error consultando {source.upper()}.")
        return

    # Cache miss — obtener de API
    logger.info("🌐 /%s: Fetching from API (cache miss)", source)
    
    # Mensaje de carga
    loading_msg = await update.message.reply_text(f"⏳ Consultando {source.upper()}...")

    try:
        # Obtener response completo de la API
        response = await api_client.get_latest()

        # Validar respuesta
        if not response or not response.get("ok"):
            logger.warning("⚠️ API respondió None o ok=False para /%s", source)
            await loading_msg.edit_text(
                f"⚠️ No se pudieron obtener datos de {source.upper()}."
            )
            asyncio.create_task(track_command_usage(update, context, command_name, source=source, success=False))
            return

        # Extraer 'data' del response
        api_data = response.get("data", {})

        if not api_data:
            logger.warning("⚠️ API data está vacío para /%s", source)
            await loading_msg.edit_text(
                f"⚠️ Datos no disponibles de {source.upper()}."
            )
            asyncio.create_task(track_command_usage(update, context, command_name, source=source, success=False))
            return

        # Construir mensaje SOLO TEXTO (sin imagen)
        text = build_message_func(api_data)
        keyboard = _build_source_refresh_keyboard(source)

        # Enviar respuesta SOLO TEXTO
        try:
            await loading_msg.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            logger.info("✅ /%s enviado (texto con botones)", source)
        except Exception as send_error:
            # Fallback si el envío falla
            logger.error("❌ Error enviando texto para /%s: %s", source, send_error, exc_info=True)
            try:
                await update.message.reply_text(
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                logger.info("✅ Texto enviado para /%s (fallback)", source)
            except Exception as fallback_error:
                logger.error("❌ Error en fallback final para /%s: %s", source, fallback_error, exc_info=True)

        logger.info("✅ Comando /%s ejecutado correctamente", source)

    except Exception as e:
        logger.error("❌ Error en comando /%s: %s", source, e, exc_info=True)
        await loading_msg.edit_text(f"❌ Error consultando {source.upper()}.")
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


async def fuel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /fuel — Precios de combustible del mercado informal (ElToque)."""
    user_id = update.effective_user.id if update.effective_user else 0
    logger.info("⛽ /fuel command invoked by user %s", user_id)

    asyncio.create_task(track_command_usage(update, context, "/fuel", source="fuel"))

    if not update.message:
        logger.warning("⚠️ update.message es None para /fuel")
        return

    api_client: TasaloApiClient = context.bot_data.get("api_client")
    if not api_client:
        logger.error("❌ api_client no está disponible en bot_data")
        await update.message.reply_text("❌ Error de configuración del bot.")
        return

    loading_msg = await update.message.reply_text("⏳ Consultando combustible...")

    try:
        response = await api_client.get_fuel()

        if not response or response.get("rates") is None:
            logger.warning("⚠️ API respondió None o sin rates para /fuel")
            await loading_msg.edit_text("⚠️ No se pudieron obtener datos de combustible.")
            asyncio.create_task(track_command_usage(update, context, "/fuel", source="fuel", success=False))
            return

        text = build_fuel_only_message(response)
        keyboard = _build_source_refresh_keyboard("fuel")

        try:
            await loading_msg.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            logger.info("✅ /fuel enviado (texto con botones)")
        except Exception as send_error:
            logger.error("❌ Error enviando /fuel: %s", send_error, exc_info=True)
            try:
                await update.message.reply_text(
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                logger.info("✅ Texto enviado para /fuel (fallback)")
            except Exception as fallback_error:
                logger.error("❌ Error en fallback final /fuel: %s", fallback_error, exc_info=True)

    except Exception as e:
        logger.error("❌ Error en comando /fuel: %s", e, exc_info=True)
        try:
            await loading_msg.edit_text("❌ Error consultando combustible.")
        except Exception:
            pass
        asyncio.create_task(track_command_usage(update, context, "/fuel", source="fuel", success=False))


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
        # Fuel tiene su propio endpoint separado de /latest
        if source == "fuel":
            response = await api_client.get_fuel()
            if not response or response.get("rates") is None:
                logger.warning("⚠️ API respondió None o sin rates en refresh /fuel")
                await query.answer("⚠️ Error actualizando datos", show_alert=True)
                return
            text = build_fuel_only_message(response)
            keyboard = _build_source_refresh_keyboard("fuel")
            await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="Markdown")
            logger.info("✅ Refresh /fuel completado")
            return

        # Resto de fuentes usan /latest
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
            "fuel": build_fuel_only_message,
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
