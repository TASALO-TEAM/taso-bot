"""El texto que escribe el usuario no debe quedar en el log (puede ser una clave)."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from src.handlers.image_alerts import handle_time_input

SECRETO = "nsec1clave-privada-de-prueba-0123456789"


def _update(texto):
    u = MagicMock()
    u.effective_user.id = 42
    u.message.text = texto
    u.message.reply_text = AsyncMock()
    return u


def _ctx(esperando):
    c = MagicMock()
    c.user_data = {"waiting_for_time": True} if esperando else {}
    return c


def test_texto_ajeno_no_se_registra(caplog):
    caplog.set_level(logging.DEBUG)
    asyncio.run(handle_time_input(_update(SECRETO), _ctx(False)))
    assert SECRETO not in caplog.text


def test_formato_invalido_no_registra_el_texto(caplog):
    caplog.set_level(logging.DEBUG)
    asyncio.run(handle_time_input(_update(SECRETO), _ctx(True)))
    assert SECRETO not in caplog.text


def test_hora_valida_sigue_funcionando(caplog):
    caplog.set_level(logging.DEBUG)
    u = _update("99:99")
    asyncio.run(handle_time_input(u, _ctx(True)))
    u.message.reply_text.assert_awaited()
