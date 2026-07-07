"""Tests para el handler /help."""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, Message, User

from src.handlers.help import help_command


def _make_update(user_id: int = 123):
    user = User(id=user_id, first_name="User", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()
    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message
    return update, message


def _make_context(args):
    context = MagicMock()
    context.args = args
    context.bot_data = {"api_client": AsyncMock()}
    return context


@pytest.mark.asyncio
async def test_help_no_args_normal_user_shows_categories_no_admin_block():
    update, message = _make_update(user_id=999)
    context = _make_context([])

    with patch("src.handlers.help.is_admin", return_value=False):
        await help_command(update, context)

    text = message.reply_text.call_args[0][0]
    assert "Tasas de cambio" in text
    assert "Criptomonedas" in text
    assert "Trading" in text
    assert "Alertas" in text
    assert "Año" in text
    assert "Utilidades" in text
    assert "Administración" not in text

@pytest.mark.asyncio
async def test_help_no_args_admin_user_shows_admin_block():
    update, message = _make_update(user_id=123)
    context = _make_context([])

    with patch("src.handlers.help.is_admin", return_value=True):
        await help_command(update, context)

    text = message.reply_text.call_args[0][0]
    assert "Administración" in text


@pytest.mark.asyncio
async def test_help_topic_p_shows_detail():
    update, message = _make_update()
    context = _make_context(["p"])

    with patch("src.handlers.help.is_admin", return_value=False):
        await help_command(update, context)

    text = message.reply_text.call_args[0][0]
    assert "Uso:" in text
    assert "/p btc" in text


@pytest.mark.asyncio
async def test_help_topic_alias_resolves_same_as_real_topic():
    update1, message1 = _make_update()
    context1 = _make_context(["alertas"])
    update2, message2 = _make_update()
    context2 = _make_context(["alert"])

    with patch("src.handlers.help.is_admin", return_value=False):
        await help_command(update1, context1)
        await help_command(update2, context2)

    assert message1.reply_text.call_args[0][0] == message2.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_help_ads_normal_user_does_not_reveal_topic():
    update, message = _make_update()
    context = _make_context(["ads"])

    with patch("src.handlers.help.is_admin", return_value=False):
        await help_command(update, context)

    text = message.reply_text.call_args[0][0]
    assert "No encontré ayuda" in text


@pytest.mark.asyncio
async def test_help_ads_admin_user_gets_real_topic():
    update, message = _make_update()
    context = _make_context(["ads"])

    with patch("src.handlers.help.is_admin", return_value=True):
        await help_command(update, context)

    text = message.reply_text.call_args[0][0]
    assert "Gestión de anuncios" in text


@pytest.mark.asyncio
async def test_help_unknown_topic_shows_fallback():
    update, message = _make_update()
    context = _make_context(["topico-inexistente"])

    with patch("src.handlers.help.is_admin", return_value=False):
        await help_command(update, context)

    text = message.reply_text.call_args[0][0]
    assert "No encontré ayuda" in text
    assert "topico-inexistente" in text


@pytest.mark.asyncio
async def test_help_tracks_command_usage_once():
    update, message = _make_update()
    context = _make_context([])

    with patch("src.handlers.help.is_admin", return_value=False), \
         patch("src.handlers.help.track_command_usage", new_callable=AsyncMock) as mock_track:
        await help_command(update, context)
        await asyncio.sleep(0)  # deja correr la task creada por create_task

    mock_track.assert_called_once()
    assert mock_track.call_args[0][2] == "/help"
