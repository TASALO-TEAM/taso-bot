"""/mapa: mapa de calor cripto o forex como imagen + resumen breve (F3).

Un solo punto de registro: una linea en COMANDOS (src/commands.py) y otra en
ROUTE_MAP (callback_router.py). Datos en src/heatmap/data.py, dibujo en
src/heatmap/render.py. El resumen es calculado (sin IA); TASALO IA lo ampliara
cuando F5 defina su contrato (F3-T4).
"""

import asyncio
import html
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.handlers.p import get_crypto_client
from src.heatmap.data import HeatmapError, obtener_cripto, obtener_forex
from src.heatmap.render import render_mapa
from src.stats_tracker import track_command_usage

logger = logging.getLogger(__name__)

CUBA = ZoneInfo("America/Havana")
VISTAS = {"cripto_24h": ("cripto", "24h"), "cripto_7d": ("cripto", "7d"), "forex": ("forex", None)}
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
MSG_ERROR = "⚠️ No pude obtener datos de mercado ahora mismo. Intenta de nuevo en unos minutos."
MSG_USO = "Uso: /mapa [cripto|forex] [24h|7d]\nEjemplos: /mapa, /mapa cripto 7d, /mapa forex"

_png: dict = {}  # vista -> (snapshot, bytes): evita re-dibujar mientras el dato no cambie


def reset_cache_png() -> None:
    _png.clear()


def parse_vista(data: str):
    """'mapa_cripto_24h' -> ('cripto', '24h'); cualquier otra cosa -> None."""
    if not data or len(data) > 32 or not data.startswith("mapa_"):
        return None
    return VISTAS.get(data[len("mapa_"):])


def _clave(vista) -> str:
    return "forex" if vista[0] == "forex" else f"cripto_{vista[1]}"


def _vista_desde_args(args):
    if not args:
        return VISTAS["cripto_24h"]
    if args[0] == "forex" and len(args) == 1:
        return VISTAS["forex"]
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
        [InlineKeyboardButton("🔄 Actualizar", callback_data=f"mapa_{activa}")],
    ])


def _bloque(titulo, emoji, celdas, n=3):
    """Seccion del caption: titulo en negrita y una linea por moneda (vacia si no hay celdas)."""
    if not celdas:
        return []
    return ["", f"{emoji} <b>{titulo}</b>"] + [
        f"• {html.escape(c.simbolo)} {c.variacion:+.2f}%" for c in celdas[:n]
    ]


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
        lineas += [
            f"🗺 <b>Mapa de calor cripto · {ventana}</b>",
            f"Mercado <b>{pond:+.2f}%</b> · {len(suben)} suben · {len(bajan)} bajan",
            "<i>Ponderado por capitalización</i>",
        ]
        lineas += _bloque("Mayores subas", "🟢", suben) + _bloque("Mayores bajas", "🔴", bajan)
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
    return ("Mapa de calor forex · monedas frente al USD",
            "Tamaño igual · color = variación diaria (referencia BCE)", gen)


async def _preparar(vista):
    """Devuelve (png, caption). Lanza HeatmapError si no hay datos."""
    if vista[0] == "cripto":
        snap = await obtener_cripto(get_crypto_client()._cmc_get, vista[1])
    else:
        snap = await obtener_forex()
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
