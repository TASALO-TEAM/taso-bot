# src/handlers/alert.py
"""Handler para /alert — alertas de precio de criptomonedas.

Comandos:
    /alert               → Ver alertas activas con botones de gestión
    /alert <COIN> <PRECIO>  → Crear alerta directamente

Callbacks inline (prefijo "alert_"):
    alert_create         → Mostrar instrucciones de creación
    alert_delete_menu    → Menú de eliminación por alerta
    alert_delete_{id}    → Eliminar alerta específica
    alert_delete_all     → Eliminar todas las alertas del usuario
    alert_back           → Volver al listado principal
"""

import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.stats_tracker import track_command_usage

logger = logging.getLogger(__name__)


def _get_api_client(context: ContextTypes.DEFAULT_TYPE):
    """Obtiene el api_client desde bot_data."""
    return context.application.bot_data.get("api_client")


def _format_price(price: float) -> str:
    """Formatea el precio con la cantidad apropiada de decimales."""
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:,.4f}"
    else:
        return f"${price:.8f}"


# ── Vista principal de alertas ──

async def show_alerts_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query=None,
) -> None:
    """Muestra las alertas activas del usuario con botones de gestión."""
    user_id = update.effective_user.id
    api = _get_api_client(context)

    alertas = await api.get_user_price_alerts(user_id)

    if not alertas:
        keyboard = [[
            InlineKeyboardButton("➕ Crear mi primera alerta", callback_data="alert_create")
        ]]
        text = (
            "🔔 *Sin alertas de precio*\n\n"
            "Crea una alerta fácilmente:\n"
            "`/alert BTC 70000`\n\n"
            "O usa el botón de abajo."
        )
        markup = InlineKeyboardMarkup(keyboard)
        if query:
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        return

    # Agrupar por coin+price para mostrar como par ABOVE/BELOW
    grupos: dict = {}
    for a in alertas:
        key = (a["coin"], a["target_price"])
        grupos.setdefault(key, []).append(a)

    texto = "🔔 *Tus alertas de precio activas:*\n\n"
    for (coin, price), lista in sorted(grupos.items()):
        precio_fmt = _format_price(price)
        for a in lista:
            emoji = "📈" if a["condition"] == "ABOVE" else "📉"
            signo = ">" if a["condition"] == "ABOVE" else "<"
            texto += f"• {coin} {emoji} {signo} {precio_fmt}\n"

    keyboard = [
        [InlineKeyboardButton("➕ Crear nueva alerta", callback_data="alert_create")],
        [InlineKeyboardButton("🗑️ Eliminar alerta", callback_data="alert_delete_menu")],
    ]
    markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(texto, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(texto, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


# ── Comando principal ──

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /alert              → ver alertas activas
    /alert BTC 70000   → crear alerta para BTC en $70,000
    """
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    logger.info("🔔 /alert invocado por user %d (@%s)", user_id, username)

    # Sin argumentos → mostrar lista
    if not context.args:
        await show_alerts_menu(update, context)
        return

    # Con argumentos → crear alerta
    if len(context.args) != 2:
        await update.message.reply_text(
            "⚠️ *Formato incorrecto*\n\n"
            "Uso: `/alert <MONEDA> <PRECIO>`\n"
            "Ejemplo: `/alert BTC 70000`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    coin = context.args[0].upper()
    try:
        price = float(context.args[1].replace(",", ""))
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            f"⚠️ Precio inválido: `{context.args[1]}`\nDebe ser un número mayor a 0.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await update.message.reply_chat_action("typing")
    api = _get_api_client(context)
    created = await api.create_price_alert(user_id, coin, price)

    if created:
        precio_fmt = _format_price(price)
        keyboard = [[
            InlineKeyboardButton("📋 Ver mis alertas", callback_data="alert_back")
        ]]
        await update.message.reply_text(
            f"✅ *Alerta creada*\n\n"
            f"🔔 *{coin}* @ {precio_fmt}\n\n"
            f"Recibirás notificación cuando el precio suba o baje de este nivel.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info("✅ /alert creada: user=%d coin=%s price=%.6f (%.0fms)",
                    user_id, coin, price, (time.time() - cmd_start) * 1000)
    else:
        await update.message.reply_text(
            "❌ Error al crear la alerta. Inténtalo de nuevo.",
            parse_mode=ParseMode.MARKDOWN,
        )

    import asyncio
    asyncio.create_task(
        track_command_usage(update, context, "/alert", source=coin, success=bool(created))
    )


# ── Callbacks ──

async def alert_create_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra instrucciones para crear una alerta."""
    query = update.callback_query
    await query.answer()

    text = (
        "➕ *Crear alerta de precio*\n\n"
        "Envía el comando con moneda y precio:\n"
        "`/alert BTC 70000`\n"
        "`/alert ETH 3500`\n"
        "`/alert HIVE 0.35`\n\n"
        "_Recibirás notificación cuando el precio suba o baje del nivel indicado._"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="alert_back")]]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN
    )


async def alert_delete_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra menú de eliminación con un botón por cada alerta."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    api = _get_api_client(context)

    alertas = await api.get_user_price_alerts(user_id)

    if not alertas:
        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="alert_back")]]
        await query.edit_message_text(
            "ℹ️ No tienes alertas para eliminar.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    texto = "🗑️ *Selecciona la alerta a eliminar:*\n\n"
    keyboard = []
    alertas_ord = sorted(alertas, key=lambda x: (x.get("coin", ""), x.get("target_price", 0)))

    for idx, a in enumerate(alertas_ord, 1):
        coin = a["coin"]
        price = a["target_price"]
        condition = a["condition"]
        alert_id = a["id"]
        emoji = "📈" if condition == "ABOVE" else "📉"
        signo = ">" if condition == "ABOVE" else "<"
        precio_fmt = _format_price(price)
        texto += f"{idx}. {coin} {emoji} {signo} {precio_fmt}\n"
        keyboard.append([
            InlineKeyboardButton(
                f"🗑️ {coin} {idx} ({condition})",
                callback_data=f"alert_delete_{alert_id}",
            )
        ])

    keyboard.append([InlineKeyboardButton("🗑️ Eliminar TODAS", callback_data="alert_delete_all")])
    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="alert_back")])

    await query.edit_message_text(
        texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN
    )


async def alert_delete_single_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Elimina una alerta específica por su id."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # callback_data: "alert_delete_{alert_id}"
    try:
        alert_id = int(query.data.split("alert_delete_")[1])
    except (IndexError, ValueError):
        await query.answer("❌ Error procesando la solicitud", show_alert=True)
        return

    api = _get_api_client(context)
    ok = await api.delete_price_alert(alert_id, user_id)

    if ok:
        logger.info("🗑️ Alert %d eliminada por user %d", alert_id, user_id)
    else:
        logger.warning("⚠️ No se pudo eliminar alert %d para user %d", alert_id, user_id)

    await show_alerts_menu(update, context, query)


async def alert_delete_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Elimina todas las alertas del usuario."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    api = _get_api_client(context)

    await api.delete_all_price_alerts(user_id)
    logger.info("🗑️ Todas las alertas eliminadas para user %d", user_id)
    await show_alerts_menu(update, context, query)


async def alert_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vuelve al listado principal de alertas."""
    query = update.callback_query
    await query.answer()
    await show_alerts_menu(update, context, query)
