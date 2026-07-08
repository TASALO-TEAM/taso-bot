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

from src.handlers import image_alerts, tasalo, start, toqueimg, p, ta, trading, y, alert as price_alert, spl, ms

logger = logging.getLogger(__name__)

# Route map: prefix → handler function
# Multi-segment prefixes (e.g. "year_sub") are resolved by _resolve_namespace()
# before lookup, so the map key must be the full compound prefix.
ROUTE_MAP: dict[str, str] = {
    "start":    "_handle_start",
    "tasalo":   "_handle_tasalo",
    "toque":    "_handle_tasalo",
    "bcc":      "_handle_tasalo",
    "cadeca":   "_handle_tasalo",
    "toqueimg": "_handle_toqueimg",
    "alert":    "_handle_alert",
    "p":        "_handle_p",
    "ta":       "_handle_ta",
    "ai":       "_handle_ta",
    "graf":     "_handle_graf",
    "year_sub": "_handle_year",
    "spl":      "_handle_spl",
    "ms":       "_handle_ms",
}

# Known multi-segment namespace prefixes that must be resolved atomically
_NS_PREFIXES: tuple[str, ...] = tuple(k for k in ROUTE_MAP if "_" in k)


def _resolve_namespace(callback_data: str) -> str:
    """Resolve the namespace of a callback data string.

    Supports both single-segment (``"tasalo"``) and multi-segment
    (``"year_sub"``) prefixes.  For multi-segment prefixes only the
    *first* join (first + second segment) is attempted so that prefixes
    like ``year_sub`` are matched as one key instead of yielding only
    ``"year"``.
    """
    parts = callback_data.split("_")
    if len(parts) >= 2:
        candidate = f"{parts[0]}_{parts[1]}"
        if candidate in ROUTE_MAP:
            return candidate
    return parts[0]


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route callback queries to appropriate handlers based on namespace prefix."""
    callback_start = time.time()
    query = update.callback_query
    if not query:
        return

    user_id = query.from_user.id
    callback_data = query.data
    namespace = _resolve_namespace(callback_data)

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

    # Callbacks de image_alerts (alertas de imagen diaria)
    image_alert_handlers = {
        "alert_enable_default": image_alerts.alert_enable_default_callback,
        "alert_custom_time": image_alerts.alert_custom_time_callback,
        "alert_disable": image_alerts.alert_disable_callback,
        "alert_change_time": image_alerts.alert_change_time_callback,
        "alert_change_format": image_alerts.alert_change_format_callback,
        "alert_status": image_alerts.alert_status_callback,
        "alert_cancel": image_alerts.alert_cancel_callback,
    }

    try:
        # ── Price alerts (nuevos, /alert command) ──
        if callback_data == "alert_create":
            await price_alert.alert_create_callback(update, context)
        elif callback_data == "alert_delete_menu":
            await price_alert.alert_delete_menu_callback(update, context)
        elif callback_data == "alert_delete_all":
            await price_alert.alert_delete_all_callback(update, context)
        elif callback_data == "alert_back":
            await price_alert.alert_back_callback(update, context)
        elif callback_data.startswith("alert_delete_") and not callback_data.startswith("alert_delete_menu"):
            await price_alert.alert_delete_single_callback(update, context)
        elif callback_data.startswith("alert_menu|"):
            await price_alert.alert_levels_menu_callback(update, context)
        elif callback_data.startswith("alert_lvl|"):
            await price_alert.alert_create_level_callback(update, context)
        elif callback_data.startswith("alert_hint|"):
            await price_alert.alert_hint_callback(update, context)
        # ── Image alerts (existentes, /toqueimg) ──
        elif callback_data.startswith("alert_format_"):
            logger.debug("Routing '%s' to alert_format_callback for user %d", callback_data, user_id)
            await image_alerts.alert_format_callback(update, context)
        elif callback_data in image_alert_handlers:
            handler_name = image_alert_handlers[callback_data].__name__
            logger.debug("Routing '%s' to '%s' for user %d", callback_data, handler_name, user_id)
            await image_alert_handlers[callback_data](update, context)
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
        elif callback_data.startswith("ai_panorama|"):
            await p.p_ai_panorama_callback(update, context)
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


# ── Spotlight (/spl) callbacks ──

async def _handle_spl(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle spl_* callbacks (refresh button from /spl)."""
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id
    logger.info("🔦 Handler _handle_spl processing '%s' for user %d", callback_data, user_id)
    try:
        if callback_data == "spl_refresh":
            await spl.spl_refresh_callback(update, context)
        else:
            logger.warning("Unknown spl callback: %s for user %d", callback_data, user_id)
            duration_ms = (time.time() - handler_start) * 1000
            logger.info("⚠️ _handle_spl unknown callback '%s' for user %d (%.0fms)", callback_data, user_id, duration_ms)
            return
        duration_ms = (time.time() - handler_start) * 1000
        logger.info("✅ _handle_spl completed for user %d callback '%s' (%.0fms)", user_id, callback_data, duration_ms)
    except Exception as e:
        duration_ms = (time.time() - handler_start) * 1000
        logger.error("❌ Error in _handle_spl for user %d callback '%s' (%.0fms): %s", user_id, callback_data, duration_ms, e, exc_info=True)
        raise


def get_callback_handler() -> CallbackQueryHandler:
    """Return the router as a CallbackQueryHandler for registration in main.py."""
    return CallbackQueryHandler(callback_router)


# ── Year subscription callbacks ──

async def _handle_year(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle year_sub_* callbacks (subscription toggle buttons from /y).

    The actual implementation lives in ``handlers/y.py``; this thin wrapper
    exists so ``globals().get("_handle_year")`` continues to resolve
    correctly within the callback router.
    """
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id

    logger.info("📅 Handler _handle_year processing '%s' for user %d", callback_data, user_id)

    try:
        await y.year_sub_callback(update, context)

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
        # at line 80. A second answerCallbackQuery would fail with BadRequest
        # and silence the error toast. Errors are already logged above.


# ── Broadcast (/ms) callbacks ──

async def _handle_ms(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle ms_confirm:<admin_id> / ms_cancel:<admin_id> callbacks from /ms.

    The actual implementation lives in ``handlers/ms.py``; this thin wrapper
    dispatches to confirm_callback or cancel_callback based on the prefix,
    following the same pattern as ``_handle_year`` above.
    """
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id

    logger.info("📢 Handler _handle_ms processing '%s' for user %d", callback_data, user_id)

    try:
        if callback_data.startswith("ms_confirm:"):
            await ms.confirm_callback(update, context)
        elif callback_data.startswith("ms_cancel:"):
            await ms.cancel_callback(update, context)
        else:
            logger.warning("⚠️ _handle_ms recibió callback_data desconocido: '%s'", callback_data)
            return

        duration_ms = (time.time() - handler_start) * 1000
        logger.info(
            "✅ _handle_ms completed for user %d callback '%s' (%.0fms)",
            user_id, callback_data, duration_ms,
        )
    except Exception as e:
        duration_ms = (time.time() - handler_start) * 1000
        logger.error(
            "❌ Error in _handle_ms for user %d callback '%s' (%.0fms): %s",
            user_id, callback_data, duration_ms, e, exc_info=True,
        )
