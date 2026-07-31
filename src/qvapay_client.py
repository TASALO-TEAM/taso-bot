# src/qvapay_client.py
"""Cliente asíncrono para la API pública P2P de QvaPay (comando /qp).

Consume `GET /p2p/completed_pairs_average?coin={CODIGO}`, que devuelve
`{average_buy, average_sell}` para una forma de pago. El promedio que se
muestra en /qp es `(average_buy + average_sell) / 2` — el mismo cálculo
que usa QvaPay para su propio proyecto CambioCUP
(https://github.com/n3omaster/cambiocup, ver `app/api/cron/route.js`).

No requiere API key: es el mismo endpoint público que consume cambiocup.com.

⚠️ Códigos de moneda: CambioCUP solo confirma 5 de los 9 que usa /qp
(BANK_CUP, BANK_MLC, CLASICA, ETECSA, BANDECPREPAGO). TROPIPAY, ZELLE,
BOLSATM y SBERBANK son la mejor estimación a partir de las páginas
públicas de monedas de QvaPay (ej. qvapay.com/coins/TROPIPAY) pero NO
están verificados contra la API real — si alguno da 404 o un payload
distinto, get_p2p_rates() lo trata como "sin datos" (None) en vez de
tumbar el resto del comando. Verificar y ajustar QVAPAY_COINS ni bien
se confirmen los códigos reales.
"""

import asyncio
import httpx
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.qvapay.com/p2p/completed_pairs_average"

# Etiqueta a mostrar en /qp -> código de moneda esperado por la API de
# QvaPay. El orden del dict es el orden de aparición en el mensaje.
QVAPAY_COINS: Dict[str, str] = {
    "CUP": "BANK_CUP",
    "MLC": "BANK_MLC",
    "TROPIPAY": "TROPIPAY",
    "ETECSA": "ETECSA",
    "ZELLE": "ZELLE",
    "CLASICA": "CLASICA",
    "BOLSATM": "BOLSATM",
    "BANDECPREPAGO": "BANDECPREPAGO",
    "SBERBANK": "SBERBANK",
}


class QvaPayClient:
    """Cliente mínimo para el endpoint de promedios P2P de QvaPay."""

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=4.0))
        return self._client

    async def close(self) -> None:
        """Cierra el cliente HTTP y libera recursos."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("🔌 QvaPay client cerrado")

    async def _fetch_average(self, coin_code: str) -> Optional[float]:
        """Obtiene `(average_buy + average_sell) / 2` para un código de moneda.

        Retorna None si la moneda no existe, no tiene operaciones
        recientes, o la petición falla — nunca lanza, para que una sola
        moneda caída no tumbe el resto del comando /qp.
        """
        client = self._get_client()
        try:
            resp = await client.get(_BASE_URL, params={"coin": coin_code})
            resp.raise_for_status()
            data = resp.json()
            buy = data.get("average_buy")
            sell = data.get("average_sell")
            if buy is None and sell is None:
                logger.info("QvaPay %s: sin operaciones recientes (average_buy/sell nulos)", coin_code)
                return None
            return ((buy or 0.0) + (sell or 0.0)) / 2
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
            logger.warning("QvaPay %s: error de red: %s", coin_code, e)
            return None
        except httpx.HTTPStatusError as e:
            logger.warning("QvaPay %s: HTTP %s", coin_code, e.response.status_code)
            return None
        except Exception as e:
            logger.warning("QvaPay %s: error inesperado: %s", coin_code, e)
            return None

    async def get_p2p_rates(self) -> Dict[str, Optional[float]]:
        """Consulta todas las monedas de QVAPAY_COINS en paralelo.

        Returns:
            Dict {etiqueta: promedio_o_None} en el mismo orden que
            QVAPAY_COINS. None indica moneda sin datos disponibles ahora
            mismo (el formatter la muestra como "$0.00", igual que hace
            el bot oficial de QvaPay).
        """
        labels = list(QVAPAY_COINS.keys())
        codes = list(QVAPAY_COINS.values())
        results = await asyncio.gather(*(self._fetch_average(code) for code in codes))
        return dict(zip(labels, results))
