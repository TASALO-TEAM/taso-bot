# src/coingecko_client.py
"""Cliente asíncrono para CoinGecko (enriquecimiento del comando /p).

Este cliente es complementario a CryptoApiClient (CoinMarketCap/CryptoCompare),
NO un reemplazo. Su único propósito es aportar datos que CMC no provee:

    - ATH / ATL (precio histórico máximo/mínimo) + % de distancia al ATH
    - Supply circulante / total / máximo
    - Categoría principal del proyecto (ej: "Smart Contract Platform")
    - Sentiment de la comunidad (votos positivos)
    - Su propio market cap rank, SOLO si difiere del de CMC

Por eso get_enrichment_data() nunca devuelve price/high/low/% de cambio:
esos campos ya los maneja crypto_client.py con CMC como fuente de verdad.

Usa el plan Demo de CoinGecko (header `x-cg-demo-api-key`, base URL
`api.coingecko.com`). Si no hay API key configurada, todas las llamadas
devuelven None de forma silenciosa y /p sigue funcionando como antes.

Distinción de resultados en _resolve_coin_id():
  - Retorna str  → símbolo encontrado en CoinGecko
  - Retorna None → símbolo NO existe en CoinGecko (moneda inválida o no listada)
  - Lanza CoinGeckoNetworkError → fallo de red/timeout, no sabemos si existe
"""

import httpx
import logging
from typing import Optional, Dict, Any

from src.config import get_settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.coingecko.com/api/v3"


class CoinGeckoNetworkError(Exception):
    """Error de red/timeout al contactar CoinGecko (no significa que la moneda no exista)."""
    pass


class CoinGeckoClient:
    """Cliente para datos de enriquecimiento de CoinGecko (plan Demo)."""

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None
        # Cache en memoria de resoluciones símbolo → id (evita golpear /search
        # repetidamente por el mismo símbolo durante la vida del proceso).
        self._id_cache: Dict[str, Optional[str]] = {}

    @property
    def is_configured(self) -> bool:
        """True si hay una API key de CoinGecko configurada."""
        return bool(self.settings.coingecko_api_key)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("🔌 CoinGecko client closed")

    def _headers(self) -> Dict[str, str]:
        return {"x-cg-demo-api-key": self.settings.coingecko_api_key}

    # ── Resolución de IDs ──

    async def _resolve_coin_id(self, symbol: str) -> Optional[str]:
        """Resuelve un símbolo al id de CoinGecko via /search (totalmente dinámico).

        Flujo:
          1. Cache en memoria (evita /search repetido en el mismo proceso)
          2. GET /search?query={symbol} → primer resultado con symbol exacto

        Retorna:
          str  → id encontrado (ej: 'bitcoin')
          None → símbolo no existe en CoinGecko

        Lanza:
          CoinGeckoNetworkError → fallo de red/timeout (no sabemos si existe)
        """
        symbol_upper = symbol.upper()

        # Cache hit (None guardado = confirmado que no existe)
        if symbol_upper in self._id_cache:
            cached = self._id_cache[symbol_upper]
            logger.debug("CoinGecko cache hit para %s: %s", symbol_upper, cached)
            return cached

        client = self._get_client()
        try:
            resp = await client.get(
                f"{_BASE_URL}/search",
                headers=self._headers(),
                params={"query": symbol},
                timeout=5.0,
            )
            resp.raise_for_status()
            data = resp.json()
            coins = data.get("coins", [])

            # Buscar coincidencia exacta de símbolo (case-insensitive)
            match = next(
                (c for c in coins if c.get("symbol", "").upper() == symbol_upper),
                None,
            )
            coin_id = match.get("id") if match else None
            # Guardar en cache (incluyendo None = no existe)
            self._id_cache[symbol_upper] = coin_id
            if coin_id:
                logger.debug("CoinGecko resolvió %s → %s", symbol_upper, coin_id)
            else:
                logger.debug("CoinGecko: símbolo %s no encontrado en /search", symbol_upper)
            return coin_id
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
            # Error de red: NO guardamos None en cache (podría existir, solo falló la red)
            logger.warning("CoinGecko /search error de red para %s: %s", symbol, e)
            raise CoinGeckoNetworkError(str(e)) from e
        except httpx.HTTPStatusError as e:
            logger.warning("CoinGecko /search HTTP %s para %s: %s", e.response.status_code, symbol, e)
            raise CoinGeckoNetworkError(str(e)) from e
        except Exception as e:
            logger.warning("CoinGecko /search error inesperado para %s: %s", symbol, e)
            raise CoinGeckoNetworkError(str(e)) from e

    # ── Datos de enriquecimiento ──

    async def get_enrichment_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtiene datos de enriquecimiento desde CoinGecko para un símbolo.

        Args:
            symbol: Símbolo de la criptomoneda (ej: BTC, ETH)

        Returns:
            Dict con datos si la moneda existe, incluyendo:
              - 'not_found': True → símbolo no existe en ninguna API
              - Campos de precio (solo como fuente primaria si CMC falla)
              - Campos de enriquecimiento: ath, atl, supply, categoría, etc.
            None si CoinGecko no está configurado o hubo error de red.

        Lanza:
            CoinGeckoNetworkError si falla la red (para que crypto_client
            pueda distinguir "no existe" de "error técnico").
        """
        if not self.is_configured:
            return None

        try:
            coin_id = await self._resolve_coin_id(symbol)
        except CoinGeckoNetworkError:
            # Propagar: el caller decide qué hacer
            raise

        if not coin_id:
            # Símbolo confirmado como no existente en CoinGecko
            logger.info("CoinGecko: símbolo %s no existe", symbol)
            return {"not_found": True}

        client = self._get_client()
        try:
            resp = await client.get(
                f"{_BASE_URL}/coins/{coin_id}",
                headers=self._headers(),
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "true",
                    "developer_data": "false",
                    "sparkline": "false",
                },
                timeout=8.0,
            )
            resp.raise_for_status()
            data = resp.json()

            market_data = data.get("market_data", {})
            categories = [c for c in data.get("categories", []) if c]

            circulating = market_data.get("circulating_supply")
            total = market_data.get("total_supply")
            max_sup = market_data.get("max_supply")

            return {
                "not_found": False,
                "symbol_used": data.get("symbol", symbol).upper(),
                "ath": market_data.get("ath", {}).get("usd"),
                "ath_change_pct": market_data.get("ath_change_percentage", {}).get("usd"),
                "ath_date": market_data.get("ath_date", {}).get("usd"),
                "atl": market_data.get("atl", {}).get("usd"),
                "atl_date": market_data.get("atl_date", {}).get("usd"),
                "circulating_supply": circulating,
                "total_supply": total,
                "max_supply": max_sup,
                "category": categories[0] if categories else None,
                "sentiment_up_pct": data.get("sentiment_votes_up_percentage"),
                "market_cap_rank": market_data.get("market_cap_rank") or data.get("market_cap_rank"),
                # Datos de precio — SOLO se usan cuando CMC no tiene la moneda
                # (caso "solo CoinGecko"), nunca para pisar datos de CMC.
                "price": market_data.get("current_price", {}).get("usd"),
                "percent_change_24h": market_data.get("price_change_percentage_24h"),
                "percent_change_7d": market_data.get("price_change_percentage_7d"),
                "market_cap": market_data.get("market_cap", {}).get("usd"),
                "volume_24h": market_data.get("total_volume", {}).get("usd"),
                "high_24h": market_data.get("high_24h", {}).get("usd"),
                "low_24h": market_data.get("low_24h", {}).get("usd"),
            }
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
            logger.warning("CoinGecko /coins/%s error de red: %s", coin_id, e)
            return None
        except httpx.HTTPStatusError as e:
            logger.warning("CoinGecko /coins/%s HTTP %s: %s", coin_id, e.response.status_code, e)
            return None
        except Exception as e:
            logger.warning("CoinGecko /coins/%s error inesperado: %s", coin_id, e)
            return None
