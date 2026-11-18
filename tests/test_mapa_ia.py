"""/mapa: boton de analisis con TASALO IA (F3-T4). Sin red: IA y datos van con mocks."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import BadRequest

from src.handlers import mapa
from src.heatmap.data import HeatmapError, Snapshot
from src.heatmap.render import Celda


def _cripto():
    celdas = (
        Celda("BTC", 2e12, -7.0),
        Celda("ETH", 5e11, -9.0),
        Celda("SOL", 1e11, 3.0),
        Celda("ADA", 1e10, None),
    )
    return Snapshot(celdas, "Fuente: CoinMarketCap", 5.0)


@pytest.fixture(autouse=True)
def _limpia():
    mapa.reset_cache_png()
    yield
    mapa.reset_cache_png()


def _q(data="mapa_ia_cripto_24h"):
    q = MagicMock()
    q.data = data
    q.message.reply_text = AsyncMock()
    q.message.chat.send_action = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    return u, q


def _run(u, snap=None, texto="Analisis de prueba", config=True, error=None):
    ia = AsyncMock(return_value=texto)
    with patch("src.handlers.mapa._snapshot", AsyncMock(side_effect=error, return_value=snap or _cripto())), \
         patch("src.handlers.mapa.ai_logic.get_mapa_analysis", ia), \
         patch("src.handlers.mapa.ai_logic._ia_configurada", return_value=config):
        asyncio.run(mapa.mapa_callback(u, MagicMock()))
    return ia


def test_teclado_tiene_boton_de_analisis_con_la_vista_activa():
    for clave, vista in (("cripto_24h", ("cripto", "24h")), ("cripto_7d", ("cripto", "7d")),
                         ("forex", ("forex", None)), ("acciones", ("acciones", None))):
        kb = mapa.armar_teclado(vista)
        ultimo = kb.inline_keyboard[-1][0]
        assert ultimo.callback_data == f"mapa_ia_{clave}"
        assert len(ultimo.callback_data) <= 32
        assert "TASALO IA" in ultimo.text


def test_parse_vista_no_confunde_el_boton_de_analisis():
    assert mapa.parse_vista("mapa_ia_forex") is None


def test_contexto_solo_lleva_datos_de_mercado():
    txt = mapa.contexto_ia(("cripto", "24h"), _cripto())
    assert "BTC -7.00%" in txt and "SOL +3.00%" in txt
    assert "ADA" not in txt  # sin dato de variacion
    assert "24h" in txt and "ponderada" in txt.lower()


def test_contexto_limpia_simbolos_raros():
    celdas = (Celda("BT\nC*<x>", 1e9, 1.0), Celda("ETH", 1e9, -1.0))
    txt = mapa.contexto_ia(("cripto", "24h"), Snapshot(celdas, "f", 5.0))
    assert "<" not in txt and "*" not in txt
    assert "BTCx" in txt


def test_contexto_indica_datos_viejos():
    snap = Snapshot(_cripto().celdas, "f", 5.0, obsoleto_min=12)
    assert "12 min" in mapa.contexto_ia(("cripto", "24h"), snap)


def test_boton_envia_el_analisis_como_mensaje_nuevo():
    u, q = _q()
    ia = _run(u)
    ia.assert_awaited_once()
    assert "BTC" in ia.await_args.args[0]
    assert q.message.reply_text.await_args.args[0] == "Analisis de prueba"


def test_mismo_dato_reutiliza_el_analisis():
    u, q = _q()
    ia = AsyncMock(return_value="Texto")
    with patch("src.handlers.mapa._snapshot", AsyncMock(return_value=_cripto())), \
         patch("src.handlers.mapa.ai_logic.get_mapa_analysis", ia), \
         patch("src.handlers.mapa.ai_logic._ia_configurada", return_value=True):
        asyncio.run(mapa.mapa_callback(u, MagicMock()))
        asyncio.run(mapa.mapa_callback(u, MagicMock()))
    assert ia.await_count == 1
    assert q.message.reply_text.await_count == 2


def test_un_error_de_la_ia_no_se_guarda_en_cache():
    u, _ = _q()
    ia = AsyncMock(side_effect=["⚠️ La IA tardó demasiado.", "Texto bueno"])
    with patch("src.handlers.mapa._snapshot", AsyncMock(return_value=_cripto())), \
         patch("src.handlers.mapa.ai_logic.get_mapa_analysis", ia), \
         patch("src.handlers.mapa.ai_logic._ia_configurada", return_value=True):
        asyncio.run(mapa.mapa_callback(u, MagicMock()))
        asyncio.run(mapa.mapa_callback(u, MagicMock()))
    assert ia.await_count == 2


def test_sin_ia_configurada_avisa_y_no_llama():
    u, q = _q()
    ia = _run(u, config=False)
    ia.assert_not_awaited()
    assert "no está disponible" in q.message.reply_text.await_args.args[0]


def test_sin_datos_de_mercado_responde_el_error_fijo():
    u, q = _q()
    ia = _run(u, error=HeatmapError("x"))
    ia.assert_not_awaited()
    assert q.message.reply_text.await_args.args[0] == mapa.MSG_ERROR


def test_vista_invalida_no_hace_nada():
    u, q = _q("mapa_ia_zzz")
    ia = _run(u)
    ia.assert_not_awaited()
    q.message.reply_text.assert_not_awaited()


def test_si_telegram_rechaza_el_markdown_reenvia_en_texto_plano():
    u, q = _q()
    q.message.reply_text = AsyncMock(side_effect=[BadRequest("Can't parse entities"), None])
    _run(u, texto="Texto con _ raro")
    assert q.message.reply_text.await_count == 2
    assert "parse_mode" not in q.message.reply_text.await_args_list[1].kwargs
