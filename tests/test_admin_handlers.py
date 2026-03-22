"""Tests para handlers de administración."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, Chat, User

from src.handlers.admin import (
    refresh_command,
    status_command,
    _is_admin,
)


@pytest.mark.asyncio
async def test_refresh_command_no_admin():
    """Test /refresh desde usuario no admin."""
    # Mock update
    user = User(id=999, first_name="NotAdmin", is_bot=False)
    chat = Chat(id=999, type="private")
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock context
    context = MagicMock()
    context.bot_data = {"api_client": AsyncMock()}

    # Call handler
    await refresh_command(update, context)

    # Verify access denied
    message.reply_text.assert_called_once()
    call_args = message.reply_text.call_args[0][0]
    assert "Acceso Denegado" in call_args


@pytest.mark.asyncio
async def test_refresh_command_admin_success():
    """Test /refresh desde admin exitoso."""
    # Mock update
    user = User(id=123, first_name="Admin", is_bot=False)
    chat = Chat(id=123, type="private")
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock context with admin API client
    mock_api_client = AsyncMock()
    mock_api_client.admin_refresh = AsyncMock(return_value={
        "ok": True,
        "data": {
            "sources": ["eltoque", "cadeca", "bcc"],
            "timestamp": "2026-03-22T14:30:00Z"
        }
    })
    mock_api_client.admin_key = "test_key"

    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    # Mock settings to return user as admin
    with patch('src.handlers.admin.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123, 456]

        # Call handler
        await refresh_command(update, context)

    # Verify success message
    status_msg = message.reply_text.return_value
    status_msg.edit_text.assert_called_once()
    call_args = status_msg.edit_text.call_args[0][0]
    assert "Refresco Completado" in call_args


@pytest.mark.asyncio
async def test_refresh_command_admin_api_error():
    """Test /refresh con error de API."""
    # Mock update
    user = User(id=123, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock API client returning None
    mock_api_client = AsyncMock()
    mock_api_client.admin_refresh = AsyncMock(return_value=None)
    mock_api_client.admin_key = "test_key"

    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    with patch('src.handlers.admin.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]

        # Call handler
        await refresh_command(update, context)

    # Verify error message
    status_msg = message.reply_text.return_value
    status_msg.edit_text.assert_called_once()
    call_args = status_msg.edit_text.call_args[0][0]
    assert "Error de Conexión" in call_args


@pytest.mark.asyncio
async def test_refresh_command_no_api_key():
    """Test /refresh sin API key configurada."""
    # Mock update
    user = User(id=123, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock API client without admin_key
    mock_api_client = AsyncMock()
    mock_api_client.admin_key = None

    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    with patch('src.handlers.admin.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]

        # Call handler
        await refresh_command(update, context)

    # Verify config error message
    message.reply_text.assert_called_once()
    call_args = message.reply_text.call_args[0][0]
    assert "Error de Configuración" in call_args


@pytest.mark.asyncio
async def test_status_command_no_admin():
    """Test /status desde usuario no admin."""
    # Mock update
    user = User(id=999, first_name="NotAdmin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock context
    context = MagicMock()
    context.bot_data = {"api_client": AsyncMock()}

    # Call handler
    await status_command(update, context)

    # Verify access denied
    message.reply_text.assert_called_once()
    call_args = message.reply_text.call_args[0][0]
    assert "Acceso Denegado" in call_args


@pytest.mark.asyncio
async def test_status_command_admin_success():
    """Test /status desde admin exitoso."""
    # Mock update
    user = User(id=123, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock API client
    mock_api_client = AsyncMock()
    mock_api_client.admin_status = AsyncMock(return_value={
        "ok": True,
        "data": {
            "scheduler": {
                "is_running": True,
                "last_run_at": "2026-03-22T14:30:00Z",
                "last_success_at": "2026-03-22T14:30:00Z",
                "next_run_at": "2026-03-22T14:35:00Z",
                "error_count": 0,
                "last_error": None
            }
        }
    })
    mock_api_client.admin_key = "test_key"

    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    with patch('src.handlers.admin.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]

        # Call handler
        await status_command(update, context)

    # Verify success message
    status_msg = message.reply_text.return_value
    status_msg.edit_text.assert_called_once()
    call_args = status_msg.edit_text.call_args[0][0]
    assert "Estado del Scheduler" in call_args
    assert "Corriendo" in call_args


@pytest.mark.asyncio
async def test_status_command_scheduler_stopped():
    """Test /status con scheduler detenido."""
    # Mock update
    user = User(id=123, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock API client with stopped scheduler
    mock_api_client = AsyncMock()
    mock_api_client.admin_status = AsyncMock(return_value={
        "ok": True,
        "data": {
            "scheduler": {
                "is_running": False,
                "last_run_at": "2026-03-22T10:00:00Z",
                "last_success_at": "2026-03-22T10:00:00Z",
                "next_run_at": None,
                "error_count": 3,
                "last_error": "Connection timeout"
            }
        }
    })
    mock_api_client.admin_key = "test_key"

    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    with patch('src.handlers.admin.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]

        # Call handler
        await status_command(update, context)

    # Verify stopped status
    status_msg = message.reply_text.return_value
    status_msg.edit_text.assert_called_once()
    call_args = status_msg.edit_text.call_args[0][0]
    assert "Detenido" in call_args
    assert "*Errores:* 3" in call_args


@pytest.mark.asyncio
async def test_status_command_api_error():
    """Test /status con error de API."""
    # Mock update
    user = User(id=123, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock API client returning None
    mock_api_client = AsyncMock()
    mock_api_client.admin_status = AsyncMock(return_value=None)
    mock_api_client.admin_key = "test_key"

    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    with patch('src.handlers.admin.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]

        # Call handler
        await status_command(update, context)

    # Verify error message
    status_msg = message.reply_text.return_value
    status_msg.edit_text.assert_called_once()
    call_args = status_msg.edit_text.call_args[0][0]
    assert "Error de Conexión" in call_args


def test_is_admin_true():
    """Test _is_admin con usuario admin."""
    with patch('src.handlers.admin.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123, 456, 789]
        assert _is_admin(123) is True
        assert _is_admin(456) is True


def test_is_admin_false():
    """Test _is_admin con usuario no admin."""
    with patch('src.handlers.admin.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123, 456]
        assert _is_admin(999) is False
        assert _is_admin(0) is False


def test_is_admin_empty_list():
    """Test _is_admin con lista vacía."""
    with patch('src.handlers.admin.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = []
        assert _is_admin(123) is False
