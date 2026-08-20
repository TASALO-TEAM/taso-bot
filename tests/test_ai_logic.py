# tests/test_ai_logic.py
"""Tests para la rotación de API keys de Groq en src/core/ai_logic.py."""

import httpx
import pytest
from unittest.mock import MagicMock, patch

import src.core.ai_logic as ai_logic


def _mock_settings(groq_api_key: str = "gsk_test", keys: list = None):
    """Mock de Settings. Si no se pasa `keys`, se deriva de `groq_api_key`
    (split por coma), igual que la property real groq_api_keys.
    """
    settings = MagicMock()
    settings.groq_api_key = groq_api_key
    if keys is not None:
        settings.groq_api_keys = keys
    else:
        settings.groq_api_keys = (
            [k.strip() for k in groq_api_key.split(",") if k.strip()] if groq_api_key else []
        )
    return settings


def _mock_response(json_data, status_code=200, text=""):
    """Mock de httpx.Response. raise_for_status() lanza HTTPStatusError
    real para status_code >= 400 (necesario para que _call_groq_async
    detecte 429 igual que con el httpx real)."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.text = text
    if status_code >= 400:
        def _raise(_resp=resp):
            raise httpx.HTTPStatusError("error", request=MagicMock(), response=_resp)
        resp.raise_for_status = MagicMock(side_effect=_raise)
    else:
        resp.raise_for_status = MagicMock()
    return resp


class _FakeAsyncClient:
    """Reemplaza httpx.AsyncClient dentro de _call_groq_async. Devuelve las
    respuestas en `responses` en orden, una por cada llamada a .post(), y
    registra los headers usados en cada llamada (para verificar qué key
    se usó)."""

    def __init__(self, responses):
        self._responses = iter(responses)
        self.post_calls = []
        self.post_json = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.post_calls.append(headers)
        self.post_json.append(json)
        return next(self._responses)


def _patch_client(responses):
    """Contexto que reemplaza httpx.AsyncClient por _FakeAsyncClient,
    devolviendo la instancia para poder inspeccionar post_calls."""
    fake = _FakeAsyncClient(responses)
    return patch("src.core.ai_logic.httpx.AsyncClient", return_value=fake), fake


@pytest.fixture(autouse=True)
def _reset_key_cycle():
    """El cycle de rotación es lazy y se cachea a nivel de módulo (mismo
    patrón que core/ai_client.py en taso-gcg) — hay que resetearlo antes de
    cada test para que tome la config mockeada de ese test, no la de uno
    anterior."""
    ai_logic._groq_key_cycle = None
    yield
    ai_logic._groq_key_cycle = None


@pytest.mark.asyncio
async def test_next_groq_key_rotates_round_robin():
    with patch("src.core.ai_logic.settings", _mock_settings(keys=["gsk_aaa", "gsk_bbb"])):
        assert [ai_logic._next_groq_key() for _ in range(4)] == [
            "gsk_aaa", "gsk_bbb", "gsk_aaa", "gsk_bbb",
        ]


@pytest.mark.asyncio
async def test_next_groq_key_single_key_always_same():
    with patch("src.core.ai_logic.settings", _mock_settings(keys=["gsk_solo"])):
        assert [ai_logic._next_groq_key() for _ in range(3)] == ["gsk_solo"] * 3


@pytest.mark.asyncio
async def test_next_groq_key_none_without_keys():
    with patch("src.core.ai_logic.settings", _mock_settings(groq_api_key="", keys=[])):
        assert ai_logic._next_groq_key() is None


@pytest.mark.asyncio
async def test_call_groq_async_falls_back_to_next_key_on_429():
    """Si la primera key da 429, reintenta con la siguiente y tiene éxito."""
    responses = [
        _mock_response({}, status_code=429),
        _mock_response({"choices": [{"message": {"content": "ok"}}]}),
    ]
    patcher, fake_client = _patch_client(responses)
    with patch("src.core.ai_logic.settings", _mock_settings(keys=["gsk_aaa", "gsk_bbb"])), patcher:
        data = await ai_logic._call_groq_async({"model": "x"})
        assert data["choices"][0]["message"]["content"] == "ok"
        assert len(fake_client.post_calls) == 2
        # La primera llamada usó gsk_aaa, la segunda gsk_bbb
        assert fake_client.post_calls[0]["Authorization"] == "Bearer gsk_aaa"
        assert fake_client.post_calls[1]["Authorization"] == "Bearer gsk_bbb"


@pytest.mark.asyncio
async def test_call_groq_async_single_key_no_retry_on_429():
    """Con 1 sola key, un 429 se propaga de inmediato (no hay a qué key cambiar)."""
    responses = [_mock_response({}, status_code=429)]
    patcher, fake_client = _patch_client(responses)
    with patch("src.core.ai_logic.settings", _mock_settings(keys=["gsk_solo"])), patcher:
        with pytest.raises(httpx.HTTPStatusError):
            await ai_logic._call_groq_async({"model": "x"})
        assert len(fake_client.post_calls) == 1


@pytest.mark.asyncio
async def test_call_groq_async_does_not_retry_on_400():
    """Un 400 (bad request) NO dispara reintento con otra key, aunque haya
    varias disponibles — rotar de key no arregla un bad request."""
    responses = [_mock_response({}, status_code=400, text='{"error": "invalid model"}')]
    patcher, fake_client = _patch_client(responses)
    with patch("src.core.ai_logic.settings", _mock_settings(keys=["gsk_aaa", "gsk_bbb"])), patcher:
        with pytest.raises(httpx.HTTPStatusError):
            await ai_logic._call_groq_async({"model": "x"})
        # Una sola llamada — no rotó a gsk_bbb ante un 400
        assert len(fake_client.post_calls) == 1


@pytest.mark.asyncio
async def test_call_groq_async_raises_after_exhausting_all_keys_on_429():
    """Si TODAS las keys dan 429, se propaga el HTTPStatusError (sin colgarse)."""
    responses = [_mock_response({}, status_code=429) for _ in range(2)]
    patcher, fake_client = _patch_client(responses)
    with patch("src.core.ai_logic.settings", _mock_settings(keys=["gsk_aaa", "gsk_bbb"])), patcher:
        with pytest.raises(httpx.HTTPStatusError):
            await ai_logic._call_groq_async({"model": "x"})
        assert len(fake_client.post_calls) == 2


# ── Forma del payload enviado a Groq (gpt-oss-120b: reasoning_effort +
# max_completion_tokens en vez de max_tokens deprecado) ─────────────────────

def _assert_gpt_oss_payload_shape(payload: dict, expected_max_completion_tokens: int):
    """Chequeos comunes a las 4 funciones públicas: reasoning_effort seteado
    explícitamente a 'low', max_completion_tokens presente con el valor
    esperado, y max_tokens (deprecado) ausente."""
    assert payload["reasoning_effort"] == "low"
    assert payload["max_completion_tokens"] == expected_max_completion_tokens
    assert "max_tokens" not in payload


@pytest.mark.asyncio
async def test_crypto_analysis_payload_uses_low_reasoning_and_max_completion_tokens():
    responses = [_mock_response({"choices": [{"message": {"content": "análisis ok"}}], "usage": {}})]
    patcher, fake_client = _patch_client(responses)
    with patch("src.core.ai_logic.settings", _mock_settings(keys=["gsk_aaa"])), patcher:
        await ai_logic.get_groq_crypto_analysis("BTCUSDT", "4h", "reporte de prueba")
        _assert_gpt_oss_payload_shape(fake_client.post_json[0], expected_max_completion_tokens=1024)


@pytest.mark.asyncio
async def test_price_spotlight_payload_uses_low_reasoning_and_max_completion_tokens():
    responses = [_mock_response({"choices": [{"message": {"content": "comentario ok"}}], "usage": {}})]
    patcher, fake_client = _patch_client(responses)
    with patch("src.core.ai_logic.settings", _mock_settings(keys=["gsk_aaa"])), patcher:
        await ai_logic.get_groq_price_spotlight({"symbol": "BTC", "price": 65000})
        _assert_gpt_oss_payload_shape(fake_client.post_json[0], expected_max_completion_tokens=512)


@pytest.mark.asyncio
async def test_market_spotlight_payload_uses_low_reasoning_and_max_completion_tokens():
    responses = [_mock_response({"choices": [{"message": {"content": "panorama ok"}}], "usage": {}})]
    patcher, fake_client = _patch_client(responses)
    with patch("src.core.ai_logic.settings", _mock_settings(keys=["gsk_aaa"])), patcher:
        await ai_logic.get_groq_market_spotlight({"fear_greed": {"value": 50, "classification": "Neutral"}})
        _assert_gpt_oss_payload_shape(fake_client.post_json[0], expected_max_completion_tokens=512)


@pytest.mark.asyncio
async def test_tspl_digest_payload_uses_low_reasoning_and_max_completion_tokens():
    digest_json = (
        '{"lede": "lede", "teaser": "teaser. Vamos a empezar.", '
        '"items": [{"emoji": "📰", "titulo": "t", "parrafo": "p"}], "radar": "radar"}'
    )
    responses = [_mock_response({"choices": [{"message": {"content": digest_json}, "finish_reason": "stop"}], "usage": {}})]
    patcher, fake_client = _patch_client(responses)
    with patch("src.core.ai_logic.settings", _mock_settings(keys=["gsk_aaa"])), patcher:
        await ai_logic.get_groq_tspl_digest([{"title": "t", "description": "d", "source_name": "s"}])
        _assert_gpt_oss_payload_shape(fake_client.post_json[0], expected_max_completion_tokens=2048)


@pytest.mark.asyncio
async def test_call_groq_async_uses_default_timeout_25s():
    """DEFAULT_TIMEOUT subió de 15 a 25s — verificar que se propaga a
    httpx.AsyncClient cuando no se pasa un timeout explícito."""
    responses = [_mock_response({"choices": [{"message": {"content": "ok"}}]})]
    captured_kwargs = {}

    class _CapturingAsyncClient(_FakeAsyncClient):
        def __init__(self, *args, **kwargs):
            captured_kwargs.update(kwargs)
            super().__init__(responses)

    with patch("src.core.ai_logic.settings", _mock_settings(keys=["gsk_aaa"])), \
         patch("src.core.ai_logic.httpx.AsyncClient", _CapturingAsyncClient):
        await ai_logic._call_groq_async({"model": "x"}, timeout=ai_logic.DEFAULT_TIMEOUT)
        assert ai_logic.DEFAULT_TIMEOUT == 25
        assert captured_kwargs.get("timeout") == 25
