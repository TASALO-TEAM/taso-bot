"""Tests para el handler del comando /log (src/handlers/logs.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User

from src.handlers.logs import log_command
from src.services.log_manager import ArchivedLogFile, ServiceLogInfo


def _make_update(user_id=123, args=None):
    user = User(id=user_id, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()
    message.reply_document = AsyncMock()

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    context = MagicMock()
    context.args = args or []

    return update, context, message


@pytest.mark.asyncio
async def test_log_command_denied_for_non_admin():
    update, context, message = _make_update(user_id=999)

    with patch("src.handlers.admin.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await log_command(update, context)

    message.reply_text.assert_called_once()
    assert "Acceso Denegado" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_log_command_summary(tmp_path):
    update, context, message = _make_update(args=[])

    bot_info = ServiceLogInfo(
        service="bot", display_name="taso-bot", logs_dir="x", exists=True,
        active_log_path="x.log", active_size_bytes=1024,
    )
    api_info = ServiceLogInfo(
        service="api", display_name="taso-api", logs_dir="y", exists=False,
        error="No se encontró el directorio de logs en `y`.",
    )
    web_info = ServiceLogInfo(
        service="web", display_name="taso-app", logs_dir="z", exists=True,
        active_log_path=None,
    )

    with patch("src.handlers.admin.settings") as mock_settings, \
         patch("src.handlers.logs.log_manager.list_all_services") as mock_list:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        mock_list.return_value = {"bot": bot_info, "api": api_info, "web": web_info}
        await log_command(update, context)

    message.reply_text.assert_called_once()
    text = message.reply_text.call_args[0][0]
    assert "taso-bot" in text
    assert "taso-api" in text
    assert "no encontrado" in text
    assert "sin log activo" in text


@pytest.mark.asyncio
async def test_log_command_unknown_service():
    update, context, message = _make_update(args=["ftp"])

    with patch("src.handlers.admin.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await log_command(update, context)

    message.reply_text.assert_called_once()
    assert "Servicio desconocido" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_log_command_sends_active_log_as_document(tmp_path):
    log_file = tmp_path / "taso-bot.log"
    log_file.write_text("contenido de prueba")

    update, context, message = _make_update(args=["bot"])

    info = ServiceLogInfo(
        service="bot", display_name="taso-bot", logs_dir=str(tmp_path), exists=True,
        active_log_path=str(log_file), active_size_bytes=log_file.stat().st_size,
    )

    with patch("src.handlers.admin.settings") as mock_settings, \
         patch("src.handlers.logs.log_manager.get_service_log_info", return_value=info):
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await log_command(update, context)

    message.reply_document.assert_called_once()
    assert message.reply_document.call_args.kwargs["filename"] == "taso-bot.log"


@pytest.mark.asyncio
async def test_log_command_service_not_found():
    update, context, message = _make_update(args=["api"])

    info = ServiceLogInfo(
        service="api", display_name="taso-api", logs_dir="/tmp/nope", exists=False,
        error="No se encontró el directorio de logs en `/tmp/nope`.",
    )

    with patch("src.handlers.admin.settings") as mock_settings, \
         patch("src.handlers.logs.log_manager.get_service_log_info", return_value=info):
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await log_command(update, context)

    message.reply_text.assert_called_once()
    text = message.reply_text.call_args[0][0]
    assert "taso-api" in text
    assert "No se encontró el directorio" in text


@pytest.mark.asyncio
async def test_log_command_date_not_found_suggests_dates(tmp_path):
    log_file = tmp_path / "taso-bot.log"
    log_file.write_text("activo")

    update, context, message = _make_update(args=["bot", "2020-01-01"])

    info = ServiceLogInfo(
        service="bot", display_name="taso-bot", logs_dir=str(tmp_path), exists=True,
        active_log_path=str(log_file),
    )

    with patch("src.handlers.admin.settings") as mock_settings, \
         patch("src.handlers.logs.log_manager.get_service_log_info", return_value=info), \
         patch(
             "src.handlers.logs.log_manager.find_archive_by_date",
             return_value=(None, ["2026-07-01", "2026-06-30"]),
         ):
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await log_command(update, context)

    message.reply_text.assert_called_once()
    text = message.reply_text.call_args[0][0]
    assert "2020-01-01" in text
    assert "2026-07-01" in text


@pytest.mark.asyncio
async def test_log_command_sends_archived_document_by_date(tmp_path):
    archived_file = tmp_path / "taso-bot_2026-07-01_09-00-00.log"
    archived_file.write_text("log viejo")

    update, context, message = _make_update(args=["bot", "2026-07-01"])

    info = ServiceLogInfo(
        service="bot", display_name="taso-bot", logs_dir=str(tmp_path), exists=True,
    )
    archived = ArchivedLogFile(
        path=str(archived_file), filename=archived_file.name,
        date_str="2026-07-01", size_bytes=archived_file.stat().st_size,
    )

    with patch("src.handlers.admin.settings") as mock_settings, \
         patch("src.handlers.logs.log_manager.get_service_log_info", return_value=info), \
         patch(
             "src.handlers.logs.log_manager.find_archive_by_date",
             return_value=(archived, ["2026-07-01"]),
         ):
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await log_command(update, context)

    message.reply_document.assert_called_once()
    assert message.reply_document.call_args.kwargs["filename"] == archived_file.name


@pytest.mark.asyncio
async def test_log_command_clear_all():
    update, context, message = _make_update(args=["clear"])

    results = {
        "bot": {"removed": 3, "bytes_freed": 1500, "error": None},
        "api": {"removed": 1, "bytes_freed": 500, "error": None},
        "web": {"removed": 0, "bytes_freed": 0, "error": None},
    }

    with patch("src.handlers.admin.settings") as mock_settings, \
         patch("src.handlers.logs.log_manager.clear_archives", return_value=results) as mock_clear:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await log_command(update, context)

    mock_clear.assert_called_once_with(None)
    text = message.reply_text.call_args[0][0]
    assert "Total:* 4 archivo" in text


@pytest.mark.asyncio
async def test_log_command_clear_single_service():
    update, context, message = _make_update(args=["clear", "api"])

    results = {"api": {"removed": 2, "bytes_freed": 2048, "error": None}}

    with patch("src.handlers.admin.settings") as mock_settings, \
         patch("src.handlers.logs.log_manager.clear_archives", return_value=results) as mock_clear:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await log_command(update, context)

    mock_clear.assert_called_once_with("api")
    text = message.reply_text.call_args[0][0]
    assert "taso-api" in text


@pytest.mark.asyncio
async def test_log_command_clear_unknown_service():
    update, context, message = _make_update(args=["clear", "ftp"])

    with patch("src.handlers.admin.settings") as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await log_command(update, context)

    message.reply_text.assert_called_once()
    assert "Servicio desconocido" in message.reply_text.call_args[0][0]
