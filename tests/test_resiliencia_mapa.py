"""F7-T2: resiliencia del mapa de calor ante fuentes caidas, respuestas hostiles y rafagas."""
import asyncio
import time

import pytest

from src.heatmap import data
from src.heatmap.data import HeatmapError, obtener_acciones, obtener_cripto, obtener_forex

NAN, INF = float("nan"), float("inf")


@pytest.fixture(autouse=True)
def _limpio():
    data.reset_cache()
    yield
    data.reset_cache()


def run(coro):
    return asyncio.run(coro)


def _cmc(lista):
    async def cmc_get(url, params):
        return lista
    return cmc_get


def _cmc_falla(exc):
    async def cmc_get(url, params):
        raise exc
    return cmc_get


def _m(sym="BTC", cap=1e12, **q):
    return {"symbol": sym, "quote": {"USD": {"market_cap": cap, "percent_change_24h": 1.0, **q}}}


@pytest.mark.parametrize("raw", [
    None, [], {}, "texto", 7, [None], ["BTC"], [[]], [{}],
    [{"symbol": "BTC"}], [{"symbol": "BTC", "quote": None}],
    [{"symbol": "BTC", "quote": {"USD": None}}],
    [_m(cap=NAN)], [_m(cap=INF)], [_m(cap=-5)], [_m(cap=0)], [_m(cap="1e12")], [_m(sym=None)],
])
def test_cripto_hostil_da_heatmaperror(raw):
    with pytest.raises(HeatmapError):
        run(obtener_cripto(_cmc(raw)))


def test_cripto_variacion_invalida_no_rompe():
    snap = run(obtener_cripto(_cmc([_m(percent_change_24h=NAN), _m("ETH", 5e11, percent_change_24h="x")])))
    assert len(snap.celdas) == 2
    assert all(c.variacion is None for c in snap.celdas)


@pytest.mark.parametrize("exc", [TimeoutError(), ConnectionError("x"), RuntimeError("boom"), ValueError()])
def test_cripto_fuente_caida_sin_cache(exc):
    with pytest.raises(HeatmapError):
        run(obtener_cripto(_cmc_falla(exc)))


def test_cripto_fuente_caida_usa_dato_viejo():
    run(obtener_cripto(_cmc([_m()])))
    t, valor = data._cache["cripto"]
    data._cache["cripto"] = (t - data.TTL_CRIPTO - 600, valor)
    snap = run(obtener_cripto(_cmc_falla(TimeoutError())))
    assert snap.obsoleto_min is not None and snap.obsoleto_min >= 10


def test_cripto_rafaga_hace_una_sola_carga():
    llamadas = []

    async def cmc_get(url, params):
        llamadas.append(1)
        await asyncio.sleep(0.05)
        return [_m()]

    async def rafaga():
        return await asyncio.gather(*(obtener_cripto(cmc_get) for _ in range(50)))

    res = run(rafaga())
    assert len(res) == 50 and len(llamadas) == 1


def test_cripto_ventana_invalida():
    with pytest.raises(ValueError):
        run(obtener_cripto(_cmc([_m()]), "1y"))


async def _http_raw(raw):
    async def http(url, params):
        return raw
    return http


@pytest.mark.parametrize("raw", [
    None, [], {}, "x", 5, [None], ["a"], [{}],
    [{"date": "2026-11-16", "quote": "EUR", "rate": 0.9}],
    [{"date": "2026-11-16", "quote": "EUR", "rate": 0}, {"date": "2026-11-17", "quote": "EUR", "rate": NAN}],
    [{"date": "2026-11-17", "quote": "EUR", "rate": 0.9}, {"date": "2026-11-17", "quote": "EUR", "rate": 0.91}],
])
def test_forex_hostil_da_heatmaperror(raw):
    async def http(url, params):
        return raw
    with pytest.raises(HeatmapError):
        run(obtener_forex(http))


def test_forex_caida_usa_dato_viejo():
    filas = [
        {"date": "2026-11-16", "quote": "EUR", "rate": 0.90},
        {"date": "2026-11-17", "quote": "EUR", "rate": 0.91},
    ]

    async def ok(url, params):
        return filas

    async def mal(url, params):
        raise TimeoutError()

    run(obtener_forex(ok))
    t, valor = data._cache["forex"]
    data._cache["forex"] = (t - data.TTL_FOREX - 300, valor)
    snap = run(obtener_forex(mal))
    assert snap.obsoleto_min is not None


@pytest.mark.parametrize("raw", [
    None, [], {}, "x", 3, {"data": None}, {"data": []}, {"data": [None]}, {"data": [{}]},
    {"data": [{"d": []}]}, {"data": [{"d": ["AAPL"]}]}, {"data": [{"d": [5, 1e12, 1.0]}]},
    {"data": [{"d": ["AAPL", NAN, 1.0]}]}, {"data": [{"d": ["AAPL", -1, 1.0]}]},
    {"data": [{"d": ["GOOG", 1e12, 1.0]}]},
])
def test_acciones_hostil_da_heatmaperror(raw):
    async def post(url, body):
        return raw
    with pytest.raises(HeatmapError):
        run(obtener_acciones(post))


def test_acciones_variacion_invalida_no_rompe():
    async def post(url, body):
        return {"data": [{"d": ["AAPL", 3e12, "n/a", "Tech"]}, {"d": ["MSFT", 2e12, NAN]}]}
    snap = run(obtener_acciones(post))
    assert len(snap.celdas) == 2 and all(c.variacion is None for c in snap.celdas)


def test_acciones_caida_sin_cache():
    async def post(url, body):
        raise ConnectionError()
    with pytest.raises(HeatmapError):
        run(obtener_acciones(post))


def test_cache_vigente_no_vuelve_a_pedir():
    n = []

    async def cmc_get(url, params):
        n.append(1)
        return [_m()]

    run(obtener_cripto(cmc_get))
    t0 = time.time()
    run(obtener_cripto(cmc_get))
    assert len(n) == 1 and time.time() - t0 < 1
