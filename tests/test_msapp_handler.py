"""Tests para /msapp (publicar mensajes en la sección Alertas de la app Android)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, Message, User
from telegram.error import BadRequest

from src.api_client import TasaloApiClient
from src.handlers import msapp
from src.handlers.msapp import (
    cancel_callback,
    confirm_callback,
    msapp_command,
    plain_title,
    split_title_body,
)


def _make_update(text: str, user_id: int = 123, reply_text_of_source: str | None = None):
    user = User(id=user_id, first_name="Admin", is_bot=False, username="admin")
    message = MagicMock(spec=Message)
    message.text = text
    message.reply_text = AsyncMock()
    if reply_text_of_source is not None:
        message.reply_to_message = MagicMock()
        message.reply_to_message.text = reply_text_of_source
    else:
        message.reply_to_message = None
    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message
    return update, message


def _make_api_client(admin_key="test_key"):
    client = AsyncMock()
    client.admin_key = admin_key
    return client


def _make_context(api_client):
    context = MagicMock()
    context.bot_data = {"api_client": api_client}
    return context


def _admin_patch():
    return patch("src.utils.permissions.settings")


# ── Funciones puras ──────────────────────────────────────────────────────────


def test_plain_title_strips_markdown_marks_and_links():
    assert plain_title("*Aviso importante*") == "Aviso importante"
    assert plain_title("_Nueva_ *versión* disponible") == "Nueva versión disponible"
    assert plain_title("Mira [esto](https://x.org) ya") == "Mira esto ya"
    assert plain_title("snake_case se queda") == "snake_case se queda"


def test_plain_title_truncates_to_120_characters():
    title = plain_title("x" * 300)
    assert len(title) == 120
    assert title.endswith("…")


def test_split_title_body_multiline_uses_first_line_as_title():
    title, body = split_title_body("*Aviso*\nPrimera línea del cuerpo\n\nSegunda *con* formato")
    assert title == "Aviso"
    assert body == "Primera línea del cuerpo\n\nSegunda *con* formato"


def test_split_title_body_single_line_keeps_the_whole_text_as_body():
    title, body = split_title_body("Mantenimiento esta noche")
    assert title == "Mantenimiento esta noche"
    assert body == "Mantenimiento esta noche"


def test_callback_namespaces_do_not_collide_with_ms():
    # Import local: callback_router importa todos los handlers (dependencias pesadas).
    from src.handlers.callback_router import _resolve_namespace

    assert _resolve_namespace("msapp_confirm:123") == "msapp"
    assert _resolve_namespace("msapp_cancel:123") == "msapp"
    assert _resolve_namespace("ms_confirm:123") == "ms"


# ── Comando ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_msapp_denies_non_admin():
    update, message = _make_update("/msapp hola", user_id=999)
    with _admin_patch() as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await msapp_command(update, _make_context(_make_api_client()))
    assert "Acceso Denegado" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_msapp_requires_admin_key():
    update, message = _make_update("/msapp hola")
    with _admin_patch() as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await msapp_command(update, _make_context(_make_api_client(admin_key=None)))
    assert "Error de Configuración" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_msapp_without_text_shows_usage():
    update, message = _make_update("/msapp")
    with _admin_patch() as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await msapp_command(update, _make_context(_make_api_client()))
    text = message.reply_text.call_args[0][0]
    assert "/msapp list" in text and "primera línea" in text


@pytest.mark.asyncio
async def test_msapp_builds_preview_and_stores_pending_payload():
    update, message = _make_update("/msapp *Aviso*\nCuerpo con _formato_")
    context = _make_context(_make_api_client())
    with _admin_patch() as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await msapp_command(update, context)

    kwargs = message.reply_text.call_args.kwargs
    assert "Vista previa en la app" in message.reply_text.call_args[0][0]
    assert kwargs["reply_markup"] is not None
    pending = context.bot_data["msapp_pending"][123]
    assert pending == {"title": "Aviso", "body": "Cuerpo con _formato_", "format": "telegram"}


@pytest.mark.asyncio
async def test_msapp_preserves_newlines_typed_after_the_command():
    update, _ = _make_update("/msapp@tasalo_bot Título\nlínea 1\nlínea 2")
    context = _make_context(_make_api_client())
    with _admin_patch() as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await msapp_command(update, context)
    assert context.bot_data["msapp_pending"][123]["body"] == "línea 1\nlínea 2"


@pytest.mark.asyncio
async def test_msapp_accepts_a_reply_as_the_source_text():
    update, _ = _make_update("/msapp", reply_text_of_source="Texto respondido")
    context = _make_context(_make_api_client())
    with _admin_patch() as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await msapp_command(update, context)
    assert context.bot_data["msapp_pending"][123]["title"] == "Texto respondido"


@pytest.mark.asyncio
async def test_msapp_rejects_text_over_the_limit():
    update, message = _make_update("/msapp Título\n" + "x" * (msapp.MAX_BODY_LENGTH + 1))
    context = _make_context(_make_api_client())
    with _admin_patch() as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await msapp_command(update, context)
    assert "supera los" in message.reply_text.call_args[0][0]
    assert "msapp_pending" not in context.bot_data or 123 not in context.bot_data["msapp_pending"]


@pytest.mark.asyncio
async def test_msapp_invalid_markdown_is_reported_and_not_left_pending():
    update, message = _make_update("/msapp Título\ncuerpo con *negrita sin cerrar")
    message.reply_text = AsyncMock(side_effect=[BadRequest("Can't parse entities"), None])
    context = _make_context(_make_api_client())
    with _admin_patch() as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await msapp_command(update, context)
    assert 123 not in context.bot_data["msapp_pending"]
    assert "no es válido" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_msapp_list_shows_entries_with_state():
    update, message = _make_update("/msapp list")
    api_client = _make_api_client()
    api_client.admin_list_app_messages = AsyncMock(return_value=[
        {"id": 5, "title": "Nuevo aviso", "is_active": True, "created_at": "2026-10-01T10:30:00Z"},
        {"id": 4, "title": "Retirado", "is_active": False, "created_at": "2026-09-30T08:00:00+00:00"},
    ])
    with _admin_patch() as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await msapp_command(update, _make_context(api_client))
    text = message.reply_text.call_args[0][0]
    assert "#5 ✅ 01/10 10:30 UTC — Nuevo aviso" in text
    assert "#4 ⏸" in text


@pytest.mark.asyncio
async def test_msapp_list_empty():
    update, message = _make_update("/msapp list")
    api_client = _make_api_client()
    api_client.admin_list_app_messages = AsyncMock(return_value=[])
    with _admin_patch() as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await msapp_command(update, _make_context(api_client))
    assert "No hay mensajes" in message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_msapp_del_deletes_by_id_and_reports_missing():
    api_client = _make_api_client()
    api_client.admin_delete_app_message = AsyncMock(side_effect=[True, False])
    with _admin_patch() as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        update, message = _make_update("/msapp del 7")
        await msapp_command(update, _make_context(api_client))
        assert "#7 eliminado" in message.reply_text.call_args[0][0]
        update2, message2 = _make_update("/msapp del 99")
        await msapp_command(update2, _make_context(api_client))
        assert "No se pudo eliminar #99" in message2.reply_text.call_args[0][0]
    api_client.admin_delete_app_message.assert_any_call(7)


# ── Callbacks ────────────────────────────────────────────────────────────────


def _make_callback_update(data: str, clicker_id: int = 123):
    query = MagicMock()
    query.data = data
    query.from_user = User(id=clicker_id, first_name="Admin", is_bot=False)
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update = MagicMock(spec=Update)
    update.callback_query = query
    return update, query


@pytest.mark.asyncio
async def test_confirm_publishes_and_clears_pending():
    api_client = _make_api_client()
    api_client.admin_create_app_message = AsyncMock(return_value={"ok": True, "data": {"id": 42}})
    context = _make_context(api_client)
    context.bot_data["msapp_pending"] = {123: {"title": "T", "body": "B", "format": "telegram"}}
    update, query = _make_callback_update("msapp_confirm:123")

    await confirm_callback(update, context)

    api_client.admin_create_app_message.assert_awaited_once_with(
        title="T", body="B", format="telegram", created_by=123
    )
    assert 123 not in context.bot_data["msapp_pending"]
    text = query.edit_message_text.call_args[0][0]
    assert "#42" in text and "/msapp del 42" in text


@pytest.mark.asyncio
async def test_confirm_reports_api_failure():
    api_client = _make_api_client()
    api_client.admin_create_app_message = AsyncMock(return_value=None)
    context = _make_context(api_client)
    context.bot_data["msapp_pending"] = {123: {"title": "T", "body": "B", "format": "telegram"}}
    update, query = _make_callback_update("msapp_confirm:123")

    await confirm_callback(update, context)

    assert "No se pudo publicar" in query.edit_message_text.call_args[0][0]
    assert 123 not in context.bot_data["msapp_pending"]


@pytest.mark.asyncio
async def test_confirm_from_another_admin_is_refused():
    api_client = _make_api_client()
    context = _make_context(api_client)
    context.bot_data["msapp_pending"] = {123: {"title": "T", "body": "B", "format": "telegram"}}
    update, query = _make_callback_update("msapp_confirm:123", clicker_id=456)

    await confirm_callback(update, context)

    api_client.admin_create_app_message.assert_not_called()
    assert 123 in context.bot_data["msapp_pending"]
    assert query.answer.call_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_confirm_without_pending_payload_says_expired():
    context = _make_context(_make_api_client())
    update, query = _make_callback_update("msapp_confirm:123")
    await confirm_callback(update, context)
    assert "ya no está disponible" in query.edit_message_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cancel_discards_pending():
    context = _make_context(_make_api_client())
    context.bot_data["msapp_pending"] = {123: {"title": "T", "body": "B", "format": "telegram"}}
    update, query = _make_callback_update("msapp_cancel:123")
    await cancel_callback(update, context)
    assert 123 not in context.bot_data["msapp_pending"]
    assert "Cancelado" in query.edit_message_text.call_args[0][0]


# ── Cliente de la API ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_client_create_app_message_posts_expected_payload():
    client = TasaloApiClient(api_url="http://api.test", admin_key="k")
    client._post_with_retry = AsyncMock(return_value={"ok": True, "data": {"id": 1}})

    result = await client.admin_create_app_message("T", "B", format="telegram", created_by=7)

    assert result == {"ok": True, "data": {"id": 1}}
    args, kwargs = client._post_with_retry.call_args
    assert args[0] == "http://api.test/api/v1/app/messages"
    assert kwargs["json"] == {"title": "T", "body": "B", "format": "telegram", "created_by": 7}
    assert kwargs["headers"]["X-API-Key"] == "k"


@pytest.mark.asyncio
async def test_api_client_app_message_methods_require_admin_key():
    client = TasaloApiClient(api_url="http://api.test", admin_key=None)
    assert await client.admin_create_app_message("T", "B") is None
    assert await client.admin_list_app_messages() == []
    assert await client.admin_delete_app_message(1) is False
