"""Menu principal y submenus por botones (F6-T4).

Pantallas puras (`render`, sin red) + un handler que edita el mensaje en el
sitio. Se registra por el contrato de F6-T2 (una linea en COMANDOS, namespace
`menu`). Los botones que ya tenian flujo propio (`start_*`) se reutilizan tal
cual; el resto abre una ficha del comando. Los flujos con argumentos por
botones son F6-T5.

callback_data (v2, F6-T3): `menu:<seccion>` y `menu:cmd:<comando>:<seccion>`.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import BadRequest

from src import callback_data as cd
from src.config import settings

logger = logging.getLogger(__name__)

# Botones `start_*` existentes (flujo propio) y el comando que cubren.
ACCESO_DIRECTO = {
    "start_tasalo": "tasalo",
    "start_toque": "toque",
    "start_bcc": "bcc",
    "start_spl": "spl",
    "start_p_help": "p",
    "start_ta_help": "ta",
    "start_alert_help": "alert",
    "pick:graf": "graf",
}
_ETIQUETA_DIRECTA = {
    "pick:graf": "\U0001f4c8 Gr\u00e1fico /graf",
    "start_tasalo": "🌐 Todas las tasas",
    "start_toque": "📈 El Toque",
    "start_bcc": "🏛 BCC",
    "start_spl": "🔦 Spotlight",
    "start_p_help": "💲 Precio /p",
    "start_ta_help": "📊 Análisis /ta",
    "start_alert_help": "🔔 Alertas /alert",
}

# seccion: (etiqueta, texto, hojas). Una hoja es un `start_*` (acceso directo)
# o el nombre de un comando (abre su ficha).
SECCIONES = {
    "tasas": ("💱 Tasas", "Tasas de cambio de Cuba.",
              ("start_tasalo", "start_toque", "start_bcc", "qp", "toqueimg", "y")),
    "cripto": ("🪙 Cripto", "Precios y resúmenes del mercado cripto.",
               ("start_spl", "start_p_help", "mk", "tspl")),
    "analisis": ("📊 Análisis", "Análisis técnico y gráficos.",
                 ("start_ta_help", "pick:graf")),
    "alertas": ("🔔 Alertas", "Avisos de precio.", ("start_alert_help",)),
    "noticias": ("📰 Noticias", "Noticias del mercado.", ("news",)),
    "mercado": ("🗺 Mercado", "Vista general del mercado.", ("mapa",)),
    "ayuda": ("❓ Ayuda", "Ayuda y contacto con el equipo.", ("help", "tkt")),
}
_ADMIN = ("🛠 Admin", "Comandos de administración. Escríbelos en el chat.")

# Comandos que corren sin argumentos y para cualquier usuario: su ficha ofrece
# "Ejecutar". Lista cerrada a proposito (nada de admin ni de flujos con texto).
EJECUTABLES = ("qp", "news", "mapa", "tspl", "toqueimg", "help")

_TEXTO_CATEGORIAS = "\u2630 Categor\u00edas\n\nElige una categor\u00eda."


def _es_admin(user_id: int) -> bool:
    return user_id in settings.get_admin_chat_ids_list()


def _cmds() -> dict:
    from src.commands import COMANDOS

    return {c.name: c for c in COMANDOS}


def _seccion(sec: str, es_admin: bool):
    """(etiqueta, texto, hojas) de la seccion, o None si no existe o no es visible."""
    if sec == "admin":
        if not es_admin:
            return None
        return (*_ADMIN, tuple(n for n, c in _cmds().items() if c.admin))
    return SECCIONES.get(sec)


def _btn(texto: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(texto, callback_data=data)


def _fila_nav(sec: str | None = None) -> list[InlineKeyboardButton]:
    fila = [_btn("◀ Atrás", cd.build("menu", sec))] if sec else []
    return [*fila, _btn("🏠 Inicio", cd.build("menu", "home"))]


def _categorias(es_admin: bool):

    botones = [_btn(v[0], cd.build("menu", k)) for k, v in SECCIONES.items()]
    if es_admin:
        botones.append(_btn(_ADMIN[0], cd.build("menu", "admin")))
    filas = [botones[i:i + 2] for i in range(0, len(botones), 2)]
    filas.append(_fila_nav())
    return _TEXTO_CATEGORIAS, InlineKeyboardMarkup(filas)


def _pantalla_seccion(sec: str, es_admin: bool):
    from src.commands import menu_entries

    etiqueta, texto, hojas = _seccion(sec, es_admin)
    filas = []
    for h in hojas:
        if h in ACCESO_DIRECTO:
            filas.append([_btn(_ETIQUETA_DIRECTA[h], h)])
        else:
            filas.append([_btn(f"/{h} — {_cmds()[h].descripcion}"[:60], cd.build("menu", "cmd", h, sec))])
    # Modulos registrados por el contrato (F6-T2): su boton abre `<ns>_open`.
    for e in menu_entries(sec, es_admin):
        filas.append([_btn(e.label, e.callback_data)])
    filas.append(_fila_nav("all"))
    return f"{etiqueta}\n\n{texto}", InlineKeyboardMarkup(filas)


def _pantalla_cmd(args: tuple, es_admin: bool):
    if len(args) != 2:
        return None
    nombre, sec = args
    s = _seccion(sec, es_admin)
    if s is None or nombre not in s[2] or nombre in ACCESO_DIRECTO:
        return None
    c = _cmds().get(nombre)
    if c is None:
        return None
    if nombre in EJECUTABLES and not c.admin:
        texto = f"/{nombre} — {c.descripcion}\n\nToca Ejecutar o escríbelo en el chat."
        filas = [[_btn("▶ Ejecutar", cd.build("menu", "run", nombre))], _fila_nav(sec)]
    else:
        texto = f"/{nombre} — {c.descripcion}\n\nEscríbelo en el chat para usarlo."
        filas = [_fila_nav(sec)]
    return texto, InlineKeyboardMarkup(filas)


def _resolve(args: tuple, es_admin: bool, user=None):
    """(texto, teclado, es_html). Lo desconocido o prohibido cae en la bienvenida."""
    if args and args[0] == "all":
        return (*_categorias(es_admin), False)
    r = None
    if args and args[0] == "cmd":
        r = _pantalla_cmd(args[1:], es_admin)
    elif args and _seccion(args[0], es_admin) is not None:
        r = _pantalla_seccion(args[0], es_admin)
    if r:
        return (*r, False)
    from src.handlers.start import build_start_keyboard, build_welcome_text

    return build_welcome_text(user), build_start_keyboard(), True


def render(args: tuple, es_admin: bool, user=None):
    """(texto, teclado) de la pantalla `args`."""
    return _resolve(args, es_admin, user)[:2]


class _UpdateEquivalente:
    """Lo que leen los handlers de EJECUTABLES, como si el usuario escribiera el comando."""

    callback_query = None

    def __init__(self, message, user):
        self.message = self.effective_message = message
        self.effective_user = user
        self.effective_chat = message.chat


async def _ejecutar(query, context, nombre: str) -> bool:
    """Corre el handler real de `nombre`. False si no esta permitido (cae en el inicio)."""
    c = _cmds().get(nombre)
    if nombre not in EJECUTABLES or c is None or c.admin:
        return False
    context.args = []
    try:
        await c.handler(_UpdateEquivalente(query.message, query.from_user), context)
    except Exception:
        logger.exception("menu: fallo al ejecutar /%s", nombre)
        await query.message.reply_text(f"⚠️ No pude ejecutar /{nombre} ahora. Inténtalo de nuevo en un momento.")
    return True


async def menu_callback(update, context, callback_data: str) -> None:
    """Navega el menu editando el mensaje; si no es editable, envia uno nuevo."""
    query = update.callback_query
    parsed = cd.parse_v2(callback_data)
    if parsed and len(parsed[1]) == 2 and parsed[1][0] == "run":
        if await _ejecutar(query, context, parsed[1][1]):
            return
    texto, markup, html = _resolve(parsed[1] if parsed else (), _es_admin(query.from_user.id), query.from_user)
    modo = "HTML" if html else None
    try:
        await query.edit_message_text(texto, reply_markup=markup, parse_mode=modo)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        logger.info("menu: mensaje no editable (%s); se envia uno nuevo", e)
        await query.message.reply_text(texto, reply_markup=markup, parse_mode=modo)
