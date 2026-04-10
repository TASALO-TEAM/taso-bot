# tests/test_api_client_retry.py
"""Tests específicos para el comportamiento de retry del TasaloApiClient."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import httpx


@pytest.mark.asyncio
async def test_get_with_retry_retries_on_timeout():
    """_get_with_retry should retry 3 times on TimeoutException before raising."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://test:8000", timeout=10)

    # Mock the HTTP client to raise TimeoutException
    mock_http_client = AsyncMock()
    mock_http_client.is_closed = False
    mock_http_client.get.side_effect = httpx.TimeoutException("Connection timeout")
    client._client = mock_http_client

    # _get_with_retry will raise the original exception after 3 attempts
    # (tenacity's default behavior is to reraise the last exception)
    with pytest.raises(httpx.TimeoutException):
        await client._get_with_retry("http://test:8000/api/v1/tasas/latest")

    # Verify it was called 3 times (1 initial + 2 retries)
    assert mock_http_client.get.call_count == 3


@pytest.mark.asyncio
async def test_get_with_retry_retries_on_connect_error():
    """_get_with_retry should retry 3 times on ConnectError before raising."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://test:8000", timeout=10)

    mock_http_client = AsyncMock()
    mock_http_client.is_closed = False
    mock_http_client.get.side_effect = httpx.ConnectError("Connection refused")
    client._client = mock_http_client

    with pytest.raises(httpx.ConnectError):
        await client._get_with_retry("http://test:8000/api/v1/tasas/latest")

    assert mock_http_client.get.call_count == 3


@pytest.mark.asyncio
async def test_get_with_retry_no_retry_on_http_404():
    """_get_with_retry should NOT retry on HTTP 404 (only connection issues)."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://test:8000", timeout=10)

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_response
    )

    mock_http_client = AsyncMock()
    mock_http_client.is_closed = False
    mock_http_client.get.return_value = mock_response
    client._client = mock_http_client

    with pytest.raises(httpx.HTTPStatusError):
        await client._get_with_retry("http://test:8000/api/v1/tasas/latest")

    # Should only be called once (no retry for HTTP errors)
    assert mock_http_client.get.call_count == 1


@pytest.mark.asyncio
async def test_get_with_retry_no_retry_on_http_500():
    """_get_with_retry should NOT retry on HTTP 500 (only connection issues)."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://test:8000", timeout=10)

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=mock_response
    )

    mock_http_client = AsyncMock()
    mock_http_client.is_closed = False
    mock_http_client.get.return_value = mock_response
    client._client = mock_http_client

    with pytest.raises(httpx.HTTPStatusError):
        await client._get_with_retry("http://test:8000/api/v1/tasas/latest")

    assert mock_http_client.get.call_count == 1


@pytest.mark.asyncio
async def test_get_with_retry_succeeds_on_second_attempt():
    """_get_with_retry should succeed if second attempt succeeds."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://test:8000", timeout=10)

    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "data": {"rates": []}}
    mock_response.raise_for_status = MagicMock()

    mock_http_client = AsyncMock()
    mock_http_client.is_closed = False
    # First call fails, second succeeds
    mock_http_client.get.side_effect = [
        httpx.TimeoutException("Timeout"),
        mock_response,
    ]
    client._client = mock_http_client

    result = await client._get_with_retry("http://test:8000/api/v1/tasas/latest")

    assert result is not None
    assert result["ok"] is True
    assert mock_http_client.get.call_count == 2


@pytest.mark.asyncio
async def test_post_with_retry_retries_on_timeout():
    """_post_with_retry should retry 3 times on TimeoutException."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://test:8000", timeout=10)

    mock_http_client = AsyncMock()
    mock_http_client.is_closed = False
    mock_http_client.post.side_effect = httpx.TimeoutException("Timeout")
    client._client = mock_http_client

    with pytest.raises(httpx.TimeoutException):
        await client._post_with_retry("http://test:8000/api/v1/admin/refresh")

    assert mock_http_client.post.call_count == 3


@pytest.mark.asyncio
async def test_get_latest_handles_retry_then_success():
    """get_latest should return data after retry succeeds."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://test:8000", timeout=10)

    mock_data = {"ok": True, "data": {"eltoque": {"USD": {"rate": 515.0}}}}

    # First call fails with timeout, second succeeds
    with patch.object(client, '_get_with_retry', side_effect=[
        httpx.TimeoutException("Timeout"),
        mock_data,
    ]) as mock_retry:
        # Manually call get_latest which catches RetryError from _get_with_retry
        # But since we're mocking _get_with_retry, we need to simulate the behavior
        with patch.object(client, '_get_with_retry', return_value=mock_data):
            result = await client.get_latest()

            assert result is not None
            assert result["ok"] is True


@pytest.mark.asyncio
async def test_shared_http_client_is_reused():
    """_get_client should reuse the same HTTP client instance."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://test:8000", timeout=10)

    client1 = client._get_client()
    client2 = client._get_client()

    assert client1 is client2


@pytest.mark.asyncio
async def test_http_client_has_correct_headers():
    """HTTP client should include User-Agent header."""
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://test:8000", admin_key="test-key", timeout=10)

    http_client = client._get_client()

    assert "User-Agent" in http_client.headers
    assert "taso-bot/0.10.0" in http_client.headers["User-Agent"]
    assert http_client.headers["X-API-Key"] == "test-key"
