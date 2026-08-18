"""Info de build/versión del bot taso-bot: commit, fecha, hora de arranque.

Usado por /status (panel ejecutivo, botón "📝 Cambios recientes") y por el
log de arranque en main.py. Se calcula una sola vez al importar el módulo
(no en cada request/callback) — mismo criterio aplicado en taso-api
(src/main.py::_get_git_build_info).

Ver docs/plans/2026-07-08-status-command-v2.md (Fase 3/4).
"""

import logging
import subprocess
import time

logger = logging.getLogger(__name__)

BOT_VERSION = "0.13.2.0"

# Timestamp de arranque del proceso — usado para calcular uptime en /status.
BOT_START_TIME = time.time()


def _get_git_build_info() -> dict[str, str]:
    """Lee commit corto + fecha del último commit del repo taso-bot.

    Fallback a "unknown" si no hay .git (ej. corriendo desde un tarball
    en el VPS) o si el comando git falla por cualquier razón.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3, check=True,
        ).stdout.strip()
        commit_date = subprocess.run(
            ["git", "log", "-1", "--format=%cd", "--date=short"],
            capture_output=True, text=True, timeout=3, check=True,
        ).stdout.strip()
        return {"commit": commit or "unknown", "commit_date": commit_date or "unknown"}
    except Exception as e:
        logger.warning("⚠️ No se pudo leer info de git del bot (%s) — usando 'unknown'", e)
        return {"commit": "unknown", "commit_date": "unknown"}


BOT_BUILD_INFO: dict[str, str] = _get_git_build_info()


def format_uptime(start_time: float = BOT_START_TIME) -> str:
    """Formatea el tiempo transcurrido desde start_time como 'Xd Yh' / 'Xh Ym' / 'Xm'."""
    total_seconds = int(time.time() - start_time)
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
