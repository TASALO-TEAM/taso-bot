"""/ta: bloque de niveles con probabilidad de toque (determinista) y sin rotulo 'Experimental'."""
from src.handlers.ta import _levels_block

DATA = {"R3": 130.0, "R2": 120.0, "R1": 110.0, "Pivot": 100.5, "S1": 90.0, "S2": 80.0, "S3": 70.0}


def test_cada_nivel_lleva_su_porcentaje():
    probs = {"R1": 0.31, "Pivot": 0.97, "S1": 0.28}
    txt = _levels_block(DATA, probs)
    assert "R1: `$110.0000` · 31%" in txt
    assert "Pivot: $100.5000*" in txt and "97%" in txt
    assert "S1: `$90.0000` · 28%" in txt


def test_sin_probabilidad_no_rompe_ni_muestra_basura():
    txt = _levels_block(DATA, {})
    assert "R3: `$130.0000`" in txt
    assert "%" not in txt.replace("prob.", "")
    assert "None" not in txt and "nan" not in txt.lower()


def test_titulo_explica_el_horizonte():
    assert "24 velas" in _levels_block(DATA, {"R1": 0.3})


def test_orden_de_arriba_a_abajo():
    txt = _levels_block(DATA, {})
    pos = [txt.index(m) for m in ("R3:", "R2:", "R1:", "Pivot:", "S1:", "S2:", "S3:")]
    assert pos == sorted(pos)


def test_markdown_v1_balanceado():
    txt = _levels_block(DATA, {"R1": 0.31, "Pivot": 0.97})
    assert txt.count("`") % 2 == 0 and txt.count("*") % 2 == 0


def test_prompt_ta_explica_probabilidades_y_se_puede_formatear():
    from src.core import ai_logic

    p = ai_logic.CRYPTO_ANALYSIS_PROMPT
    assert "24 velas" in p and "No la recalcules" in p and "TOQUE" in p
    assert "Experimental" not in p
    out = p.format(symbol="BTCUSDT", timeframe="1h", source="BINANCE", report_text="x")
    assert "{" not in out and "}" not in out


def test_prompt_spotlight_se_puede_formatear():
    from src.core import ai_logic

    out = ai_logic.PRICE_SPOTLIGHT_PROMPT.format(market_data_text="x")
    assert "{" not in out and "}" not in out
