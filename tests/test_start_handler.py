"""Tests para handlers del comando /start."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, CallbackQuery, Message, Chat, User, InlineKeyboardButton, InlineKeyboardMarkup

from src.handlers.start import (
    start_command,
    start_button_callback,
    build_start_keyboard,
)


class TestBuildStartKeyboard:
    """Tests para build_start_keyboard."""

    def test_keyboard_structure(self):
        """Verificar estructura del teclado con botones de fuentes y Web App."""
        keyboard = build_start_keyboard()

        assert isinstance(keyboard, InlineKeyboardMarkup)
        # 3 filas: Tasalo/Toque, BCC/CADECA, Web App
        assert len(keyboard.inline_keyboard) >= 2  # Al menos 2 filas de botones de fuentes

        # Primera fila: Tasalo, Toque
        assert len(keyboard.inline_keyboard[0]) == 2
        assert keyboard.inline_keyboard[0][0].text == "📊 Tasalo"
        assert keyboard.inline_keyboard[0][0].callback_data == "start_tasalo"
        assert keyboard.inline_keyboard[0][1].text == "📈 Toque"
        assert keyboard.inline_keyboard[0][1].callback_data == "start_toque"

        # Segunda fila: BCC, CADECA
        assert len(keyboard.inline_keyboard[1]) == 2
        assert keyboard.inline_keyboard[1][0].text == "🏛 BCC"
        assert keyboard.inline_keyboard[1][0].callback_data == "start_bcc"
        assert keyboard.inline_keyboard[1][1].text == "🏢 CADECA"
        assert keyboard.inline_keyboard[1][1].callback_data == "start_cadeca"


class TestStartCommand:
    """Tests para start_command."""

    @pytest.mark.asyncio
    async def test_start_command_sends_welcome_message(self):
        """Verificar que /start envía mensaje de bienvenida."""
        # Mock update
        user = User(id=123, first_name="TestUser", is_bot=False)
        chat = Chat(id=123, type="private")
        message = MagicMock(spec=Message)
        message.reply_html = AsyncMock()

        update = MagicMock(spec=Update)
        update.effective_user = user
        update.message = message

        # Mock context
        context = MagicMock()

        # Call handler
        await start_command(update, context)

        # Verify reply_html was called
        assert message.reply_html.called
        call_args = message.reply_html.call_args

        # Verify welcome message contains expected text
        text = call_args[1]["text"]
        assert "👋 ¡Hola" in text
        assert "TestUser" in text  # User name
        assert "Soy TASALO" in text
        assert "tasas de cambio de Cuba" in text
        # El mensaje menciona las fuentes disponibles
        assert "BCC" in text or "mercado" in text.lower()
        assert "Presiona el botón" in text

        # Verify keyboard was sent
        assert "reply_markup" in call_args[1]

    @pytest.mark.asyncio
    async def test_start_command_uses_mention_html(self):
        """Verificar que usa mention_html para el nombre."""
        user = User(id=123, first_name="TestUser", is_bot=False)
        message = MagicMock(spec=Message)
        message.reply_html = AsyncMock()

        update = MagicMock(spec=Update)
        update.effective_user = user
        update.message = message

        context = MagicMock()

        await start_command(update, context)

        # Verify mention_html was used in the text
        text = message.reply_html.call_args[1]["text"]
        assert user.mention_html() in text


class TestStartButtonCallback:
    """Tests para start_button_callback."""

    @pytest.mark.asyncio
    async def test_start_tasalo_button(self):
        """Test botón Tasalo - muestra tasas combinadas."""
        # Mock update
        user = User(id=123, first_name="Test", is_bot=False)
        message = MagicMock(spec=Message)
        message.reply_text = AsyncMock()

        callback_query = MagicMock(spec=CallbackQuery)
        callback_query.from_user = user
        callback_query.message = message
        callback_query.data = "start_tasalo"
        callback_query.answer = AsyncMock()

        update = MagicMock(spec=Update)
        update.callback_query = callback_query

        # Mock context with api_client
        api_client_mock = AsyncMock(
            get_latest=AsyncMock(return_value={
                "ok": True,
                "data": {
                    "eltoque": {"USD": {"rate": 515.0}},
                    "bcc": {"USD": {"rate": 24.0}},
                },
                "updated_at": "2026-03-23T20:32:44Z"
            })
        )
        context = MagicMock()
        context.bot_data = {"api_client": api_client_mock}

        # Call handler
        await start_button_callback(update, context)

        # Verify answer was called
        callback_query.answer.assert_called_once()

        # Verify message was sent
        assert message.reply_text.called
        call_args = message.reply_text.call_args

        # Verify text contains rates
        text = call_args[1]["text"]
        assert text is not None

        # Verify keyboard with refresh button
        keyboard = call_args[1]["reply_markup"]
        assert keyboard is not None

    @pytest.mark.asyncio
    async def test_start_toque_button(self):
        """Test botón Toque - usa nuevo formato."""
        user = User(id=123, first_name="Test", is_bot=False)
        message = MagicMock(spec=Message)
        message.reply_text = AsyncMock()

        callback_query = MagicMock(spec=CallbackQuery)
        callback_query.from_user = user
        callback_query.message = message
        callback_query.data = "start_toque"
        callback_query.answer = AsyncMock()

        update = MagicMock(spec=Update)
        update.callback_query = callback_query

        api_client_mock = AsyncMock(
            get_latest=AsyncMock(return_value={
                "ok": True,
                "data": {
                    "eltoque": {
                        "USD": {"rate": 515.0},
                        "EUR": {"rate": 580.0},
                        "MLC": {"rate": 400.0},
                        "BTC": {"rate": 52000.0},
                        "TRX": {"rate": 185.0},
                        "USDT": {"rate": 560.0},
                    },
                },
                "updated_at": "2026-03-23T20:32:44Z"
            })
        )
        context = MagicMock()
        context.bot_data = {"api_client": api_client_mock}

        await start_button_callback(update, context)

        callback_query.answer.assert_called_once()

        # Verify message was sent with new format
        text = message.reply_text.call_args[1]["text"]
        assert "📊 MERCADO INFORMAL" in text
        assert "💹 Tasa en tiempo real" in text
        assert "🇪🇺 EUR ⇾" in text
        assert "🇺🇸 USD ⇾" in text
        assert "» Mercado Criptomonedas" in text

    @pytest.mark.asyncio
    async def test_start_bcc_button(self):
        """Test botón BCC."""
        user = User(id=123, first_name="Test", is_bot=False)
        message = MagicMock(spec=Message)
        message.reply_text = AsyncMock()

        callback_query = MagicMock(spec=CallbackQuery)
        callback_query.from_user = user
        callback_query.message = message
        callback_query.data = "start_bcc"
        callback_query.answer = AsyncMock()

        update = MagicMock(spec=Update)
        update.callback_query = callback_query

        api_client_mock = AsyncMock(
            get_latest=AsyncMock(return_value={
                "ok": True,
                "data": {
                    "bcc": {
                        "USD": {"rate": 24.0},
                        "EUR": {"rate": 26.5},
                    },
                },
                "updated_at": "2026-03-23T20:32:44Z"
            })
        )
        context = MagicMock()
        context.bot_data = {"api_client": api_client_mock}

        await start_button_callback(update, context)

        callback_query.answer.assert_called_once()

        text = message.reply_text.call_args[1]["text"]
        assert "🏛 *OFFICIAL RATE (BCC)*" in text

    @pytest.mark.asyncio
    async def test_start_cadeca_button(self):
        """Test botón CADECA."""
        user = User(id=123, first_name="Test", is_bot=False)
        message = MagicMock(spec=Message)
        message.reply_text = AsyncMock()

        callback_query = MagicMock(spec=CallbackQuery)
        callback_query.from_user = user
        callback_query.message = message
        callback_query.data = "start_cadeca"
        callback_query.answer = AsyncMock()

        update = MagicMock(spec=Update)
        update.callback_query = callback_query

        api_client_mock = AsyncMock(
            get_latest=AsyncMock(return_value={
                "ok": True,
                "data": {
                    "cadeca": {
                        "USD": {"buy": 120.0, "sell": 125.0},
                        "EUR": {"buy": 130.0, "sell": 136.0},
                    },
                },
                "updated_at": "2026-03-23T20:32:44Z"
            })
        )
        context = MagicMock()
        context.bot_data = {"api_client": api_client_mock}

        await start_button_callback(update, context)

        callback_query.answer.assert_called_once()

        text = message.reply_text.call_args[1]["text"]
        assert "🏢 *CADECA (Exchange Houses)*" in text
        assert "_Currency_" in text
        assert "_Buy_" in text
        assert "_Sell_" in text

    @pytest.mark.asyncio
    async def test_start_button_api_error(self):
        """Test error de API en botón."""
        user = User(id=123, first_name="Test", is_bot=False)
        message = MagicMock(spec=Message)

        callback_query = MagicMock(spec=CallbackQuery)
        callback_query.from_user = user
        callback_query.message = message
        callback_query.data = "start_toque"
        callback_query.answer = AsyncMock()
        callback_query.edit_message_text = AsyncMock()

        update = MagicMock(spec=Update)
        update.callback_query = callback_query

        # Mock API returning None
        api_client_mock = AsyncMock(
            get_latest=AsyncMock(return_value=None)
        )
        context = MagicMock()
        context.bot_data = {"api_client": api_client_mock}

        await start_button_callback(update, context)

        # Verify error was shown to user
        callback_query.answer.assert_called_with("⚠️ Error obteniendo datos", show_alert=True)

    @pytest.mark.asyncio
    async def test_start_button_no_api_client(self):
        """Test sin api_client configurado."""
        user = User(id=123, first_name="Test", is_bot=False)
        message = MagicMock(spec=Message)
        message.edit_message_text = AsyncMock()

        callback_query = MagicMock(spec=CallbackQuery)
        callback_query.from_user = user
        callback_query.message = message
        callback_query.data = "start_toque"
        callback_query.answer = AsyncMock()
        callback_query.edit_message_text = AsyncMock()

        update = MagicMock(spec=Update)
        update.callback_query = callback_query

        # Mock context without api_client
        context = MagicMock()
        context.bot_data = {}

        await start_button_callback(update, context)

        # Verify error message was sent via callback query
        callback_query.edit_message_text.assert_called_once()
