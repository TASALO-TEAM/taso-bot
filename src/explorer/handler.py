"""Explorador de direcciones, hashes y usuarios de Hive (F4-T7).

Tres entradas y una sola logica: /explorar, el boton del menu (Mercado) y el texto
libre en privado. Registro en dos puntos unicos: `COMANDOS` y `register(app)`.
La red vive en `sources`, el texto en `present` y la clasificacion en `classify`.
"""

import asyncio
import logging
import math
import time
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import MessageHandler, filters

from src import callback_data as cd
from src.cache import cache
from src.core import ai_logic
from src.explorer import analisis, sources
from src.explorer.classify import clasificar, etiqueta_log
from src.explorer.guard import UserLimiter
from src.explorer.present import formatear, mensaje_error

logger = logging.getLogger(__name__)

LIMITER = UserLimiter(max_calls=5, window=60.0)
IA_LIMITER = UserLimiter(max_calls=3, window=60.0)   # solo cuenta llamadas reales a la IA
_IA_CTX = "explorer_ia"   # user_data: {"t", "n", "ctx", "txt"} de la ultima consulta analizable
_IA_TTL = 900.0
_IA_CADUCO = "Esa consulta ya caduc\u00f3. Vuelve a consultarla para pedir el an\u00e1lisis."
_IA_NO = "\u26a0\ufe0f El an\u00e1lisis con IA no est\u00e1 disponible ahora mismo."
_ESPERA = "explorer_waiting"   # user_data: instante (monotonic) en que se pidio la entrada
_ESPERA_TTL = 120.0
# Flags de otros flujos que esperan texto libre: si hay uno, el explorador no actua.
_OTROS_FLUJOS = ("waiting_for_time", "tkt_awaiting", "awaiting_tspl_hour", "awaiting_year_hour")
_CONSULTABLES = ("btc_address", "btc_tx", "hive_account", "hive_tx", "evm_address", "evm_tx")
_PRECIO_KEY = "explorer:btc_usd"
_PRECIO_TTL = 60
_OPCIONAL_TIMEOUT = 6.0
_PEDIR = (
    "\U0001f50e Explorador\n\n"
    "Env\u00edame una direcci\u00f3n o transacci\u00f3n de Bitcoin o EVM (0x...), un usuario de Hive (@usuario) "
    "o una factura Lightning, y te muestro lo que hay en la cadena."
)


async def _precio_btc():
    """(usd_por_btc, fuente, hora) de CoinMarketCap, o None.

    Sin hora valida no hay precio: el USD solo se muestra con fuente y hora.
    """
    hit = cache.get(_PRECIO_KEY, ttl=_PRECIO_TTL)
    if hit:
        return hit
    from src.handlers.p import get_crypto_client

    datos = await get_crypto_client()._get_from_cmc(["BTC"])
    try:
        usd = datos["BTC"]["quote"]["USD"]
        precio = float(usd["price"])
        hora = datetime.fromisoformat(usd["last_updated"].replace("Z", "+00:00")).astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if not math.isfinite(precio) or precio <= 0:
        return None
    resultado = (precio, "CoinMarketCap", hora.strftime("%H:%M UTC"))
    cache.set(_PRECIO_KEY, resultado)
    return resultado


async def _opcional(coro):
    """Dato secundario: si falla o tarda se omite, sin tumbar la consulta."""
    try:
        return await asyncio.wait_for(coro, _OPCIONAL_TIMEOUT)
    except Exception as e:
        logger.debug("explorer: dato opcional omitido (%s)", type(e).__name__)
        return None


async def _consultar_real(e):
    """-> (datos, txs, precio). La fuente principal manda: si falla, se propaga ExplorerError."""
    if e.tipo == "btc_address":
        datos = await sources.btc_address(e.valor)
        txs, precio = await asyncio.gather(
            _opcional(sources.btc_address_txs(e.valor)), _opcional(_precio_btc())
        )
        return datos, txs, precio
    if e.tipo == "btc_tx":
        datos = await sources.btc_tx(e.valor)
        return datos, None, await _opcional(_precio_btc())
    if e.tipo == "hive_account":
        return await sources.hive_cuenta(e.valor), None, None
    if e.tipo == "hive_tx":
        return await sources.hive_tx(e.valor), None, None
    if e.tipo == "evm_address":
        return await sources.evm_address(e.valor), None, None
    if e.tipo == "evm_tx":
        return await sources.evm_tx(e.valor), None, None
    raise sources.ExplorerError("no_encontrado")


_consultar = _consultar_real   # los tests sustituyen este nombre


async def _responder(msg, user_id, e, user_data=None) -> None:
    """Consulta (si el tipo se consulta) y contesta. Solo mensajes fijos ante errores."""
    markup = None
    if e.tipo not in _CONSULTABLES:
        texto = formatear(e)   # LN se decodifica local; LNURL/address solo se reconocen
    else:
        permitido, _ = LIMITER.allow(user_id)
        if not permitido:
            await msg.reply_text(mensaje_error("limite"))
            return
        await msg.reply_chat_action("typing")
        try:
            datos, txs, precio = await _consultar(e)
        except sources.ExplorerError as ex:
            await msg.reply_text(mensaje_error(ex.codigo))
            return
        except Exception as ex:
            # Sin traza ni str(ex): podrian traer la entrada completa dentro de una URL.
            logger.warning("explorer: fallo inesperado %s en %s", type(ex).__name__, etiqueta_log(e))
            await msg.reply_text(mensaje_error("generico"))
            return
        logger.info("explorer: consulta %s", etiqueta_log(e))
        texto = formatear(e, datos, txs=txs, precio=precio)
        markup = _boton_ia(user_data, e, datos, txs, precio)
    await msg.reply_text(texto, parse_mode="HTML", disable_web_page_preview=True, reply_markup=markup)


def _esperando(user_data) -> bool:
    t = user_data.get(_ESPERA)
    if t is None:
        return False
    if time.monotonic() - t > _ESPERA_TTL:
        user_data.pop(_ESPERA, None)
        return False
    return True


async def explorer_text(update, context) -> None:
    """Texto libre en privado. Calla ante lo que no reconoce, salvo que se haya pedido la entrada."""
    msg = update.message
    if not msg or not msg.text or any(context.user_data.get(f) for f in _OTROS_FLUJOS):
        return
    esperando = _esperando(context.user_data)
    e = clasificar(msg.text, nombre_hive_suelto=esperando)
    if esperando:
        context.user_data.pop(_ESPERA, None)   # se consume: un solo mensaje por peticion
    if e.tipo == "desconocido" and not esperando:
        return
    await _responder(msg, update.effective_user.id, e, context.user_data)


async def explorar_command(update, context) -> None:
    msg = update.message
    if not context.args:
        context.user_data[_ESPERA] = time.monotonic()
        await msg.reply_text(_PEDIR)
        return
    e = clasificar(" ".join(context.args), nombre_hive_suelto=True)
    await _responder(msg, update.effective_user.id, e, context.user_data)


async def explorer_callback(update, context, callback_data: str) -> None:
    """Boton del menu (`explorer_open`): pide la entrada editando el mismo mensaje."""
    query = update.callback_query
    if callback_data.startswith("explorer:ia"):
        n = _ia_nonce(callback_data)
        if n is None:
            logger.warning("explorer: callback de analisis invalido")
            return
        await _ia_callback(update, context, n)
        return
    context.user_data[_ESPERA] = time.monotonic()
    teclado = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("\u25c0 Atr\u00e1s", callback_data=cd.build("menu", "mercado")),
            InlineKeyboardButton("\U0001f3e0 Inicio", callback_data=cd.build("menu", "home")),
        ]]
    )
    try:
        await query.edit_message_text(_PEDIR, reply_markup=teclado)
    except BadRequest as ex:
        if "message is not modified" in str(ex).lower():
            return
        logger.info("explorer: mensaje no editable (%s); se envia uno nuevo", ex)
        await query.message.reply_text(_PEDIR, reply_markup=teclado)


def _boton_ia(user_data, e, datos, txs, precio):
    """Boton de analisis bajo el resultado. El contexto agregado queda en user_data (nunca en
    callback_data); el numero del boton evita que uno viejo analice otra consulta."""
    if user_data is None or not ai_logic._ia_configurada():
        return None
    ctx = analisis.contexto(e, datos, txs, precio)
    if not ctx:
        user_data.pop(_IA_CTX, None)
        return None
    prev = user_data.get(_IA_CTX)
    n = (prev["n"] + 1) % 100 if prev else 1
    user_data[_IA_CTX] = {"t": time.monotonic(), "n": n, "ctx": ctx, "txt": None}
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("\U0001f916 An\u00e1lisis TASALO IA", callback_data=cd.build("explorer", "ia", str(n)))]]
    )


def _ia_nonce(data: str):
    p = data.split(":")
    if len(p) == 3 and p[0] == "explorer" and p[1] == "ia" and p[2].isascii() and p[2].isdigit():
        return int(p[2])
    return None


async def _ia_callback(update, context, n: int) -> None:
    """Boton "Analisis TASALO IA": responde con un mensaje nuevo bajo el resultado."""
    query = update.callback_query
    msg = query.message
    ent = context.user_data.get(_IA_CTX)
    if not ent or ent["n"] != n or time.monotonic() - ent["t"] > _IA_TTL:
        await msg.reply_text(_IA_CADUCO)
        return
    texto = ent.get("txt")
    if texto is None:
        if not ai_logic._ia_configurada():
            await msg.reply_text(_IA_NO)
            return
        permitido, _ = IA_LIMITER.allow(query.from_user.id)
        if not permitido:
            await msg.reply_text(mensaje_error("limite"))
            return
        await msg.chat.send_action("typing")
        texto = await ai_logic.get_explorer_analysis(ent["ctx"])
        if not texto.startswith("\u26a0"):   # un error no se guarda: el siguiente toque reintenta
            ent["txt"] = texto
    try:
        await msg.reply_text(texto, parse_mode="Markdown")
    except BadRequest:   # Markdown del modelo mal formado: se reenvia como texto plano
        await msg.reply_text(texto)


def register(app) -> None:
    """Texto libre solo en privado. group=-1: va antes que los demas flujos de texto,
    que no se ven afectados porque el explorador se salta cualquier flag pendiente."""
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, explorer_text),
        group=-1,
    )
