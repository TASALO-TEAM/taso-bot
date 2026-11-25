"""Registro único de comandos del bot.

Una sola lista (COMANDOS) alimenta dos cosas:
- los CommandHandler de la Application (register_commands)
- el menú "/" de Telegram (publish_menu, vía set_my_commands)

Para añadir un comando: importar su handler y sumar una línea a COMANDOS.
Los comandos admin salen en el menú solo para los ids de ADMIN_CHAT_IDS.
Los alias se registran como handler pero no aparecen en el menú.
"""

import importlib
import logging
from dataclasses import dataclass
from typing import Callable

from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.ext import Application, CommandHandler

from src.config import settings
from src.explorer.handler import explorar_command, explorer_callback
from src.handlers.admin import health_check, refresh_command, status_command
from src.handlers.ads import ads_command
from src.handlers.alert import alert_command
from src.handlers.db import db_command
from src.handlers.help import help_command
from src.handlers.logs import log_command
from src.handlers.ms import ms_command
from src.handlers.msapp import msapp_command
from src.handlers.news import news_command
from src.handlers.p import p_command
from src.handlers.privacidad import (
    privacidad_callback,
    privacidad_command,
    silencio_callback,
    silencio_command,
)
from src.handlers.qp import qp_command
from src.handlers.spl import spl_command
from src.handlers.start import start_command
from src.handlers.tasalo import bcc_command, tasalo_command, toque_command
from src.handlers.tkt import tkt_command
from src.handlers.toqueimg import toqueimg_command
from src.handlers.tspl import tspl_command
from src.handlers.y import y_command
from src.ia_admin import ia_callback, ia_command
from src.menu import menu_callback
from src.pick import pick_callback

logger = logging.getLogger(__name__)


def _lazy(modulo: str, nombre: str) -> Callable:
    """Handler que importa `modulo` en la primera llamada.

    ta/trading cargan pandas + numba + matplotlib (~140 MB de RSS): solo se
    pagan cuando alguien usa el comando.
    shortcut: el primer import bloquea el loop 1-3 s, una vez por proceso.
    """

    async def handler(update, context):
        return await getattr(importlib.import_module(modulo), nombre)(update, context)

    handler.__name__ = nombre
    return handler


@dataclass(frozen=True)
class Cmd:
    name: str
    handler: Callable
    descripcion: str  # 1-256 caracteres (límite de Telegram)
    admin: bool = False
    alias: tuple[str, ...] = ()
    # Contrato de extension (F6-T2): con `callback` el comando atiende sus
    # propios botones, sin tocar callback_router.py. Firma:
    # async (update, context, callback_data). `namespaces` por defecto es
    # (name,). `menu=(seccion, etiqueta)` lo lista en el menu principal; su
    # boton abre `<namespace>_open`.
    callback: Callable | None = None
    namespaces: tuple[str, ...] = ()
    menu: tuple[str, str] | None = None

    def rutas(self) -> tuple[str, ...]:
        if self.callback is None:
            return ()
        return self.namespaces or (self.name,)


@dataclass(frozen=True)
class MenuEntry:
    label: str
    callback_data: str


COMANDOS: tuple[Cmd, ...] = (
    # Públicos (el orden es el del menú)
    Cmd("start", start_command, "Menú principal", callback=menu_callback, namespaces=("menu",)),
    Cmd("help", help_command, "Ayuda y lista de comandos", alias=("ayuda",)),
    Cmd("tasalo", tasalo_command, "Todas las tasas de cambio"),
    Cmd("toque", toque_command, "Tasas de El Toque"),
    Cmd("bcc", bcc_command, "Tasas del Banco Central de Cuba"),
    Cmd("qp", qp_command, "Tasas P2P de QvaPay"),
    Cmd("toqueimg", toqueimg_command, "Imagen diaria de El Toque"),
    Cmd("y", y_command, "Estado del año"),
    # `pick` (F6-T5): selectores por botones de /p, /ta y /graf.
    Cmd("p", p_command, "Precio de criptomonedas", callback=pick_callback, namespaces=("pick",)),
    Cmd("ta", _lazy("src.handlers.ta", "ta_command"), "Análisis técnico"),
    Cmd("graf", _lazy("src.handlers.trading", "graf_command"), "Gráfico con indicadores"),
    Cmd("mk", _lazy("src.handlers.trading", "mk_command"), "Resumen del mercado"),
    Cmd("alert", alert_command, "Alertas de precio"),
    Cmd("mapa", _lazy("src.handlers.mapa", "mapa_command"), "Mapa de calor: cripto, forex, acciones e índices"),
    Cmd("explorar", explorar_command, "Explorador de direcciones, hashes y usuarios de Hive",
        callback=explorer_callback, namespaces=("explorer",), menu=("mercado", "\U0001f50e Explorador")),
    Cmd("spl", spl_command, "Spotlight del mercado"),
    Cmd("tspl", tspl_command, "TASALO Spotlight completo"),
    Cmd("news", news_command, "Noticias cripto"),
    Cmd("tkt", tkt_command, "Contactar a los administradores"),
    Cmd("privacidad", privacidad_command, "Borrar mis datos",
        callback=privacidad_callback),
    Cmd("silencio", silencio_command, "Dejar de recibir difusiones",
        callback=silencio_callback),
    # Solo administradores
    Cmd("status", status_command, "Panel de estado del bot", admin=True),
    Cmd("refresh", refresh_command, "Refrescar las tasas ahora", admin=True),
    Cmd("health", health_check, "Verificar conexión con el backend", admin=True),
    Cmd("log", log_command, "Ver y descargar logs", admin=True),
    Cmd("db", db_command, "Backups y mantenimiento de la BD", admin=True),
    Cmd("ads", ads_command, "Gestión de anuncios", admin=True),
    Cmd("ms", ms_command, "Difundir mensaje a los usuarios", admin=True),
    Cmd("msapp", msapp_command, "Publicar mensaje en la app Android", admin=True),
    Cmd("ia", ia_command, "Proveedor y modelo de TASALO IA", admin=True,
        callback=ia_callback, namespaces=("ia",)),
)


def menu_publico() -> list[BotCommand]:
    return [BotCommand(c.name, c.descripcion) for c in COMANDOS if not c.admin]


def menu_admin() -> list[BotCommand]:
    return [BotCommand(c.name, c.descripcion) for c in COMANDOS]


def menu_entries(seccion: str, es_admin: bool = False) -> list[MenuEntry]:
    """Botones del menu principal para `seccion`, en el orden de COMANDOS."""
    return [
        MenuEntry(c.menu[1], f"{(c.namespaces or (c.name,))[0]}_open")
        for c in COMANDOS
        if c.menu and c.menu[0] == seccion and (es_admin or not c.admin)
    ]


def register_commands(application: Application) -> int:
    """Registra un CommandHandler por comando (con sus alias). Devuelve cuántos."""
    for c in COMANDOS:
        application.add_handler(CommandHandler([c.name, *c.alias], c.handler))
    return len(COMANDOS)


async def publish_menu(application: Application) -> None:
    """Publica el menú "/" de Telegram. Un fallo se loguea y el bot sigue."""
    bot = application.bot
    try:
        await bot.set_my_commands(menu_publico(), scope=BotCommandScopeDefault())
    except Exception as e:
        logger.warning("⚠️ No se pudo publicar el menú público de comandos: %s", e)
        return

    for admin_id in settings.get_admin_chat_ids_list():
        try:
            await bot.set_my_commands(menu_admin(), scope=BotCommandScopeChat(admin_id))
        except Exception as e:
            logger.warning("⚠️ No se pudo publicar el menú admin para %s: %s", admin_id, e)
