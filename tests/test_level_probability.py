"""Probabilidad de toque de niveles S/R/Pivot: calculo determinista, sin IA ni red."""
import math

import pytest

from src.core.level_probability import (
    HORIZON_BARS,
    format_pct,
    levels_probabilities,
    sigma_from_atr,
    touch_probability,
)


def test_nivel_en_el_precio_es_100():
    assert touch_probability(100.0, 100.0, sigma=1.0, bars=24) == 1.0


def test_cerca_es_mas_probable_que_lejos():
    near = touch_probability(100.0, 101.0, sigma=1.0, bars=24)
    far = touch_probability(100.0, 110.0, sigma=1.0, bars=24)
    assert near > far
    assert 0.0 <= far < near <= 1.0


def test_simetrico_arriba_y_abajo():
    up = touch_probability(100.0, 103.0, sigma=1.0, bars=24)
    down = touch_probability(100.0, 97.0, sigma=1.0, bars=24)
    assert up == pytest.approx(down)


def test_mas_velas_mas_probabilidad():
    assert touch_probability(100.0, 105.0, 1.0, 48) > touch_probability(100.0, 105.0, 1.0, 12)


def test_valor_conocido_principio_de_reflexion():
    # d = sigma * sqrt(n)  ->  P = 2 * (1 - Phi(1)) = 0.3173
    p = touch_probability(100.0, 100.0 + math.sqrt(24), sigma=1.0, bars=24)
    assert p == pytest.approx(0.3173, abs=1e-3)


@pytest.mark.parametrize("sigma", [0, -1, None, float("nan")])
def test_sigma_invalida_devuelve_none(sigma):
    assert touch_probability(100.0, 105.0, sigma=sigma, bars=24) is None


@pytest.mark.parametrize("price,level", [(0, 100), (None, 100), (100, 0), (100, None), (float("nan"), 1)])
def test_entradas_invalidas_devuelven_none(price, level):
    assert touch_probability(price, level, sigma=1.0, bars=24) is None


def test_sigma_from_atr():
    assert sigma_from_atr(1.6) == pytest.approx(1.0)
    assert sigma_from_atr(0) is None
    assert sigma_from_atr(None) is None


def test_levels_probabilities_devuelve_solo_niveles_validos():
    levels = {"R1": 105.0, "Pivot": 100.5, "S1": 0, "S2": None}
    out = levels_probabilities(100.0, levels, sigma=1.0)
    assert set(out) == {"R1", "Pivot"}
    assert out["Pivot"] > out["R1"]


def test_levels_probabilities_sin_sigma_es_vacio():
    assert levels_probabilities(100.0, {"R1": 105.0}, sigma=None) == {}


def test_horizonte_por_defecto():
    assert HORIZON_BARS == 24


@pytest.mark.parametrize(
    "p,esperado",
    [(0.624, "62%"), (0.004, "<1%"), (0.999, ">99%"), (1.0, ">99%"), (None, "--")],
)
def test_format_pct(p, esperado):
    assert format_pct(p) == esperado
