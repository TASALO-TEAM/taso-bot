# src/api_client.py
"""Cliente HTTP asíncrono para consumir taso-api con retry automático y logging detallado."""

import httpx
import logging
import time
from typing import Optional, Dict, Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


class TasaloApiClient:
    """Cliente para consumir la API de taso-api.

    Features:
    - Retry automático en timeouts y errores de conexión (3 intentos)
    - Timeout configurable (default 15s)
    - Cliente HTTP compartido para mejor performance
    - Retorna None en errores para que el handler decida

    Todos los métodos son asíncronos y devuelven None en caso de error.
    """

    def __init__(
        self,
        api_url: str = "http://localhost:8040",
        admin_key: Optional[str] = None,
        timeout: int = 15,
    ):
        """Inicializar cliente de API.

        Args:
            api_url: URL base de taso-api
            admin_key: API key para endpoints protegidos (opcional)
            timeout: Timeout en segundos para las peticiones
        """
        self.api_url = api_url.rstrip('/')
        self.admin_key = admin_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

        # Headers base para todas las peticiones
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "taso-bot/0.10.0",
        }

    def _get_client(self) -> httpx.AsyncClient:
        """Obtener o crear el cliente HTTP compartido."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=5.0),
                headers=self._headers.copy(),
            )
        if self.admin_key:
            self._client.headers["X-API-Key"] = self.admin_key
        return self._client

    @property
    def _admin_headers(self) -> Dict[str, str]:
        """Headers para endpoints admin (con API key)."""
        headers = self._headers.copy()
        if self.admin_key:
            headers["X-API-Key"] = self.admin_key
        return headers

    async def close(self):
        """Cerrar el cliente HTTP y liberar recursos."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("🔌 API client HTTP cerrado")

    # ── Retry decorator helper ──

    def _log_retry(self, retry_state):
        """Log cuando se reintenta una petición."""
        exception = retry_state.outcome.exception()
        logger.warning(
            f"⚠️ Reintento {retry_state.attempt_number}/3 tras {exception.__class__.__name__}: {exception}"
        )

    # ── Public API methods ──

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _get_with_retry(self, url: str, headers: Dict[str, str] = None, params: Dict = None) -> Optional[Dict[str, Any]]:
        """Método interno con retry automático para GET."""
        client = self._get_client()
        response = await client.get(url, headers=headers or self._headers, params=params)
        response.raise_for_status()
        return response.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _post_with_retry(self, url: str, headers: Dict[str, str] = None, json: Dict = None) -> Optional[Dict[str, Any]]:
        """Método interno con retry automático para POST."""
        client = self._get_client()
        response = await client.post(url, headers=headers or self._headers, json=json)
        response.raise_for_status()
        return response.json()

    async def get_latest(self) -> Optional[Dict[str, Any]]:
        """Obtener las tasas más recientes de todas las fuentes.

        Returns:
            Dict con la respuesta de la API o None si hay error.

        Endpoint: GET /api/v1/tasas/latest
        """
        url = f"{self.api_url}/api/v1/tasas/latest"
        start_time = time.time()

        try:
            data = await self._get_with_retry(url)
            duration_ms = (time.time() - start_time) * 1000
            
            if data and data.get('ok'):
                logger.info("✅ Tasas obtenidas de taso-api (%.0fms)", duration_ms)
                return data
            else:
                logger.warning("⚠️ API respondió ok=False (%.0fms)", duration_ms)
                return None

        except httpx.TimeoutException as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("⏱️ Timeout tras 3 reintentos (%.0fms): %s", duration_ms, e)
            return None
        except httpx.ConnectError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("🔌 Error de conexión tras 3 reintentos (%.0fms): %s", duration_ms, e)
            return None
        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("❌ Error HTTP %d (%.0fms): %s", e.response.status_code, duration_ms, e)
            return None
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("❌ Error inesperado en get_latest (%.0fms): %s", duration_ms, e, exc_info=True)
            return None

    async def get_eltoque(self) -> Optional[Dict[str, Any]]:
        """Obtener solo tasas de ElToque."""
        url = f"{self.api_url}/api/v1/tasas/eltoque"
        start_time = time.time()

        try:
            data = await self._get_with_retry(url)
            duration_ms = (time.time() - start_time) * 1000
            
            if data and data.get('ok'):
                logger.info("✅ Tasas ElToque obtenidas (%.0fms)", duration_ms)
                return data
            logger.warning("⚠️ ElToque respondió ok=False (%.0fms)", duration_ms)
            return None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("❌ Error obteniendo ElToque (%.0fms): %s", duration_ms, e)
            return None

    async def get_cadeca(self) -> Optional[Dict[str, Any]]:
        """Obtener solo tasas de CADECA."""
        url = f"{self.api_url}/api/v1/tasas/cadeca"
        start_time = time.time()

        try:
            data = await self._get_with_retry(url)
            duration_ms = (time.time() - start_time) * 1000
            
            if data and data.get('ok'):
                logger.info("✅ Tasas CADECA obtenidas (%.0fms)", duration_ms)
                return data
            return None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("❌ Error obteniendo CADECA (%.0fms): %s", duration_ms, e)
            return None

    async def get_bcc(self) -> Optional[Dict[str, Any]]:
        """Obtener solo tasas de BCC."""
        url = f"{self.api_url}/api/v1/tasas/bcc"
        start_time = time.time()

        try:
            data = await self._get_with_retry(url)
            duration_ms = (time.time() - start_time) * 1000
            
            if data and data.get('ok'):
                logger.info("✅ Tasas BCC obtenidas (%.0fms)", duration_ms)
                return data
            return None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("❌ Error obteniendo BCC (%.0fms): %s", duration_ms, e)
            return None

    async def admin_refresh(self) -> Optional[Dict[str, Any]]:
        """Forzar refresco inmediato de tasas en el backend."""
        if not self.admin_key:
            logger.error("❌ admin_refresh requiere admin_key configurado")
            return None

        url = f"{self.api_url}/api/v1/admin/refresh"
        start_time = time.time()

        try:
            data = await self._post_with_retry(url, headers=self._admin_headers)
            duration_ms = (time.time() - start_time) * 1000
            
            if data and data.get('ok'):
                logger.info("✅ Refresh admin ejecutado (%.0fms)", duration_ms)
                return data
            else:
                logger.warning("⚠️ Refresh admin respondió ok=False (%.0fms)", duration_ms)
                return None

        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            if e.response.status_code == 401:
                logger.error("🔑 Error 401: API key inválida o faltante (%.0fms)", duration_ms)
            else:
                logger.error("❌ Error HTTP %d (%.0fms): %s", e.response.status_code, duration_ms, e)
            return None
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("❌ Error en admin_refresh (%.0fms): %s", duration_ms, e)
            return None

    async def admin_status(self) -> Optional[Dict[str, Any]]:
        """Obtener estado del scheduler del backend."""
        if not self.admin_key:
            logger.error("❌ admin_status requiere admin_key configurado")
            return None

        url = f"{self.api_url}/api/v1/admin/status"
        start_time = time.time()

        try:
            data = await self._get_with_retry(url, headers=self._admin_headers)
            duration_ms = (time.time() - start_time) * 1000
            
            if data and data.get('ok'):
                logger.info("✅ Status admin obtenido (%.0fms)", duration_ms)
                return data
            return None

        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            if e.response.status_code == 401:
                logger.error("🔑 Error 401: API key inválida o faltante (%.0fms)", duration_ms)
            else:
                logger.error("❌ Error HTTP %d (%.0fms): %s", e.response.status_code, duration_ms, e)
            return None
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("❌ Error en admin_status (%.0fms): %s", duration_ms, e)
            return None

    async def get_history(
        self,
        source: str = "eltoque",
        currency: str = "USD",
        days: int = 7,
    ) -> Optional[Dict[str, Any]]:
        """Obtener histórico de tasas para una fuente y moneda."""
        url = f"{self.api_url}/api/v1/tasas/history"
        params = {
            "source": source,
            "currency": currency,
            "days": days,
        }
        start_time = time.time()

        try:
            data = await self._get_with_retry(url, params=params)
            duration_ms = (time.time() - start_time) * 1000
            
            if data and data.get('ok'):
                logger.info("✅ Histórico obtenido: %d días %s/%s (%.0fms)", days, source, currency, duration_ms)
                return data
            else:
                logger.warning("⚠️ Histórico respondió ok=False (%.0fms)", duration_ms)
                return None

        except httpx.TimeoutException as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("⏱️ Timeout tras 3 reintentos (%.0fms): %s", duration_ms, e)
            return None
        except httpx.ConnectError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("🔌 Error de conexión tras 3 reintentos (%.0fms): %s", duration_ms, e)
            return None
        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("❌ Error HTTP %d (%.0fms): %s", e.response.status_code, duration_ms, e)
            return None
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("❌ Error inesperado en histórico (%.0fms): %s", duration_ms, e, exc_info=True)
            return None

    async def track_command(
        self,
        command: str,
        user_id: int,
        username: Optional[str] = None,
        source: Optional[str] = None,
        success: bool = True,
    ) -> None:
        """
        Registra el uso de un comando en la API para estadísticas.
        Fire-and-forget: errores son silenciosos.
        """
        url = f"{self.api_url}/api/v1/admin/stats/track"
        payload = {
            "command": command,
            "user_id": user_id,
            "username": username,
            "source": source,
            "success": success,
        }
        start_time = time.time()

        try:
            # Timeout corto para no bloquear, sin retry (fire-and-forget)
            client = self._get_client()
            response = await client.post(
                url,
                headers=self._admin_headers,
                json=payload,
                timeout=httpx.Timeout(5.0, connect=2.0),
            )
            response.raise_for_status()
            duration_ms = (time.time() - start_time) * 1000
            logger.debug("✅ Comando trackeado: %s por user %d (%.0fms)", command, user_id, duration_ms)
        except httpx.TimeoutException:
            logger.debug("⏱️ Timeout trackeando comando %s", command)
        except Exception as e:
            logger.debug("⚠️ Error trackeando comando %s: %s", command, e)

    async def get_stats_summary(self) -> Optional[Dict[str, Any]]:
        """Obtiene resumen de estadísticas del bot."""
        if not self.admin_key:
            logger.error("❌ get_stats_summary requiere admin_key configurado")
            return None

        url = f"{self.api_url}/api/v1/admin/stats/summary"
        start_time = time.time()

        try:
            data = await self._get_with_retry(url, headers=self._admin_headers)
            duration_ms = (time.time() - start_time) * 1000
            
            if data and data.get('ok'):
                logger.info("✅ Estadísticas obtenidas (%.0fms)", duration_ms)
                return data
            return None

        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            if e.response.status_code == 401:
                logger.error("🔑 Error 401: API key inválida o faltante (%.0fms)", duration_ms)
            else:
                logger.error("❌ Error HTTP %d (%.0fms): %s", e.response.status_code, duration_ms, e)
            return None
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("❌ Error en get_stats_summary (%.0fms): %s", duration_ms, e)
            return None
