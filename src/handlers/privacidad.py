"""/privacidad (borrar mis datos) y /silencio (sin difusiones) — taso-bot#72 F5.

Ambos son publicos y actuan solo sobre quien pulsa el boton. El bot no guarda
nada propio por usuario: el borrado y el silencio viven en la API.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src import user_seen

_ERROR = "No pude hacerlo ahora mismo. Inténtalo de nuevo en un rato."


def _teclado(*botones: tuple[str, str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(texto, callback_data=data)] for texto, data in botones]
    )


async def privacidad_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🗑 Borrar mis datos\n\n"
        "Se borran tu registro, tus estadísticas de uso, tus alertas de precio e imagen "
        "y tus suscripciones (/tspl y /y). Tus tickets quedan anónimos.\n\n"
        "No es un bloqueo: si vuelves a escribirle al bot, te registra de nuevo.",
        reply_markup=_teclado(
            ("🗑 Sí, borrar mis datos", "privacidad:ok"),
            ("Cancelar", "privacidad:no"),
        ),
    )


async def privacidad_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    query = update.callback_query
    await query.answer()
    if data != "privacidad:ok":
        await query.edit_message_text("Listo, no se borró nada.")
        return

    user_id = query.from_user.id
    api = context.bot_data.get("api_client")
    result = await api.erase_user_data(user_id) if api else None
    if result is None:
        await query.edit_message_text(f"❌ {_ERROR} Tus datos siguen como estaban.")
        return

    # Sin esto el limitador de F1 creeria que el usuario sigue registrado.
    user_seen._last_sent.pop(user_id, None)
    await query.edit_message_text(
        "✅ Tus datos fueron borrados y tus tickets quedaron anónimos.\n\n"
        "Las copias de seguridad los conservan hasta que se roten."
    )


async def silencio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔕 Silencio\n\n"
        "Silenciado, no recibes los mensajes masivos de los administradores. "
        "Sigues recibiendo tus alertas, suscripciones y avisos de tickets.",
        reply_markup=_teclado(
            ("🔕 Silenciar difusiones", "silencio:on"),
            ("🔔 Reactivar difusiones", "silencio:off"),
        ),
    )


async def silencio_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    query = update.callback_query
    await query.answer()
    muted = data == "silencio:on"
    api = context.bot_data.get("api_client")
    ok = await api.set_user_muted(query.from_user.id, muted) if api else None
    if not ok:
        await query.edit_message_text(f"❌ {_ERROR}")
        return
    await query.edit_message_text(
        "🔕 Listo: no recibirás difusiones." if muted else "🔔 Listo: volverás a recibir difusiones."
    )
