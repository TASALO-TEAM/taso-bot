# src/utils/subscription_manager.py
# Minimal stub for BBAlert trading command integration.
# Provides no-op rate limiting to keep commands freely accessible.

from typing import Tuple

def check_feature_access(chat_id: int, feature_type: str, current_count: int = None) -> Tuple[bool, str]:
    """
    Stub: always allow access.
    Returns (True, "OK").
    """
    return True, "OK"

def registrar_uso_comando(chat_id: int, comando: str) -> None:
    """Stub: do not track command usage."""
    return
