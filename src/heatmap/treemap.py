"""Treemap squarified (Bruls, Huizing, van Wijk). Python puro, sin dependencias."""

from math import isfinite


def _peor_razon(fila, lado):
    """Peor proporcion ancho/alto de una fila de areas colocada sobre `lado`."""
    s = sum(fila)
    return max(lado * lado * max(fila) / (s * s), s * s / (lado * lado * min(fila)))


def squarify(pesos, x, y, w, h):
    """Reparte el rectangulo (x, y, w, h) en celdas de area proporcional a `pesos`.

    `pesos` debe venir ordenado de mayor a menor para que las celdas queden
    lo mas cuadradas posible. Devuelve [(x, y, w, h)] en el mismo orden.
    """
    if not pesos:
        return []
    if any(not isfinite(p) or p <= 0 for p in pesos):
        raise ValueError("los pesos deben ser numeros finitos mayores que 0")

    escala = w * h / float(sum(pesos))
    areas = [p * escala for p in pesos]
    rects = []
    i = 0
    while i < len(areas):
        lado = min(w, h)
        fila = [areas[i]]
        j = i + 1
        while j < len(areas) and _peor_razon(fila + [areas[j]], lado) <= _peor_razon(fila, lado):
            fila.append(areas[j])
            j += 1
        franja = sum(fila) / lado
        pos = y if w >= h else x
        for a in fila:
            largo = a / franja
            rects.append((x, pos, franja, largo) if w >= h else (pos, y, largo, franja))
            pos += largo
        if w >= h:
            x += franja
            w -= franja
        else:
            y += franja
            h -= franja
        i = j
    return rects
