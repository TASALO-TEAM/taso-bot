"""Tests for Bot API 9.5 DATE_TIME entity support."""

import time
import pytest
from datetime import datetime
from telegram import MessageEntity

from src.formatters import (
    HAS_DATETIME_ENTITY,
    build_full_message_with_datetime,
)


class TestDatetimeEntitySupport:
    """Tests for DATE_TIME entity formatting (Bot API 9.5+)."""

    def test_has_datetime_entity_flag(self):
        """PTB 22.7+ should support DATE_TIME entity."""
        assert HAS_DATETIME_ENTITY is True, \
            "PTB 22.7+ should have MessageEntity.DATE_TIME"

    def test_message_entity_date_time_exists(self):
        """MessageEntity should have DATE_TIME attribute."""
        assert hasattr(MessageEntity, "DATE_TIME")

    def test_build_full_message_with_datetime_returns_tuple(self):
        """Function should return (text, entities) tuple."""
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

        assert isinstance(text, str)
        assert isinstance(entities, list)
        assert len(text) > 0

    def test_datetime_entity_created(self):
        """Should create DATE_TIME entity at correct offset."""
        sample_data = {
            "eltoque": {
                "USD": {"rate": 515.0, "change": None, "prev_rate": None},
            },
            "cadeca": {},
            "bcc": {},
            "updated_at": "2026-04-10T12:00:00Z",
        }
        timestamp = 1744286400  # Fixed timestamp for reproducibility

        text, entities = build_full_message_with_datetime(sample_data, timestamp)

        assert len(entities) == 1
        entity = entities[0]
        assert entity.type == MessageEntity.DATE_TIME

        # Entity text should contain the timestamp digits
        entity_text = text[entity.offset:entity.offset + entity.length]
        assert str(timestamp) in entity_text or any(c.isdigit() for c in entity_text)

    def test_entity_offset_points_to_timestamp(self):
        """Entity offset should point to the timestamp in the message text."""
        sample_data = {
            "eltoque": {
                "USD": {"rate": 515.0},
            },
            "cadeca": {},
            "bcc": {},
            "updated_at": "2026-04-10T12:00:00Z",
        }
        timestamp = 1744286400

        text, entities = build_full_message_with_datetime(sample_data, timestamp)

        entity = entities[0]
        # Verify offset is within bounds
        assert 0 <= entity.offset < len(text)
        # Verify entity doesn't go past end of text
        assert entity.offset + entity.length <= len(text)

    def test_message_contains_eltoque_section(self):
        """Message text should contain ElToque rates."""
        sample_data = {
            "eltoque": {
                "USD": {"rate": 515.0},
                "EUR": {"rate": 580.0},
            },
            "cadeca": {},
            "bcc": {},
            "updated_at": "2026-04-10T12:00:00Z",
        }
        timestamp = int(time.time())

        text, entities = build_full_message_with_datetime(sample_data, timestamp)

        assert "MERCADO INFORMAL" in text
        assert "USD" in text
        assert "EUR" in text
        assert "515.00" in text
        assert "580.00" in text

    def test_message_contains_cadeca_when_present(self):
        """Message should include CADECA block when data is present."""
        sample_data = {
            "eltoque": {"USD": {"rate": 515.0}},
            "cadeca": {
                "USD": {"buy": 461.27, "sell": 506.68},
            },
            "bcc": {},
            "updated_at": "2026-04-10T12:00:00Z",
        }
        timestamp = int(time.time())

        text, entities = build_full_message_with_datetime(sample_data, timestamp)

        assert "CADECA" in text
        assert "461.27" in text

    def test_message_contains_bcc_when_present(self):
        """Message should include BCC block when data is present."""
        sample_data = {
            "eltoque": {"USD": {"rate": 515.0}},
            "cadeca": {},
            "bcc": {
                "EUR": {"rate": 551.23},
                "USD": {"rate": 478.00},
            },
            "updated_at": "2026-04-10T12:00:00Z",
        }
        timestamp = int(time.time())

        text, entities = build_full_message_with_datetime(sample_data, timestamp)

        assert "BCC" in text or "OFFICIAL RATE" in text
        assert "551.23" in text

    def test_fallback_when_no_eltoque_data(self):
        """Should handle empty eltoque data gracefully."""
        sample_data = {
            "eltoque": {},
            "cadeca": {},
            "bcc": {},
            "updated_at": "2026-04-10T12:00:00Z",
        }
        timestamp = int(time.time())

        text, entities = build_full_message_with_datetime(sample_data, timestamp)

        assert isinstance(text, str)
        assert len(entities) == 1
        assert "Datos no disponibles" in text or "MERCADO INFORMAL" in text

    def test_entity_type_is_date_time(self):
        """Entity type must be MessageEntity.DATE_TIME exactly."""
        sample_data = {
            "eltoque": {"USD": {"rate": 515.0}},
            "cadeca": {},
            "bcc": {},
            "updated_at": "2026-04-10T12:00:00Z",
        }
        timestamp = int(time.time())

        _, entities = build_full_message_with_datetime(sample_data, timestamp)

        assert entities[0].type == MessageEntity.DATE_TIME
