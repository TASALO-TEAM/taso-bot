"""/graf: lineas de niveles del pie de foto con probabilidad de toque (limite 1024 de Telegram)."""
from src.handlers.trading import _graf_levels_lines


def test_porcentajes_en_pivot_r1_s1():
    txt = _graf_levels_lines(100.0, 110.0, 90.0, {"Pivot": 0.97, "R1": 0.31, "S1": 0.28})
    assert "Pivot:* `$100" in txt and "97%" in txt
    assert "31%" in txt and "28%" in txt
    assert "24 velas" in txt


def test_sin_probabilidades_mantiene_el_formato_anterior():
    txt = _graf_levels_lines(100.0, 110.0, 90.0, {})
    assert "%" not in txt
    assert "R1:" in txt and "S1:" in txt and "Pivot:" in txt


def test_cabe_en_el_caption_con_margen():
    txt = _graf_levels_lines(123456.789, 130000.5, 110000.25, {"Pivot": 0.5, "R1": 0.3, "S1": 0.2})
    assert len(txt) < 250


def test_markdown_v1_balanceado():
    txt = _graf_levels_lines(100.0, 110.0, 90.0, {"Pivot": 0.97, "R1": 0.31, "S1": 0.28})
    assert txt.count("`") % 2 == 0 and txt.count("*") % 2 == 0
