"""Selectores por botones para /p, /ta y /graf (F6-T5). Namespace `pick`.

Moneda -> (temporalidad) -> ejecuta el comando real, sin escribir argumentos.
El callback_data no es confiable: moneda y temporalidad se validan contra
listas fijas, y lo que no encaje cae en la bienvenida sin ejecutar nada.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from src import callback_data as cd

logger = logging.getLogger(__name__)

COINS = ("BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TON")
TFS = ("15m", "1h", "4h", "1d")
FLOWS = {"p": "\U0001f4b2 Precio /p", "ta": "\U0001f4ca An\u00e1lisis /ta", "graf": "\U0001f4c8 Gr\u00e1fico /graf"}


def parse(args: tuple):
    """(flujo, moneda, temporalidad) validado, o None."""
    if not args or len(args) > 3 or args[0] not in FLOWS:
        return None
    flow = args[0]
    coin = args[1] if len(args) > 1 else None
    tf = args[2] if len(args) > 2 else None
    if coin is not None and coin not in COINS:
        return None
    if tf is not None and (flow == "p" or tf not in TFS):
        return None
    return flow, coin, tf


def _btn(texto: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(texto, callback_data=data)


def _nav(atras: str | None = None) -> list[InlineKeyboardButton]:
    fila = [_btn("\u25c0 Atr\u00e1s", atras)] if atras else []
    return [*fila, _btn("\U0001f3e0 Inicio", cd.build("menu", "home"))]


def render(args: tuple):
    """(texto, teclado) de la pantalla, o None si `args` es invalido o ya es una accion."""
    p = parse(args)
    if p is None:
        return None
    flow, coin, tf = p
    if tf or (coin and flow == "p"):
        return None
    if coin is None:
        botones = [_btn(c, cd.build("pick", flow, c)) for c in COINS]
        filas = [botones[i : i + 4] for i in range(0, len(botones), 4)]
        filas.append(_nav())
        return f"{FLOWS[flow]}\n\nElige la moneda:", InlineKeyboardMarkup(filas)
    botones = [_btn(t, cd.build("pick", flow, coin, t)) for t in TFS]
    return (
        f"{FLOWS[flow]} \u00b7 {coin}\n\nElige la temporalidad:",
        InlineKeyboardMarkup([botones, _nav(cd.build("pick", flow))]),
    )


async def _ejecutar(update, context, flow: str, coin: str, tf: str | None) -> None:
    if flow == "p":
        from src.handlers.p import p_command

        context.args = [coin]
        await p_command(update, context)
    elif flow == "ta":
        from src.handlers.ta import ta_command

        msg = update.callback_query.message
        await ta_command(
            update,
            context,
            override_source="BINANCE",
            override_args=[coin, "USDT", tf],
            force_new_message=bool(msg.photo or msg.document),
        )
    else:
        from src.handlers.trading import _do_graf

        await _do_graf(update, context, base=coin, quote="USDT", timeframe=tf, is_callback=True)


async def pick_callback(update, context, callback_data: str) -> None:
    query = update.callback_query
    parsed = cd.parse_v2(callback_data)
    args = parsed[1] if parsed else ()
    p = parse(args)
    if p is None:
        from src.menu import menu_callback

        await menu_callback(update, context, cd.build("menu", "home"))
        return
    pantalla = render(args)
    if pantalla is None:
        await _ejecutar(update, context, *p)
        return
    texto, markup = pantalla
    try:
        await query.edit_message_text(texto, reply_markup=markup)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        logger.info("pick: mensaje no editable (%s); se envia uno nuevo", e)
        await query.message.reply_text(texto, reply_markup=markup)
