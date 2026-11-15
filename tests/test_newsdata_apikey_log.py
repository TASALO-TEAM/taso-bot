"""H-053: la apikey de NewsData va en la query y str(HTTPStatusError) incluye
la URL completa; registrar la excepcion filtraba la clave al log.

Se mide solo el logger del cliente: el logger `httpx` (que tambien escribe
la URL en INFO) ya esta silenciado en produccion por src/main.py.
"""

import logging
from types import SimpleNamespace

import httpx
import pytest

from src.newsdata_client import NewsDataClient

CLAVE = "SECRETO-NEWSDATA-123"
LOGGER = "src.newsdata_client"


def _cliente(handler) -> NewsDataClient:
    c = NewsDataClient()
    c.settings = SimpleNamespace(newsdata_api_key=CLAVE)
    c._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return c


def _mensajes(caplog) -> str:
    return "\n".join(r.getMessage() for r in caplog.records if r.name == LOGGER)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 429, 500, 503])
async def test_error_http_no_filtra_apikey_al_log(status, caplog):
    c = _cliente(lambda request: httpx.Response(status, request=request))

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        resultado = await c.get_crypto_news()

    assert resultado is None
    assert CLAVE not in _mensajes(caplog)
    assert str(status) in _mensajes(caplog)


@pytest.mark.asyncio
async def test_error_de_red_no_filtra_apikey_al_log(caplog):
    def handler(request):
        raise httpx.ConnectError("sin red", request=request)

    c = _cliente(handler)

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        resultado = await c.get_crypto_news()

    assert resultado is None
    assert CLAVE not in _mensajes(caplog)


@pytest.mark.asyncio
async def test_respuesta_ok_sigue_funcionando():
    c = _cliente(lambda request: httpx.Response(
        200, request=request,
        json={"status": "success", "results": [{"title": "T", "link": "https://x"}]},
    ))

    resultado = await c.get_crypto_news()

    assert resultado and resultado[0]["title"] == "T"
