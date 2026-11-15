"""H-055: un error inesperado en la IA no debe mostrar el texto crudo de la excepcion."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.core.ai_logic as ai_logic

SECRETO = "detalle_interno*[x](http://host-interno/clave)"


def _settings():
    s = MagicMock()
    s.groq_api_key = "gsk_test"
    s.groq_api_keys = ["gsk_test"]
    return s


def _llamar_ta():
    return ai_logic.get_groq_crypto_analysis("BTCUSDT", "4h", "reporte")


def _llamar_p():
    return ai_logic.get_groq_price_spotlight({"symbol": "BTC"})


def _llamar_spl():
    return ai_logic.get_groq_market_spotlight({})


@pytest.mark.asyncio
@pytest.mark.parametrize("llamar", [_llamar_ta, _llamar_p, _llamar_spl])
async def test_error_inesperado_no_filtra_la_excepcion(llamar):
    with patch("src.core.ai_logic.settings", _settings()), \
         patch("src.core.ai_logic._format_price_spotlight_data", return_value="x"), \
         patch("src.core.ai_logic._format_market_snapshot_text", return_value="x"), \
         patch("src.core.ai_logic._call_groq_async", AsyncMock(side_effect=ValueError(SECRETO))):
        texto = await llamar()

    assert "detalle_interno" not in texto
    assert "host-interno" not in texto
    assert texto.startswith("⚠️")
