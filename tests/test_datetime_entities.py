"""Tests for Bot API 9.5 DATE_TIME entity support.

NOTE: DATE_TIME entities are currently DISABLED (HAS_DATETIME_ENTITY = False)
because Telegram's API server returns "can't parse messageentity: can't find
field unix_time" errors even though PTB 22.7+ has the constant.

These tests verify the DISABLED state and the fallback behavior.
"""

import time
import pytest
from datetime import datetime
from telegram import MessageEntity

from src.formatters import (
    HAS_DATETIME_ENTITY,
    build_full_message_with_datetime,
    build_full_message,
)


class TestDatetimeEntityDisabled:
    """Tests verifying DATE_TIME entity is properly disabled."""

    def test_has_datetime_entity_flag_is_false(self):
        """DATE_TIME entity is DISABLED until Telegram API supports it."""
        assert HAS_DATETIME_ENTITY is False, \
            "DATE_TIME entities should be disabled due to Telegram API parse errors"

    def test_message_entity_date_time_still_exists(self):
        """PTB still has the constant, but we don't use it."""
        assert hasattr(MessageEntity, "DATE_TIME"), \
            "PTB should have MessageEntity.DATE_TIME constant"

    def test_fallback_returns_markdown_text(self):
        """When disabled, should fallback to standard Markdown text."""
        sample_data = {
            "eltoque": {
                "USD": {"rate": 515.0, "change": "up", "prev_rate": 510.0},
                "EUR": {"rate": 580.0, "change": "down", "prev_rate": 585.0},
            },
            "cadeca": {},
            "bcc": {},
            "updated_at": "2026-04-10T12:00:00Z",
        }
        timestamp = int(time.time())

        text, entities = build_full_message_with_datetime(sample_data, timestamp)

        # Should return text (string) and empty entities list
        assert isinstance(text, str)
        assert isinstance(entities, list)
        assert len(entities) == 0, "Entities list should be empty when disabled"
        assert len(text) > 0

    def test_fallback_uses_build_full_message(self):
        """Disabled path should delegate to build_full_message."""
        sample_data = {
            "eltoque": {"USD": {"rate": 515.0}},
            "cadeca": {},
            "bcc": {},
            "updated_at": "2026-04-10T12:00:00Z",
        }
        timestamp = int(time.time())

        text, entities = build_full_message_with_datetime(sample_data, timestamp)
        standard_text = build_full_message(sample_data)

        # Both should produce the same text structure
        assert text == standard_text
        assert entities == []

    def test_fallback_handles_empty_eltoque(self):
        """Fallback should handle empty eltoque data gracefully."""
        sample_data = {
            "eltoque": {},
            "cadeca": {},
            "bcc": {},
            "updated_at": "2026-04-10T12:00:00Z",
        }
        timestamp = int(time.time())

        text, entities = build_full_message_with_datetime(sample_data, timestamp)

        assert isinstance(text, str)
        assert entities == []
        # Should still have the structure headers
        assert "MERCADO INFORMAL" in text or "Datos no disponibles" in text
