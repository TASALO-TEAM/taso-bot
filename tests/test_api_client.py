# tests/test_api_client.py
"""Tests para TasaloApiClient con retry logic."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import httpx

def create_mock_response(mock_data, status_code=200):
    """Crear un mock de respuesta HTTP."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_data
    mock_resp.raise_for_status = MagicMock()
    mock_resp.status_code = status_code
    return mock_resp


@pytest.mark.asyncio
async def test_get_latest_success():
    """get_latest devuelve datos cuando la API responde correctamente."""
    from src.api_client import TasaloApiClient

    mock_response_data = {
        "ok": True,
        "data": {
            "eltoque": {"USD": {"rate": 365.0, "change": "up"}},
            "cadeca": {"USD": {"buy": 120.0, "sell": 125.0}},
            "bcc": {"USD": 24.0}
        },
        "updated_at": "2026-03-22T14:30:00Z"
    }

    client = TasaloApiClient(api_url="http://localhost:8000", timeout=15)

    with patch.object(client, '_get_with_retry', return_value=mock_response_data) as mock_retry:
        result = await client.get_latest()

        assert result is not None
        assert result['ok'] is True
        assert 'eltoque' in result['data']
        mock_retry.assert_called_once()


@pytest.mark.asyncio
async def test_get_latest_timeout_after_retries():
    """get_latest devuelve None tras 3 reintentos por timeout."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://localhost:8000", timeout=15)

    with patch.object(client, '_get_with_retry', side_effect=httpx.TimeoutException("Timeout")):
        result = await client.get_latest()
        assert result is None


@pytest.mark.asyncio
async def test_get_latest_connection_error_after_retries():
    """get_latest devuelve None tras 3 reintentos por error de conexión."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://localhost:8000", timeout=15)

    with patch.object(client, '_get_with_retry', side_effect=httpx.ConnectError("Connection failed")):
        result = await client.get_latest()
        assert result is None


@pytest.mark.asyncio
async def test_admin_refresh_requires_api_key():
    """admin_refresh retorna None sin API key."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://localhost:8000", admin_key=None)
    result = await client.admin_refresh()
    assert result is None


@pytest.mark.asyncio
async def test_admin_refresh_with_api_key():
    """admin_refresh usa el header X-API-Key correctamente."""
    from src.api_client import TasaloApiClient

    mock_response_data = {"ok": True, "data": {"refreshed_at": "2026-03-22T14:30:00Z"}}

    client = TasaloApiClient(api_url="http://localhost:8000", admin_key="test_secret_key")

    with patch.object(client, '_post_with_retry', return_value=mock_response_data) as mock_retry:
        result = await client.admin_refresh()

        assert result is not None
        assert result['ok'] is True
        mock_retry.assert_called_once()


@pytest.mark.asyncio
async def test_get_history_success():
    """Test get_history con respuesta exitosa."""
    from src.api_client import TasaloApiClient

    mock_data = {
        "ok": True,
        "data": [
            {"source": "eltoque", "currency": "USD", "sell_rate": 365.0, "fetched_at": "2026-03-22T14:30:00Z"},
            {"source": "eltoque", "currency": "USD", "sell_rate": 360.0, "fetched_at": "2026-03-21T14:30:00Z"},
        ],
        "count": 2
    }

    client = TasaloApiClient(api_url="http://test:8000")

    with patch.object(client, '_get_with_retry', return_value=mock_data) as mock_retry:
        result = await client.get_history(source="eltoque", currency="USD", days=7)

        assert result is not None
        assert result["ok"] is True
        assert len(result["data"]) == 2
        assert result["data"][0]["sell_rate"] == 365.0


@pytest.mark.asyncio
async def test_get_history_default_params():
    """Test get_history con parámetros por defecto."""
    from src.api_client import TasaloApiClient

    mock_data = {"ok": True, "data": [], "count": 0}

    client = TasaloApiClient(api_url="http://test:8000")

    with patch.object(client, '_get_with_retry', return_value=mock_data):
        result = await client.get_history()

        assert result is not None
        assert result["data"] == []


@pytest.mark.asyncio
async def test_admin_status_requires_api_key():
    """admin_status retorna None sin API key."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://localhost:8000", admin_key=None)
    result = await client.admin_status()
    assert result is None


@pytest.mark.asyncio
async def test_admin_status_with_api_key():
    """admin_status obtiene estado del scheduler.

    Forma real desde Fase 2 (docs/plans/2026-07-08-status-command-v2.md):
    {ok, is_scheduler_running, jobs: [...]}, sin envoltorio "data".
    """
    from src.api_client import TasaloApiClient

    mock_data = {
        "ok": True,
        "is_scheduler_running": True,
        "jobs": [
            {"id": "refresh_all", "name": "Refresh de tasas", "next_run_at": "2026-03-22T14:35:00Z"},
        ],
    }

    client = TasaloApiClient(api_url="http://localhost:8000", admin_key="test_key")

    with patch.object(client, '_get_with_retry', return_value=mock_data):
        result = await client.admin_status()

        assert result is not None
        assert result["is_scheduler_running"] is True
        assert result["jobs"][0]["id"] == "refresh_all"


@pytest.mark.asyncio
async def test_get_eltoque_success():
    """get_eltoque devuelve tasas de ElToque."""
    from src.api_client import TasaloApiClient

    mock_data = {"ok": True, "data": {"eltoque": {"USD": {"rate": 515.0}}}}

    client = TasaloApiClient(api_url="http://test:8000")

    with patch.object(client, '_get_with_retry', return_value=mock_data):
        result = await client.get_eltoque()

        assert result is not None
        assert result["ok"] is True


@pytest.mark.asyncio
async def test_get_cadeca_success():
    """get_cadeca devuelve tasas de CADECA."""
    from src.api_client import TasaloApiClient

    mock_data = {"ok": True, "data": {"cadeca": {"USD": {"buy": 120.0, "sell": 125.0}}}}

    client = TasaloApiClient(api_url="http://test:8000")

    with patch.object(client, '_get_with_retry', return_value=mock_data):
        result = await client.get_cadeca()

        assert result is not None


@pytest.mark.asyncio
async def test_get_bcc_success():
    """get_bcc devuelve tasas de BCC."""
    from src.api_client import TasaloApiClient

    mock_data = {"ok": True, "data": {"bcc": {"USD": 24.0}}}

    client = TasaloApiClient(api_url="http://test:8000")

    with patch.object(client, '_get_with_retry', return_value=mock_data):
        result = await client.get_bcc()

        assert result is not None


@pytest.mark.asyncio
async def test_get_stats_summary_requires_api_key():
    """get_stats_summary retorna None sin API key."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://localhost:8000", admin_key=None)
    result = await client.get_stats_summary()
    assert result is None


@pytest.mark.asyncio
async def test_get_stats_summary_success():
    """get_stats_summary obtiene estadísticas."""
    from src.api_client import TasaloApiClient

    mock_data = {"ok": True, "data": {"total_commands": 100}}

    client = TasaloApiClient(api_url="http://localhost:8000", admin_key="test_key")

    with patch.object(client, '_get_with_retry', return_value=mock_data):
        result = await client.get_stats_summary()

        assert result is not None
        assert result["data"]["total_commands"] == 100


@pytest.mark.asyncio
async def test_close_client():
    """close cierra el cliente HTTP correctamente."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://localhost:8000")

    # Crear un mock client
    mock_http_client = AsyncMock()
    mock_http_client.is_closed = False
    client._client = mock_http_client

    await client.close()

    mock_http_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_close_already_closed_client():
    """close no falla si el cliente ya está cerrado."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://localhost:8000")

    mock_http_client = AsyncMock()
    mock_http_client.is_closed = True
    client._client = mock_http_client

    await client.close()

    mock_http_client.aclose.assert_not_called()
