# src/handlers/spl.py
"""Handler para comando /spl — Spotlight de Mercado (panorama general).

A diferencia de /p (una moneda especifica), /spl arma un panorama general
del mercado cripto combinando: Fear & Greed Index, dominancia BTC/ETH,
top gainers/losers, tendencias y (si el plan de la API key lo permite)
titulares reales de CoinMarketCap. El resultado se cachea globalmente
(no por usuario) 10-15 minutos, ya que es el mismo panorama para todos.

Ver docs/plans/2026-07-02-comando-spl-spotlight.md para el diseno completo.
"""

import asyncio
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.handlers.p import get_crypto_client
from src.formatters import SEPARATOR_THICK, build_market_spotlight_data_block
from src.stats_tracker import track_command_usage
from src.core.ai_logic import get_groq_market_spotlight
from src.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "market_spotlight"
CACHE_TTL_SECONDS = 900  # 15 minutos — panorama compartido entre todos los usuarios


def _build_keyboard() -> InlineKeyboardMarkup:
    """Construye el teclado inline de /spl (solo botón de refresh)."""
    btn_refresh = InlineKeyboardButton(
        "🔄 Actualizar Spotlight",
        callback_data="spl_refresh"
    )
    return InlineKeyboardMarkup([[btn_refresh]])


async def _get_or_build_spotlight_body() -> str:
    """Retorna el cuerpo completo del spotlight (datos duros + narrativa IA)
    desde caché, o lo genera si expiró.

    Se cachea el cuerpo YA ENSAMBLADO (no solo el texto de la IA) para que
    los números del bloque de datos y la narrativa correspondan siempre al
    mismo snapshot — evita que un refresh a mitad del TTL muestre datos
    duros nuevos junto a una narrativa vieja o viceversa.
    """
    cached = cache.get(CACHE_KEY, ttl=CACHE_TTL_SECONDS)
    if cached:
        return cached

    client = get_crypto_client()
    snapshot = await client.get_market_snapshot()

    data_block = build_market_spotlight_data_block(snapshot)
    narrativa = await get_groq_market_spotlight(snapshot)

    body = f"{data_block}\n{SEPARATOR_THICK}\n\n{narrativa}"
    cache.set(CACHE_KEY, body)
    return body


async def spl_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback para botón 🔄 Actualizar Spotlight."""
    query = update.callback_query
    user_id = query.from_user.id
    logger.info("🔄 /spl refresh callback by user %d", user_id)
    await spl_command(update, context)


async def spl_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el panorama general del mercado cripto (Spotlight).

    Uso: /spl (sin argumentos)
    """
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"

    logger.info("🔦 /spl command invoked by user %d (@%s)", user_id, username)

    if update.message:
        await update.message.reply_chat_action("typing")
    elif update.callback_query:
        await update.callback_query.answer("🔄 Actualizando panorama...")

    try:
        cuerpo = await _get_or_build_spotlight_body()
    except Exception as e:
        logger.error("❌ Error generando /spl: %s", e, exc_info=True)
        error_msg = "⚠️ No se pudo generar el panorama de mercado. Intenta de nuevo en unos momentos."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        asyncio.create_task(
            track_command_usage(update, context, "/spl", success=False)
        )
        return

    mensaje = f"🔦 *SPOTLIGHT — Panorama del Mercado*\n{SEPARATOR_THICK}\n\n{cuerpo}"
    keyboard = _build_keyboard()

    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
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
        if "Message is not modified" in str(e):
            logger.debug("📝 /spl: mensaje no modificado (ya actualizado)")
            if update.callback_query:
                await update.callback_query.answer("✅ Panorama ya actualizado")
        else:
            # Fallback sin Markdown si el contenido generado por la IA rompe el parseo
            logger.warning("⚠️ Fallo enviando /spl con Markdown: %s", e)
            try:
                mensaje_plano = mensaje.replace("*", "").replace("_", "")
                if update.callback_query:
                    await update.callback_query.edit_message_text(mensaje_plano, reply_markup=keyboard)
                else:
                    await update.message.reply_text(mensaje_plano, reply_markup=keyboard)
            except Exception as e2:
                logger.error("❌ Error enviando /spl (fallback): %s", e2, exc_info=True)
                asyncio.create_task(
                    track_command_usage(update, context, "/spl", success=False)
                )
                return

    total_duration_ms = (time.time() - cmd_start) * 1000
    logger.info("✅ /spl completed for user %d (total=%.0fms)", user_id, total_duration_ms)

    asyncio.create_task(
        track_command_usage(update, context, "/spl", success=True)
    )
