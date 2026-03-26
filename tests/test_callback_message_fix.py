"""Test to verify the callback message fix.

This test ensures that send_tasalo_response works correctly
when called from callback context (where update.message is None).
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update, CallbackQuery, Message, User

from src.handlers.tasalo import tasalo_refresh_callback, tasalo_back_callback


@pytest.mark.asyncio
async def test_refresh_callback_uses_query_message():
    """Verify refresh callback uses query.message instead of update.message.
    
    This is a regression test for the AttributeError bug where:
    - update.message is None in callback context
    - Code was trying to call update.message.reply_text()
    - Fix: Pass query.message to send_tasalo_response()
    """
    user = User(id=123, first_name="Test", is_bot=False)
    message = MagicMock(spec=Message)
    message.message_id = 42
    message.edit_message_text = AsyncMock()
    message.edit_message_caption = AsyncMock()
    message.reply_photo = AsyncMock()
    message.reply_text = AsyncMock()

    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.message = message
    callback_query.data = "tasalo_refresh"
    callback_query.answer = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    # CRITICAL: In real callback context, update.message is None
    update.message = None
    update.effective_message = None

    context = MagicMock()
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
    
    # Verify message methods were called (not update.message methods)
    # Since we're in text-only mode (no image), edit_message_text should be called
    assert message.edit_message_text.called or message.reply_text.called


@pytest.mark.asyncio
async def test_back_callback_uses_query_message():
    """Verify back callback uses query.message instead of update.message.
    
    Regression test for the same AttributeError bug.
    """
    user = User(id=123, first_name="Test", is_bot=False)
    message = MagicMock(spec=Message)
    message.message_id = 42
    message.edit_message_text = AsyncMock()
    message.edit_message_caption = AsyncMock()
    message.reply_photo = AsyncMock()
    message.reply_text = AsyncMock()

    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.message = message
    callback_query.data = "tasalo_back"
    callback_query.answer = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    # CRITICAL: In real callback context, update.message is None
    update.message = None
    update.effective_message = None

    context = MagicMock()
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
    
    # Verify message methods were called
    assert message.edit_message_text.called or message.reply_photo.called or message.reply_text.called


@pytest.mark.asyncio
async def test_send_tasalo_response_with_message_parameter():
    """Test send_tasalo_response directly with message parameter."""
    from src.handlers.tasalo import send_tasalo_response
    
    user = User(id=123, first_name="Test", is_bot=False)
    message = MagicMock(spec=Message)
    message.message_id = 42
    message.edit_message_text = AsyncMock()
    message.reply_photo = AsyncMock()

    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.message = message

    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    update.message = None  # None in callback context

    api_data = {
        "eltoque": {"USD": {"rate": 365.0, "change": 5.0}},
        "updated_at": "2026-03-22T14:30:00Z"
    }

    with patch('src.handlers.tasalo.generate_image', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = None

        # Call with message parameter (new signature)
        await send_tasalo_response(update, api_data, message=message)

    # Should use message.edit_message_text, not update.message.reply_text
    message.edit_message_text.assert_called_once()
