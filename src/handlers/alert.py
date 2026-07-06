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
    alert_menu|{token}   → Abrir menú de niveles (S/R/Pivot) desde /graf o /ta
    alert_lvl|{token}|{lvl} → Crear alerta en un nivel específico
    alert_hint|{symbol}  → Instrucciones personalizadas desde /p
"""

import logging
import secrets
import time
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.stats_tracker import track_command_usage
from src.handlers.p import get_crypto_client

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


def _format_hace(created_at_str: str | None) -> str:
    """'hace 2 días' / 'hace 5 horas' / 'hace 18 min' — a partir de un ISO string. '' si falla."""
    if not created_at_str:
        return ""
    try:
        dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        total_min = max(0, int((datetime.now(timezone.utc) - dt).total_seconds() // 60))
        dias, resto_min = divmod(total_min, 1440)
        horas, _ = divmod(resto_min, 60)
        if dias:
            return f"hace {dias} día{'s' if dias != 1 else ''}"
        if horas:
            return f"hace {horas} hora{'s' if horas != 1 else ''}"
        return f"hace {resto_min} min" if resto_min else "recién creada"
    except (ValueError, TypeError):
        return ""


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
            hace = _format_hace(a.get("created_at"))
            origen = f" · {a['note']}" if a.get("note") else ""
            sufijo = f"  ({hace})" if hace else ""
            texto += f"• {coin} {emoji} {signo} {precio_fmt}{origen}{sufijo}\n"

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
    crypto = get_crypto_client()

    # Consultar precio actual para guardarlo como referencia de cruce
    current_price: float | None = None
    try:
        price_data = await crypto.get_crypto_data(coin)
        if price_data and price_data.get("price"):
            current_price = price_data["price"]
    except Exception as e:
        logger.warning("⚠️ No se pudo obtener precio actual de %s: %s", coin, e)

    if current_price is None:
        await update.message.reply_text(
            f"❌ No se pudo obtener el precio actual de *{coin}*.\n"
            f"Verifica que el símbolo sea correcto e inténtalo de nuevo.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    created = await api.create_price_alert(user_id, coin, price, current_price)

    if created:
        precio_fmt = _format_price(price)
        actual_fmt = _format_price(current_price)

        # Indicar qué dirección es relevante según la posición del precio actual
        if current_price < price:
            direccion = f"📈 Notificarás cuando *{coin}* suba a {precio_fmt}"
        elif current_price > price:
            direccion = f"📉 Notificarás cuando *{coin}* baje a {precio_fmt}"
        else:
            direccion = f"🎯 El precio está exactamente en el objetivo — se disparará en el próximo check"

        keyboard = [[InlineKeyboardButton("📋 Ver mis alertas", callback_data="alert_back")]]
        await update.message.reply_text(
            f"✅ *Alerta creada*\n\n"
            f"🔔 *{coin}* objetivo: {precio_fmt}\n"
            f"💰 Precio actual: {actual_fmt}\n\n"
            f"{direccion}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info("✅ /alert creada: user=%d coin=%s target=%.6f actual=%.6f (%.0fms)",
                    user_id, coin, price, current_price, (time.time() - cmd_start) * 1000)
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


# ── Integración con /graf y /ta — alertas por nivel de S/R/Pivot ──
#
# Los niveles (Pivot/R1-R3/S1-S3) se calculan en ta.py / trading.py al
# renderizar el mensaje. Para que la alerta creada use EXACTAMENTE el mismo
# número que el usuario vio en pantalla (sin depender de una nueva llamada
# a TradingView/Binance que podría devolver un valor ligeramente distinto),
# esos niveles se cachean aquí bajo un token corto que viaja en el
# callback_data (límite de Telegram: 64 bytes).

LEVEL_ORDER = ["R3", "R2", "R1", "Pivot", "S1", "S2", "S3"]
LEVEL_EMOJI = {
    "Pivot": "🎯", "R1": "🔴", "R2": "🔴", "R3": "🔴",
    "S1": "🟢", "S2": "🟢", "S3": "🟢",
}


def cache_alert_levels(
    context: ContextTypes.DEFAULT_TYPE,
    symbol: str,
    pair: str,
    timeframe: str,
    levels: dict,
    kind: str,
    render_source: str | None = None,
) -> str:
    """Guarda los niveles ya calculados y devuelve un token corto para el callback_data.

    Args:
        symbol: símbolo base, ej. "BTC"
        pair: par de cotización, ej. "USDT"
        timeframe: ej. "4h"
        levels: dict con las claves de LEVEL_ORDER que estén disponibles
        kind: "ta" o "graf" — determina el botón "Volver" y la etiqueta de origen
        render_source: para kind="ta", "TV" o "BINANCE" (permite reconstruir el botón Volver)
    """
    token = secrets.token_hex(3)
    cache = context.user_data.setdefault("alert_levels_cache", {})
    order = context.user_data.setdefault("alert_levels_cache_order", [])
    cache[token] = {
        "symbol": symbol,
        "pair": pair,
        "tf": timeframe,
        "kind": kind,
        "render_source": render_source,
        "levels": levels,
        "created": set(),
    }
    order.append(token)
    # Evita crecimiento indefinido: solo se guardan los últimos 5 análisis por usuario
    while len(order) > 5:
        old = order.pop(0)
        cache.pop(old, None)
    return token


def _get_cache_entry(context: ContextTypes.DEFAULT_TYPE, token: str) -> dict | None:
    return context.user_data.get("alert_levels_cache", {}).get(token)


def _menu_text(entry: dict) -> str:
    return (
        f"🔔 *¿Alerta en qué nivel?*\n\n"
        f"*{entry['symbol']}{entry['pair']}* · {entry['tf']}\n\n"
        f"Toca uno o varios niveles para crear alertas de seguimiento."
    )


def _build_levels_keyboard(entry: dict, token: str) -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    for lvl in LEVEL_ORDER:
        price = entry["levels"].get(lvl)
        if not price:
            continue
        emoji = LEVEL_EMOJI[lvl]
        label = f"✅ {lvl} creada" if lvl in entry["created"] else f"{emoji} {lvl}"
        btn = InlineKeyboardButton(label, callback_data=f"alert_lvl|{token}|{lvl}")
        if lvl == "Pivot":
            if row:
                keyboard.append(row)
                row = []
            keyboard.append([btn])
        else:
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
    if row:
        keyboard.append(row)

    if entry["kind"] == "ta":
        back_cb = f"ta_switch|{entry['render_source']}|{entry['symbol']}|{entry['pair']}|{entry['tf']}"
    else:
        back_cb = f"graf_tf|{entry['symbol']}|{entry['pair']}|{entry['tf']}"
    keyboard.append([InlineKeyboardButton("⬅️ Volver al análisis", callback_data=back_cb)])
    return InlineKeyboardMarkup(keyboard)


async def _edit_menu(query, text: str, markup: InlineKeyboardMarkup) -> None:
    """Edita el mensaje del menú, sea texto (/ta) o foto con caption (/graf)."""
    if query.message and query.message.photo:
        await query.edit_message_caption(caption=text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def alert_levels_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Abre el submenú de niveles. callback_data: 'alert_menu|{token}'"""
    query = update.callback_query
    try:
        _, token = query.data.split("|", 1)
    except ValueError:
        await query.answer("❌ Datos inválidos", show_alert=True)
        return

    entry = _get_cache_entry(context, token)
    if not entry:
        await query.answer("⚠️ Este menú expiró, genera un nuevo análisis", show_alert=True)
        return

    await query.answer()
    markup = _build_levels_keyboard(entry, token)
    await _edit_menu(query, _menu_text(entry), markup)


async def alert_create_level_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Crea una alerta para un nivel específico. callback_data: 'alert_lvl|{token}|{level}'"""
    query = update.callback_query
    try:
        _, token, level = query.data.split("|")
    except ValueError:
        await query.answer("❌ Datos inválidos", show_alert=True)
        return

    entry = _get_cache_entry(context, token)
    if not entry:
        await query.answer("⚠️ Este menú expiró, genera un nuevo análisis", show_alert=True)
        return

    if level in entry["created"]:
        await query.answer(f"Ya tienes una alerta activa en {level}", show_alert=True)
        return

    target_price = entry["levels"].get(level)
    if not target_price:
        await query.answer("❌ Nivel no disponible", show_alert=True)
        return

    symbol = entry["symbol"]
    user_id = query.from_user.id
    api = _get_api_client(context)
    crypto = get_crypto_client()

    current_price = None
    try:
        price_data = await crypto.get_crypto_data(symbol)
        if price_data and price_data.get("price"):
            current_price = price_data["price"]
    except Exception as e:
        logger.warning("⚠️ No se pudo obtener precio actual de %s: %s", symbol, e)

    if current_price is None:
        await query.answer("❌ No se pudo obtener el precio actual, intenta de nuevo", show_alert=True)
        return

    origen_label = "Análisis" if entry["kind"] == "ta" else "Gráfico"
    note = f"{level} · {origen_label} {entry['tf']}"

    created = await api.create_price_alert(user_id, symbol, target_price, current_price, note=note)

    if not created:
        await query.answer("❌ Error al crear la alerta", show_alert=True)
        return

    entry["created"].add(level)
    logger.info(
        "✅ Alerta por nivel creada: user=%d coin=%s nivel=%s target=%.6f (origen=%s)",
        user_id, symbol, level, target_price, note,
    )
    await query.answer(f"✅ Alerta creada: {symbol} @ {_format_price(target_price)} ({level})")
    markup = _build_levels_keyboard(entry, token)
    await _edit_menu(query, _menu_text(entry), markup)


async def alert_hint_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Instrucciones personalizadas desde /p. callback_data: 'alert_hint|{symbol}'"""
    query = update.callback_query
    try:
        _, symbol = query.data.split("|", 1)
    except ValueError:
        await query.answer("❌ Datos inválidos", show_alert=True)
        return

    await query.answer()
    crypto = get_crypto_client()
    current_price = None
    try:
        price_data = await crypto.get_crypto_data(symbol)
        if price_data and price_data.get("price"):
            current_price = price_data["price"]
    except Exception as e:
        logger.warning("⚠️ No se pudo obtener precio actual de %s: %s", symbol, e)

    precio_line = f"\n💰 Precio actual: {_format_price(current_price)}\n" if current_price else "\n"
    ejemplo = f"{current_price:.0f}" if current_price and current_price >= 1 else "70000"

    text = (
        f"➕ *Crear alerta de precio para {symbol}*\n"
        f"{precio_line}\n"
        f"Copia y ajusta el precio objetivo:\n"
        f"`/alert {symbol} {ejemplo}`\n\n"
        f"_Recibirás notificación cuando el precio suba o baje del nivel indicado._"
    )
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
