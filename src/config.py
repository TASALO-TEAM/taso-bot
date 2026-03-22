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
        default="http://localhost:8000",
        description="URL base de la API de taso-api",
        examples=["http://localhost:8000", "https://api.tasalo.app"]
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
