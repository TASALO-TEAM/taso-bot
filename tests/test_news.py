# tests/test_news.py
"""Tests para src/handlers/news.py: resolución de subcomandos, scoring de
tendencias aproximado y armado del cuerpo cacheado."""

import pytest
from unittest.mock import AsyncMock, patch

from src.handlers.news import (
    _resolve_subcommand,
    _score_trending,
    _get_or_build_news_body,
    _TRENDING_SENTINEL,
)


# ── _resolve_subcommand: comportamiento existente ──

class TestResolveSubcommandExistente:
    def test_sin_argumento_es_general(self):
        assert _resolve_subcommand(None) == (None, None, "general")

    def test_coin_conocida(self):
        assert _resolve_subcommand("btc") == (["btc"], None, "BTC")

    def test_coin_case_insensitive(self):
        assert _resolve_subcommand("BTC") == (["btc"], None, "BTC")

    def test_topic_predefinido(self):
        assert _resolve_subcommand("defi") == (None, "DeFi", "defi")

    def test_query_libre(self):
        assert _resolve_subcommand("halving") == (None, "halving", "halving")


# ── _resolve_subcommand: alias nuevos ──

class TestResolveSubcommandAliasNuevos:
    @pytest.mark.parametrize("arg", ["headlines", "HEADLINES", "titulares"])
    def test_headlines_alias_a_general(self, arg):
        """headlines/titulares deben comportarse EXACTO igual que /news sin
        argumento (mismo cache_key, mismo feed) — no es un filtro nuevo,
        solo un nombre más claro para el mismo resultado."""
        assert _resolve_subcommand(arg) == (None, None, "general")

    @pytest.mark.parametrize("arg", ["hot", "HOT", "trending"])
    def test_hot_trending_alias_a_sentinel(self, arg):
        """hot/trending activan el sentinel de tendencias, no una query
        literal de búsqueda."""
        assert _resolve_subcommand(arg) == (None, _TRENDING_SENTINEL, "trending")


# ── _score_trending ──

def _articulo(titulo, keywords, idx=0):
    return {
        "title": titulo,
        "description": "desc",
        "url": f"https://example.com/{idx}",
        "source_name": "Fuente",
        "published_at": "2026-07-25T00:00:00Z",
        "keywords": keywords,
    }


class TestScoreTrending:
    def test_lista_vacia(self):
        assert _score_trending([]) == []

    def test_prioriza_keywords_compartidas(self):
        """Un artículo cuyas keywords se repiten en varios otros debe subir
        por encima de uno con keywords únicas, aunque este último aparezca
        primero en la lista original."""
        unico = _articulo("Nota aislada", ["oscuro", "raro"], idx=0)
        compartido_a = _articulo("ETF de Bitcoin avanza", ["etf", "bitcoin"], idx=1)
        compartido_b = _articulo("SEC revisa ETF spot", ["etf", "sec"], idx=2)
        compartido_c = _articulo("Bitcoin ETF bate récord", ["etf", "bitcoin"], idx=3)

        articulos = [unico, compartido_a, compartido_b, compartido_c]
        ranked = _score_trending(articulos)

        # Los 3 que comparten "etf"/"bitcoin" deben ir antes que el aislado
        assert ranked[-1] == unico
        assert unico not in ranked[:3]

    def test_empate_mantiene_orden_original(self):
        """Si dos artículos quedan con el mismo score, se respeta el orden
        en que llegaron (más reciente primero, según la fuente)."""
        a = _articulo("A", [], idx=0)
        b = _articulo("B", [], idx=1)
        assert _score_trending([a, b]) == [a, b]


# ── _get_or_build_news_body: integración con caché y cliente ──

@pytest.mark.asyncio
class TestGetOrBuildNewsBody:
    async def test_cache_hit_no_llama_al_cliente(self):
        with patch("src.handlers.news.cache") as mock_cache, \
             patch("src.handlers.news.get_newsdata_client") as mock_get_client:
            mock_cache.get.return_value = "Cuerpo cacheado"

            resultado = await _get_or_build_news_body(None, None, "news_general")

            assert resultado == "Cuerpo cacheado"
            mock_get_client.assert_not_called()

    async def test_filtro_normal_pide_8_articulos(self):
        with patch("src.handlers.news.cache") as mock_cache, \
             patch("src.handlers.news.get_newsdata_client") as mock_get_client:
            mock_cache.get.return_value = None
            mock_client = AsyncMock()
            mock_client.get_crypto_news = AsyncMock(
                return_value=[_articulo("T", ["k"], idx=0)]
            )
            mock_get_client.return_value = mock_client

            resultado = await _get_or_build_news_body(["btc"], None, "news_BTC")

            assert resultado is not None
            _, kwargs = mock_client.get_crypto_news.call_args
            assert kwargs["limit"] == 8
            mock_cache.set.assert_called_once()

    async def test_trending_pide_30_articulos_y_escora(self):
        """El sentinel de tendencias debe pedir un lote más grande (para
        tener con qué comparar keywords) y devolver como máximo 8 en el
        cuerpo final, ya ordenados por _score_trending."""
        with patch("src.handlers.news.cache") as mock_cache, \
             patch("src.handlers.news.get_newsdata_client") as mock_get_client:
            mock_cache.get.return_value = None
            mock_client = AsyncMock()
            mock_client.get_crypto_news = AsyncMock(
                return_value=[_articulo(f"T{i}", ["etf"], idx=i) for i in range(12)]
            )
            mock_get_client.return_value = mock_client

            resultado = await _get_or_build_news_body(
                None, _TRENDING_SENTINEL, "news_trending"
            )

            assert resultado is not None
            _, kwargs = mock_client.get_crypto_news.call_args
            assert kwargs["limit"] == 30
            assert kwargs["query"] is None
            assert kwargs["coin"] is None
            # Solo se cachean/muestran 8 de los 12 recibidos
            assert resultado.count("*T") <= 8
            mock_cache.set.assert_called_once()

    async def test_trending_sin_resultados_devuelve_none(self):
        with patch("src.handlers.news.cache") as mock_cache, \
             patch("src.handlers.news.get_newsdata_client") as mock_get_client:
            mock_cache.get.return_value = None
            mock_client = AsyncMock()
            mock_client.get_crypto_news = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            resultado = await _get_or_build_news_body(
                None, _TRENDING_SENTINEL, "news_trending"
            )

            assert resultado is None
            mock_cache.set.assert_not_called()
