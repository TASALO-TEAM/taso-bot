"""F7-T2: resiliencia de las funciones de IA ante respuestas hostiles y proveedores caidos."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import src.core.ai_logic as ai_logic

HOSTILES = [
    None, [], "x", 7, {},
    {"choices": None}, {"choices": []}, {"choices": [None]}, {"choices": ["x"]}, {"choices": [{}]},
    {"choices": [{"message": None}]}, {"choices": [{"message": "x"}]},
    {"choices": [{"message": {}}]},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": {"content": 123}}]},
    {"choices": [{"message": {"content": "   "}}]},
]
CAIDAS = [
    TimeoutError(), ConnectionError("x"), httpx.ReadTimeout("t"), httpx.ConnectError("c"),
    httpx.HTTPStatusError("429", request=httpx.Request("POST", "http://x"),
                          response=httpx.Response(429, request=httpx.Request("POST", "http://x"))),
    RuntimeError("boom"),
]


def _settings():
    s = MagicMock()
    s.groq_api_key = "gsk_test"
    s.groq_api_keys = ["gsk_test"]
    s.nvidia_api_key = ""
    return s


def _ta():
    return ai_logic.get_groq_crypto_analysis("BTCUSDT", "4h", "reporte")


def _p():
    return ai_logic.get_groq_price_spotlight({"symbol": "BTC"})


def _spl():
    return ai_logic.get_groq_market_spotlight({})


def _mapa():
    return ai_logic.get_mapa_analysis("contexto agregado")


def _explorer():
    return ai_logic.get_explorer_analysis("contexto agregado")


LLAMADAS = [_ta, _p, _spl, _mapa, _explorer]


def _parches(mock_ai):
    return (
        patch("src.core.ai_logic.settings", _settings()),
        patch("src.core.ai_logic._format_price_spotlight_data", return_value="x"),
        patch("src.core.ai_logic._format_market_snapshot_text", return_value="x"),
        patch("src.core.ai_logic._call_ai_async", mock_ai),
    )


async def _ejecutar(llamar, mock_ai):
    p1, p2, p3, p4 = _parches(mock_ai)
    with p1, p2, p3, p4:
        return await llamar()


@pytest.mark.asyncio
@pytest.mark.parametrize("llamar", LLAMADAS)
@pytest.mark.parametrize("payload", HOSTILES)
async def test_respuesta_hostil_nunca_lanza_y_devuelve_texto(llamar, payload):
    mock_ai = AsyncMock(return_value=payload)
    texto = await _ejecutar(llamar, mock_ai)
    assert mock_ai.await_count >= 1, "el parche no se aplico: la prueba seria vacua"
    assert isinstance(texto, str) and texto


@pytest.mark.asyncio
@pytest.mark.parametrize("llamar", LLAMADAS)
@pytest.mark.parametrize("exc", CAIDAS)
async def test_proveedor_caido_devuelve_mensaje_fijo(llamar, exc):
    texto = await _ejecutar(llamar, AsyncMock(side_effect=exc))
    assert isinstance(texto, str) and texto
    assert "boom" not in texto and "http://x" not in texto


@pytest.mark.asyncio
async def test_digest_tspl_hostil_devuelve_none_sin_lanzar():
    for payload in HOSTILES:
        with patch("src.core.ai_logic.settings", _settings()), \
             patch("src.core.ai_logic._call_ai_async", AsyncMock(return_value=payload)):
            res = await ai_logic.get_groq_tspl_digest([{"title": "t", "link": "l"}])
        assert res is None or isinstance(res, dict)


@pytest.mark.asyncio
async def test_dispatcher_ambos_fallan_relanza_el_ultimo_error():
    from src.core import ai_config
    with patch("src.core.ai_logic.settings", _settings()), \
         patch("src.core.ai_logic._nvidia_key", return_value="nvapi-x"), \
         patch.object(ai_config, "orden", return_value=["groq", "nvidia"]), \
         patch("src.core.ai_logic._call_groq_async", AsyncMock(side_effect=TimeoutError())), \
         patch("src.core.ai_logic._call_nvidia_async", AsyncMock(side_effect=ConnectionError("n"))):
        with pytest.raises(ConnectionError):
            await ai_logic._call_ai_async({"messages": []})


@pytest.mark.asyncio
async def test_nvidia_json_invalido_o_no_dict_se_propaga_como_error_normal():
    for cuerpo in (b"no json", b"[1,2]", b"null"):
        transport = httpx.MockTransport(lambda req, c=cuerpo: httpx.Response(200, content=c))
        with patch("src.core.ai_logic._nvidia_key", return_value="nvapi-x"):
            with pytest.raises(Exception):
                await ai_logic._call_nvidia_async({"messages": []}, transport=transport)
