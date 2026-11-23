"""F4-T9: explorador EVM (direccion en 5 redes, hash solo en Ethereum). Sin red: MockTransport."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.explorer import handler as h
from src.explorer import present as p
from src.explorer import sources
from src.explorer.classify import Entrada
from src.explorer.guard import UserLimiter
from src.explorer.sources import ExplorerError

ADDR = "0x" + "ab" * 20
OTRA = "0x" + "cd" * 20
HASH = "0x" + "ef" * 32
NODOS = ("ethereum-rpc", "bsc-rpc", "polygon-bor-rpc", "base-rpc", "arbitrum-one-rpc")


@pytest.fixture(autouse=True)
def _limpio():
    sources.reset()
    sources._sem = asyncio.Semaphore(4)
    yield
    sources.usar_cliente(None)
    sources.reset()


def _nodo(resultados, caidos=()):
    """resultados: {metodo: valor | funcion(host)->valor}; caidos: trozos de host que dan 503."""
    def h_(req):
        host = req.url.host
        if any(c in host for c in caidos):
            return httpx.Response(503)
        v = resultados[json.loads(req.content)["method"]]
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": v(host) if callable(v) else v})
    sources.usar_cliente(httpx.AsyncClient(transport=httpx.MockTransport(h_)))


def _addr_ok(saldo="0x1", nonce="0x1", code="0x"):
    return {"eth_getBalance": saldo, "eth_getTransactionCount": nonce, "eth_getCode": code}


def test_address_solo_muestra_redes_con_actividad():
    _nodo(_addr_ok(saldo=lambda host: hex(10**18) if "ethereum-rpc" in host else "0x0",
                   nonce=lambda host: "0x5" if "ethereum-rpc" in host else "0x0"))
    d = asyncio.run(sources.evm_address(ADDR))
    assert [r["red"] for r in d["redes"]] == ["Ethereum"]
    r = d["redes"][0]
    assert r["saldo_wei"] == 10**18 and r["nonce"] == 5 and r["tipo"] == "cuenta"
    assert d["sin_respuesta"] == []


def test_address_sin_actividad_en_ninguna_red_no_es_error():
    _nodo(_addr_ok(saldo="0x0", nonce="0x0"))
    d = asyncio.run(sources.evm_address(ADDR))
    assert d["redes"] == [] and d["sin_respuesta"] == []


@pytest.mark.parametrize("code,tipo", [("0x", "cuenta"), ("0xef0100" + "ab" * 20, "delegacion"),
                                       ("0x6080604052", "contrato")])
def test_address_distingue_cuenta_delegacion_7702_y_contrato(code, tipo):
    _nodo(_addr_ok(code=code))
    d = asyncio.run(sources.evm_address(ADDR))
    assert len(d["redes"]) == 5 and all(r["tipo"] == tipo for r in d["redes"])


def test_address_una_red_caida_se_anota_y_las_demas_responden():
    _nodo(_addr_ok(), caidos=("base-rpc",))
    d = asyncio.run(sources.evm_address(ADDR))
    assert len(d["redes"]) == 4 and d["sin_respuesta"] == ["Base"]


def test_address_todas_caidas_es_fuente_no_disponible():
    _nodo(_addr_ok(), caidos=("publicnode",))
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.evm_address(ADDR))
    assert e.value.codigo == "fuente_no_disponible"


@pytest.mark.parametrize("malo", ["0xzz", "12", "0x" + "f" * 65, 5, None, ""])
def test_address_hex_invalido_o_enorme_no_pasa(malo):
    _nodo(_addr_ok(saldo=malo))
    with pytest.raises(ExplorerError):
        asyncio.run(sources.evm_address(ADDR))


def _tx_ok(bloque="0x60", status="0x1", tip="0x64", **extra):
    tx = {"blockNumber": bloque, "from": ADDR, "to": OTRA, "value": hex(10**18)}
    tx.update(extra)
    rec = None if bloque is None else {"status": status, "blockNumber": bloque}
    return {"eth_getTransactionByHash": tx, "eth_getTransactionReceipt": rec, "eth_blockNumber": tip}


def test_tx_confirmada_exitosa_con_confirmaciones():
    _nodo(_tx_ok())
    d = asyncio.run(sources.evm_tx(HASH))
    assert d["estado"] == "exitosa" and d["bloque"] == 96 and d["confirmaciones"] == 5
    assert d["de"] == ADDR and d["a"] == OTRA and d["valor_wei"] == 10**18


def test_tx_fallida():
    _nodo(_tx_ok(status="0x0"))
    assert asyncio.run(sources.evm_tx(HASH))["estado"] == "fallida"


def test_tx_pendiente_sin_recibo():
    _nodo(_tx_ok(bloque=None))
    d = asyncio.run(sources.evm_tx(HASH))
    assert d["estado"] == "pendiente" and d["bloque"] is None and d["confirmaciones"] == 0


def test_tx_creacion_de_contrato_no_tiene_destino():
    _nodo(_tx_ok(to=None))
    assert asyncio.run(sources.evm_tx(HASH))["a"] is None


def test_tx_inexistente_es_no_encontrado():
    _nodo({"eth_getTransactionByHash": None, "eth_getTransactionReceipt": None, "eth_blockNumber": "0x64"})
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.evm_tx(HASH))
    assert e.value.codigo == "no_encontrado"


def test_tx_nodo_caido_es_fuente_no_disponible():
    _nodo(_tx_ok(), caidos=("ethereum-rpc",))
    with pytest.raises(ExplorerError) as e:
        asyncio.run(sources.evm_tx(HASH))
    assert e.value.codigo == "fuente_no_disponible"


# Respuestas con forma rara: ExplorerError o dato, nunca otra excepcion.
FORMAS = [[], {}, "texto", 0, None, {"result": "x"}, {"result": {"value": 5}}, {"result": {"from": 7}},
          {"result": {"blockNumber": 5}}, {"error": {"code": -32000}}, {"a": {"b": [None]}}]


def _ok_o_explorer_error(coro):
    try:
        return asyncio.run(coro)
    except ExplorerError:
        return None


@pytest.mark.parametrize("forma", FORMAS)
def test_forma_rara_en_address(forma):
    sources.usar_cliente(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=forma))))
    _ok_o_explorer_error(sources.evm_address(ADDR))


@pytest.mark.parametrize("forma", FORMAS)
def test_forma_rara_en_tx(forma):
    sources.usar_cliente(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=forma))))
    _ok_o_explorer_error(sources.evm_tx(HASH))


# ───────────── presentacion ─────────────

E_ADDR = Entrada("evm_address", ADDR, "evm")
E_TX = Entrada("evm_tx", HASH, "evm")
D_ADDR = {"direccion": ADDR, "sin_respuesta": [],
          "redes": [{"red": "Ethereum", "simbolo": "ETH", "saldo_wei": 10**18, "nonce": 5, "tipo": "cuenta"},
                    {"red": "BNB Chain", "simbolo": "BNB", "saldo_wei": 2 * 10**17, "nonce": 1, "tipo": "delegacion"},
                    {"red": "Polygon", "simbolo": "POL", "saldo_wei": 0, "nonce": 9, "tipo": "contrato"}]}
D_TX = {"hash": HASH, "estado": "exitosa", "bloque": 96, "confirmaciones": 5, "de": ADDR, "a": OTRA,
        "valor_wei": 10**18}


def test_present_address_muestra_saldo_nonce_y_tipo_por_red():
    txt = p.formatear(E_ADDR, D_ADDR)
    assert "Ethereum" in txt and "1.000000 ETH" in txt and "0.200000 BNB" in txt
    assert "7702" in txt and "contrato" in txt.lower()
    assert "etherscan.io/address/" + ADDR in txt and len(txt) <= p.MAX


def test_present_address_sin_actividad_y_con_redes_sin_respuesta():
    txt = p.formatear(E_ADDR, {"direccion": ADDR, "redes": [], "sin_respuesta": ["Base"]})
    assert "sin actividad" in txt.lower() and "Base" in txt and "sin respuesta" in txt.lower()


def test_present_address_aclara_que_no_hay_tokens_ni_usd():
    txt = p.formatear(E_ADDR, D_ADDR).lower()
    assert "tokens" in txt and "$" not in txt


def test_present_tx_estados_y_aviso_solo_ethereum():
    txt = p.formatear(E_TX, D_TX)
    assert "5" in txt and "96" in txt and "1.000000 ETH" in txt and "otras redes" in txt.lower()
    assert "etherscan.io/tx/" + HASH in txt
    assert "fall" in p.formatear(E_TX, {**D_TX, "estado": "fallida"}).lower()
    pend = p.formatear(E_TX, {**D_TX, "estado": "pendiente", "bloque": None, "confirmaciones": 0}).lower()
    assert "sin confirmar" in pend


def test_present_tx_sin_destino_es_creacion_de_contrato():
    assert "contrato" in p.formatear(E_TX, {**D_TX, "a": None}).lower()


# ───────────── handler ─────────────

def _upd(texto, uid=7):
    m = MagicMock()
    m.text = texto
    m.reply_text = AsyncMock()
    m.reply_chat_action = AsyncMock()
    u = MagicMock()
    u.message = m
    u.effective_user.id = uid
    return u, m


def _ctx():
    c = MagicMock()
    c.args = None
    c.user_data = {}
    return c


@pytest.fixture
def _consulta(monkeypatch):
    monkeypatch.setattr(h, "LIMITER", UserLimiter(max_calls=1, window=60.0))
    c = AsyncMock(return_value=(D_ADDR, None, None))
    monkeypatch.setattr(h, "_consultar", c)
    return c


def test_handler_consulta_la_direccion_evm_y_gasta_cupo(_consulta):
    u, m = _upd(ADDR)
    asyncio.run(h.explorer_text(u, _ctx()))
    _consulta.assert_awaited_once()
    assert "Ethereum" in m.reply_text.await_args.args[0]
    assert m.reply_text.await_args.kwargs["parse_mode"] == "HTML"
    asyncio.run(h.explorer_text(u, _ctx()))
    assert _consulta.await_count == 1 and "demasiadas" in m.reply_text.await_args.args[0]


def test_handler_consulta_el_hash_evm(_consulta):
    _consulta.return_value = (D_TX, None, None)
    u, m = _upd(HASH)
    asyncio.run(h.explorer_text(u, _ctx()))
    assert "otras redes" in m.reply_text.await_args.args[0].lower()


def test_consultar_real_enruta_los_dos_tipos_nuevos(monkeypatch):
    monkeypatch.setattr(sources, "evm_address", AsyncMock(return_value=D_ADDR))
    monkeypatch.setattr(sources, "evm_tx", AsyncMock(return_value=D_TX))
    assert asyncio.run(h._consultar_real(E_ADDR)) == (D_ADDR, None, None)
    assert asyncio.run(h._consultar_real(E_TX)) == (D_TX, None, None)
