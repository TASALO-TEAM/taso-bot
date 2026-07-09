"""Sistema de logging profesional para TASALO-Bot.

Características:
- Logging a consola con formato compacto y legible
- Logging a archivo con rotación (5 MB, 5 backups)
- Logging de errores separado (retención 10 backups)
- Interceptación de excepciones no controladas
- Métodos específicos para eventos del bot
- Soporte para contexto de request (user_id, command, etc.)
- Compatible con testing (sin archivos en tests)

Basado en la referencia: /home/ersus/bot/test/utils/logger.py
"""

import sys
import os
import time
import logging
import traceback
from pathlib import Path
from typing import Optional, Union, Dict, Any
from logging.handlers import RotatingFileHandler


# --- Configuración de Rutas ---
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
ARCHIVE_DIR = os.path.join(LOGS_DIR, "archive")
LOG_FILE_PATH = os.path.join(LOGS_DIR, "taso-bot.log")
ERROR_LOG_PATH = os.path.join(LOGS_DIR, "taso-bot-errors.log")

MAX_BYTES = 5 * 1024 * 1024  # 5 MB por archivo activo antes de rotar
BACKUP_COUNT = 10  # tope de seguridad de archivos rotados (además de /log clear)

# Asegurar que las carpetas de logs existan
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)


class DatedRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler que archiva por fecha de cierre en vez de sufijo numérico.

    Al superar `maxBytes`, el archivo activo se cierra y se mueve a
    `<archive_dir>/<service_name>_<timestamp>.log`. Se mantiene como máximo
    `backupCount` archivos por servicio en el directorio de archivo; los más
    viejos se eliminan automáticamente. El comando /log del bot puede así
    localizar y ofrecer un log viejo por su fecha de cierre.

    Nota: esta clase se duplica en taso-api y taso-app (repos independientes
    sin paquete compartido); mantenerlas en sync si se modifica el algoritmo.
    """

    def __init__(
        self,
        filename: str,
        service_name: str,
        archive_dir: Optional[str] = None,
        maxBytes: int = 0,
        backupCount: int = 0,
        encoding: Optional[str] = None,
        delay: bool = False,
    ):
        self.service_name = service_name
        base_dir = os.path.dirname(os.path.abspath(filename))
        self.archive_dir = archive_dir or os.path.join(base_dir, "archive")
        os.makedirs(self.archive_dir, exist_ok=True)
        super().__init__(
            filename,
            maxBytes=maxBytes,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
        )

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None

        if os.path.exists(self.baseFilename):
            archive_name = self._build_archive_name()
            try:
                os.rename(self.baseFilename, archive_name)
            except OSError:
                pass

        self._cleanup_old_archives()

        if not self.delay:
            self.stream = self._open()

    def _build_archive_name(self) -> str:
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        candidate = os.path.join(self.archive_dir, f"{self.service_name}_{timestamp}.log")
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(
                self.archive_dir, f"{self.service_name}_{timestamp}_{counter}.log"
            )
            counter += 1
        return candidate

    def _cleanup_old_archives(self):
        if self.backupCount <= 0:
            return
        try:
            prefix = f"{self.service_name}_"
            archives = sorted(
                (
                    f
                    for f in os.listdir(self.archive_dir)
                    if f.startswith(prefix) and f.endswith(".log")
                ),
                key=lambda f: os.path.getmtime(os.path.join(self.archive_dir, f)),
            )
            excess = len(archives) - self.backupCount
            for old_file in archives[: max(0, excess)]:
                os.remove(os.path.join(self.archive_dir, old_file))
        except OSError:
            pass


# --- Formatters ---

class ContextFormatter(logging.Formatter):
    """Formatter que enriquece logs con contexto del bot."""
    
    def format(self, record):
        # Agregar contexto personalizado si existe
        if hasattr(record, 'user_id'):
            record.user_context = f"[U:{record.user_id}]"
        elif hasattr(record, 'chat_id'):
            record.user_context = f"[C:{record.chat_id}]"
        else:
            record.user_context = ""
        
        return super().format(record)


def get_console_formatter() -> logging.Formatter:
    """Formatter compacto para consola."""
    return ContextFormatter(
        "%(asctime)s | %(levelname)-8s | %(name)s %(user_context)s| %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_file_formatter() -> logging.Formatter:
    """Formatter detallado para archivos (con función y línea)."""
    return ContextFormatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d %(user_context)s| %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


class BotLogger:
    """Sistema de logging profesional con rotación y manejo de errores."""

    def __init__(self, enable_file_logging: bool = True):
        """
        Args:
            enable_file_logging: Si False, solo logging a consola (para tests)
        """
        self.enable_file_logging = enable_file_logging
        # ROOT logger (name=""), no "taso-bot": todo modulo usa
        # logging.getLogger(__name__) (p.ej. "src.handlers.tkt"), que por
        # jerarquia de logging NO es hijo de un logger llamado "taso-bot" -
        # solo propaga hasta la raiz. Si los handlers se cuelgan de un
        # logger nombrado, los logs de cualquier modulo desaparecen sin
        # error (bug real detectado: 0 lineas de src.handlers.* en
        # produccion pese a actividad real). Colgando los handlers de la
        # raiz, CUALQUIER logger de la app los alcanza vía propagacion,
        # conservando su propio nombre en %(name)s.
        self.logger = logging.getLogger()

        # Configurar handlers
        self._setup_logger()

        # Interceptación de excepciones no controladas
        sys.excepthook = self._handle_unhandled_exception

    def _setup_logger(self):
        """Configura los handlers (Consola + Archivos)."""
        # Limpiar handlers existentes para evitar duplicados
        self.logger.handlers = []

        # Nivel de logging (se puede sobrescribir desde main.py)
        self.logger.setLevel(logging.DEBUG)  # DEBUG para capturar todo; handlers filtran

        # Handler de Consola
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(get_console_formatter())
        console_handler.setLevel(logging.INFO)
        self.logger.addHandler(console_handler)

        # Handlers de Archivo (solo si están habilitados)
        if self.enable_file_logging:
            # Log principal (rotación 5 MB, archivado por fecha)
            file_handler = DatedRotatingFileHandler(
                LOG_FILE_PATH,
                service_name="taso-bot",
                archive_dir=ARCHIVE_DIR,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(get_file_formatter())
            file_handler.setLevel(logging.DEBUG)
            self.logger.addHandler(file_handler)

            # Handler exclusivo para errores (retención extendida)
            error_handler = DatedRotatingFileHandler(
                ERROR_LOG_PATH,
                service_name="taso-bot-errors",
                archive_dir=ARCHIVE_DIR,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            )
            error_handler.setFormatter(get_file_formatter())
            error_handler.setLevel(logging.ERROR)
            self.logger.addHandler(error_handler)

            # Log de confirmación
            self.logger.info("✅ File logging enabled: %s", LOG_FILE_PATH)
            self.logger.info("✅ Error logging enabled: %s", ERROR_LOG_PATH)

    def _handle_unhandled_exception(self, exc_type, exc_value, exc_traceback):
        """Intercepta errores no controlados antes de que el bot muera."""
        # Ignorar interrupciones de teclado (Ctrl+C)
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Extraer información del error
        tb_summary = traceback.extract_tb(exc_traceback)
        if tb_summary:
            last_frame = tb_summary[-1]
            file_name = os.path.basename(last_frame.filename)
            line_no = last_frame.lineno
            func_name = last_frame.name
            code_line = last_frame.line
        else:
            file_name = "Desconocido"
            line_no = "?"
            func_name = "?"
            code_line = "No info"

        # Loguear crash
        crash_msg = (
            f"🛑 CRASH NO CONTROLADO\n"
            f"   📂 Archivo: {file_name} | Línea: {line_no}\n"
            f"   ⚙️ Función: {func_name}\n"
            f"   👉 Código:  {code_line}\n"
            f"   ❌ Error:   {exc_type.__name__}: {str(exc_value)}"
        )

        self.error(crash_msg, exc_info=exc_value)

        # Llamar al excepthook original
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    # --- Métodos de Logging ---

    def debug(self, message: str, *args, **kwargs):
        self.logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs):
        self.logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        self.logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args, exc_info=None, **kwargs):
        """Log de error con soporte opcional de excepción."""
        self.logger.error(message, *args, exc_info=exc_info, **kwargs)

    def critical(self, message: str, *args, **kwargs):
        self.logger.critical(message, *args, **kwargs)

    # --- Métodos Específicos del Bot ---

    def log_bot_event(
        self, level: str, message: str, user_id: Optional[int] = None, **kwargs
    ):
        """Registra un evento específico del bot."""
        log_method = getattr(self, level.lower(), self.info)
        extra_info = f"[User:{user_id}]" if user_id else ""
        full_msg = f"{extra_info} {message}".strip()
        log_method(full_msg, extra={"user_id": user_id} if user_id else {}, **kwargs)

    def log_user_action(self, action: str, user_id: int, details: Optional[str] = None):
        """Log action de usuario con contexto completo."""
        msg = f"User Action: {action}"
        if details:
            msg += f" | {details}"
        self.log_bot_event("INFO", msg, user_id)

    def log_command_execution(
        self, command: str, user_id: int, success: bool, duration_ms: Optional[float] = None,
        username: Optional[str] = None, error: Optional[str] = None
    ):
        """Log completo de ejecución de comando con todo el contexto."""
        status = "✅" if success else "❌"
        msg = f"Command {command} {status}"
        if duration_ms is not None:
            msg += f" ({duration_ms:.0f}ms)"
        if username:
            msg += f" | @{username}"
        if error:
            msg += f" | Error: {error}"
        
        level = "INFO" if success else "ERROR"
        self.log_bot_event(level, msg, user_id)

    def log_api_call(
        self, endpoint: str, success: bool, status_code: Optional[int] = None,
        duration_ms: Optional[float] = None, error: Optional[str] = None,
        retry_count: int = 0
    ):
        """Log completo de llamada a API con métricas."""
        status = "✅" if success else "❌"
        msg = f"API {endpoint} {status}"
        if status_code:
            msg += f" (HTTP {status_code})"
        if duration_ms is not None:
            msg += f" ({duration_ms:.0f}ms)"
        if retry_count > 0:
            msg += f" | {retry_count} retries"
        if error:
            msg += f" | Error: {error}"
        
        level = "INFO" if success else "WARNING"
        self.log_bot_event(level, msg)

    def log_callback_event(
        self, callback_data: str, user_id: int, success: bool,
        duration_ms: Optional[float] = None, handler: Optional[str] = None,
        error: Optional[str] = None
    ):
        """Log de procesamiento de callback con contexto completo."""
        status = "✅" if success else "❌"
        msg = f"Callback {callback_data} {status}"
        if handler:
            msg += f" | Handler: {handler}"
        if duration_ms is not None:
            msg += f" ({duration_ms:.0f}ms)"
        if error:
            msg += f" | Error: {error}"
        
        level = "INFO" if success else "ERROR"
        self.log_bot_event(level, msg, user_id)

    def log_cache_event(
        self, action: str, key: str, hit: bool, ttl: Optional[int] = None
    ):
        """Log de operaciones de cache."""
        status = "HIT" if hit else "MISS"
        msg = f"Cache {action} {key} [{status}]"
        if ttl is not None:
            msg += f" (TTL={ttl}s)"
        level = "DEBUG" if hit else "INFO"
        self.debug(msg) if level == "DEBUG" else self.info(msg)

    def get_last_logs(self, lines: int = 15) -> str:
        """Devuelve las últimas líneas del archivo de log."""
        if not self.enable_file_logging or not os.path.exists(LOG_FILE_PATH):
            return "📂 El archivo de log no existe o está deshabilitado."
        try:
            with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        except Exception as e:
            return f"❌ Error leyendo logs: {str(e)}"


# --- Instancia Global ---
# enable_file_logging=False por defecto para tests
# main.py puede crear su propia instancia con file logging habilitado
logger = BotLogger(enable_file_logging=False)


def get_logger(name: str) -> logging.Logger:
    """Obtiene un logger estándar para un módulo.
    
    Los handlers se configuran en main.py con BotLogger, así que
    los loggers de módulos heredan esa configuración.
    
    Args:
        name: Nombre del módulo (típicamente __name__)
    
    Returns:
        Logger configurado para el módulo
    """
    return logging.getLogger(name)


def get_bot_logger() -> BotLogger:
    """Obtiene la instancia global de BotLogger con métodos especializados.
    
    Útil para llamar métodos como log_command_execution, log_api_call, etc.
    
    Returns:
        Instancia global de BotLogger
    """
    return logger
