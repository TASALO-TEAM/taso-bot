"""Datos del mapa de calor: CMC (cripto) y Frankfurter/BCE (forex). Sin red."""

import asyncio

import pytest

from src.heatmap import data
from src.heatmap.data import HeatmapError, obtener_cripto, obtener_forex


@pytest.fixture(autouse=True)
def _limpiar():
    data.reset_cache()
    yield
    data.reset_cache()


def _listing(sym, cap, p24, p7=None):
    return {
        "symbol": sym,
        "quote": {"USD": {"market_cap": cap, "percent_change_24h": p24, "percent_change_7d": p7}},
    }


class CmcFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = 0
        self.params = None

    async def __call__(self, path, params=None):
        self.llamadas += 1
        self.params = (path, params)
        r = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        if isinstance(r, Exception):
            raise r
        return r


DATOS = [_listing("BTC", 2e12, 1.5, 4.0), _listing("ETH", 5e11, -2.0, 1.0), _listing("XYZ", 0, 3.0)]


def test_cripto_filtra_sin_capitalizacion_y_usa_la_ventana():
    cmc = CmcFalso([DATOS])
    snap = asyncio.run(obtener_cripto(cmc, "24h"))
    assert [(c.simbolo, c.variacion) for c in snap.celdas] == [("BTC", 1.5), ("ETH", -2.0)]
    snap7 = asyncio.run(obtener_cripto(cmc, "7d"))
    assert snap7.celdas[0].variacion == 4.0
    assert cmc.params[0] == "v1/cryptocurrency/listings/latest"
    assert cmc.params[1]["limit"] == "100"


def test_cripto_la_segunda_llamada_sale_del_cache():
    cmc = CmcFalso([DATOS])
    asyncio.run(obtener_cripto(cmc, "24h"))
    asyncio.run(obtener_cripto(cmc, "7d"))
    assert cmc.llamadas == 1  # una sola llamada a CMC sirve a las dos ventanas


def test_cripto_ventana_invalida():
    with pytest.raises(ValueError):
        asyncio.run(obtener_cripto(CmcFalso([DATOS]), "1h"))


def test_cripto_fallo_sin_cache_lanza_error():
    with pytest.raises(HeatmapError):
        asyncio.run(obtener_cripto(CmcFalso([None]), "24h"))


def test_cripto_fallo_con_cache_viejo_devuelve_dato_con_antiguedad(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(data.time, "time", lambda: t[0])
    cmc = CmcFalso([DATOS, None])
    asyncio.run(obtener_cripto(cmc, "24h"))
    t[0] += data.TTL_CRIPTO + 120
    snap = asyncio.run(obtener_cripto(cmc, "24h"))
    assert snap.obsoleto_min == (data.TTL_CRIPTO + 120) // 60
    assert snap.celdas[0].simbolo == "BTC"


def test_cripto_consultas_concurrentes_hacen_una_sola_llamada():
    cmc = CmcFalso([DATOS])

    async def dos():
        return await asyncio.gather(obtener_cripto(cmc, "24h"), obtener_cripto(cmc, "24h"))

    asyncio.run(dos())
    assert cmc.llamadas == 1


def _fila(fecha, quote, rate):
    return {"date": fecha, "base": "USD", "quote": quote, "rate": rate}


FOREX = [
    _fila("2026-11-12", "EUR", 0.9000), _fila("2026-11-12", "JPY", 150.0),
    _fila("2026-11-13", "EUR", 0.9090), _fila("2026-11-13", "JPY", 148.5),
]


async def _http(url, params):
    assert "providers" in params and params["providers"] == "ecb"
    return FOREX


def test_forex_variacion_es_la_de_la_moneda_frente_al_dolar():
    snap = asyncio.run(obtener_forex(_http))
    por = {c.simbolo: c for c in snap.celdas}
    # EUR cuesta mas por USD => el euro se debilito frente al dolar
    assert por["EUR"].variacion == pytest.approx((0.9000 / 0.9090 - 1) * 100)
    # JPY cuesta menos por USD => el yen se fortalecio
    assert por["JPY"].variacion == pytest.approx((150.0 / 148.5 - 1) * 100)
    assert all(c.peso == 1.0 for c in snap.celdas)
    assert snap.fecha_dato == "2026-11-13"


def test_forex_con_un_solo_dia_lanza_error():
    async def http(url, params):
        return [f for f in FOREX if f["date"] == "2026-11-13"]

    with pytest.raises(HeatmapError):
        asyncio.run(obtener_forex(http))


def test_forex_fallo_de_red_sin_cache_lanza_error():
    async def http(url, params):
        raise OSError("sin red")

    with pytest.raises(HeatmapError):
        asyncio.run(obtener_forex(http))
