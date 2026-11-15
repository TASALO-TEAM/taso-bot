# src/core/indicators.py
# Indicadores técnicos propios (pandas/numpy). Reemplazan a pandas_ta (H-032):
# la dependencia costaba ~130 MB de RAM (pandas_ta + numba) por ~12 indicadores.
# Las fórmulas replican pandas_ta 0.4.71b0 (ruta sin TA-Lib), salvo CCI, que
# usa la fórmula estándar (pandas_ta tiene un error de precedencia de operadores).
import numpy as np
import pandas as pd

_EPS = np.finfo(float).eps


def _nan_like(s: pd.Series) -> pd.Series:
    return pd.Series(np.nan, index=s.index, dtype=float)


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    """EMA sembrada con la SMA de las primeras n velas (como TA-Lib)."""
    if len(s) < n:
        return _nan_like(s)
    s = s.astype(float).copy()
    seed = s.iloc[:n].mean()
    s.iloc[:n - 1] = np.nan
    s.iloc[n - 1] = seed
    return s.ewm(span=n, adjust=False).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Media móvil de Wilder."""
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def _range(hi: pd.Series, lo: pd.Series) -> pd.Series:
    d = hi - lo
    return d + _EPS if (d == 0).any() else d


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    diff = close.diff()
    up, dn = diff.clip(lower=0), diff.clip(upper=0)
    up_avg, dn_avg = rma(up, n), rma(dn, n)
    return 100 * up_avg / (up_avg + dn_avg.abs())


def stoch(high, low, close, k: int = 14, d: int = 3, smooth_k: int = 3):
    """Devuelve (%K suavizado, %D)."""
    ll, hh = low.rolling(k).min(), high.rolling(k).max()
    raw = 100 * (close - ll) / _range(hh, ll)
    k_line = sma(raw, smooth_k)
    return k_line, sma(k_line, d)


def cci(high, low, close, n: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    mean = tp.rolling(n).mean()
    mad = tp.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - mean) / (0.015 * mad)


def ao(high, low, fast: int = 5, slow: int = 34) -> pd.Series:
    mid = 0.5 * (high + low)
    return sma(mid, fast) - sma(mid, slow)


def true_range(high, low, close, prenan: bool = False) -> pd.Series:
    pc = close.shift(1)
    tr = pd.concat([_range(high, low), high - pc, pc - low], axis=1).abs().max(axis=1)
    if prenan:
        tr.iloc[:1] = np.nan
    return tr


def atr(high, low, close, n: int = 14, prenan: bool = False) -> pd.Series:
    if len(close) < n + 1:
        return _nan_like(close)
    tr = true_range(high, low, close, prenan)
    seed = tr.iloc[:n].mean()
    tr.iloc[:n - 1] = np.nan
    tr.iloc[n - 1] = seed
    return rma(tr, n)


def adx(high, low, close, n: int = 14) -> pd.Series:
    if len(close) < n + 1:
        return _nan_like(close)
    k = 100 / atr(high, low, close, n, prenan=True)
    up, dn = high - high.shift(1), low.shift(1) - low
    pos = ((up > dn) & (up > 0)) * up
    neg = ((dn > up) & (dn > 0)) * dn
    dmp, dmn = k * rma(pos, n), k * rma(neg, n)
    dx = 100 * (dmp - dmn).abs() / (dmp + dmn)
    return rma(dx, n)


def macd(close, fast: int = 12, slow: int = 26, signal: int = 9):
    """Devuelve (línea MACD, histograma, señal)."""
    line = ema(close, fast) - ema(close, slow)
    start = line.first_valid_index()
    sig = _nan_like(line) if start is None else ema(line.loc[start:], signal).reindex(line.index)
    return line, line - sig, sig


def mfi(high, low, close, volume, n: int = 14) -> pd.Series:
    tp = (high + low + close) / 3
    flow = tp * volume * np.where(tp > tp.shift(1), 1, -1)
    pos = flow.clip(lower=0).rolling(n).sum()
    neg = (-flow).clip(lower=0).rolling(n).sum()
    out = 100 * pos / (pos + neg + _EPS)
    out.iloc[:n] = np.nan
    return out


def willr(high, low, close, n: int = 14) -> pd.Series:
    ll, hh = low.rolling(n).min(), high.rolling(n).max()
    return 100 * ((close - ll) / (hh - ll) - 1)


def obv(close, volume) -> pd.Series:
    sign = np.sign(close.diff())
    sign.iloc[0] = np.nan  # igual que pandas_ta: la primera vela no suma
    return (sign * volume).cumsum()
