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


# --- Acciones S&P 500 (escaner de TradingView; forma real de la respuesta) ---

def _fila(sym, cap, chg, sector="Technology Services"):
    return {"s": f"NASDAQ:{sym}", "d": [sym, cap, chg, sector]}


TV = {
    "totalCount": 503,
    "data": [
        _fila("AAPL", 5.1e12, -0.98),
        _fila("MSFT", 3.8e12, -1.12),
        _fila("GOOG", 3.45e12, -3.85),  # misma empresa que GOOGL: se descarta
        _fila("GOOGL", 3.45e12, -4.07),
        _fila("SINCAP", None, 1.0),
        _fila("SINCAMBIO", 1e11, None),
    ],
}


class HttpPostFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = 0
        self.args = None

    async def __call__(self, url, body):
        self.llamadas += 1
        self.args = (url, body)
        r = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        if isinstance(r, Exception):
            raise r
        return r


def test_acciones_parsea_filtra_y_descarta_clase_duplicada():
    from src.heatmap.data import obtener_acciones

    http = HttpPostFalso([TV])
    snap = asyncio.run(obtener_acciones(http))
    simbolos = [c.simbolo for c in snap.celdas]
    assert simbolos == ["AAPL", "MSFT", "GOOGL", "SINCAMBIO"]
    assert snap.fuente == "Fuente: TradingView"
    assert snap.tope == 3.0
    assert snap.obsoleto_min is None
    aapl = snap.celdas[0]
    assert aapl.peso == 5.1e12 and aapl.variacion == pytest.approx(-0.98)
    assert snap.celdas[-1].variacion is None  # sin cambio: se dibuja neutro


def test_acciones_pide_solo_el_sp500_y_un_tope_de_filas():
    from src.heatmap.data import obtener_acciones

    http = HttpPostFalso([TV])
    asyncio.run(obtener_acciones(http))
    url, body = http.args
    assert url == "https://scanner.tradingview.com/america/scan"
    assert body["symbols"]["groups"] == [{"type": "index", "values": ["SP:SPX"]}]
    assert body["range"] == [0, 80]


def test_acciones_cache_y_dato_viejo_si_la_fuente_falla(monkeypatch):
    from src.heatmap.data import obtener_acciones

    http = HttpPostFalso([TV, RuntimeError("caido")])
    primero = asyncio.run(obtener_acciones(http))
    asyncio.run(obtener_acciones(http))
    assert http.llamadas == 1  # el segundo salio de cache
    t = data.time.time()
    monkeypatch.setattr(data.time, "time", lambda: t + data.TTL_ACCIONES + 120)
    viejo = asyncio.run(obtener_acciones(http))
    assert http.llamadas == 2
    assert viejo.celdas == primero.celdas and viejo.obsoleto_min >= 2


def test_acciones_sin_datos_levanta_error():
    from src.heatmap.data import obtener_acciones

    with pytest.raises(HeatmapError):
        asyncio.run(obtener_acciones(HttpPostFalso([{"totalCount": 0, "data": []}])))
    data.reset_cache()
    with pytest.raises(HeatmapError):
        asyncio.run(obtener_acciones(HttpPostFalso([RuntimeError("x")])))


# ---------------- M1: el id de CMC viaja hasta la celda (ref) ----------------


def test_cripto_propaga_el_id_de_cmc_como_ref():
    filas = [
        {**_listing("BTC", 2e12, 1.5), "id": 1},
        {**_listing("ETH", 5e11, -2.0), "id": 1027},
        _listing("SIN", 1e9, 0.5),  # sin id: ref None, la celda sigue existiendo
    ]
    snap = asyncio.run(obtener_cripto(CmcFalso([filas]), "24h"))
    assert {c.simbolo: c.ref for c in snap.celdas} == {"BTC": 1, "ETH": 1027, "SIN": None}


@pytest.mark.parametrize("malo", [True, False, 0, -3, "1", 2.5, None, 10**12])
def test_cripto_ignora_ids_invalidos(malo):
    filas = [{**_listing("BTC", 2e12, 1.5), "id": malo}]
    snap = asyncio.run(obtener_cripto(CmcFalso([filas]), "24h"))
    assert snap.celdas[0].ref is None


# --- M2: mapas por indice y de indices mundiales (misma fuente, escaner de TradingView) ---

def _comp(sym, cap, chg):
    return {"s": f"X:{sym}", "d": [sym, cap, chg, "EUR", "XETR"]}


def _ind(ticker, nombre, chg):
    return {"s": ticker, "d": [nombre, 1000.0, chg, nombre]}


def test_mercado_nasdaq_consulta_america_con_el_indice_ndx():
    from src.heatmap.data import obtener_mercado
    http = HttpPostFalso([{"totalCount": 2, "data": [_comp("AAPL", 5e12, 1.0), _comp("NVDA", 4e12, -2.0)]}])
    snap = asyncio.run(obtener_mercado("nasdaq", http))
    url, body = http.args
    assert url.endswith("/america/scan")
    assert body["symbols"]["groups"] == [{"type": "index", "values": ["NASDAQ:NDX"]}]
    assert [c.simbolo for c in snap.celdas] == ["AAPL", "NVDA"]
    assert snap.fuente == "Fuente: TradingView"


def test_mercado_europa_une_dax_y_cac_sin_repetir_y_ordena_por_capitalizacion():
    from src.heatmap.data import obtener_mercado
    http = HttpPostFalso([
        {"data": [_comp("SAP", 2.1e11, 1.0), _comp("AIR", 1.5e11, 0.5)]},
        {"data": [_comp("OR", 2.3e11, 0.6), _comp("AIR", 1.5e11, 0.5)]},
    ])
    snap = asyncio.run(obtener_mercado("europa", http))
    assert http.llamadas == 2
    assert [c.simbolo for c in snap.celdas] == ["OR", "SAP", "AIR"]


def test_mercado_limita_a_80_celdas():
    from src.heatmap.data import obtener_mercado
    filas = [_comp(f"T{i}", 1e9 + i, 0.1) for i in range(120)]
    snap = asyncio.run(obtener_mercado("nasdaq", HttpPostFalso([{"data": filas}])))
    assert len(snap.celdas) == 80


def test_mercado_indices_usa_el_endpoint_global_con_peso_igual_y_nombres_cortos():
    from src.heatmap.data import obtener_mercado
    http = HttpPostFalso([{"data": [
        _ind("SP:SPX", "S&P 500", -0.5), _ind("XETR:DAX", "DAX", -1.26), _ind("TVC:NI225", "Nikkei", 2.0),
    ]}])
    snap = asyncio.run(obtener_mercado("indices", http))
    url, body = http.args
    assert url.endswith("/global/scan")
    assert "SP:SPX" in body["symbols"]["tickers"] and len(body["symbols"]["tickers"]) == 12
    assert {c.peso for c in snap.celdas} == {1.0}
    assert {c.simbolo for c in snap.celdas} == {"S&P 500", "DAX", "Nikkei"}


def test_mercado_asia_pide_solo_indices_asiaticos():
    from src.heatmap.data import obtener_mercado
    http = HttpPostFalso([{"data": [_ind("TVC:NI225", "Nikkei", 2.0)]}])
    asyncio.run(obtener_mercado("asia", http))
    tickers = http.args[1]["symbols"]["tickers"]
    assert "TVC:NI225" in tickers and "HSI:HSI" in tickers and "SP:SPX" not in tickers


def test_mercado_ignora_filas_sin_cambio_y_nombres_raros():
    from src.heatmap.data import obtener_mercado
    snap = asyncio.run(obtener_mercado("indices", HttpPostFalso([{"data": [
        _ind("SP:SPX", "S&P 500", None), _ind("ZZ:NOEXISTE", "x", 1.0), _ind("DJ:DJI", "Dow", 0.8),
    ]}])))
    assert [c.simbolo for c in snap.celdas] == ["Dow"]


def test_mercado_desconocido_es_error_de_programacion():
    from src.heatmap.data import obtener_mercado
    with pytest.raises(ValueError):
        asyncio.run(obtener_mercado("marte", HttpPostFalso([{"data": []}])))


def test_mercado_sin_datos_levanta_heatmap_error():
    from src.heatmap.data import obtener_mercado
    with pytest.raises(HeatmapError):
        asyncio.run(obtener_mercado("nasdaq", HttpPostFalso([{"totalCount": 0, "data": []}])))


def test_mercado_cache_por_clave_y_dato_viejo_si_la_fuente_falla(monkeypatch):
    from src.heatmap.data import obtener_mercado
    http = HttpPostFalso([{"data": [_comp("AAPL", 5e12, 1.0)]}])
    asyncio.run(obtener_mercado("nasdaq", http))
    asyncio.run(obtener_mercado("nasdaq", http))
    assert http.llamadas == 1
    otra = HttpPostFalso([{"data": [_comp("MSFT", 4e12, 1.0)]}])
    asyncio.run(obtener_mercado("dow", otra))  # otra clave: no reutiliza la cache de nasdaq
    assert otra.llamadas == 1
    t = data.time.time()
    monkeypatch.setattr(data.time, "time", lambda: t + data.TTL_ACCIONES + 120)
    viejo = asyncio.run(obtener_mercado("nasdaq", HttpPostFalso([RuntimeError("x")])))
    assert viejo.obsoleto_min is not None
