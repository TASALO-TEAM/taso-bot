# utils/file_manager.py
# Stub providing add_log_line used by BBAlert handlers.

import logging

logger = logging.getLogger(__name__)

def add_log_line(linea: str) -> None:
    logger.info(linea)
