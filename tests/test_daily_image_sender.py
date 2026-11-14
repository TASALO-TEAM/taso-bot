"""Despacho programado de /toqueimg: nunca debe enviar la imagen de ayer."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import daily_image_sender as mod

CUBA = mod.CUBA_TZ
HOY = (2026, 11, 14)


class _FakeDT(datetime):
    _now = None

    @classmethod
    def now(cls, tz=None):
        return cls._now.astimezone(tz) if tz else cls._now


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _cliente(alerts, captured_at, image_path):
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            if "/images/alerts" in url:
                return _Resp({"ok": True, "data": alerts})
            return _Resp({
                "ok": True,
                "data": {"image_path": str(image_path), "captured_at": captured_at, "extra_data": {}},
            })

    return _Client


def _preparar(monkeypatch, tmp_path, hora, minuto, alert_time, captured_at):
    img = tmp_path / "img.png"
    img.write_bytes(b"png")
    _FakeDT._now = datetime(*HOY, hora, minuto, tzinfo=CUBA)
    monkeypatch.setattr(mod, "datetime", _FakeDT)
    monkeypatch.setattr(mod.asyncio, "sleep", AsyncMock())
    alerts = [{"id": 1, "user_id": 111, "alert_time": alert_time, "format_type": "photo"}]
    monkeypatch.setattr(mod.httpx, "AsyncClient", _cliente(alerts, captured_at, img))
    mod._sent_today.clear()
    mod._last_reset_date = _FakeDT._now.date()
    return SimpleNamespace(bot=SimpleNamespace(send_photo=AsyncMock(), send_document=AsyncMock()))


HOY_15Z = "2026-11-14T15:00:00+00:00"   # 10:00-11:00 en Cuba, mismo dia
AYER_15Z = "2026-11-13T15:00:00+00:00"


@pytest.mark.asyncio
async def test_no_envia_la_imagen_de_ayer(monkeypatch, tmp_path):
    app = _preparar(monkeypatch, tmp_path, 8, 30, "08:30", AYER_15Z)
    await mod.send_daily_images_job(app)
    app.bot.send_photo.assert_not_called()
    assert not mod._sent_today  # no se marca como enviado: se reintenta en el proximo ciclo


@pytest.mark.asyncio
async def test_aviso_de_las_730_sale_tras_la_captura_con_imagen_de_hoy(monkeypatch, tmp_path):
    app = _preparar(monkeypatch, tmp_path, 8, 30, "07:30", HOY_15Z)
    await mod.send_daily_images_job(app)
    app.bot.send_photo.assert_awaited_once()
    assert app.bot.send_photo.await_args.kwargs["chat_id"] == 111


@pytest.mark.asyncio
async def test_aviso_temprano_no_sale_antes_de_la_captura(monkeypatch, tmp_path):
    app = _preparar(monkeypatch, tmp_path, 7, 30, "07:30", AYER_15Z)
    await mod.send_daily_images_job(app)
    app.bot.send_photo.assert_not_called()


@pytest.mark.asyncio
async def test_aviso_temprano_no_se_dispara_a_media_manana(monkeypatch, tmp_path):
    app = _preparar(monkeypatch, tmp_path, 8, 0, "07:30", HOY_15Z)
    await mod.send_daily_images_job(app)
    app.bot.send_photo.assert_not_called()


@pytest.mark.asyncio
async def test_aviso_posterior_a_la_captura_sigue_a_su_hora_y_no_se_duplica(monkeypatch, tmp_path):
    app = _preparar(monkeypatch, tmp_path, 9, 0, "09:00", HOY_15Z)
    await mod.send_daily_images_job(app)
    await mod.send_daily_images_job(app)
    app.bot.send_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_captura_tardia_aun_envia_el_aviso_de_las_730_dentro_del_margen(monkeypatch, tmp_path):
    # taso-api reintenta hasta ~8:50 si El Toque tarda; a las 8:45 la imagen ya es de hoy.
    app = _preparar(monkeypatch, tmp_path, 8, 45, "07:30", HOY_15Z)
    await mod.send_daily_images_job(app)
    app.bot.send_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_aviso_de_las_730_no_sale_pasado_el_margen_de_la_captura(monkeypatch, tmp_path):
    app = _preparar(monkeypatch, tmp_path, 9, 0, "07:30", HOY_15Z)
    await mod.send_daily_images_job(app)
    app.bot.send_photo.assert_not_called()


@pytest.mark.asyncio
async def test_aviso_a_hora_fija_posterior_no_se_envia_tarde(monkeypatch, tmp_path):
    # El margen extra es solo para avisos que dependen de la captura, no para los de 9:00.
    app = _preparar(monkeypatch, tmp_path, 9, 30, "09:00", HOY_15Z)
    await mod.send_daily_images_job(app)
    app.bot.send_photo.assert_not_called()
