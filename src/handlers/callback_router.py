# src/handlers/callback_router.py
"""Central callback router with namespace-based routing.

Consolidates 13+ individual CallbackQueryHandlers into a single handler
that routes callbacks based on their namespace prefix.

Benefits:
- 1 handler instead of 13+ in main.py
- Easy to add new namespaces (just add to ROUTE_MAP)
- Central logging of all callbacks
- Consistent error handling for unknown callbacks
- query.answer() always called first (avoids Telegram warnings)
- Comprehensive timing and user context tracking
"""
import re
import time
import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest

from src.handlers import image_alerts, tasalo, start, toqueimg, p, ta, trading, y as year_handlers

logger = logging.getLogger(__name__)

# Route map: prefix → handler function
# The handler receives (update, context, callback_data)
ROUTE_MAP = {
    "start": "_handle_start",
    "tasalo": "_handle_tasalo",
    "toque": "_handle_tasalo",
    "bcc": "_handle_tasalo",
    "cadeca": "_handle_tasalo",
    "toqueimg": "_handle_toqueimg",
    "alert": "_handle_alert",
    "p": "_handle_p",
    "ta": "_handle_ta",
    "ai": "_handle_ta",
    "graf": "_handle_graf",
    "year_sub": "_handle_year",
}


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route callback queries to appropriate handlers based on namespace prefix."""
    callback_start = time.time()
    query = update.callback_query
    if not query:
        return

    user_id = query.from_user.id
    callback_data = query.data
    namespace = callback_data.split("_")[0]

    logger.info("🔘 Callback '%s' from user %d (namespace: %s)", callback_data, user_id, namespace)

    # Answer immediately to remove loading state
    try:
        await query.answer()
    except BadRequest as e:
        logger.warning("Failed to answer query for user %d: %s", user_id, e)
        return

    handler_name = ROUTE_MAP.get(namespace)
    if handler_name:
        handler_func = globals().get(handler_name)
        if handler_func:
            logger.debug("Routing '%s' to handler '%s' for user %d", callback_data, handler_name, user_id)
            try:
                await handler_func(update, context, callback_data)
                duration_ms = (time.time() - callback_start) * 1000
                logger.info(
                    "✅ Callback '%s' completed for user %d via '%s' (%.0fms)",
                    callback_data, user_id, handler_name, duration_ms,
                )
            except Exception as e:
                duration_ms = (time.time() - callback_start) * 1000
                logger.error(
                    "❌ Error handling callback '%s' for user %d via '%s' (%.0fms): %s",
                    callback_data, user_id, handler_name, duration_ms, e, exc_info=True,
                )
                try:
                    await query.answer("⚠️ Error procesando la acción", show_alert=True)
                except BadRequest:
                    pass
        else:
            duration_ms = (time.time() - callback_start) * 1000
            logger.error(
                "❌ Handler function '%s' not found for callback '%s' from user %d (%.0fms)",
                handler_name, callback_data, user_id, duration_ms,
            )
            await query.answer("⚠️ Acción no reconocida", show_alert=True)
    else:
        duration_ms = (time.time() - callback_start) * 1000
        logger.warning(
            "⚠️ Unknown callback namespace: %s (data: %s) from user %d (%.0fms)",
            namespace, callback_data, user_id, duration_ms,
        )
        await query.answer("⚠️ Acción no reconocida", show_alert=True)


# ── Start callbacks ──

async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle start_* callbacks."""
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id

    command = callback_data.replace("start_", "")
    logger.info("🚀 Handler _handle_start processing '%s' for user %d", command, user_id)

    await start.start_button_callback(update, context)

    duration_ms = (time.time() - handler_start) * 1000
    logger.info("✅ _handle_start completed for user %d command '%s' (%.0fms)", user_id, command, duration_ms)


# ── Tasalo/source callbacks ──

async def _handle_tasalo(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle tasalo_*, toque_*, bcc_*, cadeca_* callbacks."""
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id

    logger.info("📊 Handler _handle_tasalo processing '%s' for user %d", callback_data, user_id)

    try:
        if callback_data == "tasalo_refresh":
            await tasalo.tasalo_refresh_callback(update, context)
        elif callback_data == "tasalo_back":
            await tasalo.tasalo_back_callback(update, context)
        elif callback_data.startswith("tasalo_history:"):
            await tasalo.history_callback(update, context)
        elif callback_data.endswith("_refresh"):
            await tasalo.source_refresh_callback(update, context)
        else:
            logger.warning("Unknown tasalo callback: %s for user %d", callback_data, user_id)
            duration_ms = (time.time() - handler_start) * 1000
            logger.info("⚠️ _handle_tasalo unknown callback '%s' for user %d (%.0fms)", callback_data, user_id, duration_ms)
            return

        duration_ms = (time.time() - handler_start) * 1000
        logger.info("✅ _handle_tasalo completed for user %d callback '%s' (%.0fms)", user_id, callback_data, duration_ms)
    except Exception as e:
        duration_ms = (time.time() - handler_start) * 1000
        logger.error(
            "❌ Error in _handle_tasalo for user %d callback '%s' (%.0fms): %s",
            user_id, callback_data, duration_ms, e, exc_info=True,
        )
        raise


# ── ToqueImg callbacks ──

async def _handle_toqueimg(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle toqueimg_* callbacks."""
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id

    logger.info("🖼️ Handler _handle_toqueimg processing '%s' for user %d", callback_data, user_id)

    try:
        if callback_data == "toqueimg_refresh":
            await toqueimg.toqueimg_refresh_callback(update, context)
        else:
            logger.warning("Unknown toqueimg callback: %s for user %d", callback_data, user_id)
            duration_ms = (time.time() - handler_start) * 1000
            logger.info("⚠️ _handle_toqueimg unknown callback '%s' for user %d (%.0fms)", callback_data, user_id, duration_ms)
            return

        duration_ms = (time.time() - handler_start) * 1000
        logger.info("✅ _handle_toqueimg completed for user %d callback '%s' (%.0fms)", user_id, callback_data, duration_ms)
    except Exception as e:
        duration_ms = (time.time() - handler_start) * 1000
        logger.error(
            "❌ Error in _handle_toqueimg for user %d callback '%s' (%.0fms): %s",
            user_id, callback_data, duration_ms, e, exc_info=True,
        )
        raise


# ── Alert callbacks ──

async def _handle_alert(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle alert_* callbacks."""
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id

    logger.info("🔔 Handler _handle_alert processing '%s' for user %d", callback_data, user_id)

    alert_handlers = {
        "alert_enable_default": image_alerts.alert_enable_default_callback,
        "alert_custom_time": image_alerts.alert_custom_time_callback,
        "alert_disable": image_alerts.alert_disable_callback,
        "alert_change_time": image_alerts.alert_change_time_callback,
        "alert_change_format": image_alerts.alert_change_format_callback,
        "alert_status": image_alerts.alert_status_callback,
        "alert_cancel": image_alerts.alert_cancel_callback,
    }

    try:
        # Handle format sub-callbacks: alert_format_photo, alert_format_document
        if callback_data.startswith("alert_format_"):
            logger.debug("Routing '%s' to alert_format_callback for user %d", callback_data, user_id)
            await image_alerts.alert_format_callback(update, context)
        elif callback_data in alert_handlers:
            handler_name = alert_handlers[callback_data].__name__
            logger.debug("Routing '%s' to '%s' for user %d", callback_data, handler_name, user_id)
            await alert_handlers[callback_data](update, context)
        else:
            duration_ms = (time.time() - handler_start) * 1000
            logger.warning(
                "⚠️ Unknown alert callback: %s for user %d (%.0fms)",
                callback_data, user_id, duration_ms,
            )
            return

        duration_ms = (time.time() - handler_start) * 1000
        logger.info("✅ _handle_alert completed for user %d callback '%s' (%.0fms)", user_id, callback_data, duration_ms)
    except Exception as e:
        duration_ms = (time.time() - handler_start) * 1000
        logger.error(
            "❌ Error in _handle_alert for user %d callback '%s' (%.0fms): %s",
            user_id, callback_data, duration_ms, e, exc_info=True,
        )
        raise



# ── P callbacks ──

async def _handle_p(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle refresh callbacks for /p command (prefix: p_refresh_...)."""
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id

    logger.info("💰 Handler _handle_p processing '%s' for user %d", callback_data, user_id)

    try:
        if callback_data.startswith("p_refresh_"):
            await p.p_refresh_callback(update, context)
        else:
            logger.warning("Unknown p callback: %s for user %d", callback_data, user_id)
            duration_ms = (time.time() - handler_start) * 1000
            logger.info("⚠️ _handle_p unknown callback '%s' for user %d (%.0fms)", callback_data, user_id, duration_ms)
            return

        duration_ms = (time.time() - handler_start) * 1000
        logger.info("✅ _handle_p completed for user %d callback '%s' (%.0fms)", user_id, callback_data, duration_ms)
    except Exception as e:
        duration_ms = (time.time() - handler_start) * 1000
        logger.error(
            "❌ Error in _handle_p for user %d callback '%s' (%.0fms): %s",
            user_id, callback_data, duration_ms, e, exc_info=True,
        )
        raise


# ── TA callbacks ──

async def _handle_ta(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id
    logger.info("🔍 Handler _handle_ta processing '%s' for user %d", callback_data, user_id)
    try:
        if callback_data.startswith("ta_switch|"):
            await ta.ta_switch_callback(update, context)
        elif callback_data.startswith("ta_quick|"):
            await trading.ta_quick_callback(update, context)
        elif callback_data.startswith("ai_analyze|"):
            await ta.ai_analysis_callback(update, context)
        else:
            logger.warning("Unknown ta callback: %s for user %d", callback_data, user_id)
            duration_ms = (time.time() - handler_start) * 1000
            logger.info("⚠️ _handle_ta unknown callback '%s' for user %d (%.0fms)", callback_data, user_id, duration_ms)
            return
        duration_ms = (time.time() - handler_start) * 1000
        logger.info("✅ _handle_ta completed for user %d callback '%s' (%.0fms)", user_id, callback_data, duration_ms)
    except Exception as e:
        duration_ms = (time.time() - handler_start) * 1000
        logger.error("❌ Error in _handle_ta for user %d callback '%s' (%.0fms): %s", user_id, callback_data, duration_ms, e, exc_info=True)
        raise


# ── GRAF callbacks ──

async def _handle_graf(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id
    logger.info("📈 Handler _handle_graf processing '%s' for user %d", callback_data, user_id)
    try:
        if callback_data.startswith("graf_tf|"):
            await trading.graf_timeframe_callback(update, context)
        elif callback_data.startswith("graf_from_ta|"):
            await ta.graf_from_ta_callback(update, context)
        elif callback_data.startswith("graf_from_btc|"):
            await query.answer("⚠️ Funcionalidad no disponible", show_alert=True)
            return
        else:
            logger.warning("Unknown graf callback: %s for user %d", callback_data, user_id)
            duration_ms = (time.time() - handler_start) * 1000
            logger.info("⚠️ _handle_graf unknown callback '%s' for user %d (%.0fms)", callback_data, user_id, duration_ms)
            return
        duration_ms = (time.time() - handler_start) * 1000
        logger.info("✅ _handle_graf completed for user %d callback '%s' (%.0fms)", user_id, callback_data, duration_ms)
    except Exception as e:
        duration_ms = (time.time() - handler_start) * 1000
        logger.error("❌ Error in _handle_graf for user %d callback '%s' (%.0fms): %s", user_id, callback_data, duration_ms, e, exc_info=True)
        raise


def get_callback_handler() -> CallbackQueryHandler:
    """Return the router as a CallbackQueryHandler for registration in main.py."""
    return CallbackQueryHandler(callback_router)


# ── Year subscription callbacks ──

async def _handle_year(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle year_sub_* callbacks (subscription toggle buttons from /y)."""
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id

    logger.info("📅 Handler _handle_year processing '%s' for user %d", callback_data, user_id)

    try:
        await year_handlers.year_sub_callback(update, context)

        duration_ms = (time.time() - handler_start) * 1000
        logger.info(
            "✅ _handle_year completed for user %d callback '%s' (%.0fms)",
            user_id, callback_data, duration_ms,
        )
    except Exception as e:
        duration_ms = (time.time() - handler_start) * 1000
        logger.error(
            "❌ Error in _handle_year for user %d callback '%s' (%.0fms): %s",
            user_id, callback_data, duration_ms, e, exc_info=True,
        )
        # Do not re-raise — callback_router has already answered this query
        # at line 59. A second answerCallbackQuery would fail with BadRequest
        # and silence the error toast. Errors are already logged above.
