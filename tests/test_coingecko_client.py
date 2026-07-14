# tests/test_coingecko_client.py
"""Tests para CoinGeckoClient (enriquecimiento del comando /p)."""

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.coingecko_client import CoinGeckoClient


def _mock_settings(api_key: str = "CG-test-key", keys: list = None):
    """Mock de Settings. Si no se pasa `keys`, se deriva de `api_key`
    (split por coma), igual que la property real coingecko_api_keys.
    """
    settings = MagicMock()
    settings.coingecko_api_key = api_key
    if keys is not None:
        settings.coingecko_api_keys = keys
    else:
        settings.coingecko_api_keys = (
            [k.strip() for k in api_key.split(",") if k.strip()] if api_key else []
        )
    return settings


def _mock_response(json_data, status_code=200):
    """Mock de httpx.Response. raise_for_status() lanza HTTPStatusError
    real para status_code >= 400 (necesario para que _request_with_retry
    detecte 429 igual que con el httpx real).
    """
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.request = MagicMock()
    resp.request.headers = {"x-cg-demo-api-key": "CG-mock-key"}
    if status_code >= 400:
        def _raise(_resp=resp):
            raise httpx.HTTPStatusError("error", request=_resp.request, response=_resp)
        resp.raise_for_status = MagicMock(side_effect=_raise)
    else:
        resp.raise_for_status = MagicMock()
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


# ── Rotación de múltiples API keys ──

@pytest.mark.asyncio
async def test_next_key_rotates_round_robin():
    """Con varias keys, _next_key() las va devolviendo en orden y da la vuelta."""
    with patch("src.coingecko_client.get_settings", return_value=_mock_settings(keys=["CG-aaa", "CG-bbb"])):
        client = CoinGeckoClient()
        assert [client._next_key() for _ in range(4)] == ["CG-aaa", "CG-bbb", "CG-aaa", "CG-bbb"]


@pytest.mark.asyncio
async def test_next_key_single_key_always_same():
    """Con 1 sola key, _next_key() siempre devuelve esa misma key (comportamiento actual)."""
    with patch("src.coingecko_client.get_settings", return_value=_mock_settings(keys=["CG-solo"])):
        client = CoinGeckoClient()
        assert [client._next_key() for _ in range(3)] == ["CG-solo"] * 3


@pytest.mark.asyncio
async def test_is_configured_false_with_empty_keys_list():
    """is_configured es False si coingecko_api_keys queda vacía (aunque coingecko_api_key no sea None)."""
    with patch("src.coingecko_client.get_settings", return_value=_mock_settings(api_key="", keys=[])):
        client = CoinGeckoClient()
        assert client.is_configured is False


@pytest.mark.asyncio
async def test_request_with_retry_falls_back_to_next_key_on_429():
    """Si la primera key da 429, reintenta con la siguiente y tiene éxito."""
    responses = [
        _mock_response({}, status_code=429),
        _mock_response({"coins": [{"id": "some-token", "symbol": "zzz", "name": "ZZZ Token"}]}),
    ]
    with patch("src.coingecko_client.get_settings", return_value=_mock_settings(keys=["CG-aaa", "CG-bbb"])):
        client = CoinGeckoClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(side_effect=responses)
        client._client = mock_http

        coin_id = await client._resolve_coin_id("ZZZ")
        assert coin_id == "some-token"
        assert mock_http.get.call_count == 2


@pytest.mark.asyncio
async def test_request_with_retry_raises_after_exhausting_all_keys():
    """Si TODAS las keys dan 429, se propaga como CoinGeckoNetworkError (sin colgarse en loop infinito)."""
    from src.coingecko_client import CoinGeckoNetworkError

    responses = [_mock_response({}, status_code=429) for _ in range(2)]
    with patch("src.coingecko_client.get_settings", return_value=_mock_settings(keys=["CG-aaa", "CG-bbb"])):
        client = CoinGeckoClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(side_effect=responses)
        client._client = mock_http

        with pytest.raises(CoinGeckoNetworkError):
            await client._resolve_coin_id("ZZZ")
        assert mock_http.get.call_count == 2


@pytest.mark.asyncio
async def test_request_with_retry_single_key_no_retry_on_429():
    """Con 1 sola key, un 429 se propaga de inmediato (no hay a qué key cambiar)."""
    from src.coingecko_client import CoinGeckoNetworkError

    with patch("src.coingecko_client.get_settings", return_value=_mock_settings(keys=["CG-solo"])):
        client = CoinGeckoClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=_mock_response({}, status_code=429))
        client._client = mock_http

        with pytest.raises(CoinGeckoNetworkError):
            await client._resolve_coin_id("ZZZ")
        assert mock_http.get.call_count == 1


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
    """get_enrichment_data parsea correctamente ATH/ATL/supply/categoría.

    Requiere 2 respuestas mockeadas: /search (resuelve el id) y /coins/{id}
    (datos de enriquecimiento), ya que _resolve_coin_id siempre pasa por
    /search (no hay mapeo estático de símbolos en el cliente actual).
    """
    search_response = _mock_response({
        "coins": [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}]
    })
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
        mock_http.get = AsyncMock(side_effect=[search_response, coin_response])
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
async def test_get_enrichment_data_returns_not_found_on_unresolvable_symbol():
    """Si /search no encuentra el símbolo, get_enrichment_data devuelve {'not_found': True}
    (no None — crypto_client.py distingue explícitamente este caso de un error de red).
    """
    search_response = _mock_response({"coins": []})

    with patch("src.coingecko_client.get_settings", return_value=_mock_settings()):
        client = CoinGeckoClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=search_response)
        client._client = mock_http

        result = await client.get_enrichment_data("NOEXISTE")
        assert result == {"not_found": True}


@pytest.mark.asyncio
async def test_get_enrichment_data_returns_none_on_http_error():
    """Si la llamada a /coins/{id} falla (tras resolver el id correctamente
    vía /search), devuelve None (no rompe /p).
    """
    search_response = _mock_response({
        "coins": [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}]
    })

    with patch("src.coingecko_client.get_settings", return_value=_mock_settings()):
        client = CoinGeckoClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(side_effect=[search_response, Exception("network error")])
        client._client = mock_http

        result = await client.get_enrichment_data("BTC")
        assert result is None
