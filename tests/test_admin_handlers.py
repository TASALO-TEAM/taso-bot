"""Tests para handlers de administración."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, Chat, User

from src.handlers.admin import (
    refresh_command,
    status_command,
    status_callback,
    STATUS_BUNDLE_CACHE_KEY,
    _is_admin,
)
from src.cache import cache


@pytest.mark.asyncio
async def test_refresh_command_no_admin():
    """Test /refresh desde usuario no admin."""
    # Mock update
    user = User(id=999, first_name="NotAdmin", is_bot=False)
    chat = Chat(id=999, type="private")
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock context
    context = MagicMock()
    context.bot_data = {"api_client": AsyncMock()}

    # Call handler
    await refresh_command(update, context)

    # Verify access denied
    message.reply_text.assert_called_once()
    call_args = message.reply_text.call_args[0][0]
    assert "Acceso Denegado" in call_args


@pytest.mark.asyncio
async def test_refresh_command_admin_success():
    """Test /refresh desde admin exitoso."""
    # Mock update
    user = User(id=123, first_name="Admin", is_bot=False)
    chat = Chat(id=123, type="private")
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock context with admin API client
    mock_api_client = AsyncMock()
    mock_api_client.admin_refresh = AsyncMock(return_value={
        "ok": True,
        "data": {
            "sources": ["eltoque", "cadeca", "bcc"],
            "timestamp": "2026-03-22T14:30:00Z"
        }
    })
    mock_api_client.admin_key = "test_key"

    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    # Mock settings to return user as admin
    # NOTA: _is_admin ahora delega en src.utils.permissions.is_admin, que
    # tiene su propia referencia a `settings` (ver docs/plans/2026-07-04).
    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123, 456]

        # Call handler
        await refresh_command(update, context)

    # Verify success message
    status_msg = message.reply_text.return_value
    status_msg.edit_text.assert_called_once()
    call_args = status_msg.edit_text.call_args[0][0]
    assert "Refresco Completado" in call_args


@pytest.mark.asyncio
async def test_refresh_command_admin_api_error():
    """Test /refresh con error de API."""
    # Mock update
    user = User(id=123, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock API client returning None
    mock_api_client = AsyncMock()
    mock_api_client.admin_refresh = AsyncMock(return_value=None)
    mock_api_client.admin_key = "test_key"

    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]

        # Call handler
        await refresh_command(update, context)

    # Verify error message
    status_msg = message.reply_text.return_value
    status_msg.edit_text.assert_called_once()
    call_args = status_msg.edit_text.call_args[0][0]
    assert "Error de Conexión" in call_args


@pytest.mark.asyncio
async def test_refresh_command_no_api_key():
    """Test /refresh sin API key configurada."""
    # Mock update
    user = User(id=123, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock API client without admin_key
    mock_api_client = AsyncMock()
    mock_api_client.admin_key = None

    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]

        # Call handler
        await refresh_command(update, context)

    # Verify config error message
    message.reply_text.assert_called_once()
    call_args = message.reply_text.call_args[0][0]
    assert "Error de Configuración" in call_args


@pytest.mark.asyncio
async def test_status_command_no_admin():
    """Test /status desde usuario no admin."""
    # Mock update
    user = User(id=999, first_name="NotAdmin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    # Mock context
    context = MagicMock()
    context.bot_data = {"api_client": AsyncMock()}

    # Call handler
    await status_command(update, context)

    # Verify access denied
    message.reply_text.assert_called_once()
    call_args = message.reply_text.call_args[0][0]
    assert "Acceso Denegado" in call_args


@pytest.mark.asyncio
async def test_status_command_no_api_key():
    """Test /status sin API key configurada."""
    user = User(id=123, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    mock_api_client = AsyncMock()
    mock_api_client.admin_key = None

    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await status_command(update, context)

    message.reply_text.assert_called_once()
    call_args = message.reply_text.call_args[0][0]
    assert "Error de Configuración" in call_args


def _mock_status_bundle_client() -> AsyncMock:
    """Cliente API mockeado con datos realistas para el panel /status v2.

    Formas reales de taso-api tras docs/plans/2026-07-08-status-command-v2.md:
    - admin_status(): {ok, is_scheduler_running, jobs: [...]} (Fase 2)
    - get_stats_summary(): {ok, users: {..., active_recent}, commands: {...,
      commands_30d}, top_users, performance}
    - get_api_usage_stats(window): {ok, window, total_requests, total_errors,
      error_rate, avg_duration_ms, by_client, by_endpoint}
    """
    mock_api_client = AsyncMock()
    mock_api_client.admin_key = "test_key"
    mock_api_client.admin_status = AsyncMock(return_value={
        "ok": True,
        "is_scheduler_running": True,
        "jobs": [
            {
                "id": "refresh_all", "name": "Refresh de tasas",
                "next_run_at": "2026-07-09T15:05:00Z",
                "last_run_at": "2026-07-09T15:00:00Z",
                "last_success_at": "2026-07-09T15:00:00Z",
                "error_count": 0, "last_error": None,
            },
            {
                "id": "cubanomic_daily", "name": "Cubanomic diario",
                "next_run_at": "2026-07-10T06:00:00Z",
                "last_run_at": None, "last_success_at": None,
                "error_count": 0, "last_error": None,
            },
        ],
    })
    mock_api_client.get_stats_summary = AsyncMock(return_value={
        "ok": True,
        "users": {"total": 143, "new_7d": 5, "active_24h": 30, "active_recent": 5},
        "commands": {
            "commands_24h": [{"command": "/p", "count": 30}],
            "commands_7d": [{"command": "/p", "count": 150}],
            "commands_30d": [{"command": "/p", "count": 600}],
        },
        "top_users": {"top_users": [{"username": "ersus", "user_id": 1, "total_commands": 20}]},
        "performance": {"success_rate": 98.5, "avg_response_ms": 120.0, "total_requests_24h": 200},
    })
    mock_api_client.get_api_usage_stats = AsyncMock(return_value={
        "ok": True, "window": "24h",
        "total_requests": 2340, "total_errors": 21, "error_rate": 0.9,
        "avg_duration_ms": 145.0,
        "by_client": [
            {"client_id": "bot", "requests": 1800, "errors": 10, "avg_duration_ms": 130.0},
            {"client_id": "unknown", "requests": 540, "errors": 11, "avg_duration_ms": 180.0},
        ],
        "by_endpoint": [
            {"path": "/api/v1/tasas/latest", "requests": 900, "errors": 2, "avg_duration_ms": 110.0},
        ],
    })
    mock_api_client.get_health = AsyncMock(return_value={
        "ok": True, "version": "1.5.0", "git_commit": "b7e91f2", "git_commit_date": "2026-07-08",
    })
    return mock_api_client


@pytest.mark.asyncio
async def test_status_command_admin_renders_panel():
    """Test /status desde admin exitoso: resumen ejecutivo + botones.

    Regresión: el panel v2 reemplaza el mensaje monolítico anterior por un
    resumen corto con InlineKeyboardMarkup (ver
    docs/plans/2026-07-08-status-command-v2.md, Fase 3).
    """
    cache.clear()
    user = User(id=123, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    context = MagicMock()
    context.bot_data = {"api_client": _mock_status_bundle_client()}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await status_command(update, context)

    status_msg = message.reply_text.return_value
    status_msg.edit_text.assert_called_once()
    call_kwargs = status_msg.edit_text.call_args
    text = call_kwargs[0][0]
    keyboard = call_kwargs[1]["reply_markup"]

    # Resumen ejecutivo
    assert "TASALO — Estado del sistema" in text
    assert "Todo operativo" in text
    assert "2/2 jobs OK" in text
    assert "143 usuarios" in text
    assert "5 activos ahora" in text
    assert "2340 req/24h" in text

    # Botones del panel
    button_texts = [btn.text for row in keyboard.inline_keyboard for btn in row]
    assert "📈 Comandos" in button_texts
    assert "👥 Usuarios" in button_texts
    assert "🌐 API pública" in button_texts
    assert "⚙️ Schedulers" in button_texts
    assert "📝 Cambios recientes" in button_texts
    assert "🔄 Refrescar" in button_texts

    # callback_data debe llevar el admin_id para que el panel quede "atado"
    # a quien lo abrió (ver status_callback)
    cmd_button = next(btn for row in keyboard.inline_keyboard for btn in row if btn.text == "📈 Comandos")
    assert cmd_button.callback_data == "status_cmd:123:24h"


@pytest.mark.asyncio
async def test_status_command_partial_data_shows_sin_datos():
    """Si algún endpoint falla, el resumen debe degradar con 'sin datos' en
    vez de romper el panel completo (a diferencia del comportamiento previo
    que fallaba duro si /admin/status no respondía)."""
    cache.clear()
    user = User(id=123, first_name="Admin", is_bot=False)
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.message = message

    mock_api_client = _mock_status_bundle_client()
    mock_api_client.admin_status = AsyncMock(return_value=None)
    mock_api_client.get_api_usage_stats = AsyncMock(return_value=None)

    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await status_command(update, context)

    status_msg = message.reply_text.return_value
    text = status_msg.edit_text.call_args[0][0]

    assert "⚙️ Scheduler: sin datos" in text
    assert "sin datos (24h)" in text
    # No debe reventar aunque falten piezas
    assert "TASALO — Estado del sistema" in text


def _make_callback_update(user_id: int, callback_data: str):
    """Construye un Update mockeado con callback_query para status_callback."""
    query = MagicMock()
    query.from_user = MagicMock(id=user_id)
    query.data = callback_data
    query.edit_message_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = query
    return update, query


@pytest.mark.asyncio
async def test_status_callback_owner_mismatch_denies():
    """El panel está atado al admin que lo abrió — otro admin no puede
    operarlo desde el mismo mensaje."""
    cache.clear()
    update, query = _make_callback_update(user_id=456, callback_data="status_cmd:123:24h")

    context = MagicMock()
    context.bot_data = {"api_client": _mock_status_bundle_client()}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123, 456]
        await status_callback(update, context)

    query.edit_message_text.assert_called_once()
    text = query.edit_message_text.call_args[0][0]
    assert "otro administrador" in text


@pytest.mark.asyncio
async def test_status_callback_non_admin_denies():
    """Un no-admin no puede operar el panel aunque adivine el callback_data."""
    cache.clear()
    update, query = _make_callback_update(user_id=999, callback_data="status_usr:999")

    context = MagicMock()
    context.bot_data = {"api_client": _mock_status_bundle_client()}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await status_callback(update, context)

    query.edit_message_text.assert_called_once()
    text = query.edit_message_text.call_args[0][0]
    assert "Acceso Denegado" in text


@pytest.mark.asyncio
async def test_status_callback_commands_view_respects_window():
    """status_cmd:<uid>:7d debe mostrar commands_7d, no commands_24h."""
    cache.clear()
    update, query = _make_callback_update(user_id=123, callback_data="status_cmd:123:7d")

    context = MagicMock()
    context.bot_data = {"api_client": _mock_status_bundle_client()}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await status_callback(update, context)

    query.edit_message_text.assert_called_once()
    text = query.edit_message_text.call_args[0][0]
    keyboard = query.edit_message_text.call_args[1]["reply_markup"]

    assert "últimas 7 días" in text
    assert "/p: 150 veces" in text  # commands_7d, no commands_24h (30 veces)

    # Botón "Volver" siempre presente en vistas de detalle
    button_texts = [btn.text for row in keyboard.inline_keyboard for btn in row]
    assert "🔙 Volver" in button_texts


@pytest.mark.asyncio
async def test_status_callback_api_view_uses_requested_window():
    """status_api:<uid>:7d debe llamar get_api_usage_stats('7d'), no cachear
    con la ventana 24h del bundle principal (el uso de API sí es específico
    por ventana, a diferencia del resto del bundle)."""
    cache.clear()
    update, query = _make_callback_update(user_id=123, callback_data="status_api:123:7d")

    mock_api_client = _mock_status_bundle_client()
    context = MagicMock()
    context.bot_data = {"api_client": mock_api_client}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await status_callback(update, context)

    mock_api_client.get_api_usage_stats.assert_called_once_with("7d")
    text = query.edit_message_text.call_args[0][0]
    assert "API pública — últimas 7 días" in text
    assert "2340" in text  # viene del mock, independiente de la ventana pedida


@pytest.mark.asyncio
async def test_status_callback_refresh_invalidates_cache():
    """El botón 🔄 Refrescar debe invalidar el bundle cacheado, no servir
    datos potencialmente viejos."""
    cache.clear()
    cache.set(STATUS_BUNDLE_CACHE_KEY, {"stale": True})

    update, query = _make_callback_update(user_id=123, callback_data="status_refresh:123")

    context = MagicMock()
    context.bot_data = {"api_client": _mock_status_bundle_client()}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await status_callback(update, context)

    text = query.edit_message_text.call_args[0][0]
    # Si hubiera servido el bundle viejo ("stale": True) el render hubiera
    # fallado (KeyError/AttributeError) en vez de mostrar el resumen real.
    assert "TASALO — Estado del sistema" in text


@pytest.mark.asyncio
async def test_status_callback_back_returns_to_summary():
    """status_back:<uid> debe re-renderizar el resumen ejecutivo con el
    teclado completo (no una vista de detalle)."""
    cache.clear()
    update, query = _make_callback_update(user_id=123, callback_data="status_back:123")

    context = MagicMock()
    context.bot_data = {"api_client": _mock_status_bundle_client()}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await status_callback(update, context)

    text = query.edit_message_text.call_args[0][0]
    keyboard = query.edit_message_text.call_args[1]["reply_markup"]
    assert "TASALO — Estado del sistema" in text
    button_texts = [btn.text for row in keyboard.inline_keyboard for btn in row]
    assert "📈 Comandos" in button_texts


@pytest.mark.asyncio
async def test_status_callback_schedulers_view_lists_all_jobs():
    """⚙️ Schedulers debe listar TODOS los jobs, no solo refresh_all
    (regresión directa de la Fase 2 — antes solo existía ese job)."""
    cache.clear()
    update, query = _make_callback_update(user_id=123, callback_data="status_sch:123")

    context = MagicMock()
    context.bot_data = {"api_client": _mock_status_bundle_client()}

    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123]
        await status_callback(update, context)

    text = query.edit_message_text.call_args[0][0]
    assert "Refresh de tasas" in text
    assert "Cubanomic diario" in text


def test_is_admin_true():
    """Test _is_admin con usuario admin."""
    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123, 456, 789]
        assert _is_admin(123) is True
        assert _is_admin(456) is True


def test_is_admin_false():
    """Test _is_admin con usuario no admin."""
    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = [123, 456]
        assert _is_admin(999) is False
        assert _is_admin(0) is False


def test_is_admin_empty_list():
    """Test _is_admin con lista vacía."""
    with patch('src.utils.permissions.settings') as mock_settings:
        mock_settings.get_admin_chat_ids_list.return_value = []
        assert _is_admin(123) is False

