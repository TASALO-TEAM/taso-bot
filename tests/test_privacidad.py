"""taso-bot#72 Fase 5: /privacidad (borrar mis datos) y /silencio (sin difusiones)."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _limiter_limpio():
    from src import user_seen

    user_seen._last_sent.clear()
    yield
    user_seen._last_sent.clear()


def _client_con_post(respuesta=None, error=None):
    from src.api_client import TasaloApiClient

    client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
    http = MagicMock()
    resp = MagicMock(raise_for_status=MagicMock(), json=MagicMock(return_value=respuesta))
    http.post = AsyncMock(side_effect=error) if error else AsyncMock(return_value=resp)
    client._get_client = MagicMock(return_value=http)
    return client, http


def _command_update(user_id=7):
    u = MagicMock()
    u.effective_user.id = user_id
    u.message.reply_text = AsyncMock()
    return u


def _callback_update(data, user_id=7):
    u = MagicMock()
    u.callback_query.data = data
    u.callback_query.from_user.id = user_id
    u.callback_query.answer = AsyncMock()
    u.callback_query.edit_message_text = AsyncMock()
    return u


def _context(api_client):
    ctx = MagicMock()
    ctx.bot_data = {"api_client": api_client}
    return ctx


def _botones(reply_text_mock):
    markup = reply_text_mock.call_args.kwargs["reply_markup"]
    return [b.callback_data for fila in markup.inline_keyboard for b in fila]


class TestClienteErase:
    @pytest.mark.asyncio
    async def test_envia_el_user_id_y_devuelve_el_resultado(self):
        client, http = _client_con_post({"ok": True, "deleted_rows": 6, "tickets_anonymized": 1})

        result = await client.erase_user_data(7)

        args, kwargs = http.post.call_args
        assert args[0] == "http://test:8000/api/v1/admin/stats/users/privacy"
        assert kwargs["json"] == {"user_id": 7}
        assert kwargs["headers"] == client._admin_headers
        assert result == {"ok": True, "deleted_rows": 6, "tickets_anonymized": 1}

    @pytest.mark.asyncio
    async def test_un_fallo_de_red_devuelve_none_sin_propagar(self):
        client, _ = _client_con_post(error=RuntimeError("caido"))

        assert await client.erase_user_data(7) is None

    @pytest.mark.asyncio
    async def test_sin_admin_key_devuelve_none_y_no_llama(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="")
        http = MagicMock(post=AsyncMock())
        client._get_client = MagicMock(return_value=http)

        assert await client.erase_user_data(7) is None
        http.post.assert_not_called()


class TestClienteMute:
    @pytest.mark.asyncio
    async def test_envia_user_id_y_muted_y_devuelve_found(self):
        client, http = _client_con_post({"ok": True, "found": True})

        found = await client.set_user_muted(7, True)

        args, kwargs = http.post.call_args
        assert args[0] == "http://test:8000/api/v1/admin/stats/users/mute"
        assert kwargs["json"] == {"user_id": 7, "muted": True}
        assert found is True

    @pytest.mark.asyncio
    async def test_un_fallo_de_red_devuelve_none(self):
        client, _ = _client_con_post(error=RuntimeError("caido"))

        assert await client.set_user_muted(7, False) is None


class TestPrivacidad:
    @pytest.mark.asyncio
    async def test_comando_pide_confirmacion_y_no_borra_nada(self):
        from src.handlers.privacidad import privacidad_command

        api = MagicMock(erase_user_data=AsyncMock())
        update = _command_update()

        await privacidad_command(update, _context(api))

        assert _botones(update.message.reply_text) == ["privacidad:ok", "privacidad:no"]
        api.erase_user_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancelar_no_borra(self):
        from src.handlers.privacidad import privacidad_callback

        api = MagicMock(erase_user_data=AsyncMock())
        update = _callback_update("privacidad:no")

        await privacidad_callback(update, _context(api), "privacidad:no")

        api.erase_user_data.assert_not_called()
        update.callback_query.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_confirmar_borra_al_usuario_que_pulso_el_boton(self):
        from src.handlers.privacidad import privacidad_callback

        api = MagicMock(erase_user_data=AsyncMock(return_value={"ok": True, "deleted_rows": 6, "tickets_anonymized": 1}))
        update = _callback_update("privacidad:ok", user_id=42)

        await privacidad_callback(update, _context(api), "privacidad:ok")

        api.erase_user_data.assert_awaited_once_with(42)
        texto = update.callback_query.edit_message_text.call_args.args[0]
        assert "copias de seguridad" in texto

    @pytest.mark.asyncio
    async def test_tras_borrar_el_siguiente_mensaje_vuelve_a_registrarlo(self):
        from src import user_seen
        from src.handlers.privacidad import privacidad_callback

        user_seen._last_sent[42] = 123.0  # registrado hace poco
        api = MagicMock(erase_user_data=AsyncMock(return_value={"ok": True, "deleted_rows": 1, "tickets_anonymized": 0}))

        await privacidad_callback(_callback_update("privacidad:ok", user_id=42), _context(api), "privacidad:ok")

        assert 42 not in user_seen._last_sent

    @pytest.mark.asyncio
    async def test_si_la_api_falla_avisa_y_no_dice_que_borro(self):
        from src import user_seen
        from src.handlers.privacidad import privacidad_callback

        user_seen._last_sent[42] = 123.0
        api = MagicMock(erase_user_data=AsyncMock(return_value=None))
        update = _callback_update("privacidad:ok", user_id=42)

        await privacidad_callback(update, _context(api), "privacidad:ok")

        texto = update.callback_query.edit_message_text.call_args.args[0]
        assert "copias de seguridad" not in texto
        assert "No pude" in texto
        assert user_seen._last_sent[42] == 123.0


class TestSilencio:
    @pytest.mark.asyncio
    async def test_comando_ofrece_silenciar_o_reactivar_sin_llamar_a_la_api(self):
        from src.handlers.privacidad import silencio_command

        api = MagicMock(set_user_muted=AsyncMock())
        update = _command_update()

        await silencio_command(update, _context(api))

        assert _botones(update.message.reply_text) == ["silencio:on", "silencio:off"]
        api.set_user_muted.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("data,muted", [("silencio:on", True), ("silencio:off", False)])
    async def test_boton_aplica_el_estado_al_usuario_que_pulso(self, data, muted):
        from src.handlers.privacidad import silencio_callback

        api = MagicMock(set_user_muted=AsyncMock(return_value=True))
        update = _callback_update(data, user_id=42)

        await silencio_callback(update, _context(api), data)

        api.set_user_muted.assert_awaited_once_with(42, muted)
        update.callback_query.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("respuesta", [False, None])
    async def test_si_no_se_pudo_aplicar_avisa(self, respuesta):
        from src.handlers.privacidad import silencio_callback

        api = MagicMock(set_user_muted=AsyncMock(return_value=respuesta))
        update = _callback_update("silencio:on")

        await silencio_callback(update, _context(api), "silencio:on")

        assert "No pude" in update.callback_query.edit_message_text.call_args.args[0]


class TestRegistroAutomaticoNoRecreaAlBorrar:
    @pytest.mark.asyncio
    async def test_el_clic_de_confirmar_no_cuenta_como_visto(self):
        from src.user_seen import mark_seen

        api = MagicMock(mark_user_seen=AsyncMock())
        update = _callback_update("privacidad:ok")
        update.effective_user.is_bot = False
        update.my_chat_member = None

        await mark_seen(update, _context(api))

        api.mark_user_seen.assert_not_called()

    @pytest.mark.asyncio
    async def test_otros_botones_siguen_registrando(self):
        from src.user_seen import mark_seen

        api = MagicMock(mark_user_seen=AsyncMock())
        update = _callback_update("menu_open")
        update.effective_user.id = 7
        update.effective_user.username = "ana"
        update.effective_user.first_name = "Ana"
        update.effective_user.is_bot = False
        update.my_chat_member = None

        await mark_seen(update, _context(api))

        api.mark_user_seen.assert_awaited_once()


class TestComandosRegistrados:
    def test_son_publicos_y_atienden_sus_botones(self):
        from src.commands import COMANDOS

        por_nombre = {c.name: c for c in COMANDOS}
        for nombre in ("privacidad", "silencio"):
            cmd = por_nombre[nombre]
            assert cmd.admin is False
            assert cmd.callback is not None
            assert cmd.rutas() == (nombre,)
