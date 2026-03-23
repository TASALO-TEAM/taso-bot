"""Handlers para el bot TASALO."""

# Export handlers from submodules
from src.handlers.tasalo import (
    tasalo_command,
    tasalo_refresh_callback,
    tasalo_provincias_callback,
    tasalo_back_callback,
    history_callback,
    toque_command,
    bcc_command,
    cadeca_command,
    source_refresh_callback,
)
from src.handlers.admin import (
    refresh_command,
    status_command,
)

__all__ = [
    "tasalo_command",
    "tasalo_refresh_callback",
    "tasalo_provincias_callback",
    "tasalo_back_callback",
    "history_callback",
    "toque_command",
    "bcc_command",
    "cadeca_command",
    "source_refresh_callback",
    "refresh_command",
    "status_command",
]
