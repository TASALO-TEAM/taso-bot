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

    # Cryptocurrency Prices (CoinMarketCap)
    coinmarketcap_api_key: str = Field(
        default="",
        description="CoinMarketCap Pro API key for cryptocurrency price data (/p command)",
        examples=["your_cmc_pro_api_key_here"]
    )

    # Cryptocurrency Prices (CoinGecko — enriquecimiento de /p)
    # Soporta una o varias keys separadas por coma (ver coingecko_api_keys).
    coingecko_api_key: str = Field(
        default="",
        description="CoinGecko Demo API key(s), separadas por coma si hay varias, usada(s) para enriquecer /p con ATH/ATL, supply y categoría",
        examples=["CG-xxxxxxxxxxxxxxxxxxxxxxxx", "CG-xxxxxxxxxxxxxxxxxxxxxxxx,CG-yyyyyyyyyyyyyyyyyyyyyyyy"]
    )

    # AI Analysis (Groq)
    groq_api_key: str = Field(
        default="",
        description="Groq API key for AI-powered technical analysis (/ta AI button)",
        examples=["gsk_..."]
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
