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
from src.handlers.toqueimg import (
    toqueimg_command,
    toqueimg_refresh_callback,
)
from src.handlers.image_alerts import (
    alert_enable_default_callback,
    alert_custom_time_callback,
    alert_disable_callback,
    alert_change_time_callback,
    alert_change_format_callback,
    alert_format_callback,
    alert_status_callback,
    alert_cancel_callback,
    handle_time_input,
)
from src.handlers.y import (
    y_command,
    year_sub_callback,
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
    "toqueimg_command",
    "toqueimg_refresh_callback",
    "alert_enable_default_callback",
    "alert_custom_time_callback",
    "alert_disable_callback",
    "alert_change_time_callback",
    "alert_change_format_callback",
    "alert_format_callback",
    "alert_status_callback",
    "alert_cancel_callback",
    "handle_time_input",
    "y_command",
    "year_sub_callback",
]
