# src/crypto_client.py
"""Cliente asíncrono para obtener datos de criptomonedas desde CoinMarketCap
con fallback a CryptoCompare.

Implementa la misma lógica de BBAlert /p: consulta CMC con múltiples símbolos
(moneda + ETH + BTC) y obtiene high/low desde Binance con fallback a CC.
"""

import httpx
import logging
from typing import Optional, Dict, Any

from src.config import get_settings

logger = logging.getLogger(__name__)


class CryptoApiClient:
    """Cliente para datos de criptomonedas (CoinMarketCap + fallbacks)."""

    def __init__(self):
        """Inicializar cliente."""
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Crear o retornar cliente HTTP compartido."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
        return self._client

    async def close(self) -> None:
        """Cerrar cliente HTTP."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("🔌 Crypto API client closed")

    # ── High/Low 24h ──

    async def _get_high_low_binance(self, symbol: str) -> tuple[float, float]:
        """Obtener High/Low desde Binance (USDT/USDC pairs)."""
        client = self._get_client()
        binance_pairs = [f"{symbol}USDT", f"{symbol}USDC"]

        for pair in binance_pairs:
            try:
                resp = await client.get(
                    "https://api.binance.com/api/v3/ticker/24hr",
                    params={"symbol": pair},
                    timeout=2.0,
                )
                resp.raise_for_status()
                data = resp.json()
                high = float(data.get("highPrice", 0))
                low = float(data.get("lowPrice", 0))
                if high > 0:
                    return high, low
            except Exception as e:
                logger.debug("Binance %s falló: %s", pair, e)
                continue

        return 0.0, 0.0

    async def _get_high_low_cryptocompare(self, symbol: str) -> tuple[float, float]:
        """Obtener High/Low desde CryptoCompare (fallback universal)."""
        client = self._get_client()
        try:
            resp = await client.get(
                "https://min-api.cryptocompare.com/data/pricemultifull",
                params={"fsyms": symbol, "tsyms": "USD"},
                timeout=3.0,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("RAW", {}).get(symbol, {}).get("USD", {})
            high = float(raw.get("HIGH24HOUR", 0))
            low = float(raw.get("LOW24HOUR", 0))
            return high, low
        except Exception as e:
            logger.debug("CryptoCompare HL falló para %s: %s", symbol, e)
            return 0.0, 0.0

    async def get_high_low_24h(self, symbol: str) -> tuple[float, float]:
        """Obtener High/Low 24h con fallback cascada: Binance → CryptoCompare."""
        # Intentar Binance primero (rápido)
        high, low = await self._get_high_low_binance(symbol)
        if high > 0:
            return high, low

        # Fallback CryptoCompare
        return await self._get_high_low_cryptocompare(symbol)

    # ── Datos principales (CoinMarketCap) ──

    async def _get_from_cmc(self, symbols: list[str]) -> Optional[Dict[str, Any]]:
        """Obtener datos desde CoinMarketCap Pro API."""
        if not self.settings.coinmarketcap_api_key:
            logger.warning("⚠️ COINMARKETCAP_API_KEY no configurada")
            return None

        client = self._get_client()
        try:
            resp = await client.get(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                headers={
                    "X-CMC_PRO_API_KEY": self.settings.coinmarketcap_api_key,
                    "Accept": "application/json",
                },
                params={"symbol": ",".join(symbols), "convert": "USD"},
                timeout=10.0,
            )
            resp.raise_for_status()
            full_data = resp.json().get("data", {})

            # Verificar que tenemos todos los símbolos solicitados
            if not all(s in full_data for s in symbols):
                logger.warning("⚠️ CMC no devolvió todos los símbolos: %s", symbols)
                return None

            return full_data
        except Exception as e:
            logger.warning("⚠️ CMC falló para %s: %s", symbols, e)
            return None

    async def _get_from_cryptocompare(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtener datos desde CryptoCompare (fallback universal)."""
        client = self._get_client()
        try:
            resp = await client.get(
                "https://min-api.cryptocompare.com/data/pricemultifull",
                params={"fsyms": f"{symbol},ETH,BTC", "tsyms": "USD"},
                timeout=5.0,
            )
            resp.raise_for_status()
            data = resp.json()
            raw_data = data.get("RAW", {})

            if symbol not in raw_data or "USD" not in raw_data[symbol]:
                return None

            return raw_data
        except Exception as e:
            logger.debug("CryptoCompare falló para %s: %s", symbol, e)
            return None

    async def get_crypto_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtener datos completos de una criptomoneda.

        Estrategia:
        1. Intentar CoinMarketCap (datos completos: 1h/24h/7d, market cap rank)
        2. Fallback a CryptoCompare (datos limitados: sin 1h/7d, sin rank)

        Args:
            symbol: Símbolo de la criptomoneda (ej: BTC, ETH)

        Returns:
            Diccionario con datos normalizados o None si falla todo.
        """
        symbol_upper = symbol.upper()

        # === INTENTO 1: CoinMarketCap ===
        cmc_symbols = [symbol_upper, "ETH", "BTC"]
        cmc_data = await self._get_from_cmc(cmc_symbols)

        if cmc_data and symbol_upper in cmc_data:
            try:
                data_moneda = cmc_data[symbol_upper]
                data_eth = cmc_data.get("ETH", {})
                data_btc = cmc_data.get("BTC", {})

                quote_moneda = data_moneda["quote"]["USD"]
                price_eth = data_eth.get("quote", {}).get("USD", {}).get("price", 0)
                price_btc = data_btc.get("quote", {}).get("USD", {}).get("price", 0)

                # Obtener High/Low (Binance → CC fallback)
                high_24h, low_24h = await self.get_high_low_24h(symbol_upper)

                return {
                    "symbol": data_moneda["symbol"],
                    "price": quote_moneda["price"],
                    "price_eth": quote_moneda["price"] / price_eth if price_eth else 0,
                    "price_btc": quote_moneda["price"] / price_btc if price_btc else 0,
                    "high_24h": high_24h,
                    "low_24h": low_24h,
                    "percent_change_1h": quote_moneda.get("percent_change_1h"),
                    "percent_change_24h": quote_moneda.get("percent_change_24h", 0),
                    "percent_change_7d": quote_moneda.get("percent_change_7d"),
                    "market_cap_rank": data_moneda.get("cmc_rank", 0),
                    "market_cap": quote_moneda.get("market_cap", 0),
                    "volume_24h": quote_moneda.get("volume_24h", 0),
                }
            except Exception as e:
                logger.warning("⚠️ Error procesando datos CMC para %s: %s", symbol_upper, e)

        # === INTENTO 2: CryptoCompare fallback ===
        logger.info("🔄 Usando fallback CryptoCompare para %s", symbol_upper)
        cc_raw = await self._get_from_cryptocompare(symbol_upper)

        if cc_raw and symbol_upper in cc_raw:
            try:
                symbol_data = cc_raw[symbol_upper]["USD"]
                eth_data = cc_raw.get("ETH", {}).get("USD", {})
                btc_data = cc_raw.get("BTC", {}).get("USD", {})

                price_usd = float(symbol_data.get("PRICE", 0))
                price_usd_eth = float(eth_data.get("PRICE", 0))
                price_usd_btc = float(btc_data.get("PRICE", 0))

                if price_usd == 0:
                    return None

                return {
                    "symbol": symbol_upper,
                    "price": price_usd,
                    "price_eth": price_usd / price_usd_eth if price_usd_eth else 0,
                    "price_btc": price_usd / price_usd_btc if price_usd_btc else 0,
                    "high_24h": float(symbol_data.get("HIGH24HOUR", 0)),
                    "low_24h": float(symbol_data.get("LOW24HOUR", 0)),
                    "percent_change_1h": None,
                    "percent_change_24h": float(symbol_data.get("CHANGEPCT24HOUR", 0)),
                    "percent_change_7d": None,
                    "market_cap_rank": 0,
                    "market_cap": float(symbol_data.get("MKTCAP", 0)),
                    "volume_24h": float(symbol_data.get("VOLUME24HOUR", 0)),
                }
            except Exception as e:
                logger.warning("⚠️ Error procesando CryptoCompare para %s: %s", symbol_upper, e)

        return None
