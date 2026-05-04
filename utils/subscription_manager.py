# utils/subscription_manager.py
# Stub for rate limiting and usage tracking.

from typing import Tuple

def check_feature_access(chat_id: int, feature_type: str, current_count: int = None) -> Tuple[bool, str]:
    """Always allow access."""
    return True, "OK"

def registrar_uso_comando(chat_id: int, comando: str) -> None:
    """No-op usage tracking."""
    return
