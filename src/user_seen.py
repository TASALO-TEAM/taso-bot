"""Registro automatico de usuarios en la API (taso-bot#72, Fases 1 y 2).

Un TypeHandler en su propio grupo previo avisa a la API de que el usuario
existe, para que /ms lo alcance aunque solo use /start, el explorador o botones.
No sustituye a track_command_usage: no cuenta como comando.
Un ChatMemberHandler marca si el usuario bloqueo el bot (inalcanzable) o lo desbloqueo.
"""

import logging
import time
from typing import Dict

from telegram import ChatMember, Update
from telegram.ext import ChatMemberHandler, ContextTypes, TypeHandler

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
    # Confirmar /privacidad no cuenta como actividad: recrearia al usuario recien borrado.
    query = update.callback_query
    if query is not None and isinstance(query.data, str) and query.data == "privacidad:ok":
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


async def track_reachability(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    change = update.my_chat_member
    # En un grupo o canal, que echen al bot no dice nada de ningun usuario.
    if change.chat.type != "private":
        return

    api_client = context.bot_data.get("api_client")
    if api_client is None:
        return
    # En un chat privado solo hay dos estados: "kicked" (bloqueo) y "member" (desbloqueo).
    await api_client.set_user_reachability(
        user_id=change.chat.id,
        reachable=change.new_chat_member.status != ChatMember.BANNED,
    )


def register(app) -> None:
    # block=False: la llamada a la API (hasta 5 s) no retrasa la respuesta al usuario.
    app.add_handler(TypeHandler(Update, mark_seen, block=False), group=GROUP)
    app.add_handler(
        ChatMemberHandler(track_reachability, ChatMemberHandler.MY_CHAT_MEMBER, block=False)
    )
