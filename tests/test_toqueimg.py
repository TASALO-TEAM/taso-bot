"""Tests for /toqueimg command and handlers."""

import pytest
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.handlers.toqueimg import toqueimg_command, toqueimg_refresh_callback, _build_toqueimg_keyboard


class TestToqueimgKeyboard:
    """Tests for keyboard builder."""
    
    def test_build_keyboard_no_alert(self):
        """Test keyboard when user has no alert."""
        keyboard = _build_toqueimg_keyboard(has_alert=False)
        
        # Should have 3 rows
        assert len(keyboard) == 3
        
        # First row: Activate alert button
        assert len(keyboard[0]) == 1
        assert "🔔" in keyboard[0][0].text
        assert keyboard[0][0].callback_data == "alert_enable_default"
        
        # Second row: Custom time button
        assert len(keyboard[1]) == 1
        assert "⏰" in keyboard[1][0].text
        assert keyboard[1][0].callback_data == "alert_custom_time"
        
        # Third row: Refresh button
        assert len(keyboard[2]) == 1
        assert "🔄" in keyboard[2][0].text
        assert keyboard[2][0].callback_data == "toqueimg_refresh"
    
    def test_build_keyboard_with_alert(self):
        """Test keyboard when user has active alert."""
        keyboard = _build_toqueimg_keyboard(has_alert=True)
        
        # Should have 4 rows
        assert len(keyboard) == 4
        
        # First row: Status button
        assert len(keyboard[0]) == 1
        assert "✅" in keyboard[0][0].text
        assert keyboard[0][0].callback_data == "alert_status"
        
        # Second row: Change time and format
        assert len(keyboard[1]) == 2
        assert "⏰" in keyboard[1][0].text
        assert keyboard[1][0].callback_data == "alert_change_time"
        assert "📄" in keyboard[1][1].text
        assert keyboard[1][1].callback_data == "alert_change_format"
        
        # Third row: Disable button
        assert len(keyboard[2]) == 1
        assert "❌" in keyboard[2][0].text
        assert keyboard[2][0].callback_data == "alert_disable"
        
        # Fourth row: Refresh button
        assert len(keyboard[3]) == 1
        assert "🔄" in keyboard[3][0].text
        assert keyboard[3][0].callback_data == "toqueimg_refresh"


class TestToqueimgCommand:
    """Tests for /toqueimg command."""
    
    @pytest.mark.asyncio
    async def test_toqueimg_command_structure(self):
        """Test that command handler exists and is callable."""
        # Just verify the function exists and is async
        assert callable(toqueimg_command)
    
    @pytest.mark.asyncio
    async def test_toqueimg_refresh_callback_structure(self):
        """Test that refresh callback exists and is callable."""
        assert callable(toqueimg_refresh_callback)
