"""Clientes de red del explorador (F4-T4). Solo lectura, sin claves.

Fuentes (probadas 2026-11-15, ver registro/F4-fuentes.md): mempool.space y Blockstream
(Esplora) para Bitcoin; api.hive.blog, api.deathwing.me y api.openhive.network para Hive.
Todo lo que devuelven los terceros se trata como dato no confiable: aqui solo se extraen
campos numericos, fechas y nombres validados; nunca texto libre (memos, descripciones).
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone

import httpx

from src.explorer.classify import es_nombre_hive

logger = logging.getLogger(__name__)

MEMPOOL = "https://mempool.space/api"
ESPLORA = "https://blockstream.info/api"
HIVE_NODOS = ("https://api.hive.blog", "https://api.deathwing.me", "https://api.openhive.network")
TIMEOUT = httpx.Timeout(8.0, connect=4.0)
MAX_BYTES = 400_000      # /address/<a>/txs de una direccion activa pesa ~160 KB
MAX_CACHE = 256
_UA = "TASALO-Bot/1.0 (+https://github.com/TASALO-TEAM)"
_ASSET = re.compile(r"^(\d{1,15}(?:\.\d{1,9})?) (HIVE|HBD|VESTS)$")
_NAI = {"@@000000021": "HIVE", "@@000000013": "HBD", "@@000000037": "VESTS"}


class ExplorerError(Exception):
    """codigo: no_encontrado | fuente_no_disponible | respuesta_invalida."""

    def __init__(self, codigo: str):
        super().__init__(codigo)
        self.codigo = codigo


class _Fallo(Exception):
    """La fuente fallo (red, 429, 5xx, JSON malo): probar la siguiente."""


class _NoEncontrado(Exception):
    pass


_cliente: httpx.AsyncClient | None = None
_sem = asyncio.Semaphore(4)   # tope de peticiones externas simultaneas
_cache: dict = {}             # clave -> (expira_monotonic, valor)
_vuelo: dict = {}             # clave -> tarea en curso (una sola carga por clave)


def usar_cliente(c) -> None:
    """Para tests: inyecta un cliente (p. ej. con httpx.MockTransport)."""
    global _cliente
    _cliente = c


def reset() -> None:
    _cache.clear()
    _vuelo.clear()


async def cerrar() -> None:
    global _cliente
    if _cliente is not None:
        await _cliente.aclose()
        _cliente = None


def _get_cliente() -> httpx.AsyncClient:
    global _cliente
    if _cliente is None:
        _cliente = httpx.AsyncClient(
            timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": _UA},
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=2))
    return _cliente


async def _pedir(metodo: str, url: str, cuerpo=None):
    async with _sem:
        try:
            async with _get_cliente().stream(metodo, url, json=cuerpo) as r:
                if r.status_code in (400, 404):
                    raise _NoEncontrado()
                if r.status_code != 200:           # 429, 5xx...
                    raise _Fallo(f"http_{r.status_code}")
                trozos, total = [], 0
                async for t in r.aiter_bytes():
                    total += len(t)
                    if total > MAX_BYTES:
                        raise _Fallo("respuesta_grande")
                    trozos.append(t)
            return json.loads(b"".join(trozos))
        except (httpx.HTTPError, ValueError) as e:
            raise _Fallo(type(e).__name__) from e


async def _con_respaldo(intentos):
    """Prueba cada fuente en orden. -> valor o ExplorerError."""
    no_enc = 0
    for f in intentos:
        try:
            return await f()
        except _NoEncontrado:
            no_enc += 1
        except _Fallo as e:
            logger.warning("Explorador: fuente fallo (%s)", e)
    raise ExplorerError("no_encontrado" if no_enc else "fuente_no_disponible")


async def _cacheado(clave, ttl, cargar):
    """ttl: segundos o funcion(valor)->segundos. Una sola carga por clave a la vez."""
    ent = _cache.get(clave)
    if ent and time.monotonic() < ent[0]:
        return ent[1]
    tarea = _vuelo.get(clave)
    if tarea is None:
        tarea = _vuelo[clave] = asyncio.ensure_future(cargar())
        tarea.add_done_callback(lambda t, k=clave: (_vuelo.pop(k, None), t.cancelled() or t.exception()))
    valor = await asyncio.shield(tarea)
    ahora = time.monotonic()
    if len(_cache) >= MAX_CACHE:
        for k in [k for k, v in _cache.items() if v[0] <= ahora] or [min(_cache, key=lambda k: _cache[k][0])]:
            _cache.pop(k, None)
    _cache[clave] = (ahora + (ttl(valor) if callable(ttl) else ttl), valor)
    return valor


def _int(v, defecto=0) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and abs(v) < 10**18 else defecto


def _fecha(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


# ───────────────────────── Bitcoin ─────────────────────────

async def _esplora(ruta: str):
    return await _con_respaldo([lambda b=b: _pedir("GET", f"{b}{ruta}") for b in (MEMPOOL, ESPLORA)])


async def btc_address(direccion: str) -> dict:
    async def cargar():
        j = await _esplora(f"/address/{direccion}")
        try:
            c, m = j["chain_stats"], j["mempool_stats"]
            rec, gas = _int(c["funded_txo_sum"]), _int(c["spent_txo_sum"])
            pend = _int(m["funded_txo_sum"]) - _int(m["spent_txo_sum"])
            return {"direccion": direccion, "saldo_sats": rec - gas, "pendiente_sats": pend,
                    "recibido_sats": rec, "gastado_sats": gas, "tx_count": _int(c["tx_count"]),
                    "tx_pendientes": _int(m["tx_count"])}
        except (KeyError, TypeError) as e:
            raise ExplorerError("respuesta_invalida") from e
    return await _cacheado(("btc_addr", direccion), 60, cargar)


async def btc_address_txs(direccion: str, limite: int = 5) -> list:
    async def cargar():
        lista = await _esplora(f"/address/{direccion}/txs")
        if not isinstance(lista, list):
            raise ExplorerError("respuesta_invalida")
        out = []
        for t in lista[:limite]:
            try:
                st = t.get("status", {})
                suma = lambda xs: sum(_int(x.get("value")) for x in xs if x.get("scriptpubkey_address") == direccion)
                neto = suma(t["vout"]) - suma([v["prevout"] for v in t["vin"] if v.get("prevout")])
                out.append({"txid": t["txid"], "confirmada": bool(st.get("confirmed")),
                            "altura": _int(st.get("block_height"), None), "fecha": _fecha(st.get("block_time")),
                            "neto_sats": neto})
            except (KeyError, TypeError, AttributeError):
                continue
        return out
    return await _cacheado(("btc_txs", direccion, limite), 60, cargar)


async def btc_tx(txid: str) -> dict:
    async def cargar():
        j = await _esplora(f"/tx/{txid}")
        try:
            st = j.get("status", {})
            altura = _int(st.get("block_height"), None) if st.get("confirmed") else None
            conf = 0
            if altura is not None:
                try:
                    tip = await _esplora("/blocks/tip/height")
                    conf = max(0, tip - altura + 1) if isinstance(tip, int) else None
                except ExplorerError:
                    conf = None
            return {"txid": txid, "confirmada": altura is not None, "altura": altura, "confirmaciones": conf,
                    "fecha": _fecha(st.get("block_time")), "tamano": _int(j.get("size")), "peso": _int(j.get("weight")),
                    "fee_sats": _int(j.get("fee")), "entradas": len(j["vin"]), "salidas": len(j["vout"]),
                    "total_salidas_sats": sum(_int(o.get("value")) for o in j["vout"])}
        except (KeyError, TypeError, AttributeError) as e:
            raise ExplorerError("respuesta_invalida") from e
    return await _cacheado(("btc_tx", txid), lambda v: 600 if (v["confirmaciones"] or 0) >= 6 else 30, cargar)


# ───────────────────────── Hive ─────────────────────────

async def _hive_rpc(metodo: str, params):
    cuerpo = {"jsonrpc": "2.0", "method": metodo, "params": params, "id": 1}

    async def uno(nodo):
        j = await _pedir("POST", nodo, cuerpo)
        if not isinstance(j, dict):
            raise _Fallo("json_invalido")
        if "error" in j:
            raise _NoEncontrado()     # el nodo respondio, pero sin el dato
        return j.get("result")
    return await _con_respaldo([lambda n=n: uno(n) for n in HIVE_NODOS])


def _asset(v):
    """'1.000 HIVE' o {'amount': '1000', 'precision': 3, 'nai': ...} -> (float, 'HIVE') | None."""
    if isinstance(v, str) and (m := _ASSET.match(v)):
        return float(m.group(1)), m.group(2)
    if isinstance(v, dict) and v.get("nai") in _NAI:
        try:
            return int(v["amount"]) / 10 ** int(v["precision"]), _NAI[v["nai"]]
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _monto(v) -> float | None:
    a = _asset(v)
    return a[0] if a else None


async def hive_cuenta(nombre: str) -> dict:
    async def cargar():
        cuentas = await _hive_rpc("condenser_api.get_accounts", [[nombre]])
        if not cuentas:
            raise ExplorerError("no_encontrado")
        c = cuentas[0]
        try:
            props = await _hive_rpc("condenser_api.get_dynamic_global_properties", [])
            fondo, vests_tot = _monto(props["total_vesting_fund_hive"]), _monto(props["total_vesting_shares"])
        except (ExplorerError, KeyError, TypeError):
            fondo = vests_tot = None
        vests = _monto(c.get("vesting_shares"))
        hp = vests * fondo / vests_tot if vests is not None and fondo and vests_tot else None
        fecha = lambda s: s[:10] if isinstance(s, str) and re.match(r"^\d{4}-\d\d-\d\d", s) else None
        ultima = fecha(c.get("last_post")) if fecha(c.get("last_post")) != "1970-01-01" else None
        return {"nombre": nombre, "creada": fecha(c.get("created")), "hive": _monto(c.get("balance")),
                "hbd": _monto(c.get("hbd_balance")), "hp": hp, "posts": _int(c.get("post_count")),
                "ultimo_post": ultima}
    return await _cacheado(("hive_acc", nombre), 120, cargar)


async def hive_tx(txid: str) -> dict:
    async def cargar():
        j = await _hive_rpc("account_history_api.get_transaction", {"id": txid})
        if not isinstance(j, dict) or not isinstance(j.get("operations"), list):
            raise ExplorerError("respuesta_invalida")
        ops = []
        for o in j["operations"][:10]:
            tipo = str(o.get("type", ""))[:40]
            tipo = tipo if re.match(r"^[a-z_]+$", tipo) else "desconocida"
            v = o.get("value") if isinstance(o.get("value"), dict) else {}
            res = None
            if tipo == "transfer_operation" and es_nombre_hive(str(v.get("from"))) and es_nombre_hive(str(v.get("to"))):
                a = _asset(v.get("amount"))
                if a:
                    res = {"de": v["from"], "a": v["to"], "monto": a[0], "moneda": a[1]}
            ops.append({"tipo": tipo.removesuffix("_operation"), "transferencia": res})
        return {"id": txid, "bloque": _int(j.get("block_num"), None), "operaciones": ops,
                "total_operaciones": len(j["operations"])}
    return await _cacheado(("hive_tx", txid), 300, cargar)
