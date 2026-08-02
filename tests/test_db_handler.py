"""Tests para el handler del comando /db (src/handlers/db.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Message, Update, User

from src.handlers.db import db_command


def _make_update(user_id=123, args=None, admin_key="secret"):
    user = User(id=user_id, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()
    message.reply_document = AsyncMock()

    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    message.reply_text.return_value = status_msg

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    api_client = MagicMock()
    api_client.admin_key = admin_key
    api_client.admin_db_list_backups = AsyncMock(return_value=[])
    api_client.admin_db_backup = AsyncMock(return_value=None)
    api_client.admin_db_download_backup = AsyncMock(return_value=None)
    api_client.admin_db_prune_rates = AsyncMock(return_value=None)

    context = MagicMock()
    context.args = args or []
    context.bot_data = {"api_client": api_client}

    return update, context, message, api_client, status_msg


@pytest.mark.asyncio
async def test_db_command_denied_for_non_admin():
    update, context, message, _, _ = _make_update(user_id=999)

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await db_command(update, context)

    message.reply_text.assert_called_once()
    assert "Acceso Denegado" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_db_command_summary_no_backups():
    update, context, message, api_client, _ = _make_update(args=[])

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await db_command(update, context)

    api_client.admin_db_list_backups.assert_called_once()
    text = message.reply_text.call_args[0][0]
    assert "No hay backups todavía" in text


@pytest.mark.asyncio
async def test_db_command_list_shows_backups():
    update, context, message, api_client, _ = _make_update(args=["list"])
    api_client.admin_db_list_backups.return_value = [
        {"filename": "tasalo_20260801.dump", "size_bytes": 2048, "created_at": "2026-08-01T03:10:00", "engine": "postgres"},
    ]

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await db_command(update, context)

    text = message.reply_text.call_args[0][0]
    assert "tasalo_20260801.dump" in text
    assert "2.0KB" in text


@pytest.mark.asyncio
async def test_db_command_restore_shows_cli_only_hint():
    update, context, message, _, _ = _make_update(args=["restore"])

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await db_command(update, context)

    text = message.reply_text.call_args[0][0]
    assert "CLI" in text
    assert "restore" in text.lower()


@pytest.mark.asyncio
async def test_db_command_prune_rates_reports_counts():
    update, context, message, api_client, status_msg = _make_update(args=["prune-rates"])
    api_client.admin_db_prune_rates.return_value = {
        "ok": True, "rate_snapshots_deleted": 42, "history_snapshots_deleted": 7, "days": 365,
    }

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await db_command(update, context)

    api_client.admin_db_prune_rates.assert_called_once()
    text = status_msg.edit_text.call_args[0][0]
    assert "42" in text
    assert "7" in text


@pytest.mark.asyncio
async def test_db_command_unknown_subcommand():
    update, context, message, _, _ = _make_update(args=["ftp"])

    with patch("src.utils.permissions.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await db_command(update, context)

    text = message.reply_text.call_args[0][0]
    assert "Subcomando desconocido" in text
