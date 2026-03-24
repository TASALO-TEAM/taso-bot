"""Utilidades para tracking de estadísticas del bot.

Módulo responsable de proveer funciones para trackear
el uso de comandos de forma asíncrona y no bloqueante.
"""

import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from src.api_client import TasaloApiClient

logger = logging.getLogger(__name__)


async def track_command_usage(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    command: str,
    source: Optional[str] = None,
    success: bool = True,
) -> None:
    """
    Registra el uso de un comando en la API para estadísticas.

    Esta función es asíncrona y no bloqueante - si falla, solo loguea
    en debug pero no afecta el funcionamiento del comando.

    Args:
        update: Update de Telegram
        context: Contexto del bot (debe contener api_client en bot_data)
        command: Nombre del comando (ej: "/tasalo", "/toque")
        source: Fuente consultada si aplica (ej: "eltoque", "bcc")
        success: Si el comando se ejecutó con éxito
    """
    try:
        api_client: Optional[TasaloApiClient] = context.bot_data.get("api_client")
        
        if not api_client:
            logger.debug("⚠️ No hay api_client disponible para tracking")
            return

        user = update.effective_user
        user_id = user.id if user else 0
        username = user.username if user else None

        # Trackear comando (fire-and-forget, no bloquea)
        await api_client.track_command(
            command=command,
            user_id=user_id,
            username=username,
            source=source,
            success=success,
        )
    except Exception as e:
        # Silencioso - el tracking nunca debe afectar el bot
        logger.debug(f"⚠️ Error en track_command_usage: {e}")
