"""Registro automatico de usuarios en la API (taso-bot#72, Fase 1).

Un TypeHandler en su propio grupo previo avisa a la API de que el usuario
existe, para que /ms lo alcance aunque solo use /start, el explorador o botones.
No sustituye a track_command_usage: no cuenta como comando.
"""

import logging
import time
from typing import Dict

from telegram import Update
from telegram.ext import ContextTypes, TypeHandler

logger = logging.getLogger(__name__)

GROUP = -10  # antes que pick (-2) y el explorador (-1); los grupos corren todos
RESEND_SECONDS = 3600  # como maximo una vez por hora por usuario

# shortcut: dict en memoria sin purga (un int por usuario) y se pierde al reiniciar;
# subir a un TTL cache si los usuarios pasan de cientos de miles.
# shortcut: se marca ANTES de llamar, asi una API caida no recibe una peticion por
# mensaje; el usuario se registra en su siguiente interaccion pasada la hora.
_last_sent: Dict[int, float] = {}


async def mark_seen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    # my_chat_member llega cuando alguien bloquea el bot: no es actividad.
    if user is None or user.is_bot or update.my_chat_member is not None:
        return

    now = time.monotonic()
    if now - _last_sent.get(user.id, -RESEND_SECONDS) < RESEND_SECONDS:
        return
    _last_sent[user.id] = now

    api_client = context.bot_data.get("api_client")
    if api_client is None:
        return
    await api_client.mark_user_seen(
        user_id=user.id, username=user.username, first_name=user.first_name
    )


def register(app) -> None:
    # block=False: la llamada a la API (hasta 5 s) no retrasa la respuesta al usuario.
    app.add_handler(TypeHandler(Update, mark_seen, block=False), group=GROUP)
