# tests/test_config.py
import os
import pytest
from pydantic import ValidationError

def test_config_requires_bot_token():
    """Config debe fallar sin TELEGRAM_BOT_TOKEN."""
    from src.config import Settings
    
    # Asegurar que no existe la variable de entorno
    old_token = os.environ.pop('TELEGRAM_BOT_TOKEN', None)
    
    try:
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert 'telegram_bot_token' in str(exc_info.value)
    finally:
        if old_token:
            os.environ['TELEGRAM_BOT_TOKEN'] = old_token

def test_config_with_minimal_env():
    """Config funciona con solo el bot token."""
    from src.config import Settings
    
    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
    
    try:
        config = Settings()
        assert config.telegram_bot_token == 'test_token'
        assert config.tasalo_api_url == 'http://localhost:8000'
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
