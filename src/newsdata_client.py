# src/newsdata_client.py
"""Cliente asíncrono para NewsData.io (noticias para /news y /tspl).

Por qué NewsData.io y no CryptoPanic ni CoinDesk Data (ex-CryptoCompare):
ambos fueron investigados primero, pero:
  - CryptoPanic ya no muestra un plan gratis en su página real de planes
    (cryptopanic.com/developers/api/about) — lo que encontré antes en
    buscadores eran páginas de marketing desactualizadas/de terceros.
  - CoinDesk Data (la API que era CryptoCompare/min-api) retiró su tier
    gratis el 21 de mayo de 2026 — confirmado en su propio blog oficial
    (data.coindesk.com/blogs/changes-to-coindesk-data-indices-api-free-tier-access)
    y en reportes de desarrolladores de junio 2026. Ya NO es gratis.

NewsData.io sí tiene un plan gratis vigente y verificado directo en su
página oficial (newsdata.io/blog/pricing-plan-in-newsdata-io, actualizada
22 jun 2026): 200 créditos/día, 10 artículos por crédito, incluye
explícitamente el endpoint "Crypto & Coin News API", uso comercial
permitido en el plan gratis. Limitaciones del plan gratis: artículos con
12h de delay, sin contenido completo del artículo (solo title+description,
que es justo lo que necesitamos), límite de 100 caracteres en queries de
búsqueda.

Ver docs/plans/2026-07-23-tspl-news-newsdata.md para el diseño completo.

Nunca propaga excepciones: cualquier error (sin key, red, HTTP) degrada a
None, y el caller (handlers/news.py, handlers/tspl.py, el job de digest)
decide el fallback — mismo patrón que coingecko_client.py y
crypto_client.py en este repo.
"""

import httpx
import logging
from typing import Optional, List, Dict, Any

from src.config import get_settings

logger = logging.getLogger(__name__)

_CRYPTO_ENDPOINT = "https://newsdata.io/api/1/crypto"


class NewsDataClient:
    """Cliente para el endpoint de noticias cripto de NewsData.io (plan gratis)."""

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        """True si hay una API key de NewsData.io configurada."""
        return bool(self.settings.newsdata_api_key)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("🔌 NewsData client closed")

    @staticmethod
    def _normalize_article(item: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza un artículo crudo de NewsData.io a los campos que usan
        /news y /tspl."""
        return {
            "title": item.get("title"),
            "description": item.get("description"),
            "url": item.get("link"),
            "source_name": item.get("source_name") or item.get("source_id"),
            "published_at": item.get("pubDate"),
            "keywords": item.get("keywords") or [],
        }

    async def get_crypto_news(
        self,
        query: Optional[str] = None,
        coin: Optional[List[str]] = None,
        language: str = "es",
        timezone: Optional[str] = None,
        limit: int = 8,
    ) -> Optional[List[Dict[str, Any]]]:
        """Obtiene noticias del endpoint "Crypto & Coin News" de NewsData.io.

        Args:
            query: Palabra/frase opcional para acotar (máx. 100 caracteres
                en el plan gratis — no se valida acá, lo hace la API).
            coin: Lista opcional de símbolos de moneda (ej. ["btc"],
                ["btc", "eth"]) — parámetro propio del endpoint /crypto,
                más preciso que "query" para acotar por moneda específica.
            language: Idioma (ej. "es", "en"). Default español para que el
                digest de Groq trabaje sobre texto ya en español cuando
                haya cobertura suficiente; si viene vacío para ese idioma,
                el caller puede reintentar con "en".
            timezone: Zona horaria opcional (ej. "america/new_york") para
                acotar la ventana de publicación a la hora local deseada.
            limit: Cuántos artículos devolver como máximo (se recorta del
                lado del cliente).

        Returns:
            Lista de artículos normalizados (title, description, url,
            source_name, published_at, keywords), o None si no hay key
            configurada o la llamada falló.
        """
        if not self.is_configured:
            logger.warning("⚠️ NEWSDATA_API_KEY no configurado")
            return None

        params: Dict[str, Any] = {
            "apikey": self.settings.newsdata_api_key,
            "language": language,
        }
        if query:
            params["q"] = query[:100]  # límite del plan gratis
        if coin:
            params["coin"] = ",".join(c.lower() for c in coin)
        if timezone:
            params["timezone"] = timezone

        client = self._get_client()
        try:
            resp = await client.get(_CRYPTO_ENDPOINT, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "success":
                logger.warning("⚠️ NewsData respondió status=%s: %s", data.get("status"), data.get("results"))
                return None
            results = data.get("results", [])
            return [self._normalize_article(item) for item in results[:limit]]
        except httpx.HTTPStatusError as e:
            logger.warning(
                "⚠️ NewsData HTTP %s: %s",
                e.response.status_code if e.response is not None else "??",
                e,
            )
            return None
        except Exception as e:
            logger.warning("⚠️ NewsData falló: %s", e)
            return None


# Instancia compartida (sin estado pesado, se puede reutilizar entre handlers).
_newsdata_client: Optional[NewsDataClient] = None


def get_newsdata_client() -> NewsDataClient:
    """Obtiene la instancia compartida de NewsDataClient (lazy init)."""
    global _newsdata_client
    if _newsdata_client is None:
        _newsdata_client = NewsDataClient()
    return _newsdata_client
