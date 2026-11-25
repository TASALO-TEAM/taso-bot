"""/liq: liquidaciones de futuros de las ultimas horas (M3).

Datos de GET /api/v1/liquidaciones (taso-api#27): longs y shorts liquidados en
USD, por moneda o por exchange. El colector vive en la API; aqui solo se
formatea. Los botones editan el mismo mensaje (liq:<ventana>:<m|e>).
"""

import asyncio
import html
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.stats_tracker import track_command_usage

logger = logging.getLogger(__name__)

CUBA = ZoneInfo("America/Havana")
VENTANAS = {"5m": "5 min", "15m": "15 min", "1h": "1 h", "4h": "4 h", "24h": "24 h"}
VISTAS = {"m": "symbol", "e": "exchange"}
VISTA_CODIGO = {v: k for k, v in VISTAS.items()}
ALIAS_VISTA = {"monedas": "symbol", "moneda": "symbol", "symbol": "symbol",
               "exchange": "exchange", "exchanges": "exchange"}
NOMBRES = {"binance": "Binance", "bybit": "Bybit", "okx": "OKX"}
POR_DEFECTO = ("1h", "symbol")
FILAS_MONEDAS = 8
CUADROS_BARRA = 10
LONG, SHORT = "\U0001f7e5", "\U0001f7e9"  # un long liquidado es presion vendedora: rojo
MSG_USO = ("Uso: /liq [5m|15m|1h|4h|24h] [monedas|exchanges]\n"
           "Ejemplos: /liq, /liq 4h, /liq 24h exchanges")
MSG_ERROR = "\u26a0\ufe0f No pude obtener las liquidaciones ahora mismo. Intenta de nuevo en unos minutos."


def _usd(v: float) -> str:
    if v < 1_000:
        return f"${v:.0f}"
    if v < 1_000_000:
        return f"${v / 1_000:.1f} mil"
    if v < 1_000_000_000:
        return f"${v / 1_000_000:.1f} millones"
    return f"${v / 1_000_000_000:.1f} mil millones"


def parse_args(args) -> tuple[str, str] | None:
    """['4h', 'exchanges'] en cualquier orden -> (ventana, vista); None si algo no se entiende."""
    ventana = vista = None
    for a in args:
        if a in VENTANAS and ventana is None:
            ventana = a
        elif a in ALIAS_VISTA and vista is None:
            vista = ALIAS_VISTA[a]
        else:
            return None
    return ventana or POR_DEFECTO[0], vista or POR_DEFECTO[1]


def _aviso_cobertura(meta: dict) -> str:
    try:
        since = datetime.fromisoformat(meta["since"])
        desde = datetime.fromisoformat(meta["coverage_from"])
    except (KeyError, TypeError, ValueError):
        return ""
    if desde <= since:
        return ""
    return f"\u23f3 Datos desde las {desde.astimezone(CUBA):%H:%M} (hora de Cuba): el recolector empezo despues.\n"


def _fuentes(meta: dict) -> str:
    nombres = [NOMBRES.get(s, s.capitalize()) for s in meta.get("sources") or NOMBRES]
    return ", ".join(nombres[:-1]) + " y " + nombres[-1] if len(nombres) > 1 else nombres[0]


def armar_texto(resp: dict) -> str:
    meta, items = resp.get("meta") or {}, resp.get("data") or []
    ventana = VENTANAS.get(meta.get("window"), meta.get("window", ""))
    vista = "por exchange" if meta.get("by") == "exchange" else "por moneda"
    cabecera = f"\U0001f4a5 <b>Liquidaciones de futuros</b> \u00b7 {ventana} \u00b7 {vista}\n\n"
    pie = f"\n<i>Fuente: {_fuentes(meta)} (perpetuos)</i>"
    longs = sum(i["long_usd"] for i in items)
    shorts = sum(i["short_usd"] for i in items)
    total = longs + shorts
    aviso = _aviso_cobertura(meta)
    if total <= 0:
        return cabecera + "Sin liquidaciones registradas en esta ventana. Total: $0\n" + aviso + pie
    pct_long = round(100 * longs / total)
    cuadros = round(CUADROS_BARRA * longs / total)
    barra = LONG * cuadros + SHORT * (CUADROS_BARRA - cuadros)
    texto = (f"Total liquidado: <b>{_usd(total)}</b>\n{barra}\n"
             f"{LONG} Longs {pct_long}% \u00b7 {_usd(longs)}\n"
             f"{SHORT} Shorts {100 - pct_long}% \u00b7 {_usd(shorts)}\n\n")
    filas = items if meta.get("by") == "exchange" else items[:FILAS_MONEDAS]
    for i in filas:
        texto += f"\u2022 <b>{html.escape(str(i['key']))}</b> {_usd(i['total_usd'])}"
        texto += f" (longs {round(100 * i['long_usd'] / i['total_usd'])}%)\n" if i["total_usd"] > 0 else "\n"
    return cabecera + texto + "\n" + aviso + pie


def armar_teclado(ventana: str, by: str) -> InlineKeyboardMarkup:
    v = VISTA_CODIGO[by]
    marca = lambda activo, txt: f"\u2705 {txt}" if activo else txt  # noqa: E731
    ventanas = [InlineKeyboardButton(marca(w == ventana, txt), callback_data=f"liq:{w}:{v}")
                for w, txt in VENTANAS.items()]
    vistas = [InlineKeyboardButton(marca(by == "symbol", "Monedas"), callback_data=f"liq:{ventana}:m"),
              InlineKeyboardButton(marca(by == "exchange", "Exchanges"), callback_data=f"liq:{ventana}:e")]
    actualizar = [InlineKeyboardButton("\U0001f504 Actualizar", callback_data=f"liq:{ventana}:{v}")]
    return InlineKeyboardMarkup([ventanas[:3], ventanas[3:], vistas, actualizar])


async def _datos(context, ventana: str, by: str):
    api = context.bot_data.get("api_client")
    return await api.get_liquidations(ventana, by) if api else None


async def liq_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Uso: /liq [ventana] [monedas|exchanges]"""
    parsed = parse_args([a.lower() for a in (context.args or [])])
    if parsed is None:
        await update.message.reply_text(MSG_USO)
        return
    logger.info("\U0001f4a5 /liq %s %s por usuario %s", *parsed, update.effective_user.id)
    resp = await _datos(context, *parsed)
    if resp is None:
        await update.message.reply_text(MSG_ERROR)
        asyncio.create_task(track_command_usage(update, context, "/liq", success=False))
        return
    await update.message.reply_text(
        armar_texto(resp), parse_mode=ParseMode.HTML, reply_markup=armar_teclado(*parsed))
    asyncio.create_task(track_command_usage(update, context, "/liq", success=True))


def _parse_callback(data: str) -> tuple[str, str] | None:
    if data == "liq_open":
        return POR_DEFECTO
    partes = data.split(":")
    if len(partes) == 3 and partes[0] == "liq" and partes[1] in VENTANAS and partes[2] in VISTAS:
        return partes[1], VISTAS[partes[2]]
    return None


async def liq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    """Botones: cambian ventana o vista editando el mismo mensaje."""
    parsed = _parse_callback(data)
    if parsed is None:
        logger.warning("liq callback invalido: %r", data[:40])
        return
    query = update.callback_query
    resp = await _datos(context, *parsed)
    try:
        if resp is None:
            await query.edit_message_text(MSG_ERROR)
            return
        await query.edit_message_text(
            armar_texto(resp), parse_mode=ParseMode.HTML, reply_markup=armar_teclado(*parsed))
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise
