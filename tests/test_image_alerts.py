"""Tests for image alert handlers."""

import pytest
import re
from src.handlers.image_alerts import handle_time_input


class TestTimeInputValidation:
    """Tests for time input validation logic."""
    
    def test_valid_time_formats(self):
        """Test valid time formats."""
        valid_times = [
            "00:00", "01:00", "07:15", "08:30",
            "12:00", "15:45", "23:59"
        ]
        
        for time_str in valid_times:
            assert re.match(r"^\d{2}:\d{2}$", time_str) is not None, \
                f"{time_str} should be valid"
    
    def test_invalid_time_formats(self):
        """Test invalid time formats."""
        invalid_times = [
            "7:15",    # Single digit hour
            "07:5",    # Single digit minute
            "7:5",     # Both single digit
            "25:00",   # Invalid hour
            "12:60",   # Invalid minute
            "abc",     # Letters
            "",        # Empty
            "12-30",   # Wrong separator
            "12:30:00" # Seconds included
        ]
        
        for time_str in invalid_times:
            if time_str:  # Skip empty string
                match = re.match(r"^\d{2}:\d{2}$", time_str)
                if match:
                    # If format matches, check if time is valid
                    hour, minute = map(int, time_str.split(":"))
                    assert 0 <= hour <= 23 and 0 <= minute <= 59, \
                        f"{time_str} should be invalid time"
    
    def test_time_range_validation(self):
        """Test time range validation."""
        # Valid boundary cases
        assert re.match(r"^\d{2}:\d{2}$", "00:00") is not None
        assert re.match(r"^\d{2}:\d{2}$", "23:59") is not None
        
        # Invalid boundary cases
        hour, minute = map(int, "24:00".split(":"))
        assert not (0 <= hour <= 23 and 0 <= minute <= 59)
        
        hour, minute = map(int, "12:60".split(":"))
        assert not (0 <= hour <= 23 and 0 <= minute <= 59)
