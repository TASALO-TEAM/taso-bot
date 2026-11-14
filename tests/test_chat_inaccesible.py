"""H-030: un chat que ya no existe no debe llenar el log de errores cada dia."""

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest, Forbidden, NetworkError

from src.services import daily_image_sender as img_mod
from src.services import year_alert_scheduler as year_mod
from src.utils.telegram_errors import chat_inaccesible

from tests.test_daily_image_sender import HOY_15Z, _preparar


@pytest.mark.parametrize("exc", [
    BadRequest("Chat not found"),
    Forbidden("Forbidden: bot was blocked by the user"),
    Forbidden("Forbidden: user is deactivated"),
])
def test_chat_inaccesible_reconoce_chats_muertos(exc):
    assert chat_inaccesible(exc)


@pytest.mark.parametrize("exc", [
    BadRequest("Can't parse entities: unsupported start tag"),
    NetworkError("Bad Gateway"),
    ValueError("Chat not found"),
])
def test_chat_inaccesible_no_oculta_errores_reales(exc):
    assert not chat_inaccesible(exc)


@pytest.mark.asyncio
async def test_imagen_a_chat_muerto_no_es_error_y_no_se_reintenta_hoy(monkeypatch, tmp_path, caplog):
    app = _preparar(monkeypatch, tmp_path, 8, 30, "08:30", HOY_15Z)
    app.bot.send_photo.side_effect = BadRequest("Chat not found")
    with caplog.at_level(logging.WARNING):
        await img_mod.send_daily_images_job(app)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR and r.exc_info]
    assert any(r.levelno == logging.WARNING and "inaccesible" in r.getMessage() for r in caplog.records)
    assert len(img_mod._sent_today) == 1  # no se vuelve a intentar en los proximos ciclos
    await img_mod.send_daily_images_job(app)
    assert app.bot.send_photo.await_count == 1


@pytest.mark.asyncio
async def test_imagen_con_error_de_formato_sigue_siendo_error_con_traza(monkeypatch, tmp_path, caplog):
    app = _preparar(monkeypatch, tmp_path, 8, 30, "08:30", HOY_15Z)
    app.bot.send_photo.side_effect = BadRequest("Can't parse entities: unsupported start tag")
    with caplog.at_level(logging.WARNING):
        await img_mod.send_daily_images_job(app)
    assert [r for r in caplog.records if r.levelno >= logging.ERROR and r.exc_info]
    assert not img_mod._sent_today  # un fallo real si se reintenta


class _FakeNow(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 11, 14, 7, 0, tzinfo=timezone.utc)


def _preparar_anual(monkeypatch, send):
    class _Api:
        def __init__(self, **kw):
            pass

        async def admin_list_year_subscriptions(self):
            return {"ok": True, "data": [{"user_id": 111, "hour": 7}]}

        async def get_year_state(self):
            return {"progress": {"percent": 50.0, "year": 2026}, "quote": {}}

    monkeypatch.setattr(year_mod, "get_settings", lambda: SimpleNamespace(
        tasalo_api_url="http://x", tasalo_admin_key="k", api_timeout_seconds=5))
    monkeypatch.setattr(year_mod, "TasaloApiClient", _Api)
    monkeypatch.setattr(year_mod, "datetime", _FakeNow)
    app = SimpleNamespace(bot=SimpleNamespace(send_message=send))
    return year_mod.create_year_scheduler(app).get_job("year_daily_alert").func


@pytest.mark.asyncio
async def test_aviso_anual_a_chat_muerto_es_warning(monkeypatch, caplog):
    job = _preparar_anual(monkeypatch, AsyncMock(side_effect=Forbidden("Forbidden: bot was blocked by the user")))
    with caplog.at_level(logging.WARNING):
        await job()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(r.levelno == logging.WARNING and "inaccesible" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_aviso_anual_con_error_real_sigue_siendo_error(monkeypatch, caplog):
    job = _preparar_anual(monkeypatch, AsyncMock(side_effect=BadRequest("Can't parse entities: x")))
    with caplog.at_level(logging.WARNING):
        await job()
    assert [r for r in caplog.records if r.levelno >= logging.ERROR]
