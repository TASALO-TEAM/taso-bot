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

from src.heatmap.render import Celda

logger = logging.getLogger(__name__)

TTL_CRIPTO = 600  # 10 min; CMC actualiza cada 60 s y el cupo es limitado
TTL_FOREX = 6 * 3600  # el BCE publica una vez al dia
FRANKFURTER_URL = "https://api.frankfurter.dev/v2/rates"
CMC_LISTINGS = "v1/cryptocurrency/listings/latest"

VENTANAS = {"24h": ("percent_change_24h", 5.0), "7d": ("percent_change_7d", 10.0)}
FOREX_MONEDAS = ("EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CNY", "MXN", "BRL", "SEK", "NOK")
FOREX_TOPE = 1.0


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
                                                 (v[0] for v in VENTANAS.values())}))
        if not filas:
            raise HeatmapError("CMC sin capitalizaciones")
        return filas

    filas, edad = await _cacheado("cripto", TTL_CRIPTO, cargar)
    celdas = tuple(Celda(s, cap, vars_[campo]) for s, cap, vars_ in filas)
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
