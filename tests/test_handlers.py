"""Tests para handlers de callbacks inline."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, CallbackQuery, Message, Chat, User

from src.handlers.tasalo import history_callback


@pytest.mark.asyncio
async def test_history_callback_success():
    """Test callback de historial exitoso."""
    # Mock update
    user = User(id=123, first_name="Test", is_bot=False)
    chat = Chat(id=123, type="private")
    message = MagicMock(spec=Message)
    message.message_id = 42
    
    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.message = message
    callback_query.data = "tasalo_history:USD:eltoque:7"
    callback_query.answer = AsyncMock()
    callback_query.edit_message_text = AsyncMock()
    
    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    update.effective_user = user
    
    # Mock context
    context = MagicMock()
    context.bot_data = {
        "api_client": AsyncMock(
            get_history=AsyncMock(return_value={
                "ok": True,
                "data": [
                    {"sell_rate": 365.0, "fetched_at": "2026-03-22T14:30:00Z"},
                ],
                "count": 1
            })
        )
    }
    
    # Call handler
    await history_callback(update, context)
    
    # Verify
    callback_query.answer.assert_called_once()
    callback_query.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_history_callback_api_error():
    """Test callback de historial con error de API."""
    user = User(id=123, first_name="Test", is_bot=False)
    chat = Chat(id=123, type="private")
    message = MagicMock(spec=Message)
    message.message_id = 42
    
    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.message = message
    callback_query.data = "tasalo_history:USD:eltoque:7"
    callback_query.answer = AsyncMock()
    callback_query.edit_message_text = AsyncMock()
    
    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    
    context = MagicMock()
    context.bot_data = {"api_client": AsyncMock(get_history=AsyncMock(return_value=None))}
    
    await history_callback(update, context)
    
    # Debe mostrar mensaje de error al usuario
    callback_query.answer.assert_called()


@pytest.mark.asyncio
async def test_history_callback_invalid_data():
    """Test callback de historial con datos inválidos."""
    user = User(id=123, first_name="Test", is_bot=False)
    message = MagicMock(spec=Message)
    
    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.message = message
    callback_query.data = "tasalo_history:INVALID"  # Formato inválido
    callback_query.answer = AsyncMock()
    
    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    
    context = MagicMock()
    context.bot_data = {"api_client": AsyncMock()}
    
    await history_callback(update, context)
    
    # Debe manejar error gracefulmente
    callback_query.answer.assert_called()
