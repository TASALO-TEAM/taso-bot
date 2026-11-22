"""taso-bot#72 Fase 1: registro automatico de usuarios (POST /admin/stats/users/seen)."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.ext import TypeHandler


def _update(user_id=7, username="ana", first_name="Ana", is_bot=False, my_chat_member=None):
    u = MagicMock()
    u.effective_user.id = user_id
    u.effective_user.username = username
    u.effective_user.first_name = first_name
    u.effective_user.is_bot = is_bot
    u.my_chat_member = my_chat_member
    return u


def _context(api_client):
    ctx = MagicMock()
    ctx.bot_data = {"api_client": api_client} if api_client is not None else {}
    return ctx


@pytest.fixture(autouse=True)
def _limiter_limpio():
    from src import user_seen

    user_seen._last_sent.clear()
    yield
    user_seen._last_sent.clear()


class TestClienteMarkUserSeen:
    @pytest.mark.asyncio
    async def test_envia_el_usuario_al_endpoint_admin(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        http = MagicMock()
        http.post = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
        client._get_client = MagicMock(return_value=http)

        await client.mark_user_seen(user_id=7, username="ana", first_name="Ana")

        args, kwargs = http.post.call_args
        assert args[0] == "http://test:8000/api/v1/admin/stats/users/seen"
        assert kwargs["json"] == {"user_id": 7, "username": "ana", "first_name": "Ana"}
        assert kwargs["headers"] == client._admin_headers

    @pytest.mark.asyncio
    async def test_un_fallo_de_red_no_propaga(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        http = MagicMock()
        http.post = AsyncMock(side_effect=RuntimeError("caido"))
        client._get_client = MagicMock(return_value=http)

        await client.mark_user_seen(user_id=7)  # no debe lanzar


class TestHandlerUserSeen:
    @pytest.mark.asyncio
    async def test_registra_a_un_usuario_nuevo(self):
        from src.user_seen import mark_seen

        api = MagicMock(mark_user_seen=AsyncMock())
        await mark_seen(_update(), _context(api))

        api.mark_user_seen.assert_awaited_once_with(user_id=7, username="ana", first_name="Ana")

    @pytest.mark.asyncio
    async def test_no_repite_dentro_de_la_hora(self):
        from src.user_seen import mark_seen

        api = MagicMock(mark_user_seen=AsyncMock())
        for _ in range(3):
            await mark_seen(_update(), _context(api))

        assert api.mark_user_seen.await_count == 1

    @pytest.mark.asyncio
    async def test_vuelve_a_registrar_pasada_la_hora(self):
        from src import user_seen

        api = MagicMock(mark_user_seen=AsyncMock())
        await user_seen.mark_seen(_update(), _context(api))
        user_seen._last_sent[7] = time.monotonic() - user_seen.RESEND_SECONDS - 1
        await user_seen.mark_seen(_update(), _context(api))

        assert api.mark_user_seen.await_count == 2

    @pytest.mark.asyncio
    async def test_cada_usuario_tiene_su_propio_limite(self):
        from src.user_seen import mark_seen

        api = MagicMock(mark_user_seen=AsyncMock())
        await mark_seen(_update(user_id=1), _context(api))
        await mark_seen(_update(user_id=2), _context(api))

        assert api.mark_user_seen.await_count == 2

    @pytest.mark.asyncio
    async def test_ignora_my_chat_member_porque_es_un_bloqueo_no_actividad(self):
        from src.user_seen import mark_seen

        api = MagicMock(mark_user_seen=AsyncMock())
        await mark_seen(_update(my_chat_member=MagicMock()), _context(api))

        api.mark_user_seen.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ignora_bots_y_updates_sin_usuario(self):
        from src.user_seen import mark_seen

        api = MagicMock(mark_user_seen=AsyncMock())
        sin_usuario = _update()
        sin_usuario.effective_user = None
        await mark_seen(_update(is_bot=True), _context(api))
        await mark_seen(sin_usuario, _context(api))

        api.mark_user_seen.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sin_api_client_no_falla(self):
        from src.user_seen import mark_seen

        await mark_seen(_update(), _context(None))  # no debe lanzar


def test_register_usa_grupo_previo_y_no_bloquea_el_update():
    from src.user_seen import GROUP, register

    app = MagicMock()
    register(app)

    primera = app.add_handler.call_args_list[0]  # el TypeHandler; el 2o es el de my_chat_member
    handler = primera.args[0]
    assert isinstance(handler, TypeHandler)
    assert handler.block is False
    assert primera.kwargs["group"] == GROUP
    assert GROUP < -2  # antes que pick (-2) y el explorador (-1)
