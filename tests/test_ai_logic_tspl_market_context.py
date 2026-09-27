# tests/test_ai_logic_tspl_market_context.py
"""Tests para _format_tspl_market_context() — las líneas nuevas
(dominancia, market cap 24h, Altcoin Season Index) que se suman al
contexto de mercado del lede de /tspl (ver
docs/plans/2026-09-27-tspl-market-context-mejora.md).

No cubre el grounding de CMC AI acá: esos insights ya no pasan por esta
función (se mezclan como artículos crudos en
tspl_digest_scheduler.generate_and_cache_tspl_digest, ver
test_tspl_digest_scheduler.py) para evitar duplicarlos como item y como
comentario de contexto a la vez.
"""

import src.core.ai_logic as ai_logic


def test_market_context_sin_datos_devuelve_aviso_fijo():
    texto = ai_logic._format_tspl_market_context(None)
    assert "no disponibles" in texto


def test_market_context_solo_fng_y_btc_no_regresion():
    """Con solo los 2 campos que ya existían antes de este cambio, el
    texto no debe mencionar dominancia/market cap/altseason."""
    market_data = {"fng_value": 70, "fng_classification": "Greed", "btc_price": 85000.0, "btc_change_24h": 1.5}

    texto = ai_logic._format_tspl_market_context(market_data)

    assert "Fear & Greed: 70" in texto
    assert "Dominancia" not in texto
    assert "Market cap" not in texto
    assert "Altcoin Season" not in texto


def test_market_context_incluye_dominancia_market_cap_y_altseason_cuando_estan():
    market_data = {
        "fng_value": 70,
        "fng_classification": "Greed",
        "btc_dominance": 58.61,
        "market_cap_change_24h": 0.69,
        "altcoin_season_value": 63,
        "altcoin_season_label": "Mixto",
    }

    texto = ai_logic._format_tspl_market_context(market_data)

    assert "Dominancia BTC: 58.6%" in texto
    assert "Market cap total 24h: sube 0.69%" in texto
    assert "Altcoin Season Index: 63/100 (Mixto)" in texto


def test_market_context_market_cap_negativo_usa_baja():
    market_data = {"fng_value": 70, "market_cap_change_24h": -1.2}

    texto = ai_logic._format_tspl_market_context(market_data)

    assert "Market cap total 24h: baja 1.20%" in texto


def test_market_context_no_repite_insights_de_cmc_ai():
    """Los insights de CMC AI se mezclan como artículos crudos aparte
    (ver tspl_digest_scheduler._cmc_ai_insights_to_articles) — esta
    función no debe volver a mostrarlos, para no duplicar el mismo
    contenido como item y como contexto."""
    market_data = {
        "fng_value": 70,
        "cmc_ai_market_feed": {"insights": [{"title": "X", "answer": {"tldr": "no deberia aparecer aca"}}]},
    }

    texto = ai_logic._format_tspl_market_context(market_data)

    assert "no deberia aparecer aca" not in texto
