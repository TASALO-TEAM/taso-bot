"""Handler /mapa: parseo de la vista, texto de analisis y flujo de envio (sin red)."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from telegram.error import BadRequest

from src.handlers import mapa
from src.heatmap.data import HeatmapError, Snapshot
from src.heatmap.render import Celda

HAVANA = ZoneInfo("America/Havana")
AHORA = datetime(2026, 11, 15, 12, 0, tzinfo=HAVANA)


def _cripto(obsoleto=None):
    celdas = (
        Celda("BTC", 2e12, 2.0),
        Celda("ETH", 5e11, -1.0),
        Celda("SOL", 1e11, 10.0),
        Celda("ADA", 1e10, None),
    )
    return Snapshot(celdas, "Fuente: CoinMarketCap", 5.0, obsoleto_min=obsoleto)


def _forex(fecha="2026-11-13"):
    celdas = (Celda("EUR", 1.0, -0.99), Celda("JPY", 1.0, 1.01), Celda("GBP", 1.0, 0.2))
    return Snapshot(celdas, "Fuente: BCE", 1.0, fecha_dato=fecha)


@pytest.mark.parametrize(
    "data, esperado",
    [
        ("mapa_cripto_24h", ("cripto", "24h")),
        ("mapa_cripto_7d", ("cripto", "7d")),
        ("mapa_forex", ("forex", None)),
        ("mapa_cripto_1h", None),
        ("mapa_", None),
        ("mapa_x" * 40, None),
        ("start_forex", None),
    ],
)
def test_parse_vista(data, esperado):
    assert mapa.parse_vista(data) == esperado


def test_caption_cripto_resume_mercado_ganadores_y_perdedores():
    txt = mapa.armar_caption(("cripto", "24h"), _cripto(), AHORA)
    assert "+1.73%" in txt  # ponderado por capitalizacion, ADA (sin dato) no cuenta
    assert "2 suben / 1 bajan" in txt
    assert "SOL +10.00%" in txt.split("Mayores subas:")[1].split("\n")[0]
    assert "ETH -1.00%" in txt.split("Mayores bajas:")[1].split("\n")[0]
    assert "⚠️" not in txt


def test_caption_avisa_si_el_dato_es_viejo():
    txt = mapa.armar_caption(("cripto", "24h"), _cripto(obsoleto=12), AHORA)
    assert "hace 12 min" in txt


def test_caption_forex_muestra_fecha_real_y_aclara_si_no_es_hoy():
    txt = mapa.armar_caption(("forex", None), _forex(), AHORA)
    assert "2026-11-13" in txt
    assert "último día hábil" in txt
    assert "JPY +1.01%" in txt.split("Más fuertes:")[1].split("\n")[0]
    assert "EUR -0.99%" in txt.split("Más débiles:")[1].split("\n")[0]
    hoy = mapa.armar_caption(("forex", None), _forex("2026-11-15"), AHORA)
    assert "último día hábil" not in hoy


def test_teclado_tiene_las_tres_vistas_y_actualizar_con_la_vista_actual():
    kb = mapa.armar_teclado(("cripto", "7d"))
    datos = [b.callback_data for fila in kb.inline_keyboard for b in fila]
    assert datos == ["mapa_cripto_24h", "mapa_cripto_7d", "mapa_forex", "mapa_cripto_7d"]
    assert all(len(d) <= 64 for d in datos)


def _update_mensaje(texto="/mapa"):
    u = MagicMock()
    u.callback_query = None
    u.message.reply_photo = AsyncMock()
    u.message.reply_text = AsyncMock()
    u.message.reply_chat_action = AsyncMock()
    u.effective_user.id = 7
    u.effective_user.username = "x"
    return u


def _ctx(args):
    c = MagicMock()
    c.args = args
    return c


@pytest.fixture
def parches():
    mapa.reset_cache_png()
    with patch.object(mapa, "obtener_cripto", new=AsyncMock(return_value=_cripto())) as oc, \
         patch.object(mapa, "obtener_forex", new=AsyncMock(return_value=_forex())) as of, \
         patch.object(mapa, "render_mapa", return_value=b"PNG") as rm, \
         patch.object(mapa, "get_crypto_client", return_value=MagicMock()), \
         patch.object(mapa, "track_command_usage", new=AsyncMock()):
        yield oc, of, rm


def test_comando_sin_argumentos_envia_cripto_24h(parches):
    oc, of, rm = parches
    u = _update_mensaje()
    asyncio.run(mapa.mapa_command(u, _ctx([])))
    oc.assert_awaited_once()
    assert oc.await_args.args[1] == "24h"
    of.assert_not_awaited()
    kw = u.message.reply_photo.await_args.kwargs
    assert kw["photo"] == b"PNG"
    assert "Mayores subas" in kw["caption"]
    assert kw["reply_markup"] is not None


def test_comando_forex(parches):
    oc, of, rm = parches
    u = _update_mensaje()
    asyncio.run(mapa.mapa_command(u, _ctx(["forex"])))
    of.assert_awaited_once()
    oc.assert_not_awaited()


def test_comando_argumento_invalido_explica_el_uso_sin_llamar_a_la_api(parches):
    oc, of, rm = parches
    u = _update_mensaje()
    asyncio.run(mapa.mapa_command(u, _ctx(["bitcoin*"])))
    u.message.reply_text.assert_awaited_once()
    assert "/mapa" in u.message.reply_text.await_args.args[0]
    oc.assert_not_awaited()
    u.message.reply_photo.assert_not_awaited()


def test_error_de_datos_responde_mensaje_fijo_sin_detalle_interno(parches):
    oc, of, rm = parches
    oc.side_effect = HeatmapError("secreto interno 123")
    u = _update_mensaje()
    asyncio.run(mapa.mapa_command(u, _ctx([])))
    texto = u.message.reply_text.await_args.args[0]
    assert "secreto" not in texto and "123" not in texto
    u.message.reply_photo.assert_not_awaited()


def test_render_repetido_con_el_mismo_snapshot_se_reutiliza(parches):
    oc, of, rm = parches
    for _ in range(3):
        asyncio.run(mapa.mapa_command(_update_mensaje(), _ctx([])))
    assert rm.call_count == 1


def _update_callback(data):
    u = MagicMock()
    q = u.callback_query
    q.data = data
    q.answer = AsyncMock()
    q.edit_message_media = AsyncMock()
    q.from_user.id = 7
    u.effective_user.id = 7
    return u, q


def test_callback_cambia_de_vista_editando_la_imagen(parches):
    oc, of, rm = parches
    u, q = _update_callback("mapa_forex")
    asyncio.run(mapa.mapa_callback(u, _ctx([])))
    of.assert_awaited_once()
    q.edit_message_media.assert_awaited_once()


def test_callback_con_datos_invalidos_no_toca_la_api(parches):
    oc, of, rm = parches
    u, q = _update_callback("mapa_cripto_999")
    asyncio.run(mapa.mapa_callback(u, _ctx([])))
    oc.assert_not_awaited()
    q.edit_message_media.assert_not_awaited()


def test_callback_message_not_modified_se_responde_sin_error(parches):
    oc, of, rm = parches
    u, q = _update_callback("mapa_cripto_24h")
    q.edit_message_media.side_effect = BadRequest("Message is not modified")
    asyncio.run(mapa.mapa_callback(u, _ctx([])))
    q.answer.assert_awaited()


def test_callback_sin_datos_avisa_con_mensaje_fijo(parches):
    oc, of, rm = parches
    oc.side_effect = HeatmapError("detalle interno")
    u, q = _update_callback("mapa_cripto_24h")
    q.message.reply_text = AsyncMock()
    asyncio.run(mapa.mapa_callback(u, _ctx([])))
    texto = q.message.reply_text.await_args.args[0]
    assert "detalle" not in texto
    q.edit_message_media.assert_not_awaited()


def test_callback_con_otro_badrequest_se_propaga(parches):
    oc, of, rm = parches
    u, q = _update_callback("mapa_cripto_24h")
    q.edit_message_media.side_effect = BadRequest("Chat not found")
    with pytest.raises(BadRequest):
        asyncio.run(mapa.mapa_callback(u, _ctx([])))
