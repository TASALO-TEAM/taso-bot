# src/utils/file_manager.py
# Minimal stub providing add_log_line() used by BBAlert handlers.
import logging

logger = logging.getLogger(__name__)

def add_log_line(linea: str) -> None:
    """Log a line using the standard Python logging system."""
    # BBAlert also stores in an in-memory list; not needed here.
    logger.info(linea)
