"""Tests for year handler and API client."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from telegram import Update, User, Message, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.handlers.y import y_command, year_sub_callback
from src.api_client import TasaloApiClient


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_update(message_text: str = "/y", user_id: int = 12345):
    user = User(id=user_id, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()
    message.text = message_text
    message.from_user = user
    return Update(update_id=1, message=message)


def _make_callback_update(
    callback_data: str,
    user_id: int = 12345,
):
    user = User(id=user_id, is_bot=False, first_name="Test")
    query = MagicMock()
    query.data = callback_data
    query.answer = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    query.from_user = user
    query.message = MagicMock()
    return Update(update_id=2, callback_query=query)


@pytest.fixture
def mock_context():
    ctx = MagicMock(spec=ContextTypes)
    ctx.args = []
    return ctx


def _amock(ret):
    """Return an awaitable AsyncMock that resolves to *ret* when awaited."""
    return AsyncMock(return_value=ret)


# ── API client tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_year_quote_success():
    """add_year_quote envía POST con quote_text al endpoint admin."""
    client = TasaloApiClient(api_url="http://localhost:8040", admin_key="test-key")

    with patch.object(client, '_post_with_retry', return_value={"ok": True, "success": True, "is_duplicate": False, "index": 41, "context": {"current": 42, "limit": 365, "year": 2026, "is_extra": False}, "quote_id": 43}) as mock_post:
        result = await client.add_year_quote("Test quote")
        assert result is not None
        assert result.get("ok") is True
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/api/v1/year/quotes" in call_url


@pytest.mark.asyncio
async def test_add_year_quote_duplicate():
    """add_year_quote devuelve None cuando _post_with_retry retorna None."""
    client = TasaloApiClient(api_url="http://localhost:8040", admin_key="test-key")

    with patch.object(client, '_post_with_retry', return_value=None) as mock_post:
        result = await client.add_year_quote("Duplicado")
        assert result is None
        mock_post.assert_called_once()


# ── Handler tests ────────────────────────────────────────────────────────────

_MOCK_STATE = {
    "ok": True,
    "progress": {"year": 2026, "percent": 42.0, "days_left": 180, "date_str": "21/05/2026"},
    "quote": {"quote": "Test daily quote", "context": {"current": 142, "limit": 365, "year": 2026, "is_extra": False}},
    "stats": {"total": 365, "limit": 365, "current_index": 141, "has_reached_limit": False, "next_year_count": 0},
}


@pytest.mark.asyncio
async def test_y_command_quotes_stats_added():
    """y_command llama a get_year_state y envía mensaje con progreso + frase."""
    with patch("src.handlers.y._year_api") as mock_api:
        mock_api.get_year_state = _amock(_MOCK_STATE)
        mock_api.get_year_subscription = _amock(None)

        update = _make_update("/y")
        ctx = MagicMock(spec=ContextTypes)
        ctx.args = []
        await y_command(update, ctx)

        update.message.reply_text.assert_called()
        # Last call must be the year state message
        last_msg = update.message.reply_text.call_args[0][0]
        assert "ESTADO DEL AÑO 2026" in last_msg
        assert "Test daily quote" in last_msg
        assert update.message.reply_text.call_args[1]["parse_mode"] == "Markdown"
        assert isinstance(update.message.reply_text.call_args[1]["reply_markup"], InlineKeyboardMarkup)


@pytest.mark.asyncio
async def test_y_command_shows_subscription_buttons():
    """y_command incluye botones inline en el mensaje."""
    state = {
        "ok": True,
        "progress": {"year": 2026, "percent": 10.0, "days_left": 340, "date_str": "21/05/2026"},
        "quote": {"quote": "Quote", "context": {"current": 1, "limit": 365, "year": 2026, "is_extra": False}},
        "stats": {"total": 365, "limit": 365, "current_index": 0, "has_reached_limit": False, "next_year_count": 0},
    }
    with patch("src.handlers.y._year_api") as mock_api:
        mock_api.get_year_state = _amock(state)
        mock_api.get_year_subscription = _amock(None)

        update = _make_update("/y")
        ctx = MagicMock(spec=ContextTypes)
        ctx.args = []
        await y_command(update, ctx)

        reply_args = update.message.reply_text.call_args
        markup = reply_args[1]["reply_markup"]
        assert isinstance(markup, InlineKeyboardMarkup)
        buttons = [b for row in markup.inline_keyboard for b in row]
        assert any("year_sub_6" == b.callback_data for b in buttons)
        assert any("year_sub_off" == b.callback_data for b in buttons)


@pytest.mark.asyncio
async def test_y_command_api_failure():
    """y_command avisa cuando el API no responde."""
    with patch("src.handlers.y._year_api") as mock_api:
        mock_api.get_year_state = _amock(None)

        update = _make_update("/y")
        ctx = MagicMock(spec=ContextTypes)
        ctx.args = []
        await y_command(update, ctx)

        update.message.reply_text.assert_called()
        # Last call is the error message
        last = update.message.reply_text.call_args[0][0]
        assert "❌" in last



@pytest.mark.asyncio
async def test_y_command_add_mode_success():
    """y_command con /y add <text> llama a add_year_quote y muestra confirmación."""
    from datetime import datetime as dt
    today_day = dt.now().timetuple().tm_yday
    mock_add_result = {
        "ok": True,
        "success": True,
        "is_duplicate": False,
        "index": 130,
        "context": {"current": 132, "limit": 365, "year": 2026, "is_extra": False},
        "quote_id": 132,
    }
    with patch("src.handlers.y._year_api") as mock_api:
        mock_api.get_year_state = _amock(None)
        mock_api.get_year_subscription = _amock(None)
        mock_api.add_year_quote = _amock(mock_add_result)

        update = _make_update("/y add frase de prueba")
        ctx = MagicMock(spec=ContextTypes)
        ctx.args = ["add", "frase", "de", "prueba"]
        await y_command(update, ctx)

        mock_api.add_year_quote.assert_called_once_with("frase de prueba")
        update.message.reply_text.assert_called()
        # Last call is the confirmation message
        last = update.message.reply_text.call_args[0][0]
        assert "✅" in last
        assert "frase de prueba" in last
        assert f"Día #{today_day} de 365" in last  # actual calendar day, not quote position
        assert "#132" in last  # quote_id shown in header
        assert "Quedan 233 frases" in last  # 365 - 132 = 233


@pytest.mark.asyncio
async def test_y_command_add_mode_extra_year():
    """y_command /y add when year-in-progress is full: shows 'próximo año'."""
    mock_add_result = {
        "ok": True,
        "success": True,
        "is_duplicate": False,
        "index": 3,   # 4th quote lands on day 4 of next year
        "context": {"current": 3, "limit": 365, "year": 2026, "is_extra": True},
        "quote_id": 368,
    }
    with patch("src.handlers.y._year_api") as mock_api:
        mock_api.get_year_state = _amock(None)
        mock_api.get_year_subscription = _amock(None)
        mock_api.add_year_quote = _amock(mock_add_result)

        update = _make_update("/y add frase overflow")
        ctx = MagicMock(spec=ContextTypes)
        ctx.args = ["add", "frase", "overflow"]
        await y_command(update, ctx)

        mock_api.add_year_quote.assert_called_once_with("frase overflow")
        update.message.reply_text.assert_called()
        last = update.message.reply_text.call_args[0][0]
        assert "✅" in last
        assert "próximo año" in last
        assert "Día #3 de 365" in last
        assert "Quedan 362 frases" in last  # 365 - 3 = 362 (ctx_limit - ctx_slot for extra)


@pytest.mark.asyncio
async def test_y_command_add_duplicate():
    """y_command con /y add detecta frase duplicada."""
    with patch("src.handlers.y._year_api") as mock_api:
        mock_api.get_year_state = _amock(None)
        mock_api.get_year_subscription = _amock(None)
        mock_api.add_year_quote = _amock({
            "ok": False, "success": False, "is_duplicate": True,
            "status_code": 409,
        })

        update = _make_update("/y add ya existe")
        ctx = MagicMock(spec=ContextTypes)
        ctx.args = ["add", "ya", "existe"]
        await y_command(update, ctx)

        update.message.reply_text.assert_called()
        # Last call is the duplicate error
        last = update.message.reply_text.call_args[0][0]
        assert "ya existe" in last


@pytest.mark.asyncio
async def test_y_command_add_too_short():
    """y_command con /y add texto muy corto devuelve error de uso."""
    with patch("src.handlers.y._year_api") as mock_api:
        mock_api.get_year_state = _amock(None)
        mock_api.get_year_subscription = _amock(None)

        update = _make_update("/y add hi")
        ctx = MagicMock(spec=ContextTypes)
        ctx.args = ["hi"]
        await y_command(update, ctx)

        update.message.reply_text.assert_called_once()
        assert "⚠️" in update.message.reply_text.call_args[0][0]


# ── year_sub_callback tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_year_sub_callback_set_hour():
    """year_sub_callback activa suscripción al hacer clic en hora."""
    with patch("src.handlers.y._year_api") as mock_api:
        mock_api.admin_set_year_subscription = _amock({"ok": True, "user_id": 12345, "hour": 6})
        mock_api.get_year_subscription = _amock({"ok": True, "id": 1, "user_id": 12345, "hour": 6})

        update = _make_callback_update("year_sub_6")
        ctx = MagicMock(spec=ContextTypes)
        ctx.bot = MagicMock()
        ctx.bot.send_message = AsyncMock()
        await year_sub_callback(update, ctx)

        mock_api.admin_set_year_subscription.assert_called_once_with(12345, 6)


@pytest.mark.asyncio
async def test_year_sub_callback_off():
    """year_sub_callback desactiva suscripción al clicar off."""
    with patch("src.handlers.y._year_api") as mock_api:
        mock_api.admin_delete_year_subscription = _amock({"ok": True})
        mock_api.get_year_subscription = _amock(None)

        update = _make_callback_update("year_sub_off")
        ctx = MagicMock(spec=ContextTypes)
        ctx.bot = MagicMock()
        ctx.bot.send_message = AsyncMock()
        await year_sub_callback(update, ctx)

        mock_api.admin_delete_year_subscription.assert_called_once_with(12345)


@pytest.mark.asyncio
async def test_year_sub_callback_api_failure():
    """year_sub_callback responde con error visual si el API falla."""
    with patch("src.handlers.y._year_api") as mock_api:
        mock_api.admin_set_year_subscription = _amock(None)

        update = _make_callback_update("year_sub_9")
        ctx = MagicMock(spec=ContextTypes)
        await year_sub_callback(update, ctx)

        update.callback_query.answer.assert_called()
        # 2nd call is the error message from year_sub_callback
        assert update.callback_query.answer.call_count == 2
        assert update.callback_query.answer.call_args_list[1][0][0] == "❌ Error al guardar"
