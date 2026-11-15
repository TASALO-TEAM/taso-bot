"""Indicadores propios (H-032): reemplazan a pandas_ta.

Los valores esperados salen de pandas_ta 0.4.71b0 sobre esta misma serie
(sin TA-Lib). CCI se prueba con la fórmula estándar: pandas_ta tiene un error
de precedencia y devuelve ~el precio típico en vez de un oscilador.
"""
import numpy as np
import pandas as pd
import pytest

from src.core import indicators as ind
from src.core.btc_advanced_analysis import BTCAdvancedAnalyzer

N = 500


@pytest.fixture(scope="module")
def ohlcv():
    rng = np.random.default_rng(42)
    close = pd.Series(30000 + np.cumsum(rng.normal(0, 150, N)))
    high = close + rng.uniform(10, 120, N)
    low = close - rng.uniform(10, 120, N)
    vol = pd.Series(rng.uniform(50, 500, N))
    return high, low, close, vol


def test_valores_iguales_a_pandas_ta(ohlcv):
    h, l, c, v = ohlcv
    k, d = ind.stoch(h, l, c)
    line, hist, sig = ind.macd(c)
    got = {
        "ema9": ind.ema(c, 9), "ema200": ind.ema(c, 200), "rsi": ind.rsi(c),
        "stoch_k": k, "stoch_d": d, "ao": ind.ao(h, l), "adx": ind.adx(h, l, c),
        "macd": line, "macd_hist": hist, "macd_signal": sig,
        "atr": ind.atr(h, l, c), "mfi": ind.mfi(h, l, c, v),
        "willr": ind.willr(h, l, c), "obv": ind.obv(c, v),
    }
    esperado = {
        "ema9": 29452.48618654044, "ema200": 29208.27935745779,
        "rsi": 37.92418070801628, "stoch_k": 13.939180306143578,
        "stoch_d": 31.287232762291914, "ao": 165.52986698959285,
        "adx": 20.33201138616547, "macd": 56.4259362041048,
        "macd_hist": -76.29853187990557, "macd_signal": 132.72446808401037,
        "atr": 204.22797539149337, "mfi": 31.55128328781818,
        "willr": -95.68566031739955, "obv": 1658.869914175608,
    }
    for nombre, valor in esperado.items():
        assert got[nombre].iloc[-1] == pytest.approx(valor, rel=1e-9), nombre


def test_cci_formula_estandar():
    s = pd.Series([1.0, 2.0, 3.0])
    # tp = [1,2,3]; media 2; desviación media absoluta 2/3 -> (3-2)/(0.015*2/3) = 100
    assert ind.cci(s, s, s, 3).iloc[-1] == pytest.approx(100.0)


def test_cci_es_oscilador_no_precio(ohlcv):
    h, l, c, _ = ohlcv
    assert ind.cci(h, l, c, 20).dropna().abs().max() < 1000


def test_series_cortas_no_fallan():
    s = pd.Series([1.0, 2.0, 3.0])
    assert ind.ema(s, 9).isna().all()
    assert ind.atr(s, s, s, 14).isna().all()
    assert ind.adx(s, s, s, 14).isna().all()


def test_analizador_btc_calcula_sin_pandas_ta(ohlcv):
    h, l, c, v = ohlcv
    df = pd.DataFrame({"open": c, "high": h, "low": l, "close": c, "volume": v})
    df.index = pd.date_range("2026-01-01", periods=N, freq="h")
    a = BTCAdvancedAnalyzer(df)
    cur = a.get_current_values()
    assert cur["RSI"] == pytest.approx(37.92418070801628, rel=1e-9)
    assert abs(cur["CCI"]) < 1000
    assert a.get_momentum_signal() is not None
