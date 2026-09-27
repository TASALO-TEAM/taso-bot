# tests/test_ai_logic_cmc_ai_grounding.py
"""Tests para el grounding opcional de CMC AI en los prompts de /p y /spl
(ver docs/plans/2026-09-27-cmc-ai-insights-grounding.md).

Cubre solo las funciones de formateo puras (_format_price_spotlight_data,
_format_market_snapshot_text) — no llaman a Groq ni a CMC. El caso
"sin insight disponible" es el más importante: confirma que no hay
regresión en el prompt actual cuando CMC AI no está accesible (403, plan
Basic), que es el estado real de producción hoy.
"""

import src.core.ai_logic as ai_logic


# ── /p — _format_price_spotlight_data ──

def test_price_spotlight_data_sin_cmc_ai_insight_no_agrega_seccion():
    price_data = {"symbol": "BTC", "price": 65000.0, "primary_source": "coinmarketcap"}

    texto = ai_logic._format_price_spotlight_data(price_data)

    assert "CoinMarketCap" not in texto
    assert "analista" not in texto.lower()


def test_price_spotlight_data_con_cmc_ai_insight_agrega_seccion_etiquetada():
    price_data = {
        "symbol": "BTC",
        "price": 65000.0,
        "primary_source": "coinmarketcap",
        "cmc_ai_insight": {
            "question_key": "price_up",
            "answer": {"tldr": "TLDR de prueba", "body": "Body de prueba"},
            "sources": [{"url": "https://www.coindesk.com/algun-articulo"}],
        },
    }

    texto = ai_logic._format_price_spotlight_data(price_data)

    assert "TLDR de prueba" in texto
    assert "Body de prueba" in texto
    assert "en inglés" in texto  # instrucción de traducir, no citar literal


def test_price_spotlight_data_con_insight_vacio_no_rompe():
    """Un dict de insight sin tldr/body (caso raro pero posible) no debe
    agregar una sección vacía ni tirar excepción."""
    price_data = {
        "symbol": "BTC",
        "cmc_ai_insight": {"question_key": "price_up", "answer": {}, "sources": []},
    }

    texto = ai_logic._format_price_spotlight_data(price_data)

    assert "analista" not in texto.lower()


# ── /spl — _format_market_snapshot_text ──

def test_market_snapshot_sin_cmc_ai_feed_no_agrega_seccion():
    snapshot = {"fear_greed": {"value": 50, "classification": "Neutral"}}

    texto = ai_logic._format_market_snapshot_text(snapshot)

    assert "editorial" not in texto.lower()


def test_market_snapshot_con_cmc_ai_feed_agrega_seccion_etiquetada():
    snapshot = {
        "fear_greed": {"value": 50, "classification": "Neutral"},
        "cmc_ai_market_feed": {
            "insights": [
                {"title": "Trending narratives", "answer": {"tldr": "Narrativa de prueba"}, "sources": []},
            ]
        },
    }

    texto = ai_logic._format_market_snapshot_text(snapshot)

    assert "editorial" in texto.lower()
    assert "Narrativa de prueba" in texto
    assert "Trending narratives" in texto


def test_market_snapshot_con_cmc_ai_feed_vacio_no_agrega_seccion():
    snapshot = {"cmc_ai_market_feed": {"insights": []}}

    texto = ai_logic._format_market_snapshot_text(snapshot)

    assert "editorial" not in texto.lower()


def test_market_snapshot_con_cmc_ai_feed_limita_a_5_items():
    snapshot = {
        "cmc_ai_market_feed": {
            "insights": [
                {"title": f"Item {i}", "answer": {"tldr": f"Tldr {i}"}, "sources": []}
                for i in range(8)
            ]
        }
    }

    texto = ai_logic._format_market_snapshot_text(snapshot)

    assert "Item 4" in texto
    assert "Item 5" not in texto
