# src/handlers/p.py
"""Handler para comando /p — consulta de precios de criptomonedas.

Implementa la funcionalidad de BBAlert /p en taso-bot:
- Consulta CoinMarketCap (primario) o CryptoCompare (fallback)
- Muestra precio, high/low 24h, cambios %, precio en ETH/BTC
- Botones de refresh y análisis técnico
"""

import asyncio
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.crypto_client import CryptoApiClient
from src.formatters import build_crypto_message, build_crypto_extended_block
from src.stats_tracker import track_command_usage

logger = logging.getLogger(__name__)

# Cliente singleton (lazy)
_crypto_client: CryptoApiClient | None = None


def get_crypto_client() -> CryptoApiClient:
    """Retorna instancia singleton del cliente de cripto."""
    global _crypto_client
    if _crypto_client is None:
        _crypto_client = CryptoApiClient()
    return _crypto_client


# ── Callback de refresh ──

async def p_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback para botón 🔄 Actualizar /p {symbol}.

    Re-ejecuta p_command con el símbolo extraído de callback_data.
    callback_data formato: "p_refresh_{SYMBOL}"
    """
    query = update.callback_query
    user_id = query.from_user.id
    callback_data = query.data

    logger.info("🔄 /p refresh callback: '%s' by user %d", callback_data, user_id)

    # Extraer símbolo eliminando prefijo "p_refresh_"
    symbol = callback_data.replace("p_refresh_", "").upper()
    if not symbol or symbol == "P_REFRESH_":
        await query.answer("❌ Símbolo inválido", show_alert=True)
        logger.warning("⚠️ Invalid refresh callback data: '%s' for user %d", callback_data, user_id)
        return

    # Simular args de comando y re-ejecutar p_command
    context.args = [symbol]
    await p_command(update, context)


async def p_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback para botón 📋 Ver más — expande el bloque de CoinGecko.

    callback_data formato: "p_more|{SYMBOL}"

    Vuelve a consultar los datos (no se persisten entre callbacks) para
    construir el mensaje completo con el bloque extendido + botón "Ver menos".
    Si CoinGecko ya no tiene datos de enriquecimiento al momento del click
    (p.ej. la API falló), informa al usuario sin romper el mensaje base.
    """
    query = update.callback_query
    user_id = query.from_user.id
    callback_data = query.data

    symbol = callback_data.replace("p_more|", "").upper()
    if not symbol:
        await query.answer("❌ Símbolo inválido", show_alert=True)
        return

    logger.info("📋 /p ver más callback: símbolo '%s' por usuario %d", symbol, user_id)

    client = get_crypto_client()
    try:
        datos = await client.get_crypto_data(symbol)
    except Exception as e:
        logger.error("❌ Error en p_more_callback para %s: %s", symbol, e, exc_info=True)
        await query.answer("⚠️ Error obteniendo info adicional", show_alert=True)
        return

    if not datos:
        await query.answer("⚠️ Ya no se pueden obtener datos", show_alert=True)
        return

    enrichment = datos.get("enrichment")
    if not enrichment:
        await query.answer("ℹ️ No hay info adicional disponible para esta moneda", show_alert=True)
        return

    mensaje_base = build_crypto_message(datos)
    bloque_extra = build_crypto_extended_block(enrichment)
    mensaje_completo = f"{mensaje_base}\n{bloque_extra}"

    keyboard = _build_keyboard(symbol, has_enrichment=True, expanded=True)

    try:
        await query.edit_message_text(
            mensaje_completo,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
    except Exception as e:
        if "Message is not modified" in str(e):
            await query.answer("✅ Ya estás viendo la info completa")
        else:
            logger.error("❌ Error expandiendo /p para %s: %s", symbol, e, exc_info=True)
            await query.answer("⚠️ Error mostrando info adicional", show_alert=True)


async def p_less_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback para botón 🔼 Ver menos — vuelve al mensaje compacto.

    callback_data formato: "p_less|{SYMBOL}"
    """
    query = update.callback_query
    user_id = query.from_user.id
    callback_data = query.data

    symbol = callback_data.replace("p_less|", "").upper()
    if not symbol:
        await query.answer("❌ Símbolo inválido", show_alert=True)
        return

    logger.info("🔼 /p ver menos callback: símbolo '%s' por usuario %d", symbol, user_id)

    client = get_crypto_client()
    try:
        datos = await client.get_crypto_data(symbol)
    except Exception as e:
        logger.error("❌ Error en p_less_callback para %s: %s", symbol, e, exc_info=True)
        await query.answer("⚠️ Error actualizando", show_alert=True)
        return

    if not datos:
        await query.answer("⚠️ Ya no se pueden obtener datos", show_alert=True)
        return

    mensaje = build_crypto_message(datos)
    keyboard = _build_keyboard(symbol, has_enrichment=bool(datos.get("enrichment")), expanded=False)

    try:
        await query.edit_message_text(
            mensaje,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
    except Exception as e:
        if "Message is not modified" in str(e):
            await query.answer("✅ Vista compacta")
        else:
            logger.error("❌ Error colapsando /p para %s: %s", symbol, e, exc_info=True)
            await query.answer("⚠️ Error actualizando vista", show_alert=True)


def _build_keyboard(symbol: str, has_enrichment: bool, expanded: bool) -> InlineKeyboardMarkup:
    """Construye el teclado inline de /p según el estado de expansión.

    Args:
        symbol: Símbolo de la moneda (ej: BTC)
        has_enrichment: True si hay datos de CoinGecko disponibles
        expanded: True si el bloque extendido ya está visible

    Returns:
        InlineKeyboardMarkup con botones Refresh + TA + (Ver más/Ver menos)
    """
    btn_refresh = InlineKeyboardButton(
        f"🔄 Actualizar /p {symbol}",
        callback_data=f"p_refresh_{symbol}"
    )
    btn_ta = InlineKeyboardButton(
        "📊 Ver Análisis Técnico (4H)",
        callback_data=f"ta_quick|{symbol}|4h"  # Enruta a ta.ta_quick_callback
    )

    rows = [[btn_refresh], [btn_ta]]

    if has_enrichment:
        if expanded:
            btn_toggle = InlineKeyboardButton(
                "🔼 Ver menos", callback_data=f"p_less|{symbol}"
            )
        else:
            btn_toggle = InlineKeyboardButton(
                "📋 Ver más", callback_data=f"p_more|{symbol}"
            )
        rows.append([btn_toggle])

    return InlineKeyboardMarkup(rows)


# ── Comando principal ──

async def p_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el precio y datos de una criptomoneda.

    Uso: /p <MONEDA>
    Ejemplos: /p BTC, /p ETH, /p HIVE

    Lógica:
    1. Validar que se proporcionó símbolo
    2. Mostrar "escribiendo..." para feedback visual
    3. Obtener datos (CoinMarketCap → fallback CryptoCompare)
    4. Formatear y enviar mensaje Markdown con botones inline
    """
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    first_name = update.effective_user.first_name or "Unknown"

    logger.info(
        "💰 /p command invoked by user %d (@%s, %s)",
        user_id, username, first_name
    )

    # 1. Validar argumento
    if not context.args:
        logger.warning("⚠️ /p called without arguments by user %d", user_id)
        error_msg = "⚠️ *Formato incorrecto*\n\nUso: `/p <MONEDA>`\nEjemplo: `/p BTC`"
        if update.callback_query:
            await update.callback_query.edit_message_text(
                error_msg, parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                error_msg, parse_mode=ParseMode.MARKDOWN
            )
        asyncio.create_task(
            track_command_usage(update, context, "/p", success=False)
        )
        return

    symbol = context.args[0].upper()
    logger.debug("User %d: Querying /p for symbol '%s'", user_id, symbol)

    # 2. Mostrar "escribiendo..." si es mensaje nuevo (no callback refresh)
    if update.message:
        await update.message.reply_chat_action("typing")

    # 3. Obtener datos de la criptomoneda
    client = get_crypto_client()
    fetch_start = time.time()

    try:
        datos = await client.get_crypto_data(symbol)
    except Exception as e:
        logger.error("❌ Error fetching crypto data for %s: %s", symbol, e, exc_info=True)
        datos = None

    fetch_duration_ms = (time.time() - fetch_start) * 1000

    if not datos:
        logger.warning("⚠️ No data returned for %s (%.0fms)", symbol, fetch_duration_ms)
        error_msg = f"⚠️ Error obteniendo datos para *{symbol}*. Las APIs pueden estar temporalmente inaccesibles. Intenta de nuevo en un momento."
        if update.callback_query:
            await update.callback_query.edit_message_text(
                error_msg, parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                error_msg, parse_mode=ParseMode.MARKDOWN
            )
        asyncio.create_task(
            track_command_usage(update, context, "/p", source=symbol, success=False)
        )
        return

    # Moneda confirmada como no existente en ninguna fuente
    if datos.get("not_found"):
        logger.info("❌ Símbolo %s no existe en ninguna API (%.0fms)", symbol, fetch_duration_ms)
        not_found_msg = (
            f"❌ *{symbol}* no se encontró en ninguna fuente de datos.\n\n"
            f"Verifica que el símbolo sea correcto o prueba con otro.\n"
            f"_Ejemplo: `/p BTC`, `/p ETH`, `/p SOL`_"
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(
                not_found_msg, parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                not_found_msg, parse_mode=ParseMode.MARKDOWN
            )
        asyncio.create_task(
            track_command_usage(update, context, "/p", source=symbol, success=False)
        )
        return

    logger.info(
        "✅ /p datos obtenidos para %s: price=%.2f USD (%.0fms)",
        symbol, datos.get("price", 0), fetch_duration_ms
    )

    # 4. Construir mensaje con formatter
    try:
        mensaje = build_crypto_message(datos)
    except Exception as e:
        logger.error("❌ Error formatting crypto message for %s: %s", symbol, e, exc_info=True)
        error_msg = f"😕 Error formateando datos para *{symbol}*."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(error_msg, parse_mode=ParseMode.MARKDOWN)
        asyncio.create_task(
            track_command_usage(update, context, "/p", source=symbol, success=False)
        )
        return

    # 5. Construir teclado inline (Refresh + TA + Ver más si hay datos CoinGecko)
    # Nota: usa namespace "ta_quick" para que callback_router lo enrute directamente
    keyboard = _build_keyboard(
        symbol,
        has_enrichment=bool(datos.get("enrichment")),
        expanded=False,
    )

    # 6. Enviar/editar mensaje
    send_start = time.time()
    try:
        if update.callback_query:
            query = update.callback_query
            await query.edit_message_text(
                mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
        else:
            await update.message.reply_text(
                mensaje,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
    except Exception as e:
        # Message not modified — common race condition en refresh
        if "Message is not modified" in str(e):
            logger.debug("📝 Mensaje no modificado para %s (ya actualizado)", symbol)
            if update.callback_query:
                await update.callback_query.answer("✅ Datos ya actualizados")
        else:
            logger.error("❌ Error sending /p message for %s: %s", symbol, e, exc_info=True)
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    "❌ Error mostrando datos. Intenta de nuevo.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await update.message.reply_text(
                    "❌ Error mostrando datos. Intenta de nuevo.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            asyncio.create_task(
                track_command_usage(update, context, "/p", source=symbol, success=False)
            )
            return

    send_duration_ms = (time.time() - send_start) * 1000
    total_duration_ms = (time.time() - cmd_start) * 1000

    logger.info(
        "✅ /p completed for user %d symbol=%s (total=%.0fms, send=%.0fms)",
        user_id, symbol, total_duration_ms, send_duration_ms
    )

    # 7. Trackear uso (fire-and-forget)
    asyncio.create_task(
        track_command_usage(update, context, "/p", source=symbol, success=True)
    )
