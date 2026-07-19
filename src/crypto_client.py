# src/crypto_client.py
"""Cliente asíncrono para obtener datos de criptomonedas desde CoinMarketCap
con fallback a CryptoCompare.

Implementa la misma lógica de BBAlert /p: consulta CMC con múltiples símbolos
(moneda + ETH + BTC) y obtiene high/low desde Binance con fallback a CC.
"""

import asyncio
import httpx
import itertools
import logging
from typing import Optional, Dict, Any, List

from tradingview_ta import TA_Handler, Interval

from src.config import get_settings
from src.coingecko_client import CoinGeckoClient, CoinGeckoNetworkError

logger = logging.getLogger(__name__)


class CryptoApiClient:
    """Cliente para datos de criptomonedas (CoinMarketCap + fallbacks)."""

    def __init__(self, cmc_api_keys: Optional[List[str]] = None):
        """Inicializar cliente.

        Args:
            cmc_api_keys: Pool de API keys de CoinMarketCap a rotar. Si se
                omite, usa el pool interactivo por defecto
                (settings.coinmarketcap_api_keys, usado por /p y /spl).
                El alert checker pasa aquí su propio pool
                (settings.cmc_api_key_alerta_keys) para no compartir cupo
                con los comandos interactivos.
        """
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None
        self.coingecko = CoinGeckoClient()
        self._cmc_keys = cmc_api_keys if cmc_api_keys is not None else self.settings.coinmarketcap_api_keys
        self._cmc_key_cycle = itertools.cycle(self._cmc_keys) if self._cmc_keys else None

    def _next_cmc_key(self) -> Optional[str]:
        """Siguiente API key de CMC en la rotación de esta instancia, o None
        si no hay ninguna configurada. Síncrono, sin await — seguro con
        corrutinas concurrentes usando el mismo cliente."""
        return next(self._cmc_key_cycle) if self._cmc_key_cycle else None

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
        await self.coingecko.close()

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

    async def get_high_low_24h(self, symbol: str, coingecko_fallback: Optional[Dict[str, Any]] = None) -> tuple[float, float]:
        """Obtener High/Low 24h con fallback cascada: Binance → CryptoCompare → CoinGecko.

        Args:
            symbol: Símbolo de la moneda (ej: BTC)
            coingecko_fallback: Datos de enriquecimiento de CoinGecko ya obtenidos
                (evita una llamada HTTP extra); si trae high_24h/low_24h válidos
                se usan como último recurso cuando Binance y CC fallan.
        """
        # Intentar Binance primero (rápido)
        high, low = await self._get_high_low_binance(symbol)
        if high > 0:
            return high, low

        # Fallback CryptoCompare
        high, low = await self._get_high_low_cryptocompare(symbol)
        if high > 0:
            return high, low

        # Último fallback: CoinGecko (útil para monedas no listadas en Binance/CC,
        # p.ej. HIVE, HBD u otros tokens de nicho que sí tiene CoinGecko)
        if coingecko_fallback:
            cg_high = coingecko_fallback.get("high_24h") or 0
            cg_low = coingecko_fallback.get("low_24h") or 0
            if cg_high > 0:
                logger.debug("High/Low 24h de %s obtenido desde CoinGecko (fallback final)", symbol)
                return cg_high, cg_low

        return 0.0, 0.0

    # ── Datos principales (CoinMarketCap) ──

    async def _cmc_request_with_retry(
        self, url: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0,
    ) -> httpx.Response:
        """GET a CoinMarketCap Pro API con rotación de keys de esta instancia.

        Centraliza la autenticación (X-CMC_PRO_API_KEY) para los dos puntos
        de entrada a CMC (_get_from_cmc y _cmc_get). Reintenta con la
        siguiente key del pool si la respuesta es 429 (rate limit), hasta
        len(self._cmc_keys) intentos. Un 403 (plan insuficiente) o
        cualquier otro status se propaga tal cual — cada caller decide qué
        hacer (rotar de key no arregla ninguno de los dos casos).

        Con 0 o 1 key configurada, comportamiento idéntico al actual (sin
        reintento posible).
        """
        client = self._get_client()
        attempts = max(len(self._cmc_keys), 1)
        resp: Optional[httpx.Response] = None
        for attempt in range(attempts):
            api_key = self._next_cmc_key() or self.settings.coinmarketcap_api_key
            resp = await client.get(
                url,
                headers={
                    "X-CMC_PRO_API_KEY": api_key,
                    "Accept": "application/json",
                },
                params=params or {},
                timeout=timeout,
            )
            if resp.status_code == 429 and attempt < attempts - 1:
                logger.warning(
                    "⚠️ CMC 429 (rate limit) con key ...%s, probando siguiente key (intento %d/%d)",
                    (api_key or "")[-4:], attempt + 2, attempts,
                )
                continue
            return resp
        # No debería llegar aquí (el loop siempre retorna), pero por si acaso:
        return resp

    async def _get_from_cmc(self, symbols: list[str]) -> Optional[Dict[str, Any]]:
        """Obtener datos desde CoinMarketCap Pro API."""
        if not self._cmc_keys:
            logger.warning("⚠️ COINMARKETCAP_API_KEY no configurada")
            return None

        try:
            resp = await self._cmc_request_with_retry(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                params={"symbol": ",".join(symbols), "convert": "USD"},
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
        1. Disparar EN PARALELO: CoinMarketCap (datos primarios) y
           CoinGecko (datos de enriquecimiento: ATH/ATL, supply, categoría).
        2. Si CMC responde → es la fuente de verdad para price/high/low/%
           cambios/market cap/rank/volumen (igual que siempre). Los campos
           de CoinGecko se adjuntan bajo la clave "enrichment" sin pisar nada.
        3. Si CMC falla pero CryptoCompare sí → igual que el punto 2, pero
           con CryptoCompare como base.
        4. Si CMC y CryptoCompare fallan pero CoinGecko sí tiene el símbolo
           → se usa CoinGecko como fuente PRIMARIA (caso "solo CoinGecko",
           típico de tokens no listados en CMC). En este caso el dict
           resultante tiene "primary_source": "coingecko".
        5. Si nada responde → None (comportamiento sin cambios).

        Args:
            symbol: Símbolo de la criptomoneda (ej: BTC, ETH)

        Returns:
            Diccionario con datos normalizados o None si falla todo.
            Incluye clave opcional "enrichment" con datos de CoinGecko
            cuando ambas fuentes tienen la moneda.
        """
        symbol_upper = symbol.upper()

        # === Disparar CMC y CoinGecko en paralelo ===
        cmc_symbols = [symbol_upper, "ETH", "BTC"]
        cmc_task = asyncio.create_task(self._get_from_cmc(cmc_symbols))
        coingecko_task = asyncio.create_task(self.coingecko.get_enrichment_data(symbol_upper))

        results = await asyncio.gather(cmc_task, coingecko_task, return_exceptions=True)
        cmc_data = results[0] if not isinstance(results[0], Exception) else None
        coingecko_raw = results[1]

        # Distinguir entre error de red (None) y "no existe" ({not_found: True})
        if isinstance(coingecko_raw, CoinGeckoNetworkError):
            # Error de red en CG: no sabemos si existe, tratamos como si CG no estuviera
            coingecko_data = None
            cg_confirmed_not_found = False
            logger.warning("CoinGecko error de red para %s: %s", symbol_upper, coingecko_raw)
        elif isinstance(coingecko_raw, Exception):
            coingecko_data = None
            cg_confirmed_not_found = False
        elif coingecko_raw and coingecko_raw.get("not_found"):
            # CoinGecko confirmó que el símbolo no existe en su base de datos
            coingecko_data = None
            cg_confirmed_not_found = True
        else:
            coingecko_data = coingecko_raw
            cg_confirmed_not_found = False

        # === CMC tiene el símbolo → es la fuente primaria ===
        # Si ni CMC ni CryptoCompare ni CoinGecko tienen el símbolo → moneda inválida
        if cmc_data and symbol_upper in cmc_data:
            try:
                data_moneda = cmc_data[symbol_upper]
                data_eth = cmc_data.get("ETH", {})
                data_btc = cmc_data.get("BTC", {})

                quote_moneda = data_moneda["quote"]["USD"]
                price_eth = data_eth.get("quote", {}).get("USD", {}).get("price", 0)
                price_btc = data_btc.get("quote", {}).get("USD", {}).get("price", 0)

                # Obtener High/Low (Binance → CC → CoinGecko fallback)
                high_24h, low_24h = await self.get_high_low_24h(symbol_upper, coingecko_fallback=coingecko_data)

                result = {
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
                    "primary_source": "coinmarketcap",
                }
                if coingecko_data and not coingecko_data.get("not_found"):
                    result["enrichment"] = coingecko_data
                return result
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

                # Bug fix: usar Binance → CC → CoinGecko también en path CC
                # (HIGH24HOUR de CC mismo solo como último recurso final)
                high_24h, low_24h = await self.get_high_low_24h(symbol_upper, coingecko_fallback=coingecko_data)
                if high_24h == 0:
                    high_24h = float(symbol_data.get("HIGH24HOUR", 0))
                    low_24h = float(symbol_data.get("LOW24HOUR", 0))

                result = {
                    "symbol": symbol_upper,
                    "price": price_usd,
                    "price_eth": price_usd / price_usd_eth if price_usd_eth else 0,
                    "price_btc": price_usd / price_usd_btc if price_usd_btc else 0,
                    "high_24h": high_24h,
                    "low_24h": low_24h,
                    "percent_change_1h": None,
                    "percent_change_24h": float(symbol_data.get("CHANGEPCT24HOUR", 0)),
                    "percent_change_7d": None,
                    "market_cap_rank": 0,
                    "market_cap": float(symbol_data.get("MKTCAP", 0)),
                    "volume_24h": float(symbol_data.get("VOLUME24HOUR", 0)),
                    "primary_source": "cryptocompare",
                }
                if coingecko_data and not coingecko_data.get("not_found"):
                    result["enrichment"] = coingecko_data
                return result
            except Exception as e:
                logger.warning("⚠️ Error procesando CryptoCompare para %s: %s", symbol_upper, e)

        # === INTENTO 3: CoinGecko como fuente PRIMARIA (caso "solo CoinGecko") ===
        # Llega aquí solo si CMC y CryptoCompare no tienen el símbolo, pero
        # CoinGecko sí — típico de tokens más nuevos o de menor capitalización.
        if coingecko_data and not coingecko_data.get("not_found") and coingecko_data.get("price"):
            logger.info("🔄 Usando CoinGecko como fuente primaria para %s", symbol_upper)
            return {
                "symbol": coingecko_data.get("symbol_used", symbol_upper),
                "price": coingecko_data["price"],
                "price_eth": 0,
                "price_btc": 0,
                "high_24h": coingecko_data.get("high_24h") or 0,
                "low_24h": coingecko_data.get("low_24h") or 0,
                "percent_change_1h": None,
                "percent_change_24h": coingecko_data.get("percent_change_24h") or 0,
                "percent_change_7d": coingecko_data.get("percent_change_7d"),
                "market_cap_rank": coingecko_data.get("market_cap_rank") or 0,
                "market_cap": coingecko_data.get("market_cap") or 0,
                "volume_24h": coingecko_data.get("volume_24h") or 0,
                "primary_source": "coingecko",
                "enrichment": coingecko_data,
            }

        # === MONEDA NO ENCONTRADA EN NINGUNA FUENTE ===
        # Si CoinGecko confirmó explícitamente que no existe, señalizamos
        # con un dict especial para que el handler muestre mensaje apropiado.
        if cg_confirmed_not_found:
            logger.info("❌ Símbolo %s no existe en ninguna fuente (CMC, CC, CG)", symbol_upper)
            return {"not_found": True, "symbol": symbol_upper}

        # Error técnico (todas las APIs fallaron por red/timeout)
        return None

    # ── Datos de mercado (Spotlight /spl) ──
    # Los métodos de esta sección son independientes del flujo de /p y no
    # tocan get_crypto_data ni sus fallbacks. Se usan solo desde /spl.

    async def _cmc_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """Wrapper genérico para llamadas GET a CoinMarketCap Pro API.

        Centraliza headers, manejo de errores/plan-insuficiente y logging
        para los endpoints de mercado usados por /spl (Fear&Greed,
        global-metrics, listings, trending, content).

        Args:
            path: Path relativo desde https://pro-api.coinmarketcap.com
                (ej: "v3/fear-and-greed/latest")
            params: Query params opcionales

        Returns:
            El campo "data" de la respuesta, o None si falla la llamada o
            el plan de la API key no soporta el endpoint (HTTP 403).
        """
        if not self._cmc_keys:
            logger.warning("⚠️ COINMARKETCAP_API_KEY no configurada (spotlight)")
            return None

        url = f"https://pro-api.coinmarketcap.com/{path}"
        try:
            resp = await self._cmc_request_with_retry(url, params=params or {})
            if resp.status_code == 403:
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                error_msg = body.get("status", {}).get("error_message", "plan insuficiente")
                logger.info("ℹ️ CMC %s no disponible en el plan actual: %s", path, error_msg)
                return None
            resp.raise_for_status()
            return resp.json().get("data")
        except Exception as e:
            logger.warning("⚠️ CMC %s falló: %s", path, e)
            return None

    async def get_fear_greed(self) -> Optional[Dict[str, Any]]:
        """Índice Fear & Greed de CMC (disponible en plan Basic)."""
        data = await self._cmc_get("v3/fear-and-greed/latest")
        if not data:
            return None
        return {
            "value": data.get("value"),
            "classification": data.get("value_classification"),
            "updated_at": data.get("update_time"),
        }

    async def get_global_metrics(self) -> Optional[Dict[str, Any]]:
        """Market cap total, dominancia BTC/ETH, volumen 24h globales y sus
        respectivas variaciones 24h (mismos 3 datos que el bloque "Global
        Market Cap / 24h Market Volume / Bitcoin Dominance" del Spotlight
        real de CMC).
        """
        data = await self._cmc_get("v1/global-metrics/quotes/latest")
        if not data:
            return None
        quote_usd = data.get("quote", {}).get("USD", {})
        return {
            "total_market_cap": quote_usd.get("total_market_cap"),
            "total_volume_24h": quote_usd.get("total_volume_24h"),
            "market_cap_change_24h": quote_usd.get("total_market_cap_yesterday_percentage_change"),
            "volume_change_24h": quote_usd.get("total_volume_24h_yesterday_percentage_change"),
            "btc_dominance": data.get("btc_dominance"),
            "eth_dominance": data.get("eth_dominance"),
            "btc_dominance_change_24h": data.get("btc_dominance_24h_percentage_change"),
            "eth_dominance_change_24h": data.get("eth_dominance_24h_percentage_change"),
        }

    async def get_altcoin_season_index(self) -> Optional[Dict[str, Any]]:
        """Altcoin Season Index de CMC (0-100, disponible en plan Basic e
        incluso sin API key vía Keyless Public API).

        Escala: >=75 "temporada altcoin", <=25 "temporada Bitcoin", el resto
        es mixto. Aparece en el Spotlight real de CMC junto al Fear & Greed.
        """
        data = await self._cmc_get("v1/altcoin-season-index/latest")
        if not data:
            return None
        value = data.get("altcoin_index")
        if value is None:
            return None
        if value >= 75:
            label = "Temporada Altcoin"
        elif value <= 25:
            label = "Temporada Bitcoin"
        else:
            label = "Mixto"
        return {"value": value, "label": label}

    @staticmethod
    def _fetch_tv_bias_sync(symbol_pair: str, interval: str) -> Optional[Dict[str, Any]]:
        """Llamada SINCRÓNICA (bloqueante) a tradingview_ta.

        Misma librería y patrón de fallback BINANCE→GATEIO ya usados en
        src/handlers/ta.py (get_tradingview_analysis_enhanced). Se define
        aquí como método separado y minimalista (solo la recomendación
        agregada, no todos los indicadores) para no acoplar crypto_client.py
        a src/handlers/ta.py.
        """
        interval_map = {
            "1h": Interval.INTERVAL_1_HOUR,
            "4h": Interval.INTERVAL_4_HOURS,
            "1d": Interval.INTERVAL_1_DAY,
            "1w": Interval.INTERVAL_1_WEEK,
        }
        tv_interval = interval_map.get(interval, Interval.INTERVAL_1_DAY)
        try:
            handler = TA_Handler(symbol=symbol_pair, screener="crypto", exchange="BINANCE", interval=tv_interval)
            analysis = handler.get_analysis()
        except Exception:
            try:
                handler = TA_Handler(symbol=symbol_pair, screener="crypto", exchange="GATEIO", interval=tv_interval)
                analysis = handler.get_analysis()
            except Exception:
                return None
        if not analysis:
            return None
        summ = analysis.summary
        return {
            "symbol": symbol_pair,
            "interval": interval,
            "recommendation": summ.get("RECOMMENDATION", "NEUTRAL"),
            "buy_score": summ.get("BUY", 0),
            "sell_score": summ.get("SELL", 0),
            "neutral_score": summ.get("NEUTRAL", 0),
        }

    async def get_technical_bias(self, symbol_pair: str = "BTCUSDT", interval: str = "1d") -> Optional[Dict[str, Any]]:
        """Sesgo técnico agregado de TradingView (recomendación de consenso)
        para un símbolo, usado como "pulso técnico" del mercado en /spl.

        Usa la librería tradingview-ta (ya dependencia del proyecto, usada
        en /ta), que consulta el scanner público NO OFICIAL de TradingView
        — no es una API con contrato soportado por TradingView, puede
        cambiar o fallar sin aviso. Es sincrónica, así que se ejecuta en
        threadpool para no bloquear el event loop.
        """
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._fetch_tv_bias_sync, symbol_pair, interval)
        except Exception as e:
            logger.debug("TradingView bias falló para %s: %s", symbol_pair, e)
            return None

    async def get_top_movers(self, limit: int = 3) -> Dict[str, list]:
        """Top gainers y losers de las últimas 24h.

        Se limita el universo a las 200 monedas de mayor capitalización
        para evitar que microcaps con volumen ínfimo (y variaciones %
        engañosas) dominen el resultado.

        Args:
            limit: Cuántos gainers y cuántos losers devolver (cada uno).
        """
        base_params = {"start": "1", "limit": "200", "convert": "USD"}

        gainers_task = self._cmc_get(
            "v1/cryptocurrency/listings/latest",
            {**base_params, "sort": "percent_change_24h", "sort_dir": "desc"},
        )
        losers_task = self._cmc_get(
            "v1/cryptocurrency/listings/latest",
            {**base_params, "sort": "percent_change_24h", "sort_dir": "asc"},
        )
        gainers_raw, losers_raw = await asyncio.gather(gainers_task, losers_task)

        def _extract(raw: Optional[list]) -> list:
            if not raw:
                return []
            out = []
            for item in raw[:limit]:
                quote = item.get("quote", {}).get("USD", {})
                out.append({
                    "symbol": item.get("symbol"),
                    "name": item.get("name"),
                    "percent_change_24h": quote.get("percent_change_24h"),
                    "price": quote.get("price"),
                })
            return out

        return {"gainers": _extract(gainers_raw), "losers": _extract(losers_raw)}

    async def get_trending(self, limit: int = 5) -> Optional[list]:
        """Monedas más buscadas/tendencia en CMC (últimas 24h)."""
        data = await self._cmc_get("v1/cryptocurrency/trending/latest", {"limit": str(limit)})
        if not data:
            return None
        out = []
        for item in data[:limit]:
            quote = item.get("quote", {}).get("USD", {})
            out.append({
                "symbol": item.get("symbol"),
                "name": item.get("name"),
                "percent_change_24h": quote.get("percent_change_24h"),
            })
        return out

    async def get_market_news(self, limit: int = 3) -> Optional[list]:
        """Titulares/noticias reales de CMC.

        Requiere plan Standard+ — confirmado 2026-07-03 que el plan Basic
        de este proyecto devuelve HTTP 403 (error_code 1006). Se deja
        implementado para activarse automáticamente sin cambios de código
        si algún día se actualiza el plan; mientras tanto siempre retorna
        None y /spl usa solo datos de mercado (ver docs/plans/2026-07-02-comando-spl-spotlight.md).
        """
        data = await self._cmc_get("v1/content/latest", {"limit": str(limit)})
        if not data:
            return None
        out = []
        for item in data[:limit]:
            out.append({
                "title": item.get("title"),
                "subtitle": item.get("subtitle"),
            })
        return out

    async def get_market_snapshot(self) -> Dict[str, Any]:
        """Arma el snapshot completo de mercado para /spl.

        Dispara las 7 fuentes en paralelo; si alguna falla (excepción o
        plan insuficiente) simplemente queda como None/vacía en el dict,
        sin tumbar el resto — el prompt de Groq (get_groq_market_spotlight)
        está preparado para trabajar con secciones faltantes.

        Returns:
            Dict con claves: fear_greed, global_metrics, top_movers,
            trending, news, altcoin_season, btc_technical. Cualquiera
            puede ser None (o dict vacío en el caso de top_movers) si la
            fuente falló.
        """
        results = await asyncio.gather(
            self.get_fear_greed(),
            self.get_global_metrics(),
            self.get_top_movers(),
            self.get_trending(),
            self.get_market_news(),
            self.get_altcoin_season_index(),
            self.get_technical_bias("BTCUSDT", "1d"),
            return_exceptions=True,
        )

        def _safe(value):
            return None if isinstance(value, Exception) else value

        (
            fear_greed, global_metrics, top_movers, trending, news,
            altcoin_season, btc_technical,
        ) = (_safe(r) for r in results)

        return {
            "fear_greed": fear_greed,
            "global_metrics": global_metrics,
            "top_movers": top_movers or {"gainers": [], "losers": []},
            "trending": trending,
            "news": news,
            "altcoin_season": altcoin_season,
            "btc_technical": btc_technical,
        }
