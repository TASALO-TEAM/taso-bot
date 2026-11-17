"""Boton "Ejecutar" en las fichas del menu (F6-T5): corre el comando real sin escribirlo."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import menu
from src.commands import Cmd


def _datas(markup):
    return [b.callback_data for fila in markup.inline_keyboard for b in fila]


def _ficha(nombre, sec, es_admin=False):
    return menu.render(("cmd", nombre, sec), es_admin)[1]


def _seccion_de(nombre):
    return next(s for s, (_, _, hojas) in menu.SECCIONES.items() if nombre in hojas)


@pytest.mark.parametrize("nombre", menu.EJECUTABLES)
def test_la_ficha_de_un_comando_sin_argumentos_ofrece_ejecutar(nombre):
    datos = _datas(_ficha(nombre, _seccion_de(nombre)))
    assert f"menu:run:{nombre}" in datos
    assert all(len(d.encode()) <= 64 for d in datos)


def test_comandos_con_argumentos_o_admin_no_ofrecen_ejecutar():
    for nombre in ("tkt", "y"):
        sec = _seccion_de(nombre)
        assert not any(d.startswith("menu:run:") for d in _datas(_ficha(nombre, sec, True)))
    assert not any(n in menu.EJECUTABLES for n in ("tkt", "y", "refresh", "health"))


def _query():
    q = MagicMock()
    q.from_user.id = 7
    q.message.reply_text = AsyncMock()
    q.edit_message_text = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    return u, q


def test_ejecutar_llama_al_handler_real_con_un_update_equivalente(monkeypatch):
    llamado = {}

    async def handler(update, context):
        llamado.update(msg=update.message, user=update.effective_user,
                       cq=update.callback_query, args=list(context.args))

    monkeypatch.setattr(menu, "_cmds", lambda: {"qp": Cmd("qp", handler, "d")})
    u, q = _query()
    ctx = MagicMock()
    asyncio.run(menu.menu_callback(u, ctx, "menu:run:qp"))
    assert llamado == {"msg": q.message, "user": q.from_user, "cq": None, "args": []}


@pytest.mark.parametrize("data", ["menu:run:tkt", "menu:run:refresh", "menu:run:zzz", "menu:run", "menu:run:qp:x"])
def test_lo_no_permitido_no_ejecuta_nada_y_cae_en_el_inicio(monkeypatch, data):
    handler = AsyncMock()
    monkeypatch.setattr(menu, "_cmds", lambda: {
        n: Cmd(n, handler, "d", admin=(n == "refresh")) for n in ("qp", "tkt", "refresh")})
    u, q = _query()
    asyncio.run(menu.menu_callback(u, MagicMock(), data))
    handler.assert_not_called()
    q.edit_message_text.assert_awaited()  # la bienvenida


def test_si_el_handler_falla_se_avisa_sin_romper(monkeypatch):
    monkeypatch.setattr(menu, "_cmds", lambda: {"qp": Cmd("qp", AsyncMock(side_effect=RuntimeError("x")), "d")})
    u, q = _query()
    asyncio.run(menu.menu_callback(u, MagicMock(), "menu:run:qp"))
    texto = q.message.reply_text.await_args.args[0]
    assert "/qp" in texto and "RuntimeError" not in texto
