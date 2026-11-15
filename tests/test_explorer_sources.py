"""Clientes de red del explorador (F4-T4): sin red real, con httpx.MockTransport."""
import asyncio
import json

import httpx
import pytest

from src.explorer import sources
from src.explorer.sources import ExplorerError

DIR = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
TXID = "a" * 64


@pytest.fixture(autouse=True)
def _limpio():
    sources.reset()
    sources._sem = asyncio.Semaphore(4)
    yield
    sources.usar_cliente(None)
    sources.reset()


def _cliente(handler):
    llamadas = []

    def h(req):
        llamadas.append(req)
        return handler(req)

    sources.usar_cliente(httpx.AsyncClient(transport=httpx.MockTransport(h)))
    return llamadas


def _addr(rec=5000, gas=2000, txs=3):
    return {"chain_stats": {"funded_txo_sum": rec, "spent_txo_sum": gas, "tx_count": txs},
            "mempool_stats": {"funded_txo_sum": 100, "spent_txo_sum": 0, "tx_count": 1}}


def test_btc_address_calcula_saldo_y_pendiente():
    _cliente(lambda r: httpx.Response(200, json=_addr()))
    r = asyncio.run(sources.btc_address(DIR))
    assert r["saldo_sats"] == 3000 and r["pendiente_sats"] == 100 and r["tx_count"] == 3


def test_btc_address_usa_respaldo_si_la_primera_fuente_falla():
    def h(r):
        return httpx.Response(429) if "mempool.space" in str(r.url) else httpx.Response(200, json=_addr())
    ll = _cliente(h)
    assert asyncio.run(sources.btc_address(DIR))["saldo_sats"] == 3000
    assert len(ll) == 2


def test_btc_address_no_encontrado_si_ambas_dicen_404():
    _cliente(lambda r: httpx.Response(404))
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.btc_address(DIR))
    assert e.value.codigo == "no_encontrado"


def test_btc_address_fuente_no_disponible_si_ambas_fallan():
    _cliente(lambda r: httpx.Response(503))
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.btc_address(DIR))
    assert e.value.codigo == "fuente_no_disponible"


def test_btc_address_respuesta_invalida():
    _cliente(lambda r: httpx.Response(200, json={"otra": "cosa"}))
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.btc_address(DIR))
    assert e.value.codigo == "respuesta_invalida"


def test_json_malo_cuenta_como_fallo_de_fuente():
    _cliente(lambda r: httpx.Response(200, content=b"<html>no es json</html>"))
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.btc_address(DIR))
    assert e.value.codigo == "fuente_no_disponible"


def test_respuesta_demasiado_grande_se_descarta():
    _cliente(lambda r: httpx.Response(200, content=b"[" + b"0," * sources.MAX_BYTES + b"0]"))
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.btc_address(DIR))
    assert e.value.codigo == "fuente_no_disponible"


def test_segunda_llamada_sale_del_cache():
    ll = _cliente(lambda r: httpx.Response(200, json=_addr()))
    asyncio.run(sources.btc_address(DIR))
    asyncio.run(sources.btc_address(DIR))
    assert len(ll) == 1


def test_llamadas_simultaneas_comparten_una_sola_carga():
    ll = _cliente(lambda r: httpx.Response(200, json=_addr()))

    async def varias():
        return await asyncio.gather(*(sources.btc_address(DIR) for _ in range(5)))
    asyncio.run(varias())
    assert len(ll) == 1


def test_btc_tx_confirmaciones_desde_la_punta():
    tx = {"status": {"confirmed": True, "block_height": 100, "block_time": 1700000000},
          "size": 200, "weight": 800, "fee": 1500,
          "vin": [{}], "vout": [{"value": 1000}, {"value": 2000}]}

    def h(r):
        if str(r.url).endswith("/blocks/tip/height"):
            return httpx.Response(200, content=b"105")
        return httpx.Response(200, json=tx)
    _cliente(h)
    r = asyncio.run(sources.btc_tx(TXID))
    assert r["confirmaciones"] == 6 and r["total_salidas_sats"] == 3000 and r["fee_sats"] == 1500
    assert r["fecha"] == "2023-11-14 22:13 UTC"


def test_btc_tx_sin_confirmar():
    tx = {"status": {"confirmed": False}, "vin": [{}], "vout": [{"value": 5}]}
    _cliente(lambda r: httpx.Response(200, json=tx))
    r = asyncio.run(sources.btc_tx(TXID))
    assert r["confirmada"] is False and r["confirmaciones"] == 0 and r["altura"] is None


def test_btc_address_txs_calcula_neto_y_omite_filas_malas():
    lista = [
        {"txid": "b" * 64, "status": {"confirmed": True, "block_height": 9, "block_time": 1700000000},
         "vin": [{"prevout": {"scriptpubkey_address": DIR, "value": 400}}],
         "vout": [{"scriptpubkey_address": DIR, "value": 100}, {"scriptpubkey_address": "otra", "value": 290}]},
        {"roto": True},
    ]
    _cliente(lambda r: httpx.Response(200, json=lista))
    r = asyncio.run(sources.btc_address_txs(DIR))
    assert len(r) == 1 and r[0]["neto_sats"] == -300 and r[0]["confirmada"] is True


def _rpc(resultado):
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": resultado})


def test_hive_cuenta_convierte_vests_a_hp_y_no_filtra_texto_libre():
    cuenta = {"balance": "10.500 HIVE", "hbd_balance": "2.000 HBD", "vesting_shares": "1000.000000 VESTS",
              "post_count": 42, "created": "2020-01-02T03:04:05", "last_post": "2026-11-01T00:00:00",
              "json_metadata": "<script>alert(1)</script>", "memo_key": "x"}
    props = {"total_vesting_fund_hive": "500.000 HIVE", "total_vesting_shares": "1000000.000000 VESTS"}

    def h(r):
        m = json.loads(r.content)["method"]
        return _rpc([cuenta] if m == "condenser_api.get_accounts" else props)
    _cliente(h)
    r = asyncio.run(sources.hive_cuenta("alice"))
    assert r["hive"] == 10.5 and r["hbd"] == 2.0 and abs(r["hp"] - 0.5) < 1e-9
    assert r["creada"] == "2020-01-02" and r["ultimo_post"] == "2026-11-01"
    assert "script" not in json.dumps(r)


def test_hive_cuenta_inexistente():
    _cliente(lambda r: _rpc([]))
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.hive_cuenta("noexiste"))
    assert e.value.codigo == "no_encontrado"


def test_hive_usa_otro_nodo_si_el_primero_cae():
    def h(r):
        if "api.hive.blog" in str(r.url):
            return httpx.Response(502)
        m = json.loads(r.content)["method"]
        return _rpc([{"balance": "1.000 HIVE"}] if m == "condenser_api.get_accounts"
                    else {"total_vesting_fund_hive": "1.000 HIVE", "total_vesting_shares": "1.000000 VESTS"})
    _cliente(h)
    assert asyncio.run(sources.hive_cuenta("alice"))["hive"] == 1.0


def test_hive_tx_extrae_transferencia_sin_memo():
    res = {"block_num": 99, "operations": [
        {"type": "transfer_operation",
         "value": {"from": "alice", "to": "bob", "amount": {"amount": "1500", "precision": 3, "nai": "@@000000021"},
                   "memo": "<b>hola</b>"}},
        {"type": "Tipo<raro>", "value": {}}]}
    _cliente(lambda r: _rpc(res))
    r = asyncio.run(sources.hive_tx(TXID))
    assert r["bloque"] == 99 and r["total_operaciones"] == 2
    assert r["operaciones"][0]["transferencia"] == {"de": "alice", "a": "bob", "monto": 1.5, "moneda": "HIVE"}
    assert r["operaciones"][1]["tipo"] == "desconocida"
    assert "hola" not in json.dumps(r)


def test_hive_tx_con_error_del_nodo_es_no_encontrado():
    _cliente(lambda r: httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32000}}))
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.hive_tx(TXID))
    assert e.value.codigo == "no_encontrado"


def test_el_cache_no_crece_sin_limite():
    _cliente(lambda r: httpx.Response(200, json=_addr()))

    async def muchas():
        for i in range(sources.MAX_CACHE + 20):
            await sources.btc_address(f"1Dir{i}")
    asyncio.run(muchas())
    assert len(sources._cache) <= sources.MAX_CACHE
