"""F7-T2: respuestas hostiles de las fuentes del explorador. Sin red (MockTransport).

Regla: ante cualquier cuerpo inesperado, el cliente debe lanzar ExplorerError (que el handler
traduce a un mensaje fijo) o devolver un dato vacio; nunca otra excepcion.
"""
import asyncio

import httpx
import pytest

from src.explorer import sources
from src.explorer.sources import ExplorerError

DIR = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
TXID = "a" * 64
USUARIO = "alice"

# Cuerpos validos como JSON pero con forma incorrecta.
FORMAS = [[], {}, "texto", 0, None, [1, 2, 3], {"result": "x"}, [[], []], [None], ["x"], {"a": {"b": [None]}}]

_OK_ADDR = {"chain_stats": {"funded_txo_sum": 1, "spent_txo_sum": 0, "tx_count": 1},
            "mempool_stats": {"funded_txo_sum": 0, "spent_txo_sum": 0, "tx_count": 0}}


@pytest.fixture(autouse=True)
def _limpio():
    sources.reset()
    sources._sem = asyncio.Semaphore(4)
    yield
    sources.usar_cliente(None)
    sources.reset()


def _con(respuesta):
    sources.usar_cliente(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: respuesta)))


def _ok_o_explorer_error(coro):
    try:
        return asyncio.run(coro)
    except ExplorerError:
        return None


@pytest.mark.parametrize("forma", FORMAS)
def test_btc_address_forma_rara(forma):
    _con(httpx.Response(200, json=forma))
    _ok_o_explorer_error(sources.btc_address(DIR))


@pytest.mark.parametrize("forma", FORMAS)
def test_btc_address_txs_forma_rara(forma):
    _con(httpx.Response(200, json=forma))
    _ok_o_explorer_error(sources.btc_address_txs(DIR))


@pytest.mark.parametrize("forma", FORMAS)
def test_btc_tx_forma_rara(forma):
    _con(httpx.Response(200, json=forma))
    _ok_o_explorer_error(sources.btc_tx(TXID))


@pytest.mark.parametrize("forma", FORMAS)
def test_hive_cuenta_forma_rara(forma):
    _con(httpx.Response(200, json={"result": forma}))
    _ok_o_explorer_error(sources.hive_cuenta(USUARIO))


@pytest.mark.parametrize("forma", FORMAS)
def test_hive_tx_forma_rara(forma):
    _con(httpx.Response(200, json={"result": forma}))
    _ok_o_explorer_error(sources.hive_tx(TXID))


@pytest.mark.parametrize("cuerpo", [b"", b"<html>502</html>", b"\xff\xfe\x00", b"{", b"[" * 5000])
def test_cuerpo_no_json_o_binario(cuerpo):
    _con(httpx.Response(200, content=cuerpo))
    with pytest.raises(ExplorerError):
        asyncio.run(sources.btc_address(DIR))


@pytest.mark.parametrize("codigo", [401, 403, 429, 500, 502, 503, 504])
def test_codigos_de_error_son_fuente_no_disponible(codigo):
    _con(httpx.Response(codigo))
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.btc_address(DIR))
    assert e.value.codigo == "fuente_no_disponible"


def test_excepcion_de_red_es_fuente_no_disponible():
    def h(r):
        raise httpx.ConnectError("sin ruta")
    sources.usar_cliente(httpx.AsyncClient(transport=httpx.MockTransport(h)))
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.btc_tx(TXID))
    assert e.value.codigo == "fuente_no_disponible"


def test_timeout_es_fuente_no_disponible():
    def h(r):
        raise httpx.ReadTimeout("lento")
    sources.usar_cliente(httpx.AsyncClient(transport=httpx.MockTransport(h)))
    with pytest.raises(ExplorerError):
        asyncio.run(sources.hive_cuenta(USUARIO))


def test_respuesta_gigante_se_corta_sin_leerla_entera():
    _con(httpx.Response(200, content=b"x" * (sources.MAX_BYTES + 10)))
    with pytest.raises(ExplorerError):
        asyncio.run(sources.btc_address(DIR))


def test_json_profundamente_anidado_no_revienta():
    _con(httpx.Response(200, content=b"[" * 20000 + b"]" * 20000))
    _ok_o_explorer_error(sources.btc_address(DIR))


def test_cache_no_crece_sin_limite_con_muchas_consultas():
    _con(httpx.Response(200, json=_OK_ADDR))

    async def rafaga():
        for i in range(sources.MAX_CACHE * 3):
            await sources.btc_address(f"1addr{i}")
    asyncio.run(rafaga())
    assert len(sources._cache) <= sources.MAX_CACHE


def test_rafaga_concurrente_misma_clave_hace_una_sola_llamada():
    llamadas = []

    def h(r):
        llamadas.append(1)
        return httpx.Response(200, json=_OK_ADDR)
    sources.usar_cliente(httpx.AsyncClient(transport=httpx.MockTransport(h)))

    async def rafaga():
        return await asyncio.gather(*[sources.btc_address(DIR) for _ in range(50)])
    res = asyncio.run(rafaga())
    assert len(llamadas) == 1 and all(r["saldo_sats"] == 1 for r in res)
