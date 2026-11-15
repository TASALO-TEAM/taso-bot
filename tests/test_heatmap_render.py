"""Render del mapa de calor con Pillow (sin red, datos fijos)."""

import io

import pytest
from PIL import Image

from src.heatmap import render
from src.heatmap.render import Celda, color_variacion, etiqueta_variacion, render_mapa


def _args(**extra):
    base = dict(
        titulo="Mapa de calor cripto - 24 h",
        subtitulo="Tamano = capitalizacion",
        fuente="Fuente: CoinMarketCap",
        generado="15 nov 2026 10:30",
        tope=5.0,
    )
    base.update(extra)
    return base


def test_color_cero_es_neutro_y_none_es_gris():
    r, g, b = color_variacion(0.0, 5.0)
    assert abs(r - g) <= 10 and abs(g - b) <= 15
    assert color_variacion(None, 5.0) == render.COLOR_SIN_DATO


def test_color_positivo_es_verde_y_negativo_es_rojo():
    r, g, b = color_variacion(4.0, 5.0)
    assert g > r and g > b
    r, g, b = color_variacion(-4.0, 5.0)
    assert r > g and r > b


def test_color_satura_en_el_tope():
    assert color_variacion(50.0, 5.0) == color_variacion(5.0, 5.0)
    assert color_variacion(-50.0, 5.0) == color_variacion(-5.0, 5.0)


def test_color_mas_fuerte_cuanto_mayor_la_variacion():
    suave = color_variacion(1.0, 5.0)
    fuerte = color_variacion(4.0, 5.0)
    assert sum(abs(c - n) for c, n in zip(fuerte, render.COLOR_NEUTRO)) > sum(
        abs(c - n) for c, n in zip(suave, render.COLOR_NEUTRO)
    )


@pytest.mark.parametrize(
    "valor, esperado",
    [(2.314, "+2.31%"), (-1.049, "-1.05%"), (0.0, "0.00%"), (None, "s/d")],
)
def test_etiqueta_variacion(valor, esperado):
    assert etiqueta_variacion(valor) == esperado


def test_render_devuelve_png_del_tamano_esperado():
    celdas = [Celda(f"C{i}", 1000.0 / (i + 1), (i % 9 - 4) * 1.1) for i in range(100)]
    datos = render_mapa(celdas, **_args())
    assert datos[:8] == b"\x89PNG\r\n\x1a\n"
    img = Image.open(io.BytesIO(datos))
    assert img.size == (render.ANCHO, render.ALTO)
    assert len(datos) < 2_000_000


def test_render_rechaza_entrada_vacia():
    with pytest.raises(ValueError):
        render_mapa([], **_args())


def test_render_acepta_celdas_sin_variacion():
    datos = render_mapa([Celda("AAA", 10.0, None), Celda("BBB", 5.0, 1.0)], **_args())
    assert Image.open(io.BytesIO(datos)).size == (render.ANCHO, render.ALTO)


def test_el_color_de_la_celda_se_pinta_en_su_zona():
    # Una sola celda ocupa toda el area util; su esquina superior izquierda
    # (lejos del texto centrado) debe tener el color de la escala.
    datos = render_mapa([Celda("UNO", 1.0, 5.0)], **_args())
    img = Image.open(io.BytesIO(datos)).convert("RGB")
    assert img.getpixel((6, render.CABECERA + 6)) == color_variacion(5.0, 5.0)
