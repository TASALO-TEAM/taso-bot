"""Clasificacion de errores de Telegram al enviar a un chat."""

from telegram.error import BadRequest, Forbidden


def chat_inaccesible(exc: BaseException) -> bool:
    """True si el chat ya no existe o no admite mensajes del bot (bloqueo, baja, expulsion).

    Otros BadRequest (p. ej. Markdown invalido) no cuentan: esos si son bugs.
    """
    if isinstance(exc, Forbidden):
        return True
    return isinstance(exc, BadRequest) and "chat not found" in str(exc).lower()
