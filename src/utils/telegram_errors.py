"""Clasificacion de errores de Telegram al enviar a un chat."""

from telegram.error import BadRequest, Forbidden


def chat_no_existe(exc: BaseException) -> bool:
    """True solo si Telegram dice que el chat no existe (permanente: se puede desactivar)."""
    return isinstance(exc, BadRequest) and "chat not found" in str(exc).lower()


def chat_inaccesible(exc: BaseException) -> bool:
    """True si el chat no existe o no admite mensajes del bot (bloqueo, baja, expulsion).

    Otros BadRequest (p. ej. Markdown invalido) no cuentan: esos si son bugs.
    Forbidden es recuperable (el usuario puede desbloquear): solo se omite, no se desactiva.
    """
    return isinstance(exc, Forbidden) or chat_no_existe(exc)
