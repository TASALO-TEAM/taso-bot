# src/handlers/qp.py
"""Handler para comando /qp — tasas de cambio promedio P2P de QvaPay.

Uso: /qp (sin argumentos)

Consulta QvaPayClient.get_p2p_rates() (9 monedas en paralelo contra
api.qvapay.com) y arma un solo mensaje con el promedio (compra+venta)/2
de cada una x USD. El resultado es el mismo para todos los usuarios, así
que se cachea globalmente — mismo patrón que /spl (src/handlers/spl.py).

Ver docs/plans/2026-07-30-comando-qp-qvapay.md para el diseño completo.
"""

import asyncio
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.qvapay_client import QvaPayClient
from src.formatters import build_qvapay_message
from src.stats_tracker import track_command_usage
from src.cache import cache
from src.services.ads_manager import get_ad_block, safe_append

logger = logging.getLogger(__name__)

CACHE_KEY = "qvapay_p2p_rates"
CACHE_TTL_SECONDS = 300  # 5 minutos — tasas compartidas entre todos los usuarios

# Cliente singleton (lazy) — reutiliza la misma conexión HTTP entre comandos
_qvapay_client: QvaPayClient | None = None


def get_qvapay_client() -> QvaPayClient:
    """Retorna instancia singleton del cliente de QvaPay."""
    global _qvapay_client
    if _qvapay_client is None:
        _qvapay_client = QvaPayClient()
    return _qvapay_client


def _build_keyboard() -> InlineKeyboardMarkup:
    """Construye el teclado inline de /qp (solo botón de refresh)."""
    btn_refresh = InlineKeyboardButton("🔄 Actualizar", callback_data="qp_refresh")
    return InlineKeyboardMarkup([[btn_refresh]])


async def _get_or_build_message() -> str:
    """Retorna el mensaje de /qp desde caché, o lo genera si expiró."""
    cached = cache.get(CACHE_KEY, ttl=CACHE_TTL_SECONDS)
    if cached:
        return cached

    client = get_qvapay_client()
    rates = await client.get_p2p_rates()
    mensaje = build_qvapay_message(rates)
    cache.set(CACHE_KEY, mensaje)
    return mensaje


async def qp_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback para botón 🔄 Actualizar de /qp."""
    query = update.callback_query
    user_id = query.from_user.id
    logger.info("🔄 /qp refresh callback by user %d", user_id)
    await qp_command(update, context)


async def qp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra las tasas promedio P2P de QvaPay x USD.

    Uso: /qp (sin argumentos)
    """
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"

    logger.info("💱 /qp command invoked by user %d (@%s)", user_id, username)

    if update.message:
        await update.message.reply_chat_action("typing")
    elif update.callback_query:
        await update.callback_query.answer("🔄 Actualizando tasas...")

    try:
        mensaje = await _get_or_build_message()
    except Exception as e:
        logger.error("❌ Error generando /qp: %s", e, exc_info=True)
        error_msg = "⚠️ No se pudieron obtener las tasas de QvaPay. Intenta de nuevo en unos momentos."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        asyncio.create_task(
            track_command_usage(update, context, "/qp", success=False)
        )
        return

    # Inyectar bloque de anuncio (si hay alguno activo y cabe en el límite).
    # Se aplica después del caché de tasas (no se cachea junto al ad) para
    # que la rotación de anuncios funcione igual que en /p, /y, /ta, etc.
    api_client_for_ad = context.bot_data.get("api_client")
    if api_client_for_ad:
        ad_block = await get_ad_block(api_client_for_ad)
        mensaje = safe_append(mensaje, ad_block)

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
            logger.debug("📝 /qp: mensaje no modificado (ya actualizado)")
            if update.callback_query:
                await update.callback_query.answer("✅ Tasas ya actualizadas")
        else:
            logger.error("❌ Error enviando /qp: %s", e, exc_info=True)
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    "❌ Error mostrando las tasas. Intenta de nuevo."
                )
            else:
                await update.message.reply_text(
                    "❌ Error mostrando las tasas. Intenta de nuevo."
                )
            asyncio.create_task(
                track_command_usage(update, context, "/qp", success=False)
            )
            return

    total_duration_ms = (time.time() - cmd_start) * 1000
    logger.info("✅ /qp completed for user %d (total=%.0fms)", user_id, total_duration_ms)

    asyncio.create_task(
        track_command_usage(update, context, "/qp", success=True)
    )
