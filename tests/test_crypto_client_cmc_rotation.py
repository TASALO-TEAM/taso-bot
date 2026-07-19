# tests/test_crypto_client_cmc_rotation.py
"""Tests para la rotación de API keys de CoinMarketCap en CryptoApiClient
(pool interactivo usado por /p y /spl, y pool separado del alert checker)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.crypto_client import CryptoApiClient


def _settings_stub(cmc_keys=None, cmc_alerta_keys=None):
    s = MagicMock()
    keys = cmc_keys if cmc_keys is not None else ["cmc-key"]
    s.coinmarketcap_api_key = ",".join(keys)
    s.coinmarketcap_api_keys = keys
    s.cmc_api_key_alerta_keys = cmc_alerta_keys if cmc_alerta_keys is not None else keys
    s.coingecko_api_key = "cg-key"
    return s


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    if status_code >= 400:
        def _raise(_resp=resp):
            import httpx
            raise httpx.HTTPStatusError("error", request=MagicMock(), response=_resp)
        resp.raise_for_status = MagicMock(side_effect=_raise)
    else:
        resp.raise_for_status = MagicMock()
    return resp


# ── Rotación round-robin ──

def test_next_cmc_key_rotates_round_robin():
    with patch("src.crypto_client.get_settings", return_value=_settings_stub(cmc_keys=["key1", "key2"])):
        client = CryptoApiClient()
        assert [client._next_cmc_key() for _ in range(4)] == ["key1", "key2", "key1", "key2"]


def test_next_cmc_key_single_key_always_same():
    with patch("src.crypto_client.get_settings", return_value=_settings_stub(cmc_keys=["solo"])):
        client = CryptoApiClient()
        assert [client._next_cmc_key() for _ in range(3)] == ["solo"] * 3


def test_next_cmc_key_none_without_keys():
    with patch("src.crypto_client.get_settings", return_value=_settings_stub(cmc_keys=[])):
        client = CryptoApiClient()
        assert client._next_cmc_key() is None


# ── Aislamiento entre pool interactivo y pool de alerta ──

def test_constructor_uses_interactive_pool_by_default():
    """Sin pasar cmc_api_keys, usa settings.coinmarketcap_api_keys (interactivo)."""
    with patch(
        "src.crypto_client.get_settings",
        return_value=_settings_stub(cmc_keys=["interactivo1", "interactivo2"], cmc_alerta_keys=["alerta1"]),
    ):
        client = CryptoApiClient()
        assert client._cmc_keys == ["interactivo1", "interactivo2"]


def test_constructor_accepts_explicit_pool_for_alert_checker():
    """Pasando cmc_api_keys explícito (como hace price_alert_checker.py),
    la instancia rota SU propio pool, no el interactivo."""
    with patch(
        "src.crypto_client.get_settings",
        return_value=_settings_stub(cmc_keys=["interactivo1", "interactivo2"], cmc_alerta_keys=["alerta1", "alerta2"]),
    ):
        client = CryptoApiClient(cmc_api_keys=["alerta1", "alerta2"])
        assert client._cmc_keys == ["alerta1", "alerta2"]
        assert [client._next_cmc_key() for _ in range(2)] == ["alerta1", "alerta2"]


# ── _cmc_request_with_retry ──

@pytest.mark.asyncio
async def test_cmc_request_with_retry_falls_back_to_next_key_on_429():
    with patch("src.crypto_client.get_settings", return_value=_settings_stub(cmc_keys=["key1", "key2"])):
        client = CryptoApiClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(side_effect=[
            _mock_response({}, status_code=429),
            _mock_response({"data": {"ok": True}}),
        ])
        client._client = mock_http

        resp = await client._cmc_request_with_retry("https://pro-api.coinmarketcap.com/v1/x")
        assert resp.status_code == 200
        assert mock_http.get.call_count == 2
        # La primera llamada usó key1, la segunda key2
        first_headers = mock_http.get.call_args_list[0].kwargs["headers"]
        second_headers = mock_http.get.call_args_list[1].kwargs["headers"]
        assert first_headers["X-CMC_PRO_API_KEY"] == "key1"
        assert second_headers["X-CMC_PRO_API_KEY"] == "key2"


@pytest.mark.asyncio
async def test_cmc_request_with_retry_single_key_no_retry_on_429():
    """Con 1 sola key, un 429 se devuelve tal cual (no hay a qué key cambiar)."""
    with patch("src.crypto_client.get_settings", return_value=_settings_stub(cmc_keys=["solo"])):
        client = CryptoApiClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=_mock_response({}, status_code=429))
        client._client = mock_http

        resp = await client._cmc_request_with_retry("https://pro-api.coinmarketcap.com/v1/x")
        assert resp.status_code == 429
        assert mock_http.get.call_count == 1


@pytest.mark.asyncio
async def test_cmc_request_with_retry_does_not_retry_on_403():
    """Un 403 (plan insuficiente) se devuelve en el primer intento — cada
    caller decide qué hacer, rotar de key no cambia el plan de la cuenta."""
    with patch("src.crypto_client.get_settings", return_value=_settings_stub(cmc_keys=["key1", "key2"])):
        client = CryptoApiClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(return_value=_mock_response({"status": {"error_message": "plan insuficiente"}}, status_code=403))
        client._client = mock_http

        resp = await client._cmc_request_with_retry("https://pro-api.coinmarketcap.com/v1/x")
        assert resp.status_code == 403
        assert mock_http.get.call_count == 1


# ── Integración: _get_from_cmc y _cmc_get usan la rotación ──

@pytest.mark.asyncio
async def test_get_from_cmc_recovers_from_429_via_rotation():
    with patch("src.crypto_client.get_settings", return_value=_settings_stub(cmc_keys=["key1", "key2"])):
        client = CryptoApiClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(side_effect=[
            _mock_response({}, status_code=429),
            _mock_response({"data": {"BTC": {"symbol": "BTC"}, "ETH": {}}}),
        ])
        client._client = mock_http

        result = await client._get_from_cmc(["BTC", "ETH"])
        assert result is not None
        assert "BTC" in result


@pytest.mark.asyncio
async def test_cmc_get_returns_none_on_403_plan_insuficiente():
    """_cmc_get sigue devolviendo None en 403, igual que antes de la rotación."""
    with patch("src.crypto_client.get_settings", return_value=_settings_stub(cmc_keys=["key1", "key2"])):
        client = CryptoApiClient()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.get = AsyncMock(
            return_value=_mock_response({"status": {"error_message": "plan insuficiente"}}, status_code=403)
        )
        client._client = mock_http

        result = await client._cmc_get("v1/content/latest")
        assert result is None
        assert mock_http.get.call_count == 1
