"""/mapa: mapa de calor cripto o forex como imagen + resumen breve (F3).

Un solo punto de registro: una linea en COMANDOS (src/commands.py) y otra en
ROUTE_MAP (callback_router.py). Datos en src/heatmap/data.py, dibujo en
src/heatmap/render.py. El resumen es calculado; el boton "Analisis TASALO IA" agrega un comentario
del modelo en un mensaje aparte (F3-T4).
"""

import asyncio
import html
import logging
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.core import ai_logic
from src.handlers.p import get_crypto_client
from src.heatmap.data import HeatmapError, obtener_acciones, obtener_cripto, obtener_forex
from src.heatmap.render import render_mapa
from src.stats_tracker import track_command_usage

logger = logging.getLogger(__name__)

CUBA = ZoneInfo("America/Havana")
VISTAS = {"cripto_24h": ("cripto", "24h"), "cripto_7d": ("cripto", "7d"), "forex": ("forex", None),
          "acciones": ("acciones", None)}
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
PRINCIPALES = ("BTC", "ETH", "BNB", "XRP", "SOL")
# |variacion ponderada| minima para abrir el caption con el titular "ULTIMA HORA"
UMBRAL_ULTIMA_HORA = {"24h": 5.0, "7d": 10.0}
PERIODO = {"24h": "las últimas 24 horas", "7d": "los últimos 7 días"}
MSG_ERROR = "⚠️ No pude obtener datos de mercado ahora mismo. Intenta de nuevo en unos minutos."
MSG_IA_NO = "⚠️ El análisis con IA no está disponible ahora mismo."
MSG_USO = ("Uso: /mapa [cripto|forex|acciones] [24h|7d]\n"
           "Ejemplos: /mapa, /mapa cripto 7d, /mapa forex, /mapa acciones")

_png: dict = {}  # vista -> (snapshot, bytes): evita re-dibujar mientras el dato no cambie


_ia_cache: dict = {}  # clave -> (snapshot, texto): mismo dato, mismo analisis (cuida el limite de la IA)
_ia_locks: dict = {}


def reset_cache_png() -> None:
    _png.clear()
    _ia_cache.clear()


def parse_vista(data: str):
    """'mapa_cripto_24h' -> ('cripto', '24h'); cualquier otra cosa -> None."""
    if not data or len(data) > 32 or not data.startswith("mapa_"):
        return None
    return VISTAS.get(data[len("mapa_"):])


def _clave(vista) -> str:
    return vista[0] if vista[0] in ("forex", "acciones") else f"cripto_{vista[1]}"


def _vista_desde_args(args):
    if not args:
        return VISTAS["cripto_24h"]
    if args[0] in ("forex", "acciones") and len(args) == 1:
        return VISTAS[args[0]]
    if args[0] == "cripto" and len(args) <= 2 and (len(args) == 1 or args[1] in ("24h", "7d")):
        return VISTAS[f"cripto_{args[1] if len(args) == 2 else '24h'}"]
    return None


def armar_teclado(vista) -> InlineKeyboardMarkup:
    activa = _clave(vista)

    def boton(clave, icono, texto):
        marca = "✅" if clave == activa else icono
        return InlineKeyboardButton(f"{marca} {texto}", callback_data=f"mapa_{clave}")

    return InlineKeyboardMarkup([
        [boton("cripto_24h", "₿", "24 h"), boton("cripto_7d", "₿", "7 d"), boton("forex", "💱", "Forex")],
        [boton("acciones", "📈", "Acciones S&P 500")],
        [InlineKeyboardButton("🔄 Actualizar", callback_data=f"mapa_{activa}")],
        [InlineKeyboardButton("🧠 Análisis TASALO IA", callback_data=f"mapa_ia_{activa}")],
    ])


def _bloque(titulo, emoji, celdas, n=3):
    """Seccion del caption: titulo en negrita y una linea por moneda (vacia si no hay celdas)."""
    if not celdas:
        return []
    return ["", f"{emoji} <b>{titulo}</b>"] + [
        f"• {html.escape(c.simbolo)} {c.variacion:+.2f}%" for c in celdas[:n]
    ]


def _monto(v: float) -> str:
    """Monto en USD con escala del espanol (mil millones = 1e9, billon = 1e12)."""
    v = abs(v)
    if v >= 1e12:
        return f"${v / 1e12:,.1f} billones"
    if v >= 1e9:
        return f"${v / 1e9:,.1f} mil millones"
    return f"${v / 1e6:,.1f} millones"


def _delta_capital(celdas) -> float:
    """Cambio estimado del capital (USD): cap actual - cap previa, con previa = cap / (1 + var)."""
    return sum(c.peso - c.peso / (1 + c.variacion / 100) for c in celdas if c.variacion > -100)


def _principales(celdas):
    por = {c.simbolo: c for c in celdas}
    lineas = []
    for s in PRINCIPALES:
        c = por.get(s)
        if c is None:
            continue
        v = round(c.variacion, 2)
        txt = "sin cambios" if v == 0 else f"{'subió' if v > 0 else 'cayó'} {abs(v):.2f}%"
        lineas.append(f"• ${html.escape(s)} {txt}")
    return ["", "📌 <b>Principales</b>"] + lineas if lineas else []


def _fecha_larga(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return str(iso)
    return f"{d.day} {MESES[d.month - 1]} {d.year}"


def armar_caption(vista, snap, ahora) -> str:
    """Caption en HTML (parse_mode=HTML): los simbolos vienen de un proveedor, se escapan."""
    con = [c for c in snap.celdas if c.variacion is not None]
    suben = sorted((c for c in con if c.variacion > 0), key=lambda c: -c.variacion)
    bajan = sorted((c for c in con if c.variacion < 0), key=lambda c: c.variacion)
    lineas = []
    if snap.obsoleto_min is not None:
        lineas += [f"⚠️ <i>Datos de hace {snap.obsoleto_min} min (no se pudo actualizar).</i>", ""]
    if vista[0] == "cripto":
        total = sum(c.peso for c in con)
        pond = sum(c.peso * c.variacion for c in con) / total if total else 0.0
        ventana = vista[1].replace("h", " h").replace("d", " d")
        delta = _delta_capital(con)
        lineas.append(f"🗺 <b>Mapa de calor cripto · {ventana}</b>")
        anomalo = any(c.variacion <= -100 for c in con)  # el delta no es calculable: sin titular
        titular = abs(pond) >= UMBRAL_ULTIMA_HORA[vista[1]] and not anomalo
        if titular:
            verbo = "añadidos al" if delta >= 0 else "borrados del"
            lineas.append(
                f"🚨 <b>ÚLTIMA HORA</b>: {_monto(delta)} {verbo} capital del top 100 "
                f"en {PERIODO[vista[1]]}."
            )
        lineas.append(f"Mercado <b>{pond:+.2f}%</b> · {len(suben)} suben · {len(bajan)} bajan")
        if not titular:  # con titular el monto ya esta arriba
            lineas.append(f"Capital del top 100: <b>{'+' if delta >= 0 else '-'}{_monto(delta)}</b>")
        lineas.append("<i>Ponderado por capitalización</i>")
        lineas += _principales(con)
        lineas += _bloque("Mayores subas", "🟢", suben) + _bloque("Mayores bajas", "🔴", bajan)
    elif vista[0] == "acciones":
        total = sum(c.peso for c in con)
        pond = sum(c.peso * c.variacion for c in con) / total if total else 0.0
        lineas += [
            "\U0001F4C8 <b>Mapa de calor S&amp;P 500</b> \u00b7 mayores empresas",
            f"Mercado <b>{pond:+.2f}%</b> \u00b7 {len(suben)} suben \u00b7 {len(bajan)} bajan",
            "<i>Ponderado por capitalizaci\u00f3n \u00b7 sesi\u00f3n m\u00e1s reciente</i>",
        ]
        lineas += _bloque("Mayores subas", "\U0001F7E2", suben) + _bloque("Mayores bajas", "\U0001F534", bajan)
    else:
        nota = "" if snap.fecha_dato == ahora.date().isoformat() else " <i>(último día hábil publicado)</i>"
        lineas += [
            "🗺 <b>Mapa de calor forex</b> · monedas frente al USD",
            f"Referencia BCE del {_fecha_larga(snap.fecha_dato)}{nota}",
        ]
        lineas += _bloque("Más fuertes", "🟢", suben) + _bloque("Más débiles", "🔴", bajan)
    return "\n".join(lineas)


def _textos_imagen(vista, ahora):
    gen = f"{ahora.day} {MESES[ahora.month - 1]} {ahora.year} {ahora:%H:%M} (Cuba)"
    if vista[0] == "cripto":
        ventana = vista[1].replace("h", " h").replace("d", " d")
        return (f"Mapa de calor cripto · {ventana}",
                f"Tamaño = capitalización · color = variación en {ventana}", gen)
    if vista[0] == "acciones":
        return ("Mapa de calor S&P 500 \u00b7 mayores empresas",
                "Tama\u00f1o = capitalizaci\u00f3n \u00b7 color = variaci\u00f3n del d\u00eda", gen)
    return ("Mapa de calor forex · monedas frente al USD",
            "Tamaño igual · color = variación diaria (referencia BCE)", gen)


async def _snapshot(vista):
    """Datos de la vista (con su cache de data.py). Lanza HeatmapError si no hay datos."""
    if vista[0] == "cripto":
        return await obtener_cripto(get_crypto_client()._cmc_get, vista[1])
    if vista[0] == "acciones":
        return await obtener_acciones()
    return await obtener_forex()


async def _preparar(vista):
    """Devuelve (png, caption). Lanza HeatmapError si no hay datos."""
    snap = await _snapshot(vista)
    ahora = datetime.now(CUBA)
    clave = _clave(vista)
    previo = _png.get(clave)
    if previo and previo[0] == snap:
        png = previo[1]
    else:
        titulo, subtitulo, generado = _textos_imagen(vista, ahora)
        png = await asyncio.to_thread(
            render_mapa, list(snap.celdas),
            titulo=titulo, subtitulo=subtitulo, fuente=snap.fuente, generado=generado, tope=snap.tope,
        )
        _png[clave] = (snap, png)
    return png, armar_caption(vista, snap, ahora)


def _limpio(simbolo) -> str:
    """Simbolo de un proveedor externo: solo caracteres inocuos y corto."""
    return re.sub(r"[^A-Za-z0-9.&-]", "", str(simbolo))[:12]


def contexto_ia(vista, snap) -> str:
    """Resumen de DATOS PUBLICOS de mercado para TASALO IA: solo simbolos y cifras, nada de usuarios."""
    con = [c for c in snap.celdas if c.variacion is not None]
    total = sum(c.peso for c in con)
    pond = sum(c.peso * c.variacion for c in con) / total if total else 0.0
    suben = sorted((c for c in con if c.variacion > 0), key=lambda c: -c.variacion)
    bajan = sorted((c for c in con if c.variacion < 0), key=lambda c: c.variacion)
    if vista[0] == "cripto":
        titulo = f"Cripto, top 100 por capitalización, variación en {vista[1]}"
    elif vista[0] == "acciones":
        titulo = "Acciones del S&P 500, mayores empresas, variación de la sesión"
    else:
        titulo = "Forex, monedas frente al USD, variación diaria (referencia BCE)"
    lineas = [titulo, f"Variación ponderada del mercado: {pond:+.2f}%",
              f"Suben: {len(suben)}; bajan: {len(bajan)}"]
    if vista[0] == "cripto":
        if not any(c.variacion <= -100 for c in con):
            lineas.append(f"Cambio estimado del capital del top 100: {_delta_capital(con) / 1e9:+,.1f} mil millones de USD")
        por = {c.simbolo: c for c in con}
        lineas.append("Principales: " + ", ".join(
            f"{s} {por[s].variacion:+.2f}%" for s in PRINCIPALES if s in por))
    lineas.append("Mayores subas: " + ", ".join(f"{_limpio(c.simbolo)} {c.variacion:+.2f}%" for c in suben[:5]))
    lineas.append("Mayores bajas: " + ", ".join(f"{_limpio(c.simbolo)} {c.variacion:+.2f}%" for c in bajan[:5]))
    if snap.obsoleto_min is not None:
        lineas.append(f"Nota: datos de hace {snap.obsoleto_min} min.")
    if snap.fecha_dato:
        lineas.append(f"Fecha del dato: {snap.fecha_dato}")
    return "\n".join(lineas)


async def _analisis(vista) -> str:
    """Analisis de TASALO IA para la vista; reutiliza el anterior si el dato no cambio."""
    snap = await _snapshot(vista)
    clave = _clave(vista)
    previo = _ia_cache.get(clave)
    if previo and previo[0] == snap:
        return previo[1]
    async with _ia_locks.setdefault(clave, asyncio.Lock()):
        previo = _ia_cache.get(clave)
        if previo and previo[0] == snap:
            return previo[1]
        texto = await ai_logic.get_mapa_analysis(contexto_ia(vista, snap))
        if not texto.startswith("⚠️"):  # un error no se guarda: el siguiente toque reintenta
            _ia_cache[clave] = (snap, texto)
        return texto


async def _ia_callback(query) -> None:
    """Boton "Analisis TASALO IA": envia el comentario como mensaje nuevo bajo el mapa."""
    vista = VISTAS.get(query.data[len("mapa_ia_"):]) if len(query.data) <= 32 else None
    if vista is None:
        logger.warning("mapa ia callback invalido: %r", query.data[:40])
        return
    if not ai_logic._ia_configurada():
        await query.message.reply_text(MSG_IA_NO)
        return
    await query.message.chat.send_action("typing")
    try:
        texto = await _analisis(vista)
    except HeatmapError:
        await query.message.reply_text(MSG_ERROR)
        return
    try:
        await query.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)
    except BadRequest:  # Markdown del modelo mal formado: se reenvia como texto plano
        await query.message.reply_text(texto)


async def mapa_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Uso: /mapa [cripto|forex] [24h|7d]"""
    vista = _vista_desde_args([a.lower() for a in (context.args or [])])
    if vista is None:
        await update.message.reply_text(MSG_USO)
        return
    logger.info("🗺 /mapa %s por usuario %d", _clave(vista), update.effective_user.id)
    await update.message.reply_chat_action("upload_photo")
    try:
        png, caption = await _preparar(vista)
    except HeatmapError:
        logger.warning("/mapa %s sin datos", _clave(vista))
        await update.message.reply_text(MSG_ERROR)
        asyncio.create_task(track_command_usage(update, context, "/mapa", success=False))
        return
    await update.message.reply_photo(
        photo=png, caption=caption, parse_mode=ParseMode.HTML, reply_markup=armar_teclado(vista)
    )
    asyncio.create_task(track_command_usage(update, context, "/mapa", success=True))


async def mapa_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Botones del mapa: cambia de vista o actualiza editando la misma imagen."""
    query = update.callback_query
    if query.data.startswith("mapa_ia_"):
        await _ia_callback(query)
        return
    vista = parse_vista(query.data)
    if vista is None:
        logger.warning("mapa callback invalido: %r", query.data[:40])
        return
    try:
        png, caption = await _preparar(vista)
    except HeatmapError:
        await query.message.reply_text(MSG_ERROR)
        return
    try:
        await query.edit_message_media(
            media=InputMediaPhoto(media=png, caption=caption, parse_mode=ParseMode.HTML),
            reply_markup=armar_teclado(vista),
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise
        try:
            await query.answer("Ya está actualizado")
        except BadRequest:
            pass  # el router ya respondio a este callback
