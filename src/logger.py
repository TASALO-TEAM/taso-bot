"""Sistema de logging profesional para TASALO-Bot.

Características:
- Logging a consola con colores
- Logging a archivo con rotación (5 MB)
- Logging de errores separado (retención 30 días)
- Interceptación de excepciones no controladas
- Métodos específicos para eventos del bot
- Compatible con testing (sin archivos en tests)

Basado en la referencia: /home/ersus/bot/test/utils/logger.py
"""

import sys
import os
import logging
import traceback
from pathlib import Path
from typing import Optional, Union


# --- Configuración de Rutas ---
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_FILE_PATH = os.path.join(LOGS_DIR, "taso-bot.log")
ERROR_LOG_PATH = os.path.join(LOGS_DIR, "taso-bot-errors.log")

# Asegurar que la carpeta logs exista
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR, exist_ok=True)


class BotLogger:
    """Sistema de logging profesional con rotación y manejo de errores."""

    def __init__(self, enable_file_logging: bool = True):
        """
        Args:
            enable_file_logging: Si False, solo logging a consola (para tests)
        """
        self.enable_file_logging = enable_file_logging
        self.logger = logging.getLogger("taso-bot")

        # Configurar handlers
        self._setup_logger()

        # Interceptación de excepciones no controladas
        sys.excepthook = self._handle_unhandled_exception

    def _setup_logger(self):
        """Configura los handlers (Consola + Archivos)."""
        # Evitar duplicar handlers si se inicializa múltiples veces
        if self.logger.handlers:
            return

        # Nivel de logging (se puede sobrescribir desde main.py)
        self.logger.setLevel(logging.INFO)

        # Formatter para consola (más compacto)
        console_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Handler de Consola
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.INFO)
        self.logger.addHandler(console_handler)

        # Handlers de Archivo (solo si están habilitados)
        if self.enable_file_logging:
            # Handler de archivo principal con rotación
            from logging.handlers import RotatingFileHandler

            # Log principal (rotación 5 MB, 5 backups)
            file_handler = RotatingFileHandler(
                LOG_FILE_PATH,
                maxBytes=5 * 1024 * 1024,  # 5 MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            file_handler.setLevel(logging.DEBUG)
            self.logger.addHandler(file_handler)

            # Handler exclusivo para errores (retención extendida)
            error_handler = RotatingFileHandler(
                ERROR_LOG_PATH,
                maxBytes=5 * 1024 * 1024,  # 5 MB
                backupCount=10,
                encoding="utf-8",
            )
            error_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            error_handler.setLevel(logging.ERROR)
            self.logger.addHandler(error_handler)

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
        log_method(full_msg, **kwargs)

    def log_user_action(self, action: str, user_id: int, details: Optional[str] = None):
        """Ej: logger.log_user_action('start_bot', 123456)"""
        msg = f"User Action: {action}"
        if details:
            msg += f" - {details}"
        self.log_bot_event("INFO", msg, user_id)

    def log_command_execution(
        self, command: str, user_id: int, success: bool, duration_ms: Optional[float] = None
    ):
        """Log especializado para ejecución de comandos."""
        status = "✅" if success else "❌"
        msg = f"Command {command} {status}"
        if duration_ms is not None:
            msg += f" ({duration_ms:.0f}ms)"
        level = "INFO" if success else "ERROR"
        self.log_bot_event(level, msg, user_id)

    def log_api_call(
        self, endpoint: str, success: bool, status_code: Optional[int] = None
    ):
        """Log especializado para llamadas a la API."""
        status = "✅" if success else "❌"
        msg = f"API {endpoint} {status}"
        if status_code:
            msg += f" (HTTP {status_code})"
        level = "INFO" if success else "WARNING"
        self.log_bot_event(level, msg)

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
