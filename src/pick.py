"""Selectores por botones para /p, /ta y /graf (F6-T5). Namespace `pick`.

Moneda -> (temporalidad) -> ejecuta el comando real, sin escribir argumentos.
El callback_data no es confiable: moneda y temporalidad se validan contra
listas fijas, y lo que no encaje cae en la bienvenida sin ejecutar nada.
"""

import logging
import re
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ApplicationHandlerStop, MessageHandler, filters

from src import callback_data as cd

logger = logging.getLogger(__name__)

COINS = ("BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TON")
TFS = ("15m", "1h", "4h", "1d")
_SYM = re.compile(r"^[A-Z0-9]{2,10}$")  # simbolo libre ("otra moneda"): solo mayusculas y digitos
ESPERA = "pick_awaiting"  # user_data: (flujo, instante) mientras se espera el simbolo
ESPERA_TTL = 120.0
# flags de otros flujos de texto libre: pedir una moneda cancela cualquiera pendiente
_OTROS_FLAGS = ("tkt_awaiting", "awaiting_tspl_hour", "awaiting_year_hour")
LEVELS = ("m10", "m5", "p5", "p10")  # /alert: % sobre el precio actual (m = menos, p = mas)
FLOWS = {"p": "\U0001f4b2 Precio /p", "ta": "\U0001f4ca An\u00e1lisis /ta", "graf": "\U0001f4c8 Gr\u00e1fico /graf", "alert": "\U0001f514 Alerta /alert"}


def parse(args: tuple):
    """(flujo, moneda, temporalidad) validado, o None."""
    if not args or len(args) > 3 or args[0] not in FLOWS:
        return None
    flow = args[0]
    coin = args[1] if len(args) > 1 else None
    tf = args[2] if len(args) > 2 else None
    if coin is not None and coin not in COINS and not _SYM.match(coin):
        return None
    opciones = {"p": (), "ta": TFS, "graf": TFS, "alert": LEVELS}[flow]
    if tf is not None and tf not in opciones:
        return None
    return flow, coin, tf


def _nivel(k: str) -> tuple[int, str]:
    """'m5' -> (-5, '-5%')."""
    n = int(k[1:]) * (-1 if k[0] == "m" else 1)
    return n, f"{n:+d}%"


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
        filas.append([_btn("\u270f\ufe0f Otra moneda", cd.build("pick", flow, "otra"))])
        filas.append(_nav("alert_back" if flow == "alert" else None))
        return f"{FLOWS[flow]}\n\nElige la moneda:", InlineKeyboardMarkup(filas)
    if flow == "alert":
        opciones, pide = [(k, _nivel(k)[1]) for k in LEVELS], "el nivel sobre el precio actual"
    else:
        opciones, pide = [(t, t) for t in TFS], "la temporalidad"
    botones = [_btn(txt, cd.build("pick", flow, coin, k)) for k, txt in opciones]
    return (
        f"{FLOWS[flow]} \u00b7 {coin}\n\nElige {pide}:",
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
    elif flow == "alert":
        await _crear_alerta(update, context, coin, tf)
    else:
        from src.handlers.trading import _do_graf

        await _do_graf(update, context, base=coin, quote="USDT", timeframe=tf, is_callback=True)


async def _mostrar(query, texto: str, markup) -> None:
    """Edita el mensaje; si no es editable (foto, antiguo) manda uno nuevo."""
    try:
        await query.edit_message_text(texto, reply_markup=markup)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        logger.info("pick: mensaje no editable (%s); se envia uno nuevo", e)
        await query.message.reply_text(texto, reply_markup=markup)


async def _crear_alerta(update, context, coin: str, nivel: str) -> None:
    """Alerta a +/-N% del precio actual, con la misma API que `/alert <moneda> <precio>`."""
    from src.handlers import alert as al

    query = update.callback_query
    pct, etiqueta = _nivel(nivel)
    precio = None
    try:
        datos = await al.get_crypto_client().get_crypto_data(coin)
        precio = datos.get("price") if datos else None
    except Exception as e:  # red o API caida: se avisa abajo
        logger.warning("pick: sin precio de %s: %s", coin, e)
    creada = False
    if precio:
        objetivo = float(f"{precio * (1 + pct / 100):.6g}")
        creada = await al._get_api_client(context).create_price_alert(
            query.from_user.id, coin, objetivo, precio, note=f"Botones \u00b7 {etiqueta}"
        )
    if creada:
        texto = (
            f"\u2705 Alerta creada\n\n{coin} objetivo: {al._format_price(objetivo)} ({etiqueta})\n"
            f"Precio actual: {al._format_price(precio)}"
        )
        fila = [_btn("\U0001f514 Ver mis alertas", "alert_back")]
    else:
        motivo = "No se pudo crear la alerta" if precio else f"No pude obtener el precio actual de {coin}"
        texto = f"\u274c {motivo}. Int\u00e9ntalo de nuevo."
        fila = [_btn("\u25c0 Atr\u00e1s", cd.build("pick", "alert", coin))]
    await _mostrar(query, texto, InlineKeyboardMarkup([fila, _nav()]))


async def pick_callback(update, context, callback_data: str) -> None:
    query = update.callback_query
    parsed = cd.parse_v2(callback_data)
    args = parsed[1] if parsed else ()
    if len(args) == 2 and args[0] in FLOWS and args[1] == "otra":
        await _pedir_simbolo(update, context, args[0])
        return
    p = parse(args)
    if p is None:
        from src.menu import menu_callback

        await menu_callback(update, context, cd.build("menu", "home"))
        return
    pantalla = render(args)
    if pantalla is None:
        await _ejecutar(update, context, *p)
        return
    await _mostrar(query, *pantalla)


def _cancelar_otras_esperas(user_data) -> None:
    user_data["waiting_for_time"] = False
    user_data["alert_action"] = None
    for f in _OTROS_FLAGS:
        user_data.pop(f, None)
    user_data.pop("explorer_waiting", None)


async def _pedir_simbolo(update, context, flow: str) -> None:
    _cancelar_otras_esperas(context.user_data)
    context.user_data[ESPERA] = (flow, time.monotonic())
    texto = f"{FLOWS[flow]}\n\nEscribe el s\u00edmbolo de la moneda (por ejemplo LINK)."
    await _mostrar(update.callback_query, texto, InlineKeyboardMarkup([_nav(cd.build("pick", flow))]))


async def pick_text(update, context) -> None:
    """Texto libre mientras se espera un simbolo. Sin espera no hace nada ni corta la cadena."""
    espera = context.user_data.get(ESPERA)
    if not espera:
        return
    flow, t0 = espera
    msg = update.message
    if time.monotonic() - t0 > ESPERA_TTL or not msg or not msg.text:
        context.user_data.pop(ESPERA, None)
        return
    sym = msg.text.strip().upper()
    if not _SYM.match(sym):
        context.user_data[ESPERA] = (flow, time.monotonic())  # puede reintentar
        await msg.reply_text("S\u00edmbolo no v\u00e1lido. Usa solo letras y n\u00fameros (2 a 10), por ejemplo LINK.")
        raise ApplicationHandlerStop
    context.user_data.pop(ESPERA, None)
    if flow == "p":
        from src.handlers.p import p_command

        context.args = [sym]
        await p_command(update, context)
    else:
        texto, markup = render((flow, sym))
        await msg.reply_text(texto, reply_markup=markup)
    raise ApplicationHandlerStop


def register(app) -> None:
    """Antes que el explorador (-1): mientras se espera un simbolo, ese texto es de pick."""
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, pick_text), group=-2)
