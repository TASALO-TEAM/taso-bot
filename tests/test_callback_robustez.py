"""F6-T6: robustez de los botones (una sola respuesta, doble toque, botones caducados)."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest

from src import commands
from src.handlers import callback_router as r


@pytest.fixture(autouse=True)
def _limpio():
    r._recent.clear()
    yield
    r._recent.clear()


def _tap(data, uid=1, chat=10, msg=100):
    q = MagicMock()
    q.data = data
    q.from_user.id = uid
    q.message.chat_id = chat
    q.message.message_id = msg
    q.answer = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    return u, q


def _registrar(monkeypatch, cb, ns="zzz"):
    monkeypatch.setattr(
        commands, "COMANDOS", commands.COMANDOS + (commands.Cmd(ns, None, "d", callback=cb),)
    )


def _run(u):
    asyncio.run(r.callback_router(u, MagicMock()))


def test_namespace_desconocido_responde_una_sola_vez():
    u, q = _tap("nope_1")
    _run(u)
    assert q.answer.await_count == 1
    assert q.answer.await_args.kwargs.get("show_alert") is True


def test_handler_ok_el_router_responde_una_sola_vez(monkeypatch):
    async def cb(update, context, data):
        pass

    _registrar(monkeypatch, cb)
    u, q = _tap("zzz:1")
    _run(u)
    assert q.answer.await_count == 1
    assert not q.answer.await_args.kwargs.get("show_alert")


def test_message_not_modified_no_es_error_ni_alerta(monkeypatch, caplog):
    async def cb(update, context, data):
        raise BadRequest("Message is not modified: specified new message content is exactly the same")

    _registrar(monkeypatch, cb)
    u, q = _tap("zzz:1")
    with caplog.at_level(logging.INFO):
        _run(u)
    assert q.answer.await_count == 1  # solo la respuesta inicial
    assert not [x for x in caplog.records if x.levelno >= logging.ERROR]


def test_mensaje_borrado_avisa_con_claridad(monkeypatch):
    async def cb(update, context, data):
        raise BadRequest("Message to edit not found")

    _registrar(monkeypatch, cb)
    u, q = _tap("zzz:1")
    _run(u)
    assert q.answer.await_count == 2
    texto = q.answer.await_args.args[0]
    assert "ya no está disponible" in texto
    assert q.answer.await_args.kwargs.get("show_alert") is True


def test_error_generico_mantiene_el_aviso(monkeypatch):
    async def cb(update, context, data):
        raise RuntimeError("boom")

    _registrar(monkeypatch, cb)
    u, q = _tap("zzz:1")
    _run(u)
    assert "Error procesando" in q.answer.await_args.args[0]


def test_doble_toque_descarta_el_segundo(monkeypatch):
    visto = []

    async def cb(update, context, data):
        visto.append(data)

    _registrar(monkeypatch, cb)
    u1, q1 = _tap("zzz:1")
    u2, q2 = _tap("zzz:1")
    _run(u1)
    _run(u2)
    assert visto == ["zzz:1"]
    assert q2.answer.await_count == 1  # se responde para quitar el spinner


def test_doble_toque_distinto_boton_o_usuario_si_pasa(monkeypatch):
    visto = []

    async def cb(update, context, data):
        visto.append((data,))

    _registrar(monkeypatch, cb)
    for data, uid in (("zzz:1", 1), ("zzz:2", 1), ("zzz:1", 2)):
        u, _ = _tap(data, uid=uid)
        _run(u)
    assert len(visto) == 3


def test_doble_toque_pasa_tras_la_ventana(monkeypatch):
    visto = []
    reloj = [0.0]

    async def cb(update, context, data):
        visto.append(data)

    _registrar(monkeypatch, cb)
    monkeypatch.setattr(r, "_now", lambda: reloj[0])
    u1, _ = _tap("zzz:1")
    _run(u1)
    reloj[0] = 5.0
    u2, _ = _tap("zzz:1")
    _run(u2)
    assert len(visto) == 2


@pytest.mark.parametrize("data", ["zzz:1", "nope_1"])
def test_boton_caducado_no_lanza(monkeypatch, data):
    async def cb(update, context, data):
        raise AssertionError("no debe ejecutarse")

    _registrar(monkeypatch, cb)
    u, q = _tap(data)
    q.answer.side_effect = BadRequest("Query is too old and response timeout expired")
    _run(u)  # no debe propagar la excepcion
