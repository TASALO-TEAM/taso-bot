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

    async def get_fuel(self) -> Optional[Dict[str, Any]]:
        """Obtener precios de combustible del mercado informal."""
        url = f"{self.api_url}/api/v1/tasas/fuel"
        start_time = time.time()

        try:
            data = await self._get_with_retry(url)
            duration_ms = (time.time() - start_time) * 1000

            # El endpoint fuel devuelve {source, rates, updated_at} sin campo "ok"
            if data and data.get("rates") is not None:
                logger.info("✅ Combustible obtenido de taso-api (%.0fms)", duration_ms)
                return data
            logger.warning("⚠️ Combustible respondió sin datos (%.0fms): %s", duration_ms, data)
            return None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("❌ Error obteniendo combustible (%.0fms): %s", duration_ms, e)
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

    # ── Year API methods ───────────────────────────────────────────────────────

    async def get_year_state(self) -> Optional[Dict[str, Any]]:
        """Obtener estado del año (progreso + frase del día + estadísticas)."""
        url = f"{self.api_url}/api/v1/year/state"
        try:
            data = await self._get_with_retry(url)
            return data if data and data.get("ok") else None
        except Exception as e:
            logger.error("❌ Error en get_year_state: %s", e)
            return None

    async def get_year_quote_today(self) -> Optional[Dict[str, Any]]:
        """Obtener frase del día."""
        url = f"{self.api_url}/api/v1/year/quotes/today"
        try:
            data = await self._get_with_retry(url)
            return data if data and data.get("ok") else None
        except Exception as e:
            logger.error("❌ Error en get_year_quote_today: %s", e)
            return None

    async def get_year_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Obtener suscripción de un usuario."""
        url = f"{self.api_url}/api/v1/year/subscriptions/me/{user_id}"
        try:
            data = await self._get_with_retry(url)
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error("❌ HTTP %d en get_year_subscription", e.response.status_code)
            return None
        except Exception as e:
            logger.error("❌ Error en get_year_subscription: %s", e)
            return None

    async def set_year_subscription(self, user_id: int, hour: int) -> Optional[Dict[str, Any]]:
        """Crear o actualizar suscripción propia (público, sin admin key).

        Usa POST /api/v1/year/subscriptions/me/{user_id}.
        """
        url = f"{self.api_url}/api/v1/year/subscriptions/me/{user_id}"
        try:
            data = await self._post_with_retry(
                url,
                json={"user_id": user_id, "hour": hour},
            )
            return data if data and data.get("ok") else None
        except Exception as e:
            logger.error("❌ Error en set_year_subscription: %s", e)
            return None

    async def delete_year_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Eliminar suscripción propia (público, sin admin key).

        Usa DELETE /api/v1/year/subscriptions/me/{user_id}.
        """
        url = f"{self.api_url}/api/v1/year/subscriptions/me/{user_id}"
        try:
            client = self._get_client()
            resp = await client.delete(url)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"ok": False}
            logger.error("❌ HTTP %d en delete_year_subscription", e.response.status_code)
            return None
        except Exception as e:
            logger.error("❌ Error en delete_year_subscription: %s", e)
            return None

    async def admin_set_year_subscription(self, user_id: int, hour: int) -> Optional[Dict[str, Any]]:
        """Crear o actualizar suscripción (admin, requiere X-API-Key)."""
        url = f"{self.api_url}/api/v1/year/subscriptions"
        try:
            data = await self._post_with_retry(
                url,
                headers=self._admin_headers,
                json={"user_id": user_id, "hour": hour},
            )
            return data if data and data.get("ok") else None
        except Exception as e:
            logger.error("❌ Error en admin_set_year_subscription: %s", e)
            return None

    async def admin_delete_year_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Eliminar suscripción (admin, requiere X-API-Key)."""
        try:
            await self._client.delete(
                f"{self.api_url}/api/v1/year/subscriptions/{user_id}",
                headers=self._admin_headers,
            )
            return {"ok": True}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"ok": False}
            logger.error("❌ HTTP %d en admin_delete_year_subscription", e.response.status_code)
            return None
        except Exception as e:
            logger.error("❌ Error en admin_delete_year_subscription: %s", e)
            return None

    async def admin_list_year_subscriptions(self) -> Optional[Dict[str, Any]]:
        """Listar todas las suscripciones del año (admin, requiere X-API-Key)."""
        url = f"{self.api_url}/api/v1/year/subscriptions"
        try:
            data = await self._get_with_retry(url, headers=self._admin_headers)
            return data if data and data.get("ok") else None
        except Exception as e:
            logger.error("❌ Error en admin_list_year_subscriptions: %s", e)
            return None

    async def add_year_quote(self, quote_text: str, target_year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Añadir una nueva frase (admin, requiere X-API-Key)."""
        url = f"{self.api_url}/api/v1/year/quotes"
        try:
            payload: Dict[str, Any] = {"quote_text": quote_text}
            if target_year is not None:
                payload["target_year"] = target_year
            data = await self._post_with_retry(url, headers=self._admin_headers, json=payload)
            return data if data else None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                return {"ok": False, "success": False, "is_duplicate": True,
                        "status_code": 409}
            logger.error("HTTP %d en add_year_quote: %s", e.response.status_code, e)
            return None
        except Exception as e:
            logger.error("Error en add_year_quote: %s", e)
            return None

    async def admin_get_year_quote(self, quote_id: int) -> Optional[Dict[str, Any]]:
        """Obtener una frase por id de posición (admin, requiere X-API-Key)."""
        url = f"{self.api_url}/api/v1/year/quotes/{quote_id}"
        try:
            data = await self._get_with_retry(url, headers=self._admin_headers)
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error("HTTP %d en admin_get_year_quote", e.response.status_code)
            return None
        except Exception as e:
            logger.error("Error en admin_get_year_quote: %s", e)
            return None

    async def admin_edit_year_quote(self, quote_id: int, quote_text: str) -> Optional[Dict[str, Any]]:
        """Editar frase por posición id (admin)."""
        url = f"{self.api_url}/api/v1/year/quotes/{quote_id}"
        try:
            client = self._get_client()
            resp = await client.put(url, headers=self._admin_headers, json={"quote_text": quote_text})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error("HTTP %d en admin_edit_year_quote", e.response.status_code)
            return None
        except Exception as e:
            logger.error("Error en admin_edit_year_quote: %s", e)
            return None

    async def admin_delete_year_quote(self, quote_id: int) -> Optional[Dict[str, Any]]:
        """Eliminar una frase por id de posición (admin, requiere X-API-Key)."""
        url = f"{self.api_url}/api/v1/year/quotes/{quote_id}"
        try:
            client = self._get_client()
            resp = await client.delete(url, headers=self._admin_headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"ok": False, "error": "not_found"}
            logger.error("HTTP %d en admin_delete_year_quote", e.response.status_code)
            return None
        except Exception as e:
            logger.error("Error en admin_delete_year_quote: %s", e)
            return None

    # ── Price Alert API methods ────────────────────────────────────────────────

    async def get_user_price_alerts(self, user_id: int) -> list:
        """Obtiene las alertas de precio activas de un usuario.

        Returns:
            Lista de dicts con las alertas o [] si hay error.
        """
        url = f"{self.api_url}/api/v1/alerts/{user_id}"
        try:
            data = await self._get_with_retry(url, headers=self._admin_headers)
            if data and data.get("ok"):
                return data.get("data", [])
            return []
        except Exception as e:
            logger.error("❌ Error en get_user_price_alerts user=%d: %s", user_id, e)
            return []

    async def create_price_alert(
        self, user_id: int, coin: str, target_price: float, price_at_creation: float,
        note: Optional[str] = None,
    ) -> Optional[list]:
        """Crea dos alertas de precio (ABOVE + BELOW) para el par user/coin/price.

        Args:
            user_id: Telegram user_id
            coin: Símbolo de la moneda (ej: "BTC")
            target_price: Precio objetivo configurado por el usuario
            price_at_creation: Precio real de la moneda al momento de crear la alerta.
                Permite al checker detectar cruces reales y evitar falsos positivos.
            note: Origen opcional (ej: "S1 · Análisis 4h"), cuando la alerta se crea
                desde un botón de nivel en /graf o /ta. None si se crea manualmente.

        Returns:
            Lista de alertas creadas o None si falla.
        """
        url = f"{self.api_url}/api/v1/alerts"
        payload = {
            "user_id": user_id,
            "coin": coin.upper(),
            "target_price": target_price,
            "price_at_creation": price_at_creation,
        }
        if note:
            payload["note"] = note
        try:
            data = await self._post_with_retry(url, headers=self._admin_headers, json=payload)
            if data and data.get("ok"):
                logger.info(
                    "✅ Price alert created: user=%d coin=%s target=%.6f actual=%.6f",
                    user_id, coin, target_price, price_at_creation,
                )
                return data.get("data", [])
            return None
        except Exception as e:
            logger.error("❌ Error en create_price_alert user=%d coin=%s: %s", user_id, coin, e)
            return None

    async def delete_price_alert(self, alert_id: int, user_id: int) -> bool:
        """Elimina una alerta de precio específica.

        Returns:
            True si se eliminó correctamente, False si no.
        """
        url = f"{self.api_url}/api/v1/alerts/{alert_id}"
        try:
            client = self._get_client()
            resp = await client.delete(
                url,
                headers=self._admin_headers,
                params={"user_id": user_id},
            )
            resp.raise_for_status()
            data = resp.json()
            return bool(data.get("ok"))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            logger.error("❌ HTTP %d en delete_price_alert id=%d", e.response.status_code, alert_id)
            return False
        except Exception as e:
            logger.error("❌ Error en delete_price_alert id=%d: %s", alert_id, e)
            return False

    async def delete_all_price_alerts(self, user_id: int) -> bool:
        """Elimina todas las alertas de precio de un usuario.

        Returns:
            True si tuvo éxito, False si hubo error.
        """
        url = f"{self.api_url}/api/v1/alerts/user/{user_id}"
        try:
            client = self._get_client()
            resp = await client.delete(url, headers=self._admin_headers)
            resp.raise_for_status()
            data = resp.json()
            return bool(data.get("ok"))
        except Exception as e:
            logger.error("❌ Error en delete_all_price_alerts user=%d: %s", user_id, e)
            return False

    async def trigger_price_alert(self, alert_id: int) -> bool:
        """Marca una alerta como TRIGGERED tras enviar la notificación.

        Returns:
            True si se actualizó correctamente, False si no.
        """
        url = f"{self.api_url}/api/v1/alerts/{alert_id}/trigger"
        try:
            client = self._get_client()
            resp = await client.patch(url, headers=self._admin_headers)
            resp.raise_for_status()
            data = resp.json()
            return bool(data.get("ok"))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            logger.error("❌ HTTP %d en trigger_price_alert id=%d", e.response.status_code, alert_id)
            return False
        except Exception as e:
            logger.error("❌ Error en trigger_price_alert id=%d: %s", alert_id, e)
            return False

    async def get_active_alert_coins(self) -> list:
        """Retorna la lista de coins con alertas ACTIVE.
        Usado por el checker para saber qué precios consultar.

        Returns:
            Lista de strings, ej: ["BTC", "ETH"] o [] si no hay ninguna.
        """
        url = f"{self.api_url}/api/v1/alerts/active/coins"
        try:
            data = await self._get_with_retry(url, headers=self._admin_headers)
            if data and data.get("ok"):
                return data.get("data", {}).get("coins", [])
            return []
        except Exception as e:
            logger.error("❌ Error en get_active_alert_coins: %s", e)
            return []

    # ── Ads API methods ────────────────────────────────────────────────────────

    async def get_active_ads(self) -> list:
        """Lista los anuncios activos (endpoint público, sin admin key).

        Returns:
            Lista de dicts {id, text, is_sponsored} o [] si hay error.
        """
        url = f"{self.api_url}/api/v1/ads/active"
        try:
            data = await self._get_with_retry(url)
            if data and data.get("ok"):
                return data.get("data", [])
            return []
        except Exception as e:
            logger.error("❌ Error en get_active_ads: %s", e)
            return []

    async def admin_list_ads(self) -> list:
        """Lista TODOS los anuncios (activos e inactivos). Requiere admin_key."""
        if not self.admin_key:
            logger.error("❌ admin_list_ads requiere admin_key configurado")
            return []
        url = f"{self.api_url}/api/v1/ads"
        try:
            data = await self._get_with_retry(url, headers=self._admin_headers)
            if data and data.get("ok"):
                return data.get("data", [])
            return []
        except Exception as e:
            logger.error("❌ Error en admin_list_ads: %s", e)
            return []

    async def admin_create_ad(
        self, text: str, is_sponsored: bool = False, weight: int = 1,
        created_by: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Crea un anuncio nuevo. Requiere admin_key."""
        if not self.admin_key:
            logger.error("❌ admin_create_ad requiere admin_key configurado")
            return None
        url = f"{self.api_url}/api/v1/ads"
        payload = {
            "text": text, "is_sponsored": is_sponsored,
            "weight": weight, "created_by": created_by,
        }
        try:
            data = await self._post_with_retry(url, headers=self._admin_headers, json=payload)
            return data if data and data.get("ok") else None
        except Exception as e:
            logger.error("❌ Error en admin_create_ad: %s", e)
            return None

    async def admin_update_ad(self, ad_id: int, **fields) -> Optional[Dict[str, Any]]:
        """Edita un anuncio (text/is_active/is_sponsored/weight). Requiere admin_key."""
        if not self.admin_key:
            logger.error("❌ admin_update_ad requiere admin_key configurado")
            return None
        url = f"{self.api_url}/api/v1/ads/{ad_id}"
        try:
            client = self._get_client()
            resp = await client.patch(url, headers=self._admin_headers, json=fields)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error("❌ HTTP %d en admin_update_ad id=%d", e.response.status_code, ad_id)
            return None
        except Exception as e:
            logger.error("❌ Error en admin_update_ad id=%d: %s", ad_id, e)
            return None

    async def admin_delete_ad(self, ad_id: int) -> bool:
        """Elimina un anuncio definitivamente. Requiere admin_key."""
        if not self.admin_key:
            logger.error("❌ admin_delete_ad requiere admin_key configurado")
            return False
        url = f"{self.api_url}/api/v1/ads/{ad_id}"
        try:
            client = self._get_client()
            resp = await client.delete(url, headers=self._admin_headers)
            resp.raise_for_status()
            data = resp.json()
            return bool(data.get("ok"))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            logger.error("❌ HTTP %d en admin_delete_ad id=%d", e.response.status_code, ad_id)
            return False
        except Exception as e:
            logger.error("❌ Error en admin_delete_ad id=%d: %s", ad_id, e)
            return False

    # ── Broadcast (/ms) API methods ─────────────────────────────────────────────

    async def admin_list_user_ids(self) -> list:
        """Lista el user_id de TODOS los usuarios registrados del bot.

        Endpoint admin-only (requiere admin_key). Usado por el comando /ms
        para saber a quién enviar el broadcast. Ver
        docs/plans/2026-07-07-comando-ms-broadcast.md.

        Returns:
            Lista de user_id (int) o [] si hay error.
        """
        if not self.admin_key:
            logger.error("❌ admin_list_user_ids requiere admin_key configurado")
            return []
        url = f"{self.api_url}/api/v1/admin/stats/users/ids"
        try:
            data = await self._get_with_retry(url, headers=self._admin_headers)
            if data and data.get("ok"):
                return data.get("data", [])
            return []
        except Exception as e:
            logger.error("❌ Error en admin_list_user_ids: %s", e)
            return []

    async def lookup_user_id_by_username(self, username: str) -> Optional[int]:
        """Busca el user_id de un usuario registrado a partir de su username.

        Endpoint admin-only (requiere admin_key). Usado por /ms <@usuario>
        para enviar un mensaje a un único usuario en vez de a todos. Ver
        docs/plans/2026-07-08-ms-directo-y-tkt-mejoras.md.

        Args:
            username: username a buscar (con o sin "@" inicial)

        Returns:
            user_id (int) si se encuentra, None si no hay match o hay error.
        """
        if not self.admin_key:
            logger.error("❌ lookup_user_id_by_username requiere admin_key configurado")
            return None
        url = f"{self.api_url}/api/v1/admin/stats/users/lookup"
        try:
            data = await self._get_with_retry(
                url, params={"username": username}, headers=self._admin_headers,
            )
            if data and data.get("ok") and data.get("data"):
                return data["data"].get("user_id")
            return None
        except Exception as e:
            logger.error("❌ Error en lookup_user_id_by_username(%s): %s", username, e)
            return None

    # ── Tickets (/tkt) API methods ──────────────────────────────────────────────

    async def create_ticket(
        self, user_id: int, kind: str, message: str, username: Optional[str] = None,
    ) -> Optional[dict]:
        """Crea un ticket nuevo. Llamado desde /tkt en nombre del usuario.

        Nota: requiere admin_key igual que el resto de endpoints admin — el
        bot es quien sostiene la key de confianza ante taso-api, no el
        usuario final (mismo criterio que /alerts). Ver
        docs/plans/2026-07-07-comando-tkt-tickets.md.

        Returns:
            dict con la respuesta ({"ok": bool, "data": {...}}) o None si falla.
        """
        if not self.admin_key:
            logger.error("❌ create_ticket requiere admin_key configurado")
            return None
        url = f"{self.api_url}/api/v1/tickets"
        payload = {"user_id": user_id, "kind": kind, "message": message}
        if username:
            payload["username"] = username
        try:
            data = await self._post_with_retry(url, headers=self._admin_headers, json=payload)
            return data
        except Exception as e:
            logger.error("❌ Error en create_ticket user_id=%d: %s", user_id, e)
            return None

    async def list_tickets(
        self, status: Optional[str] = None, kind: Optional[str] = None, limit: Optional[int] = None,
    ) -> list:
        """Lista tickets, opcionalmente filtrados. Uso: /tkt list, /tkt active."""
        if not self.admin_key:
            logger.error("❌ list_tickets requiere admin_key configurado")
            return []
        url = f"{self.api_url}/api/v1/tickets"
        params = {}
        if status:
            params["status"] = status
        if kind:
            params["kind"] = kind
        if limit:
            params["limit"] = limit
        try:
            client = self._get_client()
            resp = await client.get(url, headers=self._admin_headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", []) if data.get("ok") else []
        except Exception as e:
            logger.error("❌ Error en list_tickets: %s", e)
            return []

    async def get_ticket(self, ticket_id: int) -> Optional[dict]:
        """Obtiene un ticket puntual por id. Uso: /tkt show <id>."""
        if not self.admin_key:
            logger.error("❌ get_ticket requiere admin_key configurado")
            return None
        url = f"{self.api_url}/api/v1/tickets/{ticket_id}"
        try:
            client = self._get_client()
            resp = await client.get(url, headers=self._admin_headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data") if data.get("ok") else None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error("❌ HTTP %d en get_ticket id=%d", e.response.status_code, ticket_id)
            return None
        except Exception as e:
            logger.error("❌ Error en get_ticket id=%d: %s", ticket_id, e)
            return None

    async def update_ticket(
        self, ticket_id: int, status: Optional[str] = None, claimed_by: Optional[int] = None,
    ) -> Optional[dict]:
        """Actualiza status y/o claimed_by de un ticket (botones Tomar/Resolver)."""
        if not self.admin_key:
            logger.error("❌ update_ticket requiere admin_key configurado")
            return None
        url = f"{self.api_url}/api/v1/tickets/{ticket_id}"
        fields = {}
        if status is not None:
            fields["status"] = status
        if claimed_by is not None:
            fields["claimed_by"] = claimed_by
        try:
            client = self._get_client()
            resp = await client.patch(url, headers=self._admin_headers, json=fields)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error("❌ HTTP %d en update_ticket id=%d", e.response.status_code, ticket_id)
            return None
        except Exception as e:
            logger.error("❌ Error en update_ticket id=%d: %s", ticket_id, e)
            return None
