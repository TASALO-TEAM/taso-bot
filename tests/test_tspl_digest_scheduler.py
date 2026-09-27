# tests/test_tspl_digest_scheduler.py
"""Tests para las mejoras de contexto de mercado y grounding de CMC AI en
el digest diario de /tspl (ver
docs/plans/2026-09-27-tspl-market-context-mejora.md):

- _fetch_tspl_market_context(): suma dominancia/market cap/altseason/CMC
  AI en paralelo, tolerante a fallos parciales.
- _cmc_ai_insights_to_articles(): normaliza insights de CMC AI al shape
  de articulo (title/description/source_name).
- generate_and_cache_tspl_digest(): mezcla esos insights normalizados al
  pool de articulos que arma antes de llamar a Groq.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import src.services.tspl_digest_scheduler as scheduler


def _crypto_client_stub(
    fear_greed=None, btc_data=None, global_metrics=None,
    altcoin_season=None, cmc_ai_feed=None, raise_on=None,
):
    """Cliente falso con los 5 métodos que junta _fetch_tspl_market_context.
    `raise_on` es un set de nombres de método que deben lanzar una
    excepción (para probar tolerancia a fallos parciales)."""
    raise_on = raise_on or set()
    client = MagicMock()

    def _maybe_raise(name, value):
        if name in raise_on:
            async def _raiser(*a, **kw):
                raise RuntimeError(f"{name} falló")
            return _raiser
        async def _ok(*a, **kw):
            return value
        return _ok

    client.get_fear_greed = _maybe_raise("get_fear_greed", fear_greed)
    client.get_crypto_data = _maybe_raise("get_crypto_data", btc_data)
    client.get_global_metrics = _maybe_raise("get_global_metrics", global_metrics)
    client.get_altcoin_season_index = _maybe_raise("get_altcoin_season_index", altcoin_season)
    client.get_cmc_ai_market_feed = _maybe_raise("get_cmc_ai_market_feed", cmc_ai_feed)
    return client


# ── _fetch_tspl_market_context ──

@pytest.mark.asyncio
async def test_fetch_market_context_incluye_los_5_campos_nuevos_cuando_todo_responde():
    client = _crypto_client_stub(
        fear_greed={"value": 70, "classification": "Greed"},
        btc_data={"price": 85000.0, "percent_change_24h": 1.5},
        global_metrics={"btc_dominance": 58.6, "market_cap_change_24h": 0.69},
        altcoin_season={"value": 63, "label": "Mixto"},
        cmc_ai_feed={"insights": [{"title": "Q", "answer": {"tldr": "T"}, "sources": []}]},
    )
    with patch("src.services.tspl_digest_scheduler.get_crypto_client", return_value=client):
        result = await scheduler._fetch_tspl_market_context()

    assert result is not None
    assert result["btc_dominance"] == 58.6
    assert result["market_cap_change_24h"] == 0.69
    assert result["altcoin_season_value"] == 63
    assert result["altcoin_season_label"] == "Mixto"
    assert result["cmc_ai_market_feed"]["insights"][0]["title"] == "Q"


@pytest.mark.asyncio
async def test_fetch_market_context_tolera_fallo_parcial_en_campos_nuevos():
    """Si global_metrics/altseason/cmc_ai fallan, Fear&Greed y BTC (los
    dos obligatorios de antes) siguen presentes — no regresión."""
    client = _crypto_client_stub(
        fear_greed={"value": 70, "classification": "Greed"},
        btc_data={"price": 85000.0, "percent_change_24h": 1.5},
        raise_on={"get_global_metrics", "get_altcoin_season_index", "get_cmc_ai_market_feed"},
    )
    with patch("src.services.tspl_digest_scheduler.get_crypto_client", return_value=client):
        result = await scheduler._fetch_tspl_market_context()

    assert result is not None
    assert result["fng_value"] == 70
    assert result["btc_price"] == 85000.0
    assert result["btc_dominance"] is None
    assert result["cmc_ai_market_feed"] is None


@pytest.mark.asyncio
async def test_fetch_market_context_none_si_fng_y_btc_fallan_ambos():
    client = _crypto_client_stub(raise_on={"get_fear_greed", "get_crypto_data"})
    with patch("src.services.tspl_digest_scheduler.get_crypto_client", return_value=client):
        result = await scheduler._fetch_tspl_market_context()

    assert result is None


# ── _cmc_ai_insights_to_articles ──

def test_cmc_ai_insights_to_articles_vacio_sin_feed():
    assert scheduler._cmc_ai_insights_to_articles(None) == []
    assert scheduler._cmc_ai_insights_to_articles({}) == []
    assert scheduler._cmc_ai_insights_to_articles({"insights": []}) == []


def test_cmc_ai_insights_to_articles_normaliza_al_shape_de_articulo():
    feed = {
        "insights": [
            {"title": "BTC price up", "answer": {"tldr": "TLDR aqui", "body": "Body aqui"}, "sources": []},
        ]
    }
    result = scheduler._cmc_ai_insights_to_articles(feed)

    assert len(result) == 1
    assert result[0]["title"] == "BTC price up"
    assert "TLDR aqui" in result[0]["description"]
    assert "Body aqui" in result[0]["description"]
    assert result[0]["source_name"] == "CoinMarketCap AI"


def test_cmc_ai_insights_to_articles_ignora_items_sin_contenido():
    feed = {"insights": [{"title": "", "answer": {}, "sources": []}]}
    assert scheduler._cmc_ai_insights_to_articles(feed) == []


# ── generate_and_cache_tspl_digest: merge de CMC AI al pool de articulos ──

@pytest.mark.asyncio
async def test_generate_digest_mezcla_insights_de_cmc_ai_al_pool_de_articulos():
    newsdata_articles = [{"title": "Noticia NewsData", "description": "desc", "source_name": "CoinDesk"}]
    market_data = {
        "fng_value": 70,
        "cmc_ai_market_feed": {
            "insights": [{"title": "Insight CMC", "answer": {"tldr": "tldr cmc"}, "sources": []}]
        },
    }

    news_client = MagicMock()
    news_client.get_crypto_news = AsyncMock(return_value=newsdata_articles)

    with (
        patch("src.services.tspl_digest_scheduler.get_newsdata_client", return_value=news_client),
        patch("src.services.tspl_digest_scheduler._fetch_tspl_market_context", AsyncMock(return_value=market_data)),
        patch("src.services.tspl_digest_scheduler.get_groq_tspl_digest", AsyncMock(return_value={"items": []})) as mock_groq,
        patch("src.services.tspl_digest_scheduler.cache") as mock_cache,
    ):
        await scheduler.generate_and_cache_tspl_digest()

    articles_arg = mock_groq.await_args.args[0]
    titles = [a["title"] for a in articles_arg]
    assert "Noticia NewsData" in titles
    assert "Insight CMC" in titles


@pytest.mark.asyncio
async def test_generate_digest_sin_cmc_ai_feed_no_agrega_nada_al_pool():
    """Caso real de produccion hoy (plan Basic, 403) — cmc_ai_market_feed
    es None y el pool de articulos queda igual que antes de este cambio."""
    newsdata_articles = [{"title": "Noticia NewsData", "description": "desc", "source_name": "CoinDesk"}]
    market_data = {"fng_value": 70, "cmc_ai_market_feed": None}

    news_client = MagicMock()
    news_client.get_crypto_news = AsyncMock(return_value=newsdata_articles)

    with (
        patch("src.services.tspl_digest_scheduler.get_newsdata_client", return_value=news_client),
        patch("src.services.tspl_digest_scheduler._fetch_tspl_market_context", AsyncMock(return_value=market_data)),
        patch("src.services.tspl_digest_scheduler.get_groq_tspl_digest", AsyncMock(return_value={"items": []})) as mock_groq,
        patch("src.services.tspl_digest_scheduler.cache"),
    ):
        await scheduler.generate_and_cache_tspl_digest()

    articles_arg = mock_groq.await_args.args[0]
    assert len(articles_arg) == 1
    assert articles_arg[0]["title"] == "Noticia NewsData"
