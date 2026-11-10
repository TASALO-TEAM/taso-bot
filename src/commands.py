"""Registro único de comandos del bot.

Una sola lista (COMANDOS) alimenta dos cosas:
- los CommandHandler de la Application (register_commands)
- el menú "/" de Telegram (publish_menu, vía set_my_commands)

Para añadir un comando: importar su handler y sumar una línea a COMANDOS.
Los comandos admin salen en el menú solo para los ids de ADMIN_CHAT_IDS.
Los alias se registran como handler pero no aparecen en el menú.
"""

import logging
from dataclasses import dataclass
from typing import Callable

from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.ext import Application, CommandHandler

from src.config import settings
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
from src.handlers.qp import qp_command
from src.handlers.spl import spl_command
from src.handlers.start import start_command
from src.handlers.ta import ta_command
from src.handlers.tasalo import bcc_command, fuel_command, tasalo_command, toque_command
from src.handlers.tkt import tkt_command
from src.handlers.toqueimg import toqueimg_command
from src.handlers.trading import graf_command, mk_command
from src.handlers.tspl import tspl_command
from src.handlers.y import y_command

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Cmd:
    name: str
    handler: Callable
    descripcion: str  # 1-256 caracteres (límite de Telegram)
    admin: bool = False
    alias: tuple[str, ...] = ()


COMANDOS: tuple[Cmd, ...] = (
    # Públicos (el orden es el del menú)
    Cmd("start", start_command, "Menú principal"),
    Cmd("help", help_command, "Ayuda y lista de comandos", alias=("ayuda",)),
    Cmd("tasalo", tasalo_command, "Todas las tasas de cambio"),
    Cmd("toque", toque_command, "Tasas de El Toque"),
    Cmd("bcc", bcc_command, "Tasas del Banco Central de Cuba"),
    Cmd("fuel", fuel_command, "Precio del combustible"),
    Cmd("qp", qp_command, "Tasas P2P de QvaPay"),
    Cmd("toqueimg", toqueimg_command, "Imagen diaria de El Toque"),
    Cmd("y", y_command, "Estado del año"),
    Cmd("p", p_command, "Precio de criptomonedas"),
    Cmd("ta", ta_command, "Análisis técnico"),
    Cmd("graf", graf_command, "Gráfico con indicadores"),
    Cmd("mk", mk_command, "Resumen del mercado"),
    Cmd("alert", alert_command, "Alertas de precio"),
    Cmd("spl", spl_command, "Spotlight del mercado"),
    Cmd("tspl", tspl_command, "TASALO Spotlight completo"),
    Cmd("news", news_command, "Noticias cripto"),
    Cmd("tkt", tkt_command, "Contactar a los administradores"),
    # Solo administradores
    Cmd("status", status_command, "Panel de estado del bot", admin=True),
    Cmd("refresh", refresh_command, "Refrescar las tasas ahora", admin=True),
    Cmd("health", health_check, "Verificar conexión con el backend", admin=True),
    Cmd("log", log_command, "Ver y descargar logs", admin=True),
    Cmd("db", db_command, "Backups y mantenimiento de la BD", admin=True),
    Cmd("ads", ads_command, "Gestión de anuncios", admin=True),
    Cmd("ms", ms_command, "Difundir mensaje a los usuarios", admin=True),
    Cmd("msapp", msapp_command, "Publicar mensaje en la app Android", admin=True),
)


def menu_publico() -> list[BotCommand]:
    return [BotCommand(c.name, c.descripcion) for c in COMANDOS if not c.admin]


def menu_admin() -> list[BotCommand]:
    return [BotCommand(c.name, c.descripcion) for c in COMANDOS]


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
