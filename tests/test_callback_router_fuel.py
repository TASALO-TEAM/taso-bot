"""H-048: el boton de refresh de /fuel debe tener ruta en el callback_router."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update


@pytest.mark.parametrize("source", ["toque", "bcc", "fuel"])
def test_teclado_refresh_resuelve_a_un_namespace_con_ruta(source):
    # Import local: callback_router importa todos los handlers (dependencias pesadas).
    from src.handlers.callback_router import ROUTE_MAP, _resolve_namespace
    from src.handlers.tasalo import _build_source_refresh_keyboard

    boton = _build_source_refresh_keyboard(source).inline_keyboard[0][0]

    assert _resolve_namespace(boton.callback_data) in ROUTE_MAP


@pytest.mark.asyncio
async def test_fuel_refresh_llega_a_source_refresh_callback():
    from src.handlers import callback_router as router
    from src.handlers import tasalo

    query = MagicMock()
    query.data = "fuel_refresh"
    query.from_user.id = 123
    query.answer = AsyncMock()
    update = MagicMock(spec=Update)
    update.callback_query = query

    with patch.object(tasalo, "source_refresh_callback", new=AsyncMock()) as refresh:
        await router.callback_router(update, MagicMock())

    refresh.assert_awaited_once()
    # Nadie debe responder "Accion no reconocida" a un boton legitimo.
    assert all(c.kwargs.get("show_alert") is not True for c in query.answer.await_args_list)
