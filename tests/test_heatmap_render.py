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


def test_fuente_del_mapa_dibuja_acentos():
    """La fuente por defecto de Pillow no trae ñ/ó/í y las pinta como recuadro."""
    from src.heatmap import render

    fuente = render._fuente(15)
    sin_glifo = fuente.getmask("\uffff").getbbox()
    for c in "ñóíáé":
        assert fuente.getmask(c).getbbox() != sin_glifo, c


def test_colores_vivos_saturados_en_el_tope_y_visibles_con_poca_variacion():
    assert color_variacion(5.0, 5.0)[1] >= 190  # verde pleno
    assert color_variacion(-5.0, 5.0)[0] >= 230  # rojo pleno
    r, g, b = color_variacion(1.0, 5.0)  # +1 % ya se distingue del neutro
    assert g - r >= 55


# ---------------- M1: logos dentro de las celdas ----------------


def _logo(color=(255, 0, 255), lado=64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (lado, lado), color + (255,)).save(buf, format="PNG")
    return buf.getvalue()


def _tiene_color(png: bytes, color) -> bool:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    return any(c == color for _, c in img.getcolors(maxcolors=2_000_000))


def test_celda_tiene_ref_opcional_al_final():
    assert Celda("BTC", 1.0, 2.0).ref is None  # las llamadas posicionales actuales siguen valiendo
    assert Celda("BTC", 1.0, 2.0, 1).ref == 1


def test_sin_logos_el_resultado_es_el_de_siempre():
    celdas = [Celda("BTC", 100.0, 2.0, 1), Celda("ETH", 50.0, -1.0, 1027)]
    base = render_mapa(celdas, **_args())
    assert render_mapa(celdas, **_args(), logos=None) == base
    assert render_mapa(celdas, **_args(), logos={}) == base


def test_el_logo_se_dibuja_dentro_de_su_celda():
    celdas = [Celda("BTC", 100.0, 2.0, 1)]
    sin = render_mapa(celdas, **_args())
    con = render_mapa(celdas, **_args(), logos={1: _logo()})
    assert con != sin
    assert _tiene_color(con, (255, 0, 255)) and not _tiene_color(sin, (255, 0, 255))
    assert Image.open(io.BytesIO(con)).size == (render.ANCHO, render.ALTO)


def test_el_logo_solo_se_usa_si_el_ref_coincide():
    celdas = [Celda("BTC", 100.0, 2.0, 1), Celda("ETH", 50.0, -1.0, None)]
    con = render_mapa(celdas, **_args(), logos={999: _logo()})
    assert not _tiene_color(con, (255, 0, 255))


def test_logo_con_bytes_invalidos_se_ignora_y_queda_el_simbolo():
    celdas = [Celda("BTC", 100.0, 2.0, 1)]
    assert render_mapa(celdas, **_args(), logos={1: b"no soy png"}) == render_mapa(celdas, **_args())


def test_celdas_pequenas_con_logo_no_revientan_el_render():
    celdas = [Celda(f"C{i}", 1000.0 / (i + 1), (i % 9 - 4) * 1.1, i + 1) for i in range(100)]
    datos = render_mapa(celdas, **_args(), logos={i + 1: _logo() for i in range(100)})
    assert Image.open(io.BytesIO(datos)).size == (render.ANCHO, render.ALTO)
    assert len(datos) < 2_000_000


def test_celda_diminuta_no_dibuja_logo():
    # Una celda enorme y otra microscopica: el logo de la microscopica (rojo) no debe aparecer.
    celdas = [Celda("GRANDE", 1_000_000.0, 1.0, 1), Celda("MICRO", 1.0, -1.0, 2)]
    datos = render_mapa(celdas, **_args(), logos={2: _logo((255, 0, 0))})
    assert not _tiene_color(datos, (255, 0, 0))
