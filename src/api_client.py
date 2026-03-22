# src/api_client.py
"""Cliente HTTP asíncrono para consumir taso-api."""

import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TasaloApiClient:
    """Cliente para consumir la API de taso-api.
    
    Todos los métodos son asíncronos y devuelven None en caso de error,
    permitiendo que el handler decida cómo manejar el fallo.
    """
    
    def __init__(
        self,
        api_url: str = "http://localhost:8000",
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
        
        # Headers base para todas las peticiones
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        # Headers adicionales para endpoints admin
        self._admin_headers = {
            **self._headers,
            "X-API-Key": admin_key or "",
        }
    
    async def get_latest(self) -> Optional[Dict[str, Any]]:
        """Obtener las tasas más recientes de todas las fuentes.
        
        Returns:
            Dict con la respuesta de la API o None si hay error.
            
        Endpoint: GET /api/v1/tasas/latest
        """
        url = f"{self.api_url}/api/v1/tasas/latest"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()
                data = response.json()
                
                if data.get('ok'):
                    logger.info("✅ Tasas obtenidas correctamente de taso-api")
                    return data
                else:
                    logger.warning(f"⚠️ API respondió ok=False: {data}")
                    return None
                    
        except httpx.TimeoutException as e:
            logger.error(f"⏱️ Timeout al obtener tasas: {e}")
            return None
        except httpx.ConnectError as e:
            logger.error(f"🔌 Error de conexión con taso-api: {e}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Error HTTP {e.response.status_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}", exc_info=True)
            return None
    
    async def get_eltoque(self) -> Optional[Dict[str, Any]]:
        """Obtener solo tasas de ElToque.
        
        Returns:
            Dict con tasas de ElToque o None si hay error.
            
        Endpoint: GET /api/v1/tasas/eltoque
        """
        url = f"{self.api_url}/api/v1/tasas/eltoque"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()
                data = response.json()
                
                if data.get('ok'):
                    logger.info("✅ Tasas ElToque obtenidas")
                    return data
                return None
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo ElToque: {e}")
            return None
    
    async def get_cadeca(self) -> Optional[Dict[str, Any]]:
        """Obtener solo tasas de CADECA.
        
        Returns:
            Dict con tasas de CADECA o None si hay error.
        """
        url = f"{self.api_url}/api/v1/tasas/cadeca"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()
                data = response.json()
                
                if data.get('ok'):
                    logger.info("✅ Tasas CADECA obtenidas")
                    return data
                return None
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo CADECA: {e}")
            return None
    
    async def get_bcc(self) -> Optional[Dict[str, Any]]:
        """Obtener solo tasas de BCC.
        
        Returns:
            Dict con tasas de BCC o None si hay error.
        """
        url = f"{self.api_url}/api/v1/tasas/bcc"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()
                data = response.json()
                
                if data.get('ok'):
                    logger.info("✅ Tasas BCC obtenidas")
                    return data
                return None
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo BCC: {e}")
            return None
    
    async def admin_refresh(self) -> Optional[Dict[str, Any]]:
        """Forzar refresco inmediato de tasas en el backend.
        
        Returns:
            Dict con resultado del refresh o None si hay error.
            
        Endpoint: POST /api/v1/admin/refresh
        Requiere: X-API-Key header
        """
        if not self.admin_key:
            logger.error("❌ admin_refresh requiere admin_key configurado")
            return None
        
        url = f"{self.api_url}/api/v1/admin/refresh"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self._admin_headers)
                response.raise_for_status()
                data = response.json()
                
                if data.get('ok'):
                    logger.info("✅ Refresh admin ejecutado correctamente")
                    return data
                else:
                    logger.warning(f"⚠️ Refresh admin respondió ok=False: {data}")
                    return None
                    
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("🔑 Error 401: API key inválida o faltante")
            else:
                logger.error(f"❌ Error HTTP {e.response.status_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error en admin_refresh: {e}")
            return None
    
    async def admin_status(self) -> Optional[Dict[str, Any]]:
        """Obtener estado del scheduler del backend.
        
        Returns:
            Dict con estado del scheduler o None si hay error.
            
        Endpoint: GET /api/v1/admin/status
        Requiere: X-API-Key header
        """
        if not self.admin_key:
            logger.error("❌ admin_status requiere admin_key configurado")
            return None
        
        url = f"{self.api_url}/api/v1/admin/status"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._admin_headers)
                response.raise_for_status()
                data = response.json()
                
                if data.get('ok'):
                    logger.info("✅ Status admin obtenido")
                    return data
                return None
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("🔑 Error 401: API key inválida o faltante")
            else:
                logger.error(f"❌ Error HTTP {e.response.status_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error en admin_status: {e}")
            return None

    async def get_history(
        self,
        source: str = "eltoque",
        currency: str = "USD",
        days: int = 7,
    ) -> Optional[Dict[str, Any]]:
        """Obtener histórico de tasas para una fuente y moneda.

        Args:
            source: Fuente de datos (eltoque, cadeca, bcc, binance)
            currency: Moneda (USD, EUR, etc.)
            days: Días de histórico (1-365)

        Returns:
            Dict con histórico o None si hay error.

        Endpoint: GET /api/v1/tasas/history?source={source}&currency={currency}&days={days}
        """
        url = f"{self.api_url}/api/v1/tasas/history"
        params = {
            "source": source,
            "currency": currency,
            "days": days,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._headers, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get('ok'):
                    logger.info(f"✅ Histórico obtenido: {days} días para {source}/{currency}")
                    return data
                else:
                    logger.warning(f"⚠️ Histórico respondió ok=False: {data}")
                    return None

        except httpx.TimeoutException as e:
            logger.error(f"⏱️ Timeout en histórico: {e}")
            return None
        except httpx.ConnectError as e:
            logger.error(f"🔌 Error de conexión en histórico: {e}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Error HTTP {e.response.status_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado en histórico: {e}", exc_info=True)
            return None
