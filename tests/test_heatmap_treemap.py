"""Treemap squarified: propiedades geometricas (sin red, sin Pillow)."""

import pytest

from src.heatmap.treemap import squarify

LIENZO = (0.0, 0.0, 1200.0, 700.0)


def _area(r):
    return r[2] * r[3]


def _interseccion(a, b):
    ancho = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    alto = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0.0, ancho) * max(0.0, alto)


def test_vacio_devuelve_lista_vacia():
    assert squarify([], *LIENZO) == []


def test_un_solo_peso_ocupa_todo_el_lienzo():
    (r,) = squarify([5.0], *LIENZO)
    assert r == pytest.approx(LIENZO)


@pytest.mark.parametrize(
    "pesos",
    [
        [6, 6, 4, 3, 2, 2, 1],
        [1000, 500, 250, 125, 60, 30, 15, 8, 4, 2, 1],
        [1] * 37,
        [900, 3, 3, 3, 3, 3, 3],
    ],
)
def test_areas_proporcionales_dentro_del_lienzo_y_sin_solapes(pesos):
    rects = squarify(pesos, *LIENZO)
    assert len(rects) == len(pesos)

    total_lienzo = LIENZO[2] * LIENZO[3]
    for peso, r in zip(pesos, rects):
        assert _area(r) == pytest.approx(total_lienzo * peso / sum(pesos), rel=1e-9)
        assert r[0] >= LIENZO[0] - 1e-6 and r[1] >= LIENZO[1] - 1e-6
        assert r[0] + r[2] <= LIENZO[0] + LIENZO[2] + 1e-6
        assert r[1] + r[3] <= LIENZO[1] + LIENZO[3] + 1e-6

    assert sum(_area(r) for r in rects) == pytest.approx(total_lienzo, rel=1e-9)
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert _interseccion(rects[i], rects[j]) < 1e-6


def test_respeta_el_orden_de_entrada():
    pesos = [50, 30, 20]
    rects = squarify(pesos, *LIENZO)
    areas = [_area(r) for r in rects]
    assert areas == sorted(areas, reverse=True)


@pytest.mark.parametrize("malos", [[1, 0, 2], [1, -3], [float("nan"), 1]])
def test_pesos_no_positivos_o_nan_se_rechazan(malos):
    with pytest.raises(ValueError):
        squarify(malos, *LIENZO)
