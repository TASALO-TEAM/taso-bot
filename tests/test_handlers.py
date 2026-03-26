"""Tests para handlers de callbacks inline."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, CallbackQuery, Message, Chat, User

from src.handlers.tasalo import (
    history_callback,
    tasalo_refresh_callback,
    tasalo_back_callback,
    tasalo_provincias_callback,
    build_provincias_message,
)


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


@pytest.mark.asyncio
async def test_refresh_callback_shows_loading():
    """Test que refresh muestra indicador de carga."""
    user = User(id=123, first_name="Test", is_bot=False)
    chat = MagicMock()
    chat.id = 123
    
    message = MagicMock(spec=Message)
    message.message_id = 42

    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.message = message
    callback_query.data = "tasalo_refresh"
    callback_query.answer = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    update.effective_chat = chat

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.edit_message_caption = AsyncMock()
    context.bot.send_photo = AsyncMock()
    
    context.bot_data = {
        "api_client": MagicMock(
            get_latest=AsyncMock(return_value={
                "ok": True,
                "data": {"eltoque": {"USD": {"rate": 365.0}}},
                "updated_at": "2026-03-22T14:30:00Z"
            })
        )
    }

    with patch('src.handlers.tasalo.generate_image', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = None  # Skip image generation for this test

        await tasalo_refresh_callback(update, context)

    # Debe llamar answer con mensaje de actualización
    callback_query.answer.assert_called()
    # La llamada debe incluir texto de "actualizando"
    call_args = callback_query.answer.call_args
    assert "Actualizando" in str(call_args) or "🔄" in str(call_args)


@pytest.mark.asyncio
async def test_refresh_callback_api_error():
    """Test refresh callback con error de API."""
    user = User(id=123, first_name="Test", is_bot=False)
    chat = MagicMock()
    chat.id = 123
    
    message = MagicMock(spec=Message)
    message.message_id = 42

    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.message = message
    callback_query.data = "tasalo_refresh"
    callback_query.answer = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    update.effective_chat = chat

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.send_message = AsyncMock()
    
    context.bot_data = {
        "api_client": MagicMock(get_latest=AsyncMock(return_value=None))
    }

    await tasalo_refresh_callback(update, context)

    # Debe mostrar mensaje de error al usuario
    callback_query.answer.assert_called()
    assert "⚠️" in str(callback_query.answer.call_args)


@pytest.mark.asyncio
async def test_back_callback_returns_to_main():
    """Test que back button vuelve a la vista principal."""
    user = User(id=123, first_name="Test", is_bot=False)
    chat = MagicMock()
    chat.id = 123
    
    message = MagicMock(spec=Message)
    message.message_id = 42

    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.message = message
    callback_query.data = "tasalo_back"
    callback_query.answer = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    update.effective_chat = chat

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.edit_message_caption = AsyncMock()
    context.bot.send_photo = AsyncMock()
    
    context.bot_data = {
        "api_client": MagicMock(
            get_latest=AsyncMock(return_value={
                "ok": True,
                "data": {
                    "eltoque": {"USD": {"rate": 365.0, "change": "up"}},
                    "cadeca": {"USD": {"buy": 120.0, "sell": 125.0}},
                    "bcc": {"USD": 24.0}
                },
                "updated_at": "2026-03-22T14:30:00Z"
            })
        )
    }

    with patch('src.handlers.tasalo.generate_image', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = None  # Skip image generation for this test

        await tasalo_back_callback(update, context)

    # Debe volver a mostrar la vista principal
    callback_query.answer.assert_called()
    # Debe llamar context.bot methods
    assert context.bot.edit_message_text.called or context.bot.edit_message_caption.called or context.bot.send_photo.called


@pytest.mark.asyncio
async def test_provincias_callback_shows_national_rate():
    """Test que provincias callback muestra tasa nacional como placeholder."""
    user = User(id=123, first_name="Test", is_bot=False)
    chat = MagicMock()
    chat.id = 123
    
    message = MagicMock(spec=Message)
    message.message_id = 42

    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.message = message
    callback_query.data = "tasalo_provincias"
    callback_query.answer = AsyncMock()
    callback_query.edit_message_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    update.effective_chat = chat

    context = MagicMock()
    context.bot_data = {
        "api_client": AsyncMock(
            get_latest=AsyncMock(return_value={
                "ok": True,
                "data": {
                    "eltoque": {"USD": {"rate": 365.0, "change": "up"}},
                    "cadeca": {"USD": {"buy": 120.0, "sell": 125.0}},
                    "bcc": {"USD": 24.0}
                },
                "updated_at": "2026-03-22T14:30:00Z"
            })
        )
    }

    await tasalo_provincias_callback(update, context)

    # Debe llamar answer con mensaje de provincias
    callback_query.answer.assert_called()
    # Debe editar el mensaje con el texto de provincias (query.edit_message_text)
    callback_query.edit_message_text.assert_called_once()

    # Verificar que el mensaje contiene información de provincias
    call_args = callback_query.edit_message_text.call_args
    text = call_args[1].get("text", "") or (call_args[0][0] if call_args[0] else "")
    assert "PROVINCIA" in text.upper() or "TASA" in text.upper()


def test_build_provincias_message_with_data():
    """Test que build_provincias_message formatea correctamente con datos."""
    api_data = {
        "eltoque": {"USD": {"rate": 365.0, "change": "up"}},
        "updated_at": "2026-03-22T14:30:00Z"
    }
    
    result = build_provincias_message(api_data)
    
    # Verificar estructura del mensaje
    assert "🗺" in result
    assert "PROVINCIA" in result.upper()
    assert "365.00" in result  # Tasa nacional formateada
    assert "2026-03-22" in result  # Timestamp
    assert "elToque.com" in result


def test_build_provincias_message_without_data():
    """Test que build_provincias_message maneja datos vacíos."""
    api_data = {}
    
    result = build_provincias_message(api_data)
    
    # Verificar que al menos muestra el header y footer
    assert "🗺" in result
    assert "PROVINCIA" in result.upper()
