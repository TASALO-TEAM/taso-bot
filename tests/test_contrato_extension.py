"""F6-T2: contrato de extension. Un modulo nuevo se registra con UNA linea en
COMANDOS (comando + namespace de callbacks + entrada de menu), sin editar
callback_router.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


def _update(data: str):
    q = MagicMock()
    q.data = data
    q.from_user.id = 1
    q.answer = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    return u, q


def _con(monkeypatch, *cmds):
    from src import commands

    monkeypatch.setattr(commands, "COMANDOS", commands.COMANDOS + tuple(cmds))
    return commands


def test_cmd_campos_nuevos_son_opcionales():
    from src.commands import Cmd

    c = Cmd("x", None, "d")
    assert c.callback is None and c.namespaces == () and c.menu is None


def test_namespace_por_defecto_es_el_nombre_del_comando(monkeypatch):
    from src.commands import Cmd
    from src.handlers import callback_router as r

    visto = []

    async def cb(update, context, data):
        visto.append(data)

    _con(monkeypatch, Cmd("zzz", None, "d", callback=cb))
    u, q = _update("zzz_abc")
    asyncio.run(r.callback_router(u, MagicMock()))
    assert visto == ["zzz_abc"]
    q.answer.assert_awaited_once_with()  # una sola respuesta, sin alerta de error


def test_namespace_compuesto_se_resuelve_completo(monkeypatch):
    from src.commands import Cmd
    from src.handlers import callback_router as r

    visto = []

    async def cb(update, context, data):
        visto.append(data)

    _con(monkeypatch, Cmd("foo", None, "d", callback=cb, namespaces=("foo_bar",)))
    assert r._resolve_namespace("foo_bar_1") == "foo_bar"
    u, _ = _update("foo_bar_1")
    asyncio.run(r.callback_router(u, MagicMock()))
    assert visto == ["foo_bar_1"]


def test_namespace_que_choca_con_uno_existente_falla(monkeypatch):
    from src.commands import Cmd
    from src.handlers import callback_router as r

    async def cb(update, context, data):
        pass

    _con(monkeypatch, Cmd("p2", None, "d", callback=cb, namespaces=("p",)))
    with pytest.raises(ValueError, match="p"):
        r._extra_routes()


def test_dos_comandos_con_el_mismo_namespace_falla(monkeypatch):
    from src.commands import Cmd
    from src.handlers import callback_router as r

    async def cb(update, context, data):
        pass

    _con(
        monkeypatch,
        Cmd("aaa", None, "d", callback=cb),
        Cmd("bbb", None, "d", callback=cb, namespaces=("aaa",)),
    )
    with pytest.raises(ValueError, match="aaa"):
        r._extra_routes()


def test_comandos_reales_no_tienen_conflictos():
    from src.handlers import callback_router as r

    # Sin conflictos de namespace; hoy solo el menu (F6-T4) usa el contrato.
    assert set(r._extra_routes()) == {"menu"}


def test_namespace_desconocido_sigue_avisando(monkeypatch):
    from src.handlers import callback_router as r

    u, q = _update("nadie_x")
    asyncio.run(r.callback_router(u, MagicMock()))
    q.answer.assert_awaited_with("⚠️ Acción no reconocida", show_alert=True)


def test_menu_entries_filtra_por_seccion_y_admin(monkeypatch):
    from src.commands import Cmd

    commands = _con(
        monkeypatch,
        Cmd("m1", None, "d", menu=("mercado", "Uno")),
        Cmd("m2", None, "d", menu=("mercado", "Dos"), admin=True),
        Cmd("o1", None, "d", menu=("otra", "Tres")),
    )
    pub = commands.menu_entries("mercado")
    assert [e.label for e in pub] == ["Uno"]
    adm = commands.menu_entries("mercado", es_admin=True)
    assert [e.label for e in adm] == ["Uno", "Dos"]


def test_menu_entry_callback_data_cabe_en_64_bytes(monkeypatch):
    from src.commands import Cmd

    commands = _con(monkeypatch, Cmd("m1", None, "d", menu=("mercado", "Uno"), namespaces=("m_uno",)))
    (e,) = commands.menu_entries("mercado")
    assert e.callback_data == "m_uno_open"
    assert len(e.callback_data.encode()) <= 64
