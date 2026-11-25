"""Probabilidad de que el precio TOQUE un nivel (S/R/Pivot) en las proximas N velas.

Calculo determinista: movimiento browniano sin deriva y principio de reflexion,
P(toque) = 2 * (1 - Phi(d / (sigma * sqrt(N)))). Es una estimacion estadistica, no una
prediccion: ignora tendencia, volumen y saltos. La IA solo interpreta estos numeros,
nunca los calcula.
"""
import math
from typing import Optional

HORIZON_BARS = 24
# shortcut: sigma ~ ATR/1.6 (rango esperado de una vela browniana = 1.6 sigma); si hay
# velas a mano conviene la desviacion de cierres, ver sigma_from_closes en el handler.
_ATR_PER_SIGMA = 1.6


def _ok(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def sigma_from_atr(atr) -> Optional[float]:
    return atr / _ATR_PER_SIGMA if _ok(atr) and atr > 0 else None


def touch_probability(price, level, sigma, bars: int = HORIZON_BARS) -> Optional[float]:
    """Probabilidad (0-1) de tocar `level` desde `price` en `bars` velas; None si faltan datos."""
    if not (_ok(price) and _ok(level) and _ok(sigma)):
        return None
    if price <= 0 or level <= 0 or sigma <= 0 or bars <= 0:
        return None
    d = abs(level - price)
    if d == 0:
        return 1.0
    z = d / (sigma * math.sqrt(bars))
    return math.erfc(z / math.sqrt(2))  # == 2 * (1 - Phi(z))


def levels_probabilities(price, levels: dict, sigma, bars: int = HORIZON_BARS) -> dict:
    """{nombre: prob} solo para los niveles con dato valido."""
    out = {}
    for name, lvl in levels.items():
        p = touch_probability(price, lvl, sigma, bars)
        if p is not None:
            out[name] = p
    return out


def format_pct(p: Optional[float]) -> str:
    if p is None:
        return "--"
    if p >= 0.995:
        return ">99%"
    if p < 0.005:
        return "<1%"
    return f"{round(p * 100)}%"
