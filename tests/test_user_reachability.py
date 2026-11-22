"""taso-bot#72 Fase 2: alcanzabilidad (POST /admin/stats/users/reachability).

Quien bloquea el bot queda marcado inalcanzable en la API (my_chat_member y envios
de /ms que fallan con Forbidden); al desbloquear vuelve a estar alcanzable.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import ChatMember
from telegram.error import Forbidden
from telegram.ext import ChatMemberHandler


def _cambio(status, chat_type="private", chat_id=7):
    u = MagicMock()
    u.my_chat_member.chat.type = chat_type
    u.my_chat_member.chat.id = chat_id
    u.my_chat_member.new_chat_member.status = status
    return u


def _context(api_client):
    ctx = MagicMock()
    ctx.bot_data = {"api_client": api_client} if api_client is not None else {}
    return ctx


class TestClienteSetUserReachability:
    @pytest.mark.asyncio
    async def test_envia_el_estado_al_endpoint_admin(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        http = MagicMock()
        http.post = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
        client._get_client = MagicMock(return_value=http)

        await client.set_user_reachability(user_id=7, reachable=False)

        args, kwargs = http.post.call_args
        assert args[0] == "http://test:8000/api/v1/admin/stats/users/reachability"
        assert kwargs["json"] == {"user_id": 7, "reachable": False}
        assert kwargs["headers"] == client._admin_headers

    @pytest.mark.asyncio
    async def test_un_fallo_de_red_no_propaga(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        http = MagicMock()
        http.post = AsyncMock(side_effect=RuntimeError("caido"))
        client._get_client = MagicMock(return_value=http)

        await client.set_user_reachability(user_id=7, reachable=True)  # no debe lanzar


class TestHandlerMyChatMember:
    @pytest.mark.asyncio
    async def test_bloqueo_marca_inalcanzable(self):
        from src.user_seen import track_reachability

        api = MagicMock(set_user_reachability=AsyncMock())
        await track_reachability(_cambio(ChatMember.BANNED), _context(api))

        api.set_user_reachability.assert_awaited_once_with(user_id=7, reachable=False)

    @pytest.mark.asyncio
    async def test_desbloqueo_lo_restaura(self):
        from src.user_seen import track_reachability

        api = MagicMock(set_user_reachability=AsyncMock())
        await track_reachability(_cambio(ChatMember.MEMBER), _context(api))

        api.set_user_reachability.assert_awaited_once_with(user_id=7, reachable=True)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
    async def test_ignora_grupos_y_canales(self, chat_type):
        from src.user_seen import track_reachability

        api = MagicMock(set_user_reachability=AsyncMock())
        await track_reachability(_cambio(ChatMember.BANNED, chat_type=chat_type), _context(api))

        api.set_user_reachability.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sin_api_client_no_falla(self):
        from src.user_seen import track_reachability

        await track_reachability(_cambio(ChatMember.BANNED), _context(None))  # no debe lanzar


def test_register_agrega_el_handler_de_my_chat_member_sin_bloquear():
    from src.user_seen import register

    app = MagicMock()
    register(app)

    handlers = [c.args[0] for c in app.add_handler.call_args_list]
    chat_member = [h for h in handlers if isinstance(h, ChatMemberHandler)]
    assert len(chat_member) == 1
    assert chat_member[0].chat_member_types == ChatMemberHandler.MY_CHAT_MEMBER
    assert chat_member[0].block is False


def _bot_que_bloquean(bloqueados):
    async def send_message(chat_id, **kwargs):
        if chat_id in bloqueados:
            raise Forbidden("Forbidden: bot was blocked by the user")

    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=send_message)
    return bot


class TestMsMarcaInalcanzables:
    @pytest.mark.asyncio
    async def test_broadcast_marca_solo_a_quienes_bloquearon(self):
        from src.handlers.ms import _run_broadcast

        api = MagicMock(set_user_reachability=AsyncMock())
        status = MagicMock(edit_text=AsyncMock())

        await _run_broadcast(
            _bot_que_bloquean({2}), {"kind": "text", "text": "hola"}, [1, 2, 3], status, api
        )

        api.set_user_reachability.assert_awaited_once_with(user_id=2, reachable=False)

    @pytest.mark.asyncio
    async def test_broadcast_sin_api_client_sigue_funcionando(self):
        from src.handlers.ms import _run_broadcast

        status = MagicMock(edit_text=AsyncMock())

        await _run_broadcast(
            _bot_que_bloquean({2}), {"kind": "text", "text": "hola"}, [1, 2], status
        )  # no debe lanzar

        status.edit_text.assert_awaited()

    @pytest.mark.asyncio
    async def test_envio_directo_a_un_usuario_que_bloqueo_lo_marca(self):
        from src.handlers.ms import confirm_callback

        api = MagicMock(set_user_reachability=AsyncMock())
        payload = {"kind": "text", "text": "x", "target_user_id": 9, "target_username": "ana_x"}
        query = MagicMock(data="ms_confirm:5", edit_message_text=AsyncMock(), answer=AsyncMock())
        query.from_user.id = 5
        update = MagicMock(callback_query=query)
        context = MagicMock(bot=_bot_que_bloquean({9}))
        context.bot_data = {"ms_pending": {5: payload}, "api_client": api}

        await confirm_callback(update, context)

        api.set_user_reachability.assert_awaited_once_with(user_id=9, reachable=False)
