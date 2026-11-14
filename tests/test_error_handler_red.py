"""Los errores transitorios de red de Telegram no deben generar traza completa
ni avisar al grupo de soporte; los demás errores siguen igual (H-013)."""
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import Conflict, NetworkError, TimedOut

from src import main as bot_main


def _ctx(error):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return SimpleNamespace(error=error, bot=bot)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [NetworkError("Bad Gateway"), TimedOut("Timed out")])
async def test_error_de_red_va_a_warning_sin_traza_ni_aviso(error, caplog, monkeypatch):
    monkeypatch.setattr(bot_main.settings, "log_chat_id", 123, raising=False)
    ctx = _ctx(error)
    with caplog.at_level(logging.WARNING, logger=bot_main.logger.name):
        await bot_main.error_handler(None, ctx)

    registros = [r for r in caplog.records if r.name == bot_main.logger.name]
    assert len(registros) == 1
    assert registros[0].levelno == logging.WARNING
    assert registros[0].exc_info is None
    ctx.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_otros_errores_siguen_como_error_con_traza_y_aviso(caplog, monkeypatch):
    monkeypatch.setattr(bot_main.settings, "log_chat_id", 123, raising=False)
    ctx = _ctx(Conflict("terminated by other getUpdates request"))
    with caplog.at_level(logging.ERROR, logger=bot_main.logger.name):
        await bot_main.error_handler(None, ctx)

    registros = [r for r in caplog.records if r.name == bot_main.logger.name]
    assert registros and registros[0].levelno == logging.ERROR
    assert registros[0].exc_info is not None
    ctx.bot.send_message.assert_awaited_once()
