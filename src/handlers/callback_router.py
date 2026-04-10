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
"""
import re
import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest

from src.handlers import image_alerts, tasalo, start

logger = logging.getLogger(__name__)

# Route map: prefix → handler function
# The handler receives (update, context, callback_data)
ROUTE_MAP = {
    "start": "_handle_start",
    "tasalo": "_handle_tasalo",
    "toque": "_handle_tasalo",  # Reuses tasalo handler
    "bcc": "_handle_tasalo",    # Reuses tasalo handler
    "cadeca": "_handle_tasalo", # Reuses tasalo handler
    "toqueimg": "_handle_toqueimg",
    "alert": "_handle_alert",
}


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route callback queries to appropriate handlers based on namespace prefix."""
    query = update.callback_query
    if not query:
        return

    # Answer immediately to remove loading state
    try:
        await query.answer()
    except BadRequest as e:
        logger.warning(f"Failed to answer query: {e}")
        return

    callback_data = query.data
    namespace = callback_data.split("_")[0]

    handler_name = ROUTE_MAP.get(namespace)
    if handler_name:
        handler_func = globals().get(handler_name)
        if handler_func:
            try:
                await handler_func(update, context, callback_data)
            except Exception as e:
                logger.error(f"Error handling callback '{callback_data}': {e}", exc_info=True)
                await query.answer("⚠️ Error procesando la acción", show_alert=True)
        else:
            logger.error(f"Handler function '{handler_name}' not found")
            await query.answer("⚠️ Acción no reconocida", show_alert=True)
    else:
        logger.warning(f"Unknown callback namespace: {namespace} (data: {callback_data})")
        await query.answer("⚠️ Acción no reconocida", show_alert=True)


# ── Start callbacks ──

async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle start_* callbacks."""
    # Extract command: start_tasalo → tasalo, start_toque → toque, etc.
    command = callback_data.replace("start_", "")
    await start.start_button_callback(update, context)


# ── Tasalo/source callbacks ──

async def _handle_tasalo(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle tasalo_*, toque_*, bcc_*, cadeca_* callbacks."""
    if callback_data == "tasalo_refresh":
        await tasalo.tasalo_refresh_callback(update, context)
    elif callback_data == "tasalo_back":
        await tasalo.tasalo_back_callback(update, context)
    elif callback_data.startswith("tasalo_history:"):
        await tasalo.history_callback(update, context)
    elif callback_data.endswith("_refresh"):
        await tasalo.source_refresh_callback(update, context)
    else:
        logger.warning(f"Unknown tasalo callback: {callback_data}")


# ── ToqueImg callbacks ──

async def _handle_toqueimg(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle toqueimg_* callbacks."""
    if callback_data == "toqueimg_refresh":
        await tasalo.toqueimg_refresh_callback(update, context)
    else:
        logger.warning(f"Unknown toqueimg callback: {callback_data}")


# ── Alert callbacks ──

async def _handle_alert(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str) -> None:
    """Handle alert_* callbacks."""
    alert_handlers = {
        "alert_enable_default": image_alerts.alert_enable_default_callback,
        "alert_custom_time": image_alerts.alert_custom_time_callback,
        "alert_disable": image_alerts.alert_disable_callback,
        "alert_change_time": image_alerts.alert_change_time_callback,
        "alert_change_format": image_alerts.alert_change_format_callback,
        "alert_status": image_alerts.alert_status_callback,
        "alert_cancel": image_alerts.alert_cancel_callback,
    }

    # Handle format sub-callbacks: alert_format_photo, alert_format_document
    if callback_data.startswith("alert_format_"):
        await image_alerts.alert_format_callback(update, context)
    elif callback_data in alert_handlers:
        await alert_handlers[callback_data](update, context)
    else:
        logger.warning(f"Unknown alert callback: {callback_data}")


def get_callback_handler() -> CallbackQueryHandler:
    """Return the router as a CallbackQueryHandler for registration in main.py."""
    return CallbackQueryHandler(callback_router)
