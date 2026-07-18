"""Year module handler — /y command.

Shows year state (progress + daily quote + sub buttons).

Subcommands:
  /y add <frase>              — add a new quote
  /y del [id]                — delete a quote (id=1 locked; reindexes on delete)
  /y edit <id> <nueva_frase>  — edit a quote (id=1 locked)
  /y show [id] | /y show      — show a specific quote or current day quote

Consumes /api/v1/year/state, /api/v1/year/quotes/{id} from taso-api.
"""

import logging
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.api_client import TasaloApiClient
from src.config import get_settings
from src.services.ads_manager import get_ad_block, safe_append
from src.utils.permissions import is_admin

logger = logging.getLogger(__name__)
settings = get_settings()

_year_api = TasaloApiClient(
    api_url=settings.tasalo_api_url,
    admin_key=settings.tasalo_admin_key,
    timeout=30,
)

_hour_options = [
    (6, "🕕 6 AM"),
    (9, "🕘 9 AM"),
    (12, "🕛 12 PM"),
    (20, "🕗 8 PM"),
]


# ── Helpers ────────────────────────────────────────────────────────────────


async def _get_user_sub(user_id: int) -> dict | None:
    return await _year_api.get_year_subscription(user_id)


def _build_sub_keyboard(current_hour: int | None) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for hour, label in _hour_options:
        prefix = "✅ " if current_hour == hour else ""
        row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"year_sub_{hour}"))
    buttons.append(row)
    buttons.append([InlineKeyboardButton("⏰ Personalizar hora", callback_data="year_sub_custom")])
    buttons.append([InlineKeyboardButton("🔕 Desactivar Alerta Diaria", callback_data="year_sub_off")])
    return InlineKeyboardMarkup(buttons)


def _trunc(text: str, max_len: int = 120) -> str:
    return text if len(text) <= max_len else text[:max_len] + "..."


def _render_add_stats(ctx: dict, quote_text: str, slot: int, total: int, limit: int, quote_id: int) -> str:
    """Build the confirmation message for /y add with stats context.

    *ctx* comes from the API response and already carries the *target-year*
    values (``current``, ``limit``, ``year``, ``is_extra``).  When
    ``is_extra=True`` the year-in-progress is already full, so the quote
    landed in *next* year — ``ctx["year"]`` and ``ctx["limit"]`` reflect that
    target year, while ``ctx["current"]`` is the slot within it.

    *slot* and *limit* here are kept for backward compatibility but the
    canonical display values are taken from *ctx* to avoid off-by-one errors
    at year-boundary transitions.

    Remaining calculation uses ``quote_id`` (sequential position) for the
    current year, or ``ctx["current"]`` for overflow into the next year.

    ``day_of_year`` is ``None`` by default and will use the current system
    date to display today's calendar position.  For overflow (is_extra=True),
    the day shown is the quote's slot in the next year instead.
    """
    ctx_slot   = ctx.get("current", slot)
    ctx_limit  = ctx.get("limit",   limit)
    ctx_year   = ctx.get("year",    datetime.now().year)
    is_extra   = ctx.get("is_extra", False)
    if is_extra:
        remaining = max(0, ctx_limit - ctx_slot)
        day_display = ctx_slot
    else:
        remaining = max(0, ctx_limit - quote_id)
        day_display = datetime.now().timetuple().tm_yday
    label      = f"próximo año" if is_extra else f"año {ctx_year}"
    return (
        f"✅ *Frase añadida (#{quote_id})*\n"
        f"•••\n"
        f"💡 _{_trunc(quote_text)}_\n"
        f"👤 Día #{day_display} de {ctx_limit} del {label}\n"
        f"📊 *Quedan {remaining} frases* por agregar."
    )


# ── Commands ───────────────────────────────────────────────────────────────


async def y_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /y — year state + subcommands: add / show / edit / del."""
    user_id = update.effective_user.id
    logger.info("📅 /y invoked by user %s", user_id)
    args = context.args or []
    if not args:
        await _show_year_state(update, context, user_id)
        return

    sub = args[0].lower()

    if sub == "show":
        await _cmd_show(update, context, args[1:])
    elif sub in ("add", "edit", "del"):
        if not is_admin(user_id):
            await update.message.reply_text(
                "🔑 Este subcomando es solo para administradores."
            )
            return
        if sub == "add":
            await _cmd_add(update, context, args[1:])
        elif sub == "edit":
            await _cmd_edit(update, context, args[1:])
        else:
            await _cmd_del(update, context, args[1:])
    else:
        await update.message.reply_text(
            "⚠️ Subcomandos disponibles:\n"
            "`/y add <frase>` — agregar frase\n"
            "`/y show [id]`  — mostrar frase\n"
            "`/y edit <id> <nueva_frase>` — editar frase\n"
            "`/y del <id>`  — eliminar frase",
            parse_mode="Markdown",
        )


async def _show_year_state(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
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
    sub_data = await _get_user_sub(user_id)
    current_hour = sub_data.get("hour") if sub_data and sub_data.get("ok") else None
    keyboard = _build_sub_keyboard(current_hour)

    ad_block = await get_ad_block(_year_api)
    msg = safe_append(msg, ad_block)

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)


async def _cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE, extra_args: list):
    if not extra_args:
        await update.message.reply_text(
            "⚠️ Usa: `/y add <frase>`\nLa frase debe tener al menos 5 caracteres.",
            parse_mode="Markdown",
        )
        return
    quote_text = " ".join(extra_args).strip()
    if len(quote_text) < 5:
        await update.message.reply_text(
            "⚠️ La frase debe tener al menos 5 caracteres.",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text("📝 Añadiendo frase...")
    result = await _year_api.add_year_quote(quote_text)
    if not result or not result.get("ok"):
        code = result.get("status_code") if result else None
        if code == 409 or (result and result.get("success") is False):
            await update.message.reply_text("❌ Esa frase ya existe en el registro.")
        else:
            await update.message.reply_text("❌ Error añadiendo frase. Intenta más tarde.")
        return

    ctx = result.get("context", {})
    slot = result.get("index", ctx.get("current", 0))
    quote_id = result.get("quote_id", 0)
    total = max(0, quote_id - 1)  # frases de usuario agregadas hasta ahora (id 1 = Feliz año)
    await update.message.reply_text(
        _render_add_stats(ctx, quote_text, slot, total, ctx.get("limit", 365), quote_id),
        parse_mode="Markdown",
    )


async def _cmd_show(update: Update, context: ContextTypes.DEFAULT_TYPE, extra_args: list):
    """Show a specific quote by position id. No id → show day's quote."""
    if not extra_args:
        # Show today's
        await update.message.reply_text("📅 Cargando frase del día...")
        data = await _year_api.get_year_quote_today()
        if not data:
            await update.message.reply_text("❌ Error obteniendo frase del día.")
            return
        quote_text = data.get("quote", "—")
        ctx = data.get("context", {})
        slot = ctx.get("current", "—")
        year = ctx.get("year", "?")
        is_extra = ctx.get("is_extra", False)
        label = "📌 Próximo año" if is_extra else f"📌 Año {year}"
        await update.message.reply_text(
            f"💡 *Frase del día (día #{slot}, {label}):*\n"
            f'"{_trunc(quote_text, 200)}"',
            parse_mode="Markdown",
        )
        return

    try:
        quote_id = int(extra_args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Usa: `/y show [id]` — id debe ser un número.", parse_mode="Markdown")
        return

    await update.message.reply_text(f"🔍 Buscando frase #{quote_id}...")
    data = await _year_api.admin_get_year_quote(quote_id)
    if not data or not data.get("ok"):
        await update.message.reply_text(f"❌ Frase #{quote_id} no encontrada.")
        return

    quote_text = data.get("quote_text", "—")
    if data.get("is_greeting"):
        await update.message.reply_text(
            f"🔒 *Día 1 (bloqueado):*\n"
            f'"{_trunc(quote_text)}"',
            parse_mode="Markdown",
        )
        return

    created = data.get("created_at", "?")
    await update.message.reply_text(
        f"💡 *Frase #{quote_id}:*\n"
        f'"{_trunc(quote_text, 200)}"\n'
        f"🕐 Creada: {created}",
        parse_mode="Markdown",
    )


async def _cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, extra_args: list):
    """Edit quote: /y edit <id> <nueva_frase>."""
    if len(extra_args) < 2:
        await update.message.reply_text(
            "⚠️ Usa: `/y edit <id> <nueva_frase>`",
            parse_mode="Markdown",
        )
        return
    try:
        quote_id = int(extra_args[0])
    except ValueError:
        await update.message.reply_text("⚠️ El id debe ser un número.", parse_mode="Markdown")
        return
    new_text = " ".join(extra_args[1:]).strip()
    if len(new_text) < 5:
        await update.message.reply_text("⚠️ La nueva frase debe tener al menos 5 caracteres.", parse_mode="Markdown")
        return

    await update.message.reply_text(f"✏️ Editando frase #{quote_id}...")
    result = await _year_api.admin_edit_year_quote(quote_id, new_text)
    if not result or not result.get("ok"):
        err = (result or {}).get("detail", "Error desconocido")
        await update.message.reply_text(f"❌ No se pudo editar la frase #{quote_id}: {err}")
        return

    await update.message.reply_text(
        f"✅ *Frase #{quote_id} actualizada*\n•••\n"
        f'💡 *Nueva frase:* "{_trunc(new_text)}"',
        parse_mode="Markdown",
    )


async def _cmd_del(update: Update, context: ContextTypes.DEFAULT_TYPE, extra_args: list):
    """Delete quote position by id (id=1 locked). Reindexes afterward."""
    if not extra_args:
        await update.message.reply_text(
            "⚠️ Usa: `/y del <id>`\nEjemplo: `/y del 5`",
            parse_mode="Markdown",
        )
        return
    try:
        quote_id = int(extra_args[0])
    except ValueError:
        await update.message.reply_text("⚠️ El id debe ser un número.", parse_mode="Markdown")
        return

    # Fetch quote text before deleting for confirmation
    pre = await _year_api.admin_get_year_quote(quote_id)
    if not pre or not pre.get("ok"):
        await update.message.reply_text(f"❌ Frase #{quote_id} no encontrada.")
        return

    if pre.get("is_greeting"):
        await update.message.reply_text(
            "🔒 *Día 1 bloqueado*\n"
            "La frase 'Feliz año' no se puede eliminar.",
            parse_mode="Markdown",
        )
        return

    old_text = pre.get("quote_text", "—")

    await update.message.reply_text(f"🗑 Eliminando frase #{quote_id}...")
    result = await _year_api.admin_delete_year_quote(quote_id)
    if not result or not result.get("ok"):
        err = result.get("detail", "Error desconocido") if result else "Error de conexión"
        await update.message.reply_text(f"❌ No se pudo eliminar: {err}")
        return

    reindexed = result.get("reindexed", False)
    await update.message.reply_text(
        f"✅ *Frase eliminada*\n"
        f"•••\n"
        f"🗑 *#{quote_id} →* \"{_trunc(old_text)}\"\n"
        + (f"🔄 IDs reindexados correctamente." if reindexed else ""),
        parse_mode="Markdown",
    )


async def handle_year_hour_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry_time = context.user_data.get("awaiting_year_hour")
    if not entry_time:
        return
    expiry = time.time() - entry_time > 300
    if expiry:
        del context.user_data["awaiting_year_hour"]
        return
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not text.isdigit():
        del context.user_data["awaiting_year_hour"]
        await update.message.reply_text(
            "⚠️ Operación cancelada. Usa /y y selecciona ⏰ Personalizar hora para intentar de nuevo.",
        )
        return
    hour = int(text)
    if not (0 <= hour <= 23):
        await update.message.reply_text(
            "❌ Hora inválida. Usa un número entre 0 y 23 (UTC).\n"
            "Ejemplo: `9` para las 9:00 AM.",
            parse_mode="Markdown",
        )
        return
    del context.user_data["awaiting_year_hour"]
    await update.message.reply_text("⏳ Guardando alerta...")
    result = await _year_api.set_year_subscription(user_id, hour)
    if not result or not result.get("ok"):
        await update.message.reply_text("❌ Error al guardar la alerta. Intenta más tarde.")
        return
    await update.message.reply_text(
        f"✅ *Alerta diaria activada* a las {hour}:00 UTC.\n"
        "Usa /y para ver el estado y modificar la alerta.",
        parse_mode="Markdown",
    )


# year_sub_callback is defined below (line 340) and wired through callback_router.


# ── Callback handler ───────────────────────────────────────────────────────


async def year_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle year subscription button callbacks (year_sub_6, year_sub_9, etc.).

    NOTE: callback_router has already called ``query.answer()`` once
    (to dismiss the loading spinner) before routing here.  Never call
    ``query.answer()`` again — Guard branches may catch exceptions
    caused by a second call and silently swallow them, preventing
    the subscription API from ever executing.
    """
    query = update.callback_query
    user_id = query.from_user.id
    callback_data = query.data

    if callback_data == "year_sub_custom":
        context.user_data["awaiting_year_hour"] = time.time()
        await query.message.reply_text(
            "⏰ *Personalizar hora de alerta*\n\n"
            "Responde a este mensaje con la hora (0-23) en formato UTC "
            "a la que quieres recibir la alerta diaria del año.\n\n"
            "Ejemplos: `9` para las 9:00 AM, `14` para las 2:00 PM, `20` para las 8:00 PM.",
            parse_mode="Markdown",
        )
        return

    if callback_data == "year_sub_off":
        result = await _year_api.delete_year_subscription(user_id)
        if not result or not result.get("ok"):
            await query.answer("⚠️ No se pudo desactivar", show_alert=True)
            return
        await query.answer("🔕 Alerta diaria desactivada")
        try:
            await query.edit_message_reply_markup(reply_markup=_build_sub_keyboard(None))
        except BadRequest:
            pass
        return

    if callback_data.startswith("year_sub_"):
        try:
            hour = int(callback_data.split("_")[-1])
        except ValueError:
            return
        result = await _year_api.set_year_subscription(user_id, hour)
        if not result or not result.get("ok"):
            await query.answer("❌ Error al guardar", show_alert=True)
            return
        await query.answer(f"✅ Alerta activada a las {hour}:00 UTC")
        try:
            await query.edit_message_reply_markup(
                reply_markup=_build_sub_keyboard(hour)
            )
        except BadRequest:
            pass
        return

    raise ValueError(f"Unrecognised year callback: {callback_data}")

