"""Gestión de logs multi-servicio para el comando /log.

Permite al bot inspeccionar y administrar los logs de sí mismo (taso-bot) y
de sus repos hermanos taso-api y taso-app, que viven como directorios
hermanos en el VPS (~/tasalo/taso-bot, ~/tasalo/taso-api, ~/tasalo/taso-app).

No se toca journalctl ni systemd: todo se basa en los archivos de log que
cada servicio escribe con su propio `logging_config`/`logger` (rotación por
tamaño, archivado por fecha de cierre en `logs/archive/`).
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from src.config import settings
from src.logger import LOGS_DIR as BOT_LOGS_DIR

BOT_BASE_DIR = os.path.dirname(BOT_LOGS_DIR)  # .../taso-bot

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# service key -> nombre de archivo/prefijo usado por ese servicio
SERVICE_DISPLAY_NAMES = {
    "bot": "taso-bot",
    "api": "taso-api",
    "web": "taso-app",
}

# Alias que el usuario puede escribir en /log
SERVICE_ALIASES = {
    "bot": "bot",
    "api": "api",
    "web": "web",
    "app": "web",
    "miniapp": "web",
}


@dataclass
class ArchivedLogFile:
    """Un archivo de log ya rotado (cerrado), identificado por su fecha de cierre."""

    path: str
    filename: str
    date_str: str  # YYYY-MM-DD extraído del nombre de archivo
    size_bytes: int


@dataclass
class ServiceLogInfo:
    """Estado de los logs de un servicio (bot, api o web)."""

    service: str
    display_name: str
    logs_dir: str
    exists: bool
    active_log_path: Optional[str] = None
    active_error_log_path: Optional[str] = None
    active_size_bytes: int = 0
    active_error_size_bytes: int = 0
    last_modified: Optional[datetime] = None
    archives: List[ArchivedLogFile] = field(default_factory=list)
    error: Optional[str] = None


def normalize_service(name: str) -> Optional[str]:
    """Normaliza el alias escrito por el usuario ('bot', 'api', 'web', 'app'...).

    Returns:
        La clave canónica ('bot'/'api'/'web') o None si no se reconoce.
    """
    return SERVICE_ALIASES.get(name.strip().lower())


def _service_logs_dir(service: str) -> str:
    """Ruta absoluta a la carpeta logs/ de un servicio."""
    if service == "bot":
        return BOT_LOGS_DIR
    if service == "api":
        return os.path.normpath(os.path.join(BOT_BASE_DIR, settings.taso_api_log_dir))
    if service == "web":
        return os.path.normpath(os.path.join(BOT_BASE_DIR, settings.taso_app_log_dir))
    raise ValueError(f"Servicio desconocido: {service}")


def _extract_date(filename: str) -> str:
    match = DATE_RE.search(filename)
    return match.group(1) if match else "desconocida"


def get_service_log_info(service: str) -> ServiceLogInfo:
    """Recolecta el estado de logs (activos + archivados) de un servicio.

    No lanza excepciones: cualquier problema (carpeta inexistente, permisos,
    etc.) queda reflejado en `ServiceLogInfo.error` para poder informarlo al
    usuario de forma clara en Telegram.
    """
    display_name = SERVICE_DISPLAY_NAMES[service]
    logs_dir = _service_logs_dir(service)

    if not os.path.isdir(logs_dir):
        return ServiceLogInfo(
            service=service,
            display_name=display_name,
            logs_dir=logs_dir,
            exists=False,
            error=(
                f"No se encontró el directorio de logs en `{logs_dir}`. "
                "Puede que el servicio nunca haya corrido en este servidor, "
                "o que la ruta configurada no sea correcta."
            ),
        )

    info = ServiceLogInfo(
        service=service, display_name=display_name, logs_dir=logs_dir, exists=True
    )

    active_log = os.path.join(logs_dir, f"{display_name}.log")
    active_error_log = os.path.join(logs_dir, f"{display_name}-errors.log")

    if os.path.isfile(active_log):
        info.active_log_path = active_log
        info.active_size_bytes = os.path.getsize(active_log)
        info.last_modified = datetime.fromtimestamp(os.path.getmtime(active_log))

    if os.path.isfile(active_error_log):
        info.active_error_log_path = active_error_log
        info.active_error_size_bytes = os.path.getsize(active_error_log)

    archive_dir = os.path.join(logs_dir, "archive")
    if os.path.isdir(archive_dir):
        for fname in os.listdir(archive_dir):
            if not fname.endswith(".log"):
                continue
            fpath = os.path.join(archive_dir, fname)
            try:
                size = os.path.getsize(fpath)
            except OSError:
                continue
            info.archives.append(
                ArchivedLogFile(
                    path=fpath,
                    filename=fname,
                    date_str=_extract_date(fname),
                    size_bytes=size,
                )
            )
        info.archives.sort(key=lambda a: a.date_str, reverse=True)

    if not info.active_log_path and not info.archives:
        info.error = (
            f"El directorio `{logs_dir}` existe pero no tiene ningún log "
            f"todavía (ni activo ni archivado)."
        )

    return info


def list_all_services() -> dict:
    """Devuelve `ServiceLogInfo` para bot, api y web."""
    return {service: get_service_log_info(service) for service in SERVICE_DISPLAY_NAMES}


def find_archive_by_date(service: str, date_str: str) -> tuple:
    """Busca un archivo archivado por fecha exacta (YYYY-MM-DD).

    Returns:
        (ArchivedLogFile | None, List[str] fechas_disponibles)
        Si no hay coincidencia exacta, `fechas_disponibles` trae las fechas
        que sí existen (más recientes primero) para sugerirlas al usuario.
    """
    info = get_service_log_info(service)
    if not info.exists:
        return None, []

    available_dates = sorted({a.date_str for a in info.archives}, reverse=True)

    matches = [a for a in info.archives if a.date_str == date_str]
    if not matches:
        return None, available_dates

    # Si hubo varias rotaciones el mismo día, devolver la más reciente
    matches.sort(key=lambda a: a.filename, reverse=True)
    return matches[0], available_dates


def clear_archives(service: Optional[str] = None) -> dict:
    """Elimina los archivos de `logs/archive/` de uno o todos los servicios.

    Los logs activos NUNCA se tocan, solo los ya rotados.

    Args:
        service: 'bot' | 'api' | 'web', o None para limpiar los 3.

    Returns:
        dict {service: {"removed": int, "bytes_freed": int, "error": str|None}}
    """
    targets = [service] if service else list(SERVICE_DISPLAY_NAMES.keys())
    results = {}

    for svc in targets:
        info = get_service_log_info(svc)
        removed = 0
        bytes_freed = 0
        error = info.error if not info.exists else None

        for archived in info.archives:
            try:
                bytes_freed += archived.size_bytes
                os.remove(archived.path)
                removed += 1
            except OSError as exc:
                error = f"Error borrando {archived.filename}: {exc}"

        results[svc] = {
            "removed": removed,
            "bytes_freed": bytes_freed,
            "error": error,
        }

    return results


def format_size(num_bytes: int) -> str:
    """Formatea bytes en KB/MB legibles."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
