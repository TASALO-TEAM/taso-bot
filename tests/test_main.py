# tests/test_main.py
"""Test manual de integración para verificar que el bot arranca.

Este test es manual porque requiere un token de Telegram válido.
Ejecutar solo en entorno de desarrollo con .env configurado.

Usage:
    cp .env.example .env
    # Editar .env con TELEGRAM_BOT_TOKEN válido
    python -m pytest tests/test_main.py -v -s
"""

import os
import pytest

@pytest.mark.skipif(
    not os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN') == 'your_bot_token_here',
    reason="Requires valid TELEGRAM_BOT_TOKEN in .env"
)
def test_bot_can_import_main():
    """Verificar que main.py puede importarse sin errores."""
    from src import main
    assert main.create_application is not None
    assert main.post_init is not None

@pytest.mark.skipif(
    not os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN') == 'your_bot_token_here',
    reason="Requires valid TELEGRAM_BOT_TOKEN in .env"
)
@pytest.mark.asyncio
async def test_api_client_connectivity():
    """Verificar que el cliente API puede conectarse a taso-api.
    
    Requiere que taso-api esté corriendo en localhost:8000.
    """
    from src.api_client import TasaloApiClient
    
    client = TasaloApiClient(api_url="http://localhost:8000", timeout=15)
    data = await client.get_latest()
    
    if data:
        assert data.get('ok') is True
        assert 'data' in data
        print(f"✅ API connection OK. Updated at: {data.get('updated_at')}")
    else:
        pytest.skip("taso-api no está disponible en localhost:8000")
