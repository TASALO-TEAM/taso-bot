"""Datos del mapa de calor: cripto (CMC) y forex (Frankfurter, proveedor BCE).

Aislado: no importa el resto del bot. La funcion de CMC y la de HTTP se reciben
por parametro (el handler pasa `CryptoApiClient._cmc_get`), asi se prueba sin red.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Awaitable, Callable, Optional

from src.heatmap.logos import id_valido
from src.heatmap.render import Celda

logger = logging.getLogger(__name__)

TTL_CRIPTO = 600  # 10 min; CMC actualiza cada 60 s y el cupo es limitado
TTL_FOREX = 6 * 3600  # el BCE publica una vez al dia
TTL_ACCIONES = 600  # 10 min; el escaner no publica cupo, mantenemos pocas llamadas
FRANKFURTER_URL = "https://api.frankfurter.dev/v2/rates"
CMC_LISTINGS = "v1/cryptocurrency/listings/latest"

VENTANAS = {"24h": ("percent_change_24h", 5.0), "7d": ("percent_change_7d", 10.0)}
FOREX_MONEDAS = ("EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CNY", "MXN", "BRL", "SEK", "NOK")
FOREX_TOPE = 1.0
ACCIONES_URL = "https://scanner.tradingview.com/america/scan"
ACCIONES_TOPE = 3.0  # % diario a partir del cual el color satura
ACCIONES_FILAS = 80
# Segunda clase de una empresa ya listada: TradingView repite la capitalizacion completa.
ACCIONES_DUPLICADAS = frozenset({"GOOG"})


class HeatmapError(Exception):
    """No hay datos utilizables (ni frescos ni en cache)."""


@dataclass(frozen=True)
class Snapshot:
    celdas: tuple
    fuente: str
    tope: float
    fecha_dato: Optional[str] = None  # forex: fecha real del dato del BCE
    obsoleto_min: Optional[int] = None  # None = dato fresco


_cache: dict = {}
_locks: dict = {}


def reset_cache() -> None:
    _cache.clear()
    _locks.clear()


async def _cacheado(clave: str, ttl: int, cargar: Callable[[], Awaitable]):
    """Devuelve (valor, edad_en_segundos|None). Una sola carga a la vez por clave;
    si la carga falla y hay dato viejo, lo devuelve con su edad."""
    ahora = time.time()
    ent = _cache.get(clave)
    if ent and ahora - ent[0] < ttl:
        return ent[1], None
    async with _locks.setdefault(clave, asyncio.Lock()):
        ent = _cache.get(clave)
        if ent and time.time() - ent[0] < ttl:
            return ent[1], None
        try:
            valor = await cargar()
        except Exception as e:
            logger.warning("Mapa de calor: fallo al cargar '%s': %s", clave, type(e).__name__)
            if ent:
                return ent[1], time.time() - ent[0]
            raise HeatmapError(f"sin datos de {clave}") from e
        _cache[clave] = (time.time(), valor)
        return valor, None


def _numero(v):
    return float(v) if isinstance(v, (int, float)) and v == v and abs(v) != float("inf") else None


async def obtener_cripto(cmc_get, ventana: str = "24h") -> Snapshot:
    if ventana not in VENTANAS:
        raise ValueError(f"ventana invalida: {ventana}")
    campo, tope = VENTANAS[ventana]

    async def cargar():
        raw = await cmc_get(
            CMC_LISTINGS,
            {"start": "1", "limit": "100", "convert": "USD", "sort": "market_cap"},
        )
        if not raw:
            raise HeatmapError("CMC sin datos")
        filas = []
        for m in raw:
            usd = (m.get("quote") or {}).get("USD") or {}
            cap = _numero(usd.get("market_cap"))
            if m.get("symbol") and cap and cap > 0:
                filas.append((m["symbol"], cap, {k: _numero(usd.get(k)) for k in
                                                 (v[0] for v in VENTANAS.values())}, id_valido(m.get("id"))))
        if not filas:
            raise HeatmapError("CMC sin capitalizaciones")
        return filas

    filas, edad = await _cacheado("cripto", TTL_CRIPTO, cargar)
    celdas = tuple(Celda(s, cap, vars_[campo], ref) for s, cap, vars_, ref in filas)
    return Snapshot(
        celdas, "Fuente: CoinMarketCap", tope,
        obsoleto_min=None if edad is None else int(edad // 60),
    )


async def http_json(url: str, params: dict):
    import httpx  # import perezoso: solo si se pide forex

    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(url, params=params)
        r.raise_for_status()
        return r.json()


async def obtener_forex(http: Callable = http_json) -> Snapshot:
    async def cargar():
        hoy = date.today()
        filas = await http(FRANKFURTER_URL, {
            "base": "usd", "providers": "ecb", "quotes": ",".join(FOREX_MONEDAS),
            "from": (hoy - timedelta(days=10)).isoformat(), "to": hoy.isoformat(),
        })
        por_fecha: dict = {}
        for f in filas or []:
            r = _numero(f.get("rate"))
            if r and r > 0 and f.get("date") and f.get("quote"):
                por_fecha.setdefault(f["date"], {})[f["quote"]] = r
        fechas = sorted(por_fecha)
        if len(fechas) < 2:
            raise HeatmapError("el BCE no devolvio dos dias habiles")
        previo, ultimo = por_fecha[fechas[-2]], por_fecha[fechas[-1]]
        # tasa = unidades de la moneda por USD: si sube, la moneda se debilita.
        celdas = tuple(
            Celda(m, 1.0, (previo[m] / ultimo[m] - 1) * 100)
            for m in FOREX_MONEDAS if m in previo and m in ultimo
        )
        if not celdas:
            raise HeatmapError("el BCE no devolvio monedas comunes")
        return celdas, fechas[-1]

    (celdas, fecha), edad = await _cacheado("forex", TTL_FOREX, cargar)
    return Snapshot(
        celdas, "Fuente: Banco Central Europeo, via Frankfurter", FOREX_TOPE,
        fecha_dato=fecha, obsoleto_min=None if edad is None else int(edad // 60),
    )


async def http_post_json(url: str, body: dict):
    import httpx  # import perezoso: solo si se pide el mapa de acciones

    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.post(url, json=body)
        r.raise_for_status()
        return r.json()


async def obtener_acciones(http_post: Callable = http_post_json) -> Snapshot:
    """Mayores empresas del S&P 500 (capitalizacion y % del dia) via escaner de TradingView.

    Endpoint no oficial: puede cambiar sin aviso, por eso hay cache y dato viejo de respaldo.
    """
    async def cargar():
        raw = await http_post(ACCIONES_URL, {
            "symbols": {"query": {"types": []}, "tickers": [],
                        "groups": [{"type": "index", "values": ["SP:SPX"]}]},
            "columns": ["name", "market_cap_basic", "change", "sector"],
            "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
            "range": [0, ACCIONES_FILAS],
        })
        filas = []
        for f in (raw or {}).get("data") or []:
            d = f.get("d") or []
            if len(d) < 3 or not isinstance(d[0], str) or d[0] in ACCIONES_DUPLICADAS:
                continue
            cap = _numero(d[1])
            if cap and cap > 0:
                filas.append((d[0], cap, _numero(d[2])))
        if not filas:
            raise HeatmapError("TradingView sin acciones")
        return filas

    filas, edad = await _cacheado("acciones", TTL_ACCIONES, cargar)
    return Snapshot(
        tuple(Celda(s, cap, var) for s, cap, var in filas), "Fuente: TradingView", ACCIONES_TOPE,
        obsoleto_min=None if edad is None else int(edad // 60),
    )


# --- M2: mapas por indice (componentes) y mapas de indices (cotizacion), mismo escaner ---
# Verificado con red el 2026-11-25: cada (region, indice) devuelve sus componentes en una sola moneda.
TV_BASE = "https://scanner.tradingview.com"
MERCADOS_COMPONENTES = {
    "nasdaq": (("america", "NASDAQ:NDX"),),
    "dow": (("america", "DJ:DJI"),),
    "europa": (("germany", "XETR:DAX"), ("france", "EURONEXT:PX1")),  # ambos en EUR: capitalizaciones comparables
    "nikkei": (("japan", "TVC:NI225"),),
    "hsi": (("hongkong", "HSI:HSI"),),
}
INDICES_MUNDIALES = {
    "SP:SPX": "S&P 500", "NASDAQ:NDX": "Nasdaq", "DJ:DJI": "Dow", "TVC:SX5E": "Euro 50",
    "XETR:DAX": "DAX", "EURONEXT:PX1": "CAC 40", "FTSE:UKX": "FTSE 100", "TVC:NI225": "Nikkei",
    "HSI:HSI": "Hang Seng", "SSE:000001": "Shanghai", "TVC:KOSPI": "KOSPI", "BSE:SENSEX": "Sensex",
}
INDICES_ASIA = ("TVC:NI225", "HSI:HSI", "SSE:000001", "TVC:KOSPI", "BSE:SENSEX")
MERCADOS_INDICES = {"indices": tuple(INDICES_MUNDIALES), "asia": INDICES_ASIA}
MERCADOS = frozenset(MERCADOS_COMPONENTES) | frozenset(MERCADOS_INDICES)
INDICES_TOPE = 2.0  # % diario a partir del cual el color satura (un indice se mueve menos que una accion)


def _componentes(raw) -> list:
    filas = []
    for f in (raw or {}).get("data") or []:
        d = f.get("d") or []
        if len(d) < 3 or not isinstance(d[0], str) or d[0] in ACCIONES_DUPLICADAS:
            continue
        cap = _numero(d[1])
        if cap and cap > 0:
            filas.append((d[0], cap, _numero(d[2])))
    return filas


async def obtener_mercado(clave: str, http_post: Callable = http_post_json) -> Snapshot:
    """Mapa de un indice (sus mayores empresas) o de varios indices (peso igual, variacion del dia)."""
    if clave not in MERCADOS:
        raise ValueError(f"mercado invalido: {clave}")

    async def cargar():
        if clave in MERCADOS_INDICES:
            raw = await http_post(f"{TV_BASE}/global/scan", {
                "symbols": {"tickers": list(MERCADOS_INDICES[clave])},
                "columns": ["name", "close", "change", "description"],
            })
            filas = [(INDICES_MUNDIALES[f["s"]], 1.0, _numero((f.get("d") or [None] * 3)[2]))
                     for f in (raw or {}).get("data") or [] if f.get("s") in INDICES_MUNDIALES]
        else:
            vistos, filas = set(), []
            for region, indice in MERCADOS_COMPONENTES[clave]:
                raw = await http_post(f"{TV_BASE}/{region}/scan", {
                    "symbols": {"query": {"types": []}, "tickers": [],
                                "groups": [{"type": "index", "values": [indice]}]},
                    "columns": ["name", "market_cap_basic", "change", "currency"],
                    "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                    "range": [0, ACCIONES_FILAS],
                })
                for fila in _componentes(raw):
                    if fila[0] not in vistos:  # una empresa en dos indices (p. ej. Airbus) se dibuja una vez
                        vistos.add(fila[0])
                        filas.append(fila)
            filas = sorted(filas, key=lambda f: -f[1])[:ACCIONES_FILAS]
        filas = [f for f in filas if f[2] is not None]
        if not filas:
            raise HeatmapError(f"TradingView sin datos de {clave}")
        return filas

    filas, edad = await _cacheado(f"mercado_{clave}", TTL_ACCIONES, cargar)
    return Snapshot(
        tuple(Celda(s, p, v) for s, p, v in filas), "Fuente: TradingView",
        INDICES_TOPE if clave in MERCADOS_INDICES else ACCIONES_TOPE,
        obsoleto_min=None if edad is None else int(edad // 60),
    )
