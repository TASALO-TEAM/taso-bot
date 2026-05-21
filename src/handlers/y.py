"""Year module handler — /y command.

Shows year progress + daily quote. Consumes /api/v1/year/state from taso-api.
Includes subscription inline buttons and toggle callback.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.api_client import TasaloApiClient
from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_year_api = TasaloApiClient(
    api_url=settings.tasalo_api_url,
    timeout=30,
)

_hour_options = [
    (6, "🕕 6 AM"),
    (9, "🕘 9 AM"),
    (12, "🕛 12 PM"),
    (20, "🕗 8 PM"),
]


async def _get_user_sub(user_id: int) -> dict | None:
    return await _year_api.get_year_subscription(user_id)


def _build_sub_keyboard(current_hour: int | None) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for hour, label in _hour_options:
        prefix = "✅ " if current_hour == hour else ""
        row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"year_sub_{hour}"))
    buttons.append(row)
    buttons.append([InlineKeyboardButton("🔕 Desactivar Alerta Diaria", callback_data="year_sub_off")])
    return InlineKeyboardMarkup(buttons)


async def y_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /y — show year state (progress bar + daily quote + sub buttons)."""
    user_id = update.effective_user.id
    logger.info("📅 /y invoked by user %s", user_id)

    await update.message.reply_text("📅 Cargando estado del año...")

    data = await _year_api.get_year_state()
    if not data:
        await update.message.reply_text("❌ No se pudo obtener el estado del año. Intenta más tarde.")
        return

    progress = data.get("progress", {})
    quote_data = data.get("quote", {})

    year = progress.get("year")
    date_str = progress.get("date_str", "")
    percent = progress.get("percent", 0.0)
    days_left = progress.get("days_left", 0)
    bar = "▓" * int(20 * percent // 100) + "░" * (20 - int(20 * percent // 100))
    mood = (
        "🍀 Recién estamos empezando..." if percent < 2
        else "🌱 Arrancando motores..." if percent < 10
        else "🏃‍♂️ Aún hay tiempo de cumplir propósitos." if percent < 50
        else "🔥 ¡Se nos va el año!" if percent < 80
        else "🏁 Recta final, ¡agárrate!"
    )
    quote_text = quote_data.get("quote", "⏳ El tiempo vuela, pero tú eres el piloto.")

    msg = (
        f"🗓 *ESTADO DEL AÑO {year}*\n"
        f"•••\n"
        f"📆 *Fecha:* {date_str}\n"
        f"⏳ *Progreso:* `{percent:.2f}%`\n"
        f"📊 `{bar}`\n\n"
        f"🔚 Faltan *{days_left} días* para {year + 1}.\n"
        f"💭 {mood}\n"
        f"•••\n"
        f"💡 *Frase Del Día:*\n"
        f'"{quote_text}"'
    )

    # Check subscription status for button states
    sub_data = await _get_user_sub(user_id)
    current_hour = sub_data.get("hour") if sub_data and sub_data.get("ok") else None

    keyboard = _build_sub_keyboard(current_hour)
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)


async def year_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle year subscription button callbacks (year_sub_6, year_sub_9, etc.)."""
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    callback_data = query.data  # e.g. "year_sub_6" or "year_sub_off"

    if callback_data == "year_sub_off":
        result = await _year_api.admin_delete_year_subscription(user_id)
        if result and result.get("ok"):
            logger.info("✅ Year subscription removed for user %s", user_id)
            await query.edit_message_reply_markup(reply_markup=_build_sub_keyboard(None))
            try:
                await query.answer("✅ Alerta desactivada")
            except Exception:
                pass
        else:
            try:
                await query.answer("⚠️ No tenías alerta activa", show_alert=True)
            except Exception:
                pass
        return

    if callback_data.startswith("year_sub_"):
        try:
            hour = int(callback_data.split("_")[-1])
        except ValueError:
            try:
                await query.answer("⚠️ Opción inválida", show_alert=True)
            except Exception:
                pass
            return

        result = await _year_api.admin_set_year_subscription(user_id, hour)
        if result and result.get("ok"):
            logger.info("✅ Year subscription set for user %s → hour %s", user_id, hour)
            await query.edit_message_reply_markup(reply_markup=_build_sub_keyboard(hour))
            try:
                await query.answer(f"✅ Alerta activada para las {hour:02d}:00 UTC")
            except Exception:
                pass
        else:
            try:
                await query.answer("❌ Error al guardar", show_alert=True)
            except Exception:
                pass
        return

    try:
        await query.answer("⚠️ Acción no reconocida", show_alert=True)
    except Exception:
        pass
