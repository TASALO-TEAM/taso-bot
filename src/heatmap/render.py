"""Render del mapa de calor con Pillow. Sin red, sin pandas/numpy/matplotlib."""

import io
from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from src.heatmap.treemap import squarify

ANCHO = 1200
ALTO = 800
CABECERA = 64
PIE = 28
GAP = 1  # separacion entre celdas (px)

COLOR_FONDO = (18, 20, 26)
COLOR_NEUTRO = (66, 70, 82)
COLOR_SIN_DATO = (90, 90, 90)
COLOR_VERDE = (22, 200, 90)
COLOR_ROJO = (240, 50, 55)
COLOR_TEXTO = (240, 242, 245)
COLOR_TENUE = (150, 156, 168)
MARCA = "TASALO Bot"
FUENTE_MARCA = Path(__file__).resolve().parents[2] / "fonts" / "SpaceGrotesk-Regular.ttf"


@dataclass(frozen=True)
class Celda:
    simbolo: str
    peso: float
    variacion: Optional[float]
    ref: Optional[int] = None  # id del proveedor (CMC): clave del logo de la celda


def color_variacion(variacion, tope):
    """Color de la celda: gris neutro en 0, verde/rojo creciente hasta `tope`."""
    if variacion is None or not isfinite(variacion):
        return COLOR_SIN_DATO
    t = min(abs(variacion) / tope, 1.0) ** 0.65  # curva: las variaciones pequeñas ya se ven
    destino = COLOR_VERDE if variacion > 0 else COLOR_ROJO
    return tuple(round(n + (d - n) * t) for n, d in zip(COLOR_NEUTRO, destino))


def etiqueta_variacion(variacion):
    if variacion is None or not isfinite(variacion):
        return "s/d"
    return f"{variacion:+.2f}%" if round(variacion, 2) != 0 else "0.00%"


@lru_cache(maxsize=32)
def _fuente(tam):
    # La embebida de Pillow no trae ñ/ó/í (las pinta como recuadro): se usa la de marca.
    try:
        return ImageFont.truetype(str(FUENTE_MARCA), tam)
    except OSError:
        return ImageFont.load_default(size=tam)


def _texto_celda(draw, rect, celda):
    _, _, w, h = rect
    lado = min(w, h)
    if w < 34 or h < 20:
        return
    tam = max(10, min(40, int(lado / 3.2)))
    cx, cy = rect[0] + w / 2, rect[1] + h / 2
    doble = h >= tam * 2.6 and w >= tam * 3.2
    draw.text(
        (cx, cy - (tam * 0.55 if doble else 0)),
        celda.simbolo,
        font=_fuente(tam),
        fill=COLOR_TEXTO,
        anchor="mm",
    )
    if doble:
        draw.text(
            (cx, cy + tam * 0.6),
            etiqueta_variacion(celda.variacion),
            font=_fuente(max(9, int(tam * 0.65))),
            fill=COLOR_TEXTO,
            anchor="mm",
        )


LOGO_MIN = 30  # lado minimo (px) de la celda para dibujar logo
LOGO_MAX = 128  # lado maximo (px) del logo: es el tamano nativo del que se descarga


def _decodificar_logos(logos):
    """bytes -> imagenes RGBA. Son datos de un proveedor externo: si alguno no se
    puede abrir, esa celda se queda con su simbolo (nunca falla el mapa)."""
    listos = {}
    for ref, datos in (logos or {}).items():
        try:
            with Image.open(io.BytesIO(datos)) as im:
                listos[ref] = im.convert("RGBA")
        except Exception:
            continue
    return listos


def _logo_celda(img, draw, rect, celda, logo):
    """Logo centrado y, si cabe, simbolo (y variacion) debajo. False = no dibujo nada."""
    if logo is None:
        return False
    x, y, w, h = rect
    lado = min(w, h)
    if lado < LOGO_MIN:
        return False
    s = int(max(16, min(lado * 0.4, LOGO_MAX)))
    tam = max(10, min(32, int(lado / 4)))
    texto = h >= s + tam * 1.9 + 6 and w >= tam * 3.2
    doble = texto and h >= s + tam * 3.2 + 10
    total = s + (tam * 1.4 if texto else 0) + (tam * 1.0 if doble else 0)
    cx, top = x + w / 2, y + (h - total) / 2
    pegado = logo.resize((s, s), Image.Resampling.LANCZOS)
    img.paste(pegado, (round(cx - s / 2), round(top)), pegado)
    if texto:
        draw.text((cx, top + s + tam * 0.8), celda.simbolo, font=_fuente(tam), fill=COLOR_TEXTO, anchor="mm")
    if doble:
        draw.text(
            (cx, top + s + tam * 1.75), etiqueta_variacion(celda.variacion),
            font=_fuente(max(9, int(tam * 0.7))), fill=COLOR_TEXTO, anchor="mm",
        )
    return True


def render_mapa(celdas, titulo, subtitulo, fuente, generado, tope, logos=None):
    """Dibuja el treemap y devuelve los bytes del PNG. `logos`: {ref: bytes PNG} opcional."""
    validas = sorted(
        (c for c in celdas if isfinite(c.peso) and c.peso > 0),
        key=lambda c: c.peso,
        reverse=True,
    )
    if not validas:
        raise ValueError("no hay celdas con peso positivo para dibujar")

    img = Image.new("RGB", (ANCHO, ALTO), COLOR_FONDO)
    draw = ImageDraw.Draw(img)

    imagenes = _decodificar_logos(logos)
    area_alto = ALTO - CABECERA - PIE
    rects = squarify([c.peso for c in validas], 0.0, float(CABECERA), float(ANCHO), float(area_alto))
    for celda, (x, y, w, h) in zip(validas, rects):
        caja = (round(x) + GAP, round(y) + GAP, round(x + w) - GAP - 1, round(y + h) - GAP - 1)
        if caja[2] < caja[0] or caja[3] < caja[1]:
            continue
        draw.rectangle(caja, fill=color_variacion(celda.variacion, tope))
        rect = (caja[0], caja[1], caja[2] - caja[0], caja[3] - caja[1])
        if not _logo_celda(img, draw, rect, celda, imagenes.get(celda.ref)):
            _texto_celda(draw, rect, celda)

    draw.text((16, 10), titulo, font=_fuente(26), fill=COLOR_TEXTO)
    draw.text((16, 40), subtitulo, font=_fuente(17), fill=COLOR_TENUE)
    pie_y = ALTO - PIE // 2
    draw.text((16, pie_y), fuente, font=_fuente(15), fill=COLOR_TENUE, anchor="lm")
    draw.text((ANCHO / 2, pie_y), MARCA, font=_fuente(15), fill=COLOR_TENUE, anchor="mm")
    draw.text((ANCHO - 16, pie_y), generado, font=_fuente(15), fill=COLOR_TENUE, anchor="rm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
