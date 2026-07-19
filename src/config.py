# src/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List


class Settings(BaseSettings):
    """Configuración del bot cargada desde variables de entorno."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Telegram
    telegram_bot_token: str = Field(
        ...,
        description="Token del bot obtenido de @BotFather",
        examples=["1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"]
    )
    
    # Administradores
    admin_chat_ids: str = Field(
        default="",
        description="IDs de administradores separados por coma",
        examples=["123456789,987654321"]
    )
    
    # Backend API
    tasalo_api_url: str = Field(
        default="http://localhost:8040",
        description="URL base de la API de taso-api",
        examples=["http://localhost:8040", "https://api.tasalo.app"]
    )
    
    tasalo_admin_key: str = Field(
        default="",
        description="API key para endpoints admin (mismo valor que ADMIN_API_KEY en taso-api)",
        examples=["your_secret_admin_key_here"]
    )
    
    # Timeouts
    api_timeout_seconds: int = Field(
        default=15,
        ge=5,
        le=60,
        description="Timeout para llamadas a la API en segundos",
    )
    
    # Logging
    log_level: str = Field(
        default="INFO",
        description="Nivel de logging (DEBUG, INFO, WARNING, ERROR)",
        pattern="^(DEBUG|INFO|WARNING|ERROR)$"
    )

    # Rutas de logs de los repos hermanos, usadas por el comando /log.
    # Relativas a la raíz de taso-bot, asumiendo el layout de VPS
    # ~/tasalo/{taso-bot,taso-api,taso-app} (directorios hermanos).
    taso_api_log_dir: str = Field(
        default="../taso-api/logs",
        description="Ruta (relativa a taso-bot/) a la carpeta logs/ de taso-api",
    )
    taso_app_log_dir: str = Field(
        default="../taso-app/logs",
        description="Ruta (relativa a taso-bot/) a la carpeta logs/ de taso-app",
    )
    taso_gcg_log_dir: str = Field(
        default="../taso-gcg/logs",
        description="Ruta (relativa a taso-bot/) a la carpeta logs/ de taso-gcg",
    )

    # Cryptocurrency Prices (CoinMarketCap)
    # Soporta una o varias keys separadas por coma (ver coinmarketcap_api_keys).
    # Pool INTERACTIVO — usado por /p y /spl.
    coinmarketcap_api_key: str = Field(
        default="",
        description="CoinMarketCap Pro API key(s), separadas por coma si hay varias, para /p y /spl",
        examples=["your_cmc_pro_api_key_here", "key1,key2,key3"]
    )

    # Pool DEDICADO al alert checker (job automático cada 5 min), separado
    # del pool interactivo de arriba para que el polling en background no
    # consuma el cupo de /p y /spl. Si se deja vacío, el checker cae de
    # vuelta al pool de coinmarketcap_api_key (ver cmc_api_key_alerta_keys).
    cmc_api_key_alerta: str = Field(
        default="",
        description="CMC Pro API key(s) dedicadas al alert checker, separadas por coma",
        examples=["", "key1,key2"]
    )

    # Cryptocurrency Prices (CoinGecko — enriquecimiento de /p)
    # Soporta una o varias keys separadas por coma (ver coingecko_api_keys).
    coingecko_api_key: str = Field(
        default="",
        description="CoinGecko Demo API key(s), separadas por coma si hay varias, usada(s) para enriquecer /p con ATH/ATL, supply y categoría",
        examples=["CG-xxxxxxxxxxxxxxxxxxxxxxxx", "CG-xxxxxxxxxxxxxxxxxxxxxxxx,CG-yyyyyyyyyyyyyyyyyyyyyyyy"]
    )

    # AI Analysis (Groq)
    # Soporta una o varias keys separadas por coma (ver groq_api_keys).
    groq_api_key: str = Field(
        default="",
        description="Groq API key(s), separadas por coma si hay varias, para /ta, /p y /spl",
        examples=["gsk_...", "gsk_primera...,gsk_segunda..."]
    )

    # Image Generation
    template_path: str = Field(
        default="data/template.png",
        description="Ruta a la plantilla de imagen para las tasas",
    )

    # Sistema de anuncios (/ads)
    ads_enabled: bool = Field(
        default=True,
        description="Kill-switch global: si es False, no se inyecta ningún anuncio "
        "en ningún mensaje aunque haya anuncios activos en la base de datos.",
    )

    @field_validator('admin_chat_ids', mode='before')
    @classmethod
    def parse_admin_chat_ids(cls, v: str) -> str:
        """Validar que admin_chat_ids es string de enteros separados por coma."""
        if not v:
            return ""
        # Validar formato: "123,456,789"
        parts = v.split(',')
        for part in parts:
            part = part.strip()
            if part and not part.isdigit():
                raise ValueError(f"admin_chat_ids debe contener solo enteros: {part}")
        return v
    
    def get_admin_chat_ids_list(self) -> List[int]:
        """Retorna lista de IDs de administradores como enteros."""
        if not self.admin_chat_ids:
            return []
        return [int(x.strip()) for x in self.admin_chat_ids.split(',') if x.strip()]

    @property
    def is_admin_configured(self) -> bool:
        """Verifica si hay al menos un admin configurado."""
        return len(self.get_admin_chat_ids_list()) > 0

    @property
    def coingecko_api_keys(self) -> List[str]:
        """Lista de API keys de CoinGecko (soporta múltiples separadas por coma).

        Un solo valor sin coma retorna una lista de 1 elemento (comportamiento
        actual intacto). Usada por CoinGeckoClient para rotar entre keys y
        repartir carga entre distintas cuentas del plan Demo.
        """
        if not self.coingecko_api_key:
            return []
        return [k.strip() for k in self.coingecko_api_key.split(",") if k.strip()]

    @property
    def coinmarketcap_api_keys(self) -> List[str]:
        """Lista de API keys de CoinMarketCap del pool INTERACTIVO (/p, /spl).

        Soporta múltiples separadas por coma. Un solo valor sin coma retorna
        una lista de 1 elemento (comportamiento actual intacto).
        """
        if not self.coinmarketcap_api_key:
            return []
        return [k.strip() for k in self.coinmarketcap_api_key.split(",") if k.strip()]

    @property
    def cmc_api_key_alerta_keys(self) -> List[str]:
        """Lista de API keys de CoinMarketCap dedicadas al alert checker.

        Si CMC_API_KEY_ALERTA no está configurada, cae de vuelta al pool
        interactivo (coinmarketcap_api_keys) — mismo comportamiento que antes
        de existir este pool separado.
        """
        if not self.cmc_api_key_alerta:
            return self.coinmarketcap_api_keys
        return [k.strip() for k in self.cmc_api_key_alerta.split(",") if k.strip()]

    @property
    def groq_api_keys(self) -> List[str]:
        """Lista de API keys de Groq (soporta múltiples separadas por coma).

        Un solo valor sin coma retorna una lista de 1 elemento (comportamiento
        actual intacto). Usada por src/core/ai_logic.py para rotar entre
        keys y repartir carga entre distintas cuentas gratuitas.
        """
        if not self.groq_api_key:
            return []
        return [k.strip() for k in self.groq_api_key.split(",") if k.strip()]

    @property
    def template_full_path(self) -> str:
        """Retorna la ruta absoluta a la plantilla de imagen."""
        import os
        # Obtener el directorio raíz del proyecto (padre de src/)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, self.template_path)


# Instancia global para usar en toda la aplicación
# Usamos __getattr__ para lazy initialization y permitir testing
__all__ = ['Settings', 'settings', 'get_settings']

_settings: Settings | None = None


def get_settings() -> Settings:
    """Obtener instancia global de Settings (lazy initialization)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def __getattr__(name: str):
    """Lazy loading para 'settings' para permitir testing."""
    if name == 'settings':
        return get_settings()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
