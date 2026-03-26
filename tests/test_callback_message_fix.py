"""Test to verify the callback message fix.

This test ensures that send_tasalo_response works correctly
when called from callback context (where update.message is None).
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update, CallbackQuery, Message, User

from src.handlers.tasalo import tasalo_refresh_callback, tasalo_back_callback


@pytest.mark.asyncio
async def test_refresh_callback_uses_message_id():
    """Verify refresh callback uses message_id correctly.
    
    This is a regression test for the AttributeError bug where:
    - update.message is None in callback context
    - Code was trying to call update.message.reply_text()
    - Fix: Pass message_id to send_tasalo_response() and use context.bot methods
    """
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
    # CRITICAL: In real callback context, update.message is None
    update.message = None

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.edit_message_caption = AsyncMock()
    context.bot.send_photo = AsyncMock()
    context.bot.send_message = AsyncMock()
    
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
        mock_gen.return_value = None  # Skip image generation

        # This should NOT raise AttributeError
        await tasalo_refresh_callback(update, context)

    # Verify callback answer was called
    callback_query.answer.assert_called()
    
    # Verify context.bot methods were called (not update.message methods)
    assert context.bot.edit_message_text.called or context.bot.edit_message_caption.called


@pytest.mark.asyncio
async def test_back_callback_uses_message_id():
    """Verify back callback uses message_id correctly.
    
    Regression test for the same AttributeError bug.
    """
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
    update.message = None  # None in callback context

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.edit_message_caption = AsyncMock()
    context.bot.send_photo = AsyncMock()
    context.bot.send_message = AsyncMock()
    
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
        mock_gen.return_value = None

        # This should NOT raise AttributeError
        await tasalo_back_callback(update, context)

    # Verify callback answer was called
    callback_query.answer.assert_called()
    
    # Verify context.bot methods were called
    assert context.bot.edit_message_text.called or context.bot.edit_message_caption.called or context.bot.send_photo.called


@pytest.mark.asyncio
async def test_send_tasalo_response_with_message_id():
    """Test send_tasalo_response directly with message_id parameter."""
    from src.handlers.tasalo import send_tasalo_response
    
    user = User(id=123, first_name="Test", is_bot=False)
    chat = MagicMock()
    chat.id = 123
    
    message = MagicMock(spec=Message)
    message.message_id = 42

    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.message = message

    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    update.effective_chat = chat
    update.message = None  # None in callback context

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.edit_message_caption = AsyncMock()
    context.bot.send_photo = AsyncMock()

    api_data = {
        "eltoque": {"USD": {"rate": 365.0, "change": 5.0}},
        "updated_at": "2026-03-22T14:30:00Z"
    }

    with patch('src.handlers.tasalo.generate_image', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = None

        # Call with message_id parameter (correct signature)
        await send_tasalo_response(update, context, api_data, message_id=42)

    # Should use context.bot.edit_message_text, not update.message.reply_text
    assert context.bot.edit_message_text.called or context.bot.edit_message_caption.called
