"""Tests para el handler /ads (gestión de anuncios)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, Message, User

from src.handlers.ads import ads_command


def _make_update(user_id: int = 123):
    user = User(id=user_id, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()
    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message
    return update, message


def _make_context(args, api_client):
    context = MagicMock()
    context.args = args
    context.bot_data = {"api_client": api_client}
    return context


def _make_api_client(admin_key="test_key"):
    client = AsyncMock()
    client.admin_key = admin_key
    return client


@pytest.mark.asyncio
async def test_ads_command_denies_non_admin():
    update, message = _make_update(user_id=999)
    context = _make_context([], _make_api_client())

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    message.reply_text.assert_called_once()
    assert "Acceso Denegado" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_ads_command_requires_admin_key_configured():
    update, message = _make_update()
    context = _make_context([], _make_api_client(admin_key=None))

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    assert "Error de Configuración" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_ads_command_list_empty():
    update, message = _make_update()
    api_client = _make_api_client()
    api_client.admin_list_ads = AsyncMock(return_value=[])
    context = _make_context([], api_client)

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    assert "No hay ningún anuncio" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_ads_command_list_shows_entries():
    update, message = _make_update()
    api_client = _make_api_client()
    api_client.admin_list_ads = AsyncMock(return_value=[
        {"id": 1, "text": "Aviso propio", "is_active": True, "is_sponsored": False, "weight": 1},
        {"id": 2, "text": "Promo externa", "is_active": False, "is_sponsored": True, "weight": 5},
    ])
    context = _make_context([], api_client)

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    text = message.reply_text.call_args[0][0]
    assert "#1" in text and "#2" in text
    assert "Patrocinado" in text
    assert "Aviso" in text


@pytest.mark.asyncio
async def test_ads_add_creates_ad():
    update, message = _make_update()
    api_client = _make_api_client()
    api_client.admin_create_ad = AsyncMock(return_value={
        "ok": True,
        "data": {"id": 3, "text": "Nuevo aviso", "is_active": True, "is_sponsored": False, "weight": 1},
    })
    context = _make_context(["add", "Nuevo", "aviso"], api_client)

    with patch("src.utils.permissions.settings") as mock_settings, \
         patch("src.handlers.ads.invalidate_ad_cache") as mock_invalidate:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    api_client.admin_create_ad.assert_called_once()
    mock_invalidate.assert_called_once()
    assert "creado" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_ads_add_rejects_empty_text():
    update, message = _make_update()
    api_client = _make_api_client()
    context = _make_context(["add"], api_client)

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    api_client.admin_create_ad.assert_not_called()
    assert "Uso:" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_ads_add_rejects_text_too_long():
    update, message = _make_update()
    api_client = _make_api_client()
    context = _make_context(["add"] + ["x" * 301], api_client)

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    api_client.admin_create_ad.assert_not_called()
    assert "supera" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_ads_del_success():
    update, message = _make_update()
    api_client = _make_api_client()
    api_client.admin_delete_ad = AsyncMock(return_value=True)
    context = _make_context(["del", "5"], api_client)

    with patch("src.utils.permissions.settings") as mock_settings, \
         patch("src.handlers.ads.invalidate_ad_cache") as mock_invalidate:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    api_client.admin_delete_ad.assert_called_once_with(5)
    mock_invalidate.assert_called_once()
    assert "eliminado" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_ads_del_not_found():
    update, message = _make_update()
    api_client = _make_api_client()
    api_client.admin_delete_ad = AsyncMock(return_value=False)
    context = _make_context(["del", "999"], api_client)

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    assert "No existe" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_ads_on_off_toggle():
    update, message = _make_update()
    api_client = _make_api_client()
    api_client.admin_update_ad = AsyncMock(return_value={
        "ok": True,
        "data": {"id": 1, "text": "x", "is_active": False, "is_sponsored": False, "weight": 1},
    })
    context = _make_context(["off", "1"], api_client)

    with patch("src.utils.permissions.settings") as mock_settings, \
         patch("src.handlers.ads.invalidate_ad_cache"):
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    api_client.admin_update_ad.assert_called_once_with(1, is_active=False)
    assert "pausado" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_ads_sponsor_toggle():
    update, message = _make_update()
    api_client = _make_api_client()
    api_client.admin_update_ad = AsyncMock(return_value={
        "ok": True,
        "data": {"id": 2, "text": "x", "is_active": True, "is_sponsored": True, "weight": 1},
    })
    context = _make_context(["sponsor", "2"], api_client)

    with patch("src.utils.permissions.settings") as mock_settings, \
         patch("src.handlers.ads.invalidate_ad_cache"):
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    api_client.admin_update_ad.assert_called_once_with(2, is_sponsored=True)


@pytest.mark.asyncio
async def test_ads_weight_rejects_out_of_range():
    update, message = _make_update()
    api_client = _make_api_client()
    context = _make_context(["weight", "1", "999"], api_client)

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    api_client.admin_update_ad.assert_not_called()
    assert "entre 1 y 100" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_ads_weight_valid():
    update, message = _make_update()
    api_client = _make_api_client()
    api_client.admin_update_ad = AsyncMock(return_value={
        "ok": True,
        "data": {"id": 1, "text": "x", "is_active": True, "is_sponsored": False, "weight": 10},
    })
    context = _make_context(["weight", "1", "10"], api_client)

    with patch("src.utils.permissions.settings") as mock_settings, \
         patch("src.handlers.ads.invalidate_ad_cache"):
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    api_client.admin_update_ad.assert_called_once_with(1, weight=10)


@pytest.mark.asyncio
async def test_ads_edit_updates_text():
    update, message = _make_update()
    api_client = _make_api_client()
    api_client.admin_update_ad = AsyncMock(return_value={
        "ok": True,
        "data": {"id": 1, "text": "Texto nuevo", "is_active": True, "is_sponsored": False, "weight": 1},
    })
    context = _make_context(["edit", "1", "Texto", "nuevo"], api_client)

    with patch("src.utils.permissions.settings") as mock_settings, \
         patch("src.handlers.ads.invalidate_ad_cache"):
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    api_client.admin_update_ad.assert_called_once_with(1, text="Texto nuevo")


@pytest.mark.asyncio
async def test_ads_unknown_subcommand_shows_help():
    update, message = _make_update()
    api_client = _make_api_client()
    context = _make_context(["bogus"], api_client)

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await ads_command(update, context)

    assert "Gestión de Anuncios" in message.reply_text.call_args[0][0]
