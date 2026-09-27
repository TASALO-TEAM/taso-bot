# tests/test_crypto_client_cmc_ai.py
"""Tests para los métodos de CMC AI (/v5/cmc-ai) en CryptoApiClient:
get_cmc_ai_coverage_map, get_cmc_ai_price_insight, get_cmc_ai_market_feed.

Mockean _cmc_get directamente (ya cubierto por separado en
test_crypto_client_cmc_rotation.py) para aislar la lógica nueva: parseo
de la respuesta, el gate del mapa de cobertura antes de pedir
coins/latest, y el cacheo con SimpleCache.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.crypto_client import CryptoApiClient
from src.cache import cache


def _settings_stub():
    s = MagicMock()
    s.coinmarketcap_api_key = "cmc-key"
    s.coinmarketcap_api_keys = ["cmc-key"]
    s.cmc_api_key_alerta_keys = ["cmc-key"]
    s.coingecko_api_key = "cg-key"
    return s


@pytest.fixture(autouse=True)
def _reset_cache():
    """El caché es un singleton a nivel de módulo — limpiarlo antes de
    cada test para que no arrastre resultados de tests anteriores."""
    cache.clear()
    yield
    cache.clear()


def _client():
    with patch("src.crypto_client.get_settings", return_value=_settings_stub()):
        return CryptoApiClient()


# ── coins/map ──

@pytest.mark.asyncio
async def test_coverage_map_returns_none_on_403():
    client = _client()
    client._cmc_get = AsyncMock(return_value=None)  # simula 403 → _cmc_get ya devuelve None

    result = await client.get_cmc_ai_coverage_map()

    assert result is None
    client._cmc_get.assert_awaited_once_with("v5/cmc-ai/coins/map")


@pytest.mark.asyncio
async def test_coverage_map_parses_coins_list_indexed_by_symbol():
    client = _client()
    client._cmc_get = AsyncMock(return_value={
        "coins": [
            {"symbol": "btc", "available_question_keys": ["price_up", "overview"]},
            {"symbol": "ETH", "available_question_keys": ["overview"]},
        ]
    })

    result = await client.get_cmc_ai_coverage_map()

    assert result is not None
    assert set(result.keys()) == {"BTC", "ETH"}
    assert result["BTC"]["available_question_keys"] == ["price_up", "overview"]


@pytest.mark.asyncio
async def test_coverage_map_second_call_uses_cache_not_second_request():
    client = _client()
    client._cmc_get = AsyncMock(return_value={"coins": [{"symbol": "BTC", "available_question_keys": []}]})

    await client.get_cmc_ai_coverage_map()
    await client.get_cmc_ai_coverage_map()

    client._cmc_get.assert_awaited_once()  # la segunda llamada vino del caché


# ── coins/latest (price_up/price_down) ──

@pytest.mark.asyncio
async def test_price_insight_none_when_symbol_not_in_map():
    client = _client()
    client._cmc_get = AsyncMock(return_value={"coins": [{"symbol": "ETH", "available_question_keys": ["price_up"]}]})

    result = await client.get_cmc_ai_price_insight("BTC")

    assert result is None
    client._cmc_get.assert_awaited_once_with("v5/cmc-ai/coins/map")  # nunca llegó a pedir coins/latest


@pytest.mark.asyncio
async def test_price_insight_none_when_no_price_keys_available():
    """Cobertura confirmada por el mapa, pero sin price_up/price_down ahora
    mismo (caso normal — no hay movimiento que explicar)."""
    client = _client()
    client._cmc_get = AsyncMock(return_value={
        "coins": [{"symbol": "BTC", "available_question_keys": ["overview", "roadmap"]}]
    })

    result = await client.get_cmc_ai_price_insight("BTC")

    assert result is None
    client._cmc_get.assert_awaited_once_with("v5/cmc-ai/coins/map")


@pytest.mark.asyncio
async def test_price_insight_fetches_when_covered():
    client = _client()
    map_response = {"coins": [{"symbol": "BTC", "available_question_keys": ["price_up"]}]}
    latest_response = {
        "BTC": [
            {"question_key": "price_up", "answer": {"tldr": "TLDR", "body": "BODY"}, "sources": [{"url": "https://x.com/a"}]},
        ]
    }
    client._cmc_get = AsyncMock(side_effect=[map_response, latest_response])

    result = await client.get_cmc_ai_price_insight("btc")

    assert result is not None
    assert result["question_key"] == "price_up"
    assert client._cmc_get.await_args_list[1].args == ("v5/cmc-ai/coins/latest", {"symbol": "BTC"})


@pytest.mark.asyncio
async def test_price_insight_second_call_uses_cache():
    client = _client()
    map_response = {"coins": [{"symbol": "BTC", "available_question_keys": ["price_down"]}]}
    latest_response = {"BTC": [{"question_key": "price_down", "answer": {"tldr": "x", "body": "y"}, "sources": []}]}
    client._cmc_get = AsyncMock(side_effect=[map_response, latest_response])

    await client.get_cmc_ai_price_insight("BTC")
    await client.get_cmc_ai_price_insight("BTC")

    # 1 llamada a coins/map (cacheado por get_cmc_ai_coverage_map) +
    # 1 sola llamada a coins/latest (cacheada por el TTL propio de precio)
    assert client._cmc_get.await_count == 2


# ── /v5/cmc-ai/latest (feed de mercado) ──

@pytest.mark.asyncio
async def test_market_feed_returns_none_on_403():
    client = _client()
    client._cmc_get = AsyncMock(return_value=None)

    result = await client.get_cmc_ai_market_feed()

    assert result is None
    client._cmc_get.assert_awaited_once_with("v5/cmc-ai/latest")


@pytest.mark.asyncio
async def test_market_feed_parses_insights():
    client = _client()
    client._cmc_get = AsyncMock(return_value={"insights": [{"title": "Q", "answer": {"tldr": "T"}, "sources": []}]})

    result = await client.get_cmc_ai_market_feed()

    assert result is not None
    assert len(result["insights"]) == 1
    assert result["insights"][0]["title"] == "Q"


@pytest.mark.asyncio
async def test_market_feed_second_call_uses_cache():
    client = _client()
    client._cmc_get = AsyncMock(return_value={"insights": []})

    await client.get_cmc_ai_market_feed()
    await client.get_cmc_ai_market_feed()

    client._cmc_get.assert_awaited_once()
