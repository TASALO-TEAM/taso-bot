# tests/test_api_client.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

@pytest_asyncio.fixture
async def mock_httpx_client():
    """Fixture para mockear httpx.AsyncClient."""
    with patch('httpx.AsyncClient') as mock_client:
        yield mock_client

def create_mock_response(mock_data):
    """Crear un mock de respuesta HTTP."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_data
    mock_resp.raise_for_status = MagicMock()
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
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_instance = AsyncMock()
        mock_response = create_mock_response(mock_response_data)
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_client_class.return_value = mock_instance
        
        client = TasaloApiClient(api_url="http://localhost:8000", timeout=15)
        result = await client.get_latest()
        
        assert result is not None
        assert result['ok'] is True
        assert 'eltoque' in result['data']

@pytest.mark.asyncio
async def test_get_latest_timeout():
    """get_latest devuelve None cuando hay timeout."""
    from src.api_client import TasaloApiClient
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = httpx.TimeoutException("Timeout")
        mock_instance.__aenter__.return_value = mock_instance
        mock_client_class.return_value = mock_instance
        
        client = TasaloApiClient(api_url="http://localhost:8000", timeout=15)
        result = await client.get_latest()
        
        assert result is None

@pytest.mark.asyncio
async def test_get_latest_connection_error():
    """get_latest devuelve None cuando hay error de conexión."""
    from src.api_client import TasaloApiClient
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = httpx.ConnectError("Connection failed")
        mock_instance.__aenter__.return_value = mock_instance
        mock_client_class.return_value = mock_instance
        
        client = TasaloApiClient(api_url="http://localhost:8000", timeout=15)
        result = await client.get_latest()
        
        assert result is None

@pytest.mark.asyncio
async def test_admin_refresh_requires_api_key():
    """admin_refresh usa el header X-API-Key."""
    from src.api_client import TasaloApiClient

    mock_response_data = {"ok": True, "data": {"refreshed_at": "2026-03-22T14:30:00Z"}}

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_instance = AsyncMock()
        mock_response = create_mock_response(mock_response_data)
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_client_class.return_value = mock_instance

        client = TasaloApiClient(
            api_url="http://localhost:8000",
            admin_key="test_secret_key"
        )
        result = await client.admin_refresh()

        # Verificar que se llamó con el header correcto
        mock_instance.post.assert_called_once()
        call_kwargs = mock_instance.post.call_args[1]
        assert call_kwargs['headers']['X-API-Key'] == 'test_secret_key'
        assert result is not None


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

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_instance = AsyncMock()
        mock_response = create_mock_response(mock_data)
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_client_class.return_value = mock_instance

        client = TasaloApiClient(api_url="http://test:8000")
        result = await client.get_history(source="eltoque", currency="USD", days=7)

        assert result is not None
        assert result["ok"] is True
        assert len(result["data"]) == 2
        assert result["data"][0]["sell_rate"] == 365.0


@pytest.mark.asyncio
async def test_get_history_default_params():
    """Test get_history con parámetros por defecto (source=eltoque, currency=USD, days=7)."""
    from src.api_client import TasaloApiClient

    mock_data = {"ok": True, "data": [], "count": 0}

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_instance = AsyncMock()
        mock_response = create_mock_response(mock_data)
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_client_class.return_value = mock_instance

        client = TasaloApiClient(api_url="http://test:8000")
        # Llamar sin parámetros explícitos (usar defaults)
        result = await client.get_history()

        assert result is not None
        assert result["data"] == []


@pytest.mark.asyncio
async def test_get_history_timeout():
    """Test get_history con timeout."""
    from src.api_client import TasaloApiClient

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = httpx.TimeoutException("Timeout")
        mock_instance.__aenter__.return_value = mock_instance
        mock_client_class.return_value = mock_instance

        client = TasaloApiClient(api_url="http://test:8000", timeout=1)
        result = await client.get_history()

        assert result is None


@pytest.mark.asyncio
async def test_get_history_error_response():
    """Test get_history con respuesta de error."""
    from src.api_client import TasaloApiClient

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_instance = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal error"}
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_client_class.return_value = mock_instance

        client = TasaloApiClient(api_url="http://test:8000")
        result = await client.get_history()

        assert result is None
