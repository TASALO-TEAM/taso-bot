# tests/test_coingecko_client.py
"""Tests para CoinGeckoClient (enriquecimiento del comando /p)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.coingecko_client import CoinGeckoClient, SYMBOL_TO_COINGECKO_ID


def _mock_settings(api_key: str = "CG-test-key"):
    settings = MagicMock()
    settings.coingecko_api_key = api_key
    return settings


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    resp.status_code = status_code
    return resp


@pytest.mark.asyncio
async def test_is_configured_true_with_key():
    """is_configured devuelve True si hay coingecko_api_key configurada."""
    with patch("src.coingecko_client.get_settings", return_value=_mock_settings("CG-abc")):
        client = CoinGeckoClient()
        assert client.is_configured is True


@pytest.mark.asyncio
async def test_is_configured_false_without_key():
    """is_configured devuelve False si coingecko_api_key está vacía."""
    with patch("src.coingecko_client.get_settings", return_value=_mock_settings("")):
        client = CoinGeckoClient()
        assert client.is_configured is False


@pytest.mark.asyncio
async def test_get_enrichment_data_returns_none_when_not_configured():
    """Sin API key configurada, get_enrichment_data devuelve None sin llamar a la red."""
    with patch("src.coingecko_client.get_settings", return_value=_mock_settings("")):
        client = CoinGeckoClient()
        result = await client.get_enrichment_data("BTC")
        assert result is None


@pytest.mark.asyncio
async def test_resolve_coin_id_uses_static_mapping():
    """Símbolos conocidos (BTC, ETH, etc.) se resuelven sin llamar a /search."""
    with patch("src.coingecko_client.get_settings", return_value=_mock_settings()):
        client = CoinGeckoClient()
        coin_id = await client._resolve_coin_id("btc")
        assert coin_id == "bitcoin"
        assert SYMBOL_TO_COINGECKO_ID["BTC"] == "bitcoin"


@pytest.mark.asyncio
async def test_resolve_coin_id_falls_back_to_search():
    """Símbolos no mapeados estáticamente disparan una llamada a /search."""
    search_response = _mock_response({
        "coins": [
            {"id": "some-token", "symbol": "zzz", "name": "ZZZ Token"},
        ]
    })

    with patch("src.coingecko_client.get_settings", return_value=_mock_settings()):
        client = CoinGeckoClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=search_response)
        client._client = mock_http

        coin_id = await client._resolve_coin_id("ZZZ")
        assert coin_id == "some-token"
        mock_http.get.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_coin_id_caches_result():
    """La segunda resolución del mismo símbolo no vuelve a llamar a /search."""
    search_response = _mock_response({
        "coins": [{"id": "some-token", "symbol": "zzz", "name": "ZZZ Token"}]
    })

    with patch("src.coingecko_client.get_settings", return_value=_mock_settings()):
        client = CoinGeckoClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=search_response)
        client._client = mock_http

        await client._resolve_coin_id("ZZZ")
        await client._resolve_coin_id("ZZZ")

        assert mock_http.get.call_count == 1


@pytest.mark.asyncio
async def test_get_enrichment_data_success():
    """get_enrichment_data parsea correctamente ATH/ATL/supply/categoría."""
    coin_response = _mock_response({
        "symbol": "btc",
        "market_cap_rank": 1,
        "categories": ["Smart Contract Platform", ""],
        "sentiment_votes_up_percentage": 78.3,
        "market_data": {
            "current_price": {"usd": 60000.0},
            "high_24h": {"usd": 61000.0},
            "low_24h": {"usd": 59000.0},
            "price_change_percentage_24h": 1.5,
            "price_change_percentage_7d": 3.2,
            "market_cap": {"usd": 1_200_000_000_000},
            "total_volume": {"usd": 30_000_000_000},
            "ath": {"usd": 73750.07},
            "ath_change_percentage": {"usd": -18.45},
            "ath_date": {"usd": "2024-03-10T07:10:36.635Z"},
            "atl": {"usd": 67.81},
            "atl_date": {"usd": "2013-07-06T00:00:00.000Z"},
            "circulating_supply": 19_800_000,
            "total_supply": 19_800_000,
            "max_supply": 21_000_000,
        },
    })

    with patch("src.coingecko_client.get_settings", return_value=_mock_settings()):
        client = CoinGeckoClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=coin_response)
        client._client = mock_http

        result = await client.get_enrichment_data("BTC")

        assert result is not None
        assert result["ath"] == 73750.07
        assert result["ath_change_pct"] == -18.45
        assert result["atl"] == 67.81
        assert result["circulating_supply"] == 19_800_000
        assert result["max_supply"] == 21_000_000
        assert result["category"] == "Smart Contract Platform"
        assert result["sentiment_up_pct"] == 78.3
        assert result["market_cap_rank"] == 1
        # Datos de precio "puros" también se incluyen (para el caso fuente primaria)
        assert result["price"] == 60000.0


@pytest.mark.asyncio
async def test_get_enrichment_data_returns_none_on_unresolvable_symbol():
    """Si no se puede resolver el id del símbolo, devuelve None sin lanzar excepción."""
    search_response = _mock_response({"coins": []})

    with patch("src.coingecko_client.get_settings", return_value=_mock_settings()):
        client = CoinGeckoClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=search_response)
        client._client = mock_http

        result = await client.get_enrichment_data("NOEXISTE")
        assert result is None


@pytest.mark.asyncio
async def test_get_enrichment_data_returns_none_on_http_error():
    """Si la llamada a /coins/{id} falla, devuelve None (no rompe /p)."""
    with patch("src.coingecko_client.get_settings", return_value=_mock_settings()):
        client = CoinGeckoClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(side_effect=Exception("network error"))
        client._client = mock_http

        result = await client.get_enrichment_data("BTC")
        assert result is None
