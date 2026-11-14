# tests/test_p_handler.py
"""Tests de los callbacks y el teclado de /p (refresh, TA, Panorama IA, alerta)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User

from src.handlers.p import p_refresh_callback, _build_keyboard


def _make_callback_update(callback_data: str, user_id: int = 12345):
    user = User(id=user_id, is_bot=False, first_name="Test")
    query = MagicMock()
    query.data = callback_data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user = user
    return Update(update_id=1, callback_query=query)


def test_build_keyboard_botones_y_callbacks():
    keyboard = _build_keyboard("BTC")
    callback_datas = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert callback_datas == [
        "p_refresh_BTC",
        "ta_quick|BTC|4h",
        "ai_panorama|BTC",
        "alert_hint|BTC",
    ]


@pytest.mark.asyncio
async def test_p_refresh_reejecuta_p_command_con_el_simbolo():
    update = _make_callback_update("p_refresh_btc")
    ctx = MagicMock()

    with patch("src.handlers.p.p_command", new=AsyncMock()) as mock_cmd:
        await p_refresh_callback(update, ctx)

    assert ctx.args == ["BTC"]
    mock_cmd.assert_awaited_once_with(update, ctx)


@pytest.mark.asyncio
async def test_p_refresh_simbolo_invalido_avisa_con_alert():
    update = _make_callback_update("p_refresh_")
    ctx = MagicMock()

    with patch("src.handlers.p.p_command", new=AsyncMock()) as mock_cmd:
        await p_refresh_callback(update, ctx)

    update.callback_query.answer.assert_called_once()
    assert update.callback_query.answer.call_args.kwargs.get("show_alert") is True
    mock_cmd.assert_not_called()
