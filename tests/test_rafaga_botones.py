"""F7-T2: rafagas de botones. El antirrebote debe acotar memoria y despachar una sola vez por toque repetido."""

import asyncio
import logging
import tracemalloc
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.handlers import callback_router as cr


@pytest.fixture
def entorno(monkeypatch):
    reloj = {"t": 1000.0}
    llamadas = []

    async def _handle_zz(update, context, data):
        llamadas.append(data)

    monkeypatch.setattr(cr, "_now", lambda: reloj["t"])
    monkeypatch.setitem(cr.ROUTE_MAP, "zz", "_handle_zz")
    monkeypatch.setattr(cr, "_handle_zz", _handle_zz, raising=False)
    cr._recent.clear()
    logging.disable(logging.CRITICAL)
    yield reloj, llamadas
    logging.disable(logging.NOTSET)
    cr._recent.clear()


def _update(uid, msg_id, data="zz:a"):
    q = MagicMock()
    q.data = data
    q.from_user.id = uid
    q.message.chat_id = uid
    q.message.message_id = msg_id
    q.answer = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    return u


def _run(coro):
    return asyncio.run(coro)


def test_mismo_toque_en_rafaga_se_despacha_una_vez(entorno):
    _, llamadas = entorno
    u = _update(1, 10)

    async def rafaga():
        for _ in range(200):
            await cr.callback_router(u, MagicMock())

    _run(rafaga())
    assert len(llamadas) == 1
    assert u.callback_query.answer.await_count == 200  # todos pierden el spinner


def test_toque_se_repite_tras_la_ventana(entorno):
    reloj, llamadas = entorno
    u = _update(1, 10)

    async def dos():
        await cr.callback_router(u, MagicMock())
        reloj["t"] += cr._DEBOUNCE_S + 0.1
        await cr.callback_router(u, MagicMock())

    _run(dos())
    assert len(llamadas) == 2


def test_usuarios_distintos_no_se_bloquean_entre_si(entorno):
    _, llamadas = entorno

    async def varios():
        for uid in range(50):
            await cr.callback_router(_update(uid, 1), MagicMock())

    _run(varios())
    assert len(llamadas) == 50


def test_tabla_de_antirrebote_queda_acotada_en_flujo_sostenido(entorno):
    reloj, _ = entorno

    async def flujo():
        for i in range(1000):
            reloj["t"] += 0.01  # 100 toques/s distintos
            await cr.callback_router(_update(i, i), MagicMock())

    _run(flujo())
    # ventana de 1 s a 100 toques/s: ~100 vivos; la poda corre al pasar de 256
    assert len(cr._recent) <= 400


def test_memoria_de_una_rafaga_grande_es_pequena(entorno):
    reloj, _ = entorno
    updates = [_update(i, i) for i in range(2500)]

    async def flujo():
        for u in updates:
            reloj["t"] += 0.005
            await cr.callback_router(u, MagicMock())

    tracemalloc.start()
    base = tracemalloc.take_snapshot()
    _run(flujo())
    actual = tracemalloc.take_snapshot()
    tracemalloc.stop()
    stats = actual.filter_traces([tracemalloc.Filter(True, cr.__file__)]).compare_to(
        base.filter_traces([tracemalloc.Filter(True, cr.__file__)]), "filename")
    crecimiento = sum(s.size_diff for s in stats)
    assert crecimiento < 200_000, f"el router retiene {crecimiento} bytes tras 2500 toques"
    assert len(cr._recent) <= 400
