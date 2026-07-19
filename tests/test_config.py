# tests/test_config.py
import os
import sys
import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict, BaseSettings
from pydantic import Field

def test_config_requires_bot_token():
    """Config debe fallar sin TELEGRAM_BOT_TOKEN."""
    # Creamos una clase de prueba que herede la misma estructura
    # pero sin env_file para poder testear la validación
    from src.config import Settings
    
    # Asegurar que no existe la variable de entorno
    old_token = os.environ.pop('TELEGRAM_BOT_TOKEN', None)

    try:
        # La clase Settings carga desde .env por defecto, así que
        # probamos la validación creando una clase temporal sin env_file
        class TestSettings(BaseSettings):
            model_config = SettingsConfigDict(
                env_file=None,
                env_file_encoding='utf-8',
                case_sensitive=False,
                extra='ignore',
            )
            telegram_bot_token: str = Field(...)
        
        with pytest.raises(ValidationError) as exc_info:
            TestSettings()
        assert 'telegram_bot_token' in str(exc_info.value).lower()
    finally:
        if old_token:
            os.environ['TELEGRAM_BOT_TOKEN'] = old_token

def test_config_with_minimal_env():
    """Config funciona con solo el bot token."""
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import Field

    # Create a test-specific settings class that doesn't load from .env
    class TestSettings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=None,  # Don't load from .env file
            env_file_encoding='utf-8',
            case_sensitive=False,
            extra='ignore',
        )
        telegram_bot_token: str = Field(...)
        tasalo_api_url: str = Field(default="http://localhost:8040")
        api_timeout_seconds: int = Field(default=15)

    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'

    try:
        config = TestSettings()
        assert config.telegram_bot_token == 'test_token'
        assert config.tasalo_api_url == 'http://localhost:8040'
        assert config.api_timeout_seconds == 15
    finally:
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)

def test_admin_chat_ids_parsed():
    """ADMIN_CHAT_IDS se parsea como lista de enteros."""
    from src.config import Settings
    
    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
    os.environ['ADMIN_CHAT_IDS'] = '123,456,789'
    
    try:
        config = Settings()
        assert config.admin_chat_ids == '123,456,789'
        assert config.get_admin_chat_ids_list() == [123, 456, 789]
    finally:
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        os.environ.pop('ADMIN_CHAT_IDS', None)

def test_tasalo_admin_key():
    """TASALO_ADMIN_KEY se carga correctamente."""
    from src.config import Settings
    
    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
    os.environ['TASALO_ADMIN_KEY'] = 'secret_key_123'
    
    try:
        config = Settings()
        assert config.tasalo_admin_key == 'secret_key_123'
    finally:
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        os.environ.pop('TASALO_ADMIN_KEY', None)


def test_coinmarketcap_api_keys_empty():
    """coinmarketcap_api_keys retorna lista vacía si no hay key configurada.

    Nota: se fija la variable a '' en vez de hacer pop(), porque con pop()
    pydantic-settings cae al valor del .env real del proyecto (que sí tiene
    keys configuradas) en vez de quedar realmente vacía.
    """
    from src.config import Settings

    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
    os.environ['COINMARKETCAP_API_KEY'] = ''

    try:
        config = Settings()
        assert config.coinmarketcap_api_keys == []
    finally:
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        os.environ.pop('COINMARKETCAP_API_KEY', None)


def test_coinmarketcap_api_keys_single():
    """Una sola key sin coma retorna lista de 1 elemento."""
    from src.config import Settings

    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
    os.environ['COINMARKETCAP_API_KEY'] = 'abc123'

    try:
        config = Settings()
        assert config.coinmarketcap_api_keys == ['abc123']
    finally:
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        os.environ.pop('COINMARKETCAP_API_KEY', None)


def test_coinmarketcap_api_keys_multiple():
    """Varias keys separadas por coma se parsean como lista, sin espacios."""
    from src.config import Settings

    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
    os.environ['COINMARKETCAP_API_KEY'] = 'key1, key2 ,key3'

    try:
        config = Settings()
        assert config.coinmarketcap_api_keys == ['key1', 'key2', 'key3']
    finally:
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        os.environ.pop('COINMARKETCAP_API_KEY', None)


def test_cmc_api_key_alerta_falls_back_to_interactive_pool():
    """Sin CMC_API_KEY_ALERTA configurada, el checker usa el pool interactivo.

    Se fija CMC_API_KEY_ALERTA a '' (no pop()) por el mismo motivo que en
    test_coinmarketcap_api_keys_empty: pop() dejaría que pydantic-settings
    lea el valor real del .env del proyecto.
    """
    from src.config import Settings

    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
    os.environ['COINMARKETCAP_API_KEY'] = 'key1,key2,key3'
    os.environ['CMC_API_KEY_ALERTA'] = ''

    try:
        config = Settings()
        assert config.cmc_api_key_alerta_keys == ['key1', 'key2', 'key3']
    finally:
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        os.environ.pop('COINMARKETCAP_API_KEY', None)
        os.environ.pop('CMC_API_KEY_ALERTA', None)


def test_cmc_api_key_alerta_own_pool():
    """Con CMC_API_KEY_ALERTA configurada, usa su propio pool (no el interactivo)."""
    from src.config import Settings

    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
    os.environ['COINMARKETCAP_API_KEY'] = 'interactivo1,interactivo2'
    os.environ['CMC_API_KEY_ALERTA'] = 'alerta1,alerta2'

    try:
        config = Settings()
        assert config.cmc_api_key_alerta_keys == ['alerta1', 'alerta2']
        # El pool interactivo no cambia
        assert config.coinmarketcap_api_keys == ['interactivo1', 'interactivo2']
    finally:
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        os.environ.pop('COINMARKETCAP_API_KEY', None)
        os.environ.pop('CMC_API_KEY_ALERTA', None)


def test_groq_api_keys_empty():
    """groq_api_keys retorna lista vacía si no hay key configurada.

    Se fija GROQ_API_KEY a '' (no pop()) por el mismo motivo que en
    test_coinmarketcap_api_keys_empty.
    """
    from src.config import Settings

    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
    os.environ['GROQ_API_KEY'] = ''

    try:
        config = Settings()
        assert config.groq_api_keys == []
    finally:
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        os.environ.pop('GROQ_API_KEY', None)


def test_groq_api_keys_multiple():
    """Varias keys de Groq separadas por coma se parsean como lista."""
    from src.config import Settings

    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
    os.environ['GROQ_API_KEY'] = 'gsk_uno,gsk_dos'

    try:
        config = Settings()
        assert config.groq_api_keys == ['gsk_uno', 'gsk_dos']
    finally:
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        os.environ.pop('GROQ_API_KEY', None)
