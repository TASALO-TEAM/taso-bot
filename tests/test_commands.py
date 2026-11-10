"""Tests del registro único de comandos (src/commands.py)."""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import BotCommandScopeChat, BotCommandScopeDefault
from telegram.ext import CommandHandler

from src.commands import (
    COMANDOS,
    menu_admin,
    menu_publico,
    publish_menu,
    register_commands,
)
from src.handlers.help import HELP_TOPICS, TOPIC_ALIASES

NOMBRE_VALIDO = re.compile(r"^[a-z0-9_]{1,32}$")


def test_nombres_y_alias_unicos():
    todos = [n for c in COMANDOS for n in (c.name, *c.alias)]
    assert len(todos) == len(set(todos))


def test_formato_valido_para_telegram():
    for c in COMANDOS:
        for n in (c.name, *c.alias):
            assert NOMBRE_VALIDO.match(n), n
        assert 1 <= len(c.descripcion) <= 256, c.name
        assert callable(c.handler), c.name


def test_comandos_publicos_tienen_ficha_en_help():
    # /help es el propio índice; el resto debe resolver a una ficha
    for c in COMANDOS:
        if c.admin or c.name == "help":
            continue
        tema = TOPIC_ALIASES.get(c.name, c.name)
        assert tema in HELP_TOPICS, f"/{c.name} no tiene ficha en /help"


def test_menu_publico_sin_admin_y_menu_admin_completo():
    publicos = {c.command for c in menu_publico()}
    admins = {c.name for c in COMANDOS if c.admin}
    assert admins and publicos.isdisjoint(admins)
    assert {c.command for c in menu_admin()} == {c.name for c in COMANDOS}


def test_alias_no_sale_en_el_menu():
    assert "ayuda" not in {c.command for c in menu_admin()}


def test_register_commands_un_handler_por_comando_con_alias():
    app = MagicMock()
    assert register_commands(app) == len(COMANDOS)
    handlers = [call.args[0] for call in app.add_handler.call_args_list]
    assert all(isinstance(h, CommandHandler) for h in handlers)
    assert len(handlers) == len(COMANDOS)
    ayuda = next(h for h in handlers if "help" in h.commands)
    assert "ayuda" in ayuda.commands


@pytest.mark.asyncio
async def test_publish_menu_scopes_publico_y_por_admin():
    app = MagicMock()
    app.bot.set_my_commands = AsyncMock()
    with patch("src.commands.settings") as s:
        s.get_admin_chat_ids_list.return_value = [111, 222]
        await publish_menu(app)

    calls = app.bot.set_my_commands.call_args_list
    assert len(calls) == 3
    assert isinstance(calls[0].kwargs["scope"], BotCommandScopeDefault)
    assert [c.kwargs["scope"].chat_id for c in calls[1:]] == [111, 222]
    assert all(isinstance(c.kwargs["scope"], BotCommandScopeChat) for c in calls[1:])


@pytest.mark.asyncio
async def test_publish_menu_no_tumba_el_arranque_si_falla():
    app = MagicMock()
    app.bot.set_my_commands = AsyncMock(side_effect=RuntimeError("telegram caído"))
    with patch("src.commands.settings") as s:
        s.get_admin_chat_ids_list.return_value = [111]
        await publish_menu(app)  # no debe lanzar
