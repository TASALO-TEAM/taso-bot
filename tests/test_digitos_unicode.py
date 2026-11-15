"""H-050: str.isdigit() acepta dígitos Unicode (², ①) que int() rechaza.

Un mensaje así lanzaba ValueError sin capturar y llegaba al grupo de
soporte vía error_handler. Debe tratarse como entrada inválida.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.handlers import tkt, tspl, y

NO_ASCII = ["²", "①", "1²"]


def _update(text: str) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = 1
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


@pytest.mark.asyncio
@pytest.mark.parametrize("text", NO_ASCII)
async def test_tspl_hora_unicode_se_cancela(text):
    update = _update(text)
    context = MagicMock()
    context.user_data = {"awaiting_tspl_hour": time.time()}

    await tspl.handle_tspl_hour_input(update, context)

    update.message.reply_text.assert_awaited_once()
    assert "awaiting_tspl_hour" not in context.user_data


@pytest.mark.asyncio
@pytest.mark.parametrize("text", NO_ASCII)
async def test_year_hora_unicode_se_cancela(text):
    update = _update(text)
    context = MagicMock()
    context.user_data = {"awaiting_year_hour": time.time()}

    await y.handle_year_hour_input(update, context)

    update.message.reply_text.assert_awaited_once()
    assert "awaiting_year_hour" not in context.user_data


@pytest.mark.asyncio
@pytest.mark.parametrize("text", NO_ASCII)
async def test_tkt_show_id_unicode_muestra_uso(text):
    update = _update(text)
    context = MagicMock()
    context.args = ["show", text]
    api = MagicMock()
    api.get_ticket = AsyncMock()

    with patch.object(tkt, "settings") as fake_settings, \
         patch.object(tkt, "_get_api_client", return_value=api):
        fake_settings.get_admin_chat_ids_list.return_value = [1]
        await tkt.tkt_command(update, context)

    update.message.reply_text.assert_awaited_once()
    api.get_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_tspl_hora_ascii_valida_sigue_funcionando():
    """Control: '9' sigue pasando la validación y llega a la API."""
    update = _update("9")
    context = MagicMock()
    context.user_data = {"awaiting_tspl_hour": time.time()}

    with patch.object(tspl, "_tspl_api") as api:
        api.get_tspl_subscriptions = AsyncMock(return_value=[])
        api.add_tspl_subscription = AsyncMock(return_value={"ok": True})
        await tspl.handle_tspl_hour_input(update, context)

    api.add_tspl_subscription.assert_awaited_once_with(1, 9)
