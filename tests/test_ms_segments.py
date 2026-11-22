"""taso-bot#72 Fase 4: segmentos de difusion en /ms.

`/ms #activos <texto>` difunde solo a un segmento; la vista previa dice cuantos son
y el registro de F3 guarda el segmento.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


def _update_ms(texto, reply=None):
    update = MagicMock()
    update.effective_user.id = 5
    update.effective_user.username = "adm"
    update.message.text = texto
    update.message.reply_to_message = reply
    update.message.reply_text = AsyncMock()
    return update


def _context(api):
    ctx = MagicMock()
    ctx.bot_data = {"api_client": api}
    return ctx


def _api(ids=(1, 2, 3)):
    return MagicMock(
        admin_key="k",
        admin_list_user_ids=AsyncMock(return_value=list(ids)),
        log_broadcast=AsyncMock(),
        set_user_reachability=AsyncMock(),
    )


class TestExtractPayload:
    def test_sin_segmento_es_todos(self):
        from src.handlers.ms import _extract_payload

        assert _extract_payload(_update_ms("/ms hola a todos"))["segment"] == "todos"

    @pytest.mark.parametrize("seg", ["activos", "alertas", "tspl", "year"])
    def test_el_segmento_sale_del_primer_token_y_no_forma_parte_del_mensaje(self, seg):
        from src.handlers.ms import _extract_payload

        payload = _extract_payload(_update_ms(f"/ms #{seg} hola equipo"))

        assert payload["segment"] == seg
        assert payload["text"] == "hola equipo"

    def test_un_hashtag_que_no_es_segmento_es_texto_normal(self):
        from src.handlers.ms import _extract_payload

        payload = _extract_payload(_update_ms("/ms #vip hola"))

        assert payload["segment"] == "todos"
        assert payload["text"] == "#vip hola"

    def test_segmento_en_reply_a_foto(self):
        from src.handlers.ms import _extract_payload

        reply = MagicMock(caption="cap", text=None)
        reply.photo = [MagicMock(file_id="F")]

        payload = _extract_payload(_update_ms("/ms #activos", reply=reply))

        assert (payload["kind"], payload["segment"], payload["caption"]) == ("photo", "activos", "cap")


class TestClienteSegmento:
    @pytest.mark.asyncio
    async def test_pasa_el_segmento_a_la_api(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        client._get_with_retry = AsyncMock(return_value={"ok": True, "data": [1, 2]})

        ids = await client.admin_list_user_ids("activos")

        assert ids == [1, 2]
        assert client._get_with_retry.await_args.kwargs["params"] == {"segmento": "activos"}

    @pytest.mark.asyncio
    async def test_todos_no_manda_parametro_y_se_comporta_como_antes(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        client._get_with_retry = AsyncMock(return_value={"ok": True, "data": [1]})

        await client.admin_list_user_ids()

        assert not client._get_with_retry.await_args.kwargs.get("params")


class TestVistaPrevia:
    @pytest.mark.asyncio
    async def test_dice_el_segmento_y_el_conteo_real(self, monkeypatch):
        import src.handlers.ms as ms

        monkeypatch.setattr(ms, "is_admin", lambda _id: True)
        api, update = _api(ids=[7, 8]), _update_ms("/ms #alertas ojo con el precio")

        await ms.ms_command(update, _context(api))

        api.admin_list_user_ids.assert_awaited_once_with("alertas")
        texto = update.message.reply_text.await_args.args[0]
        assert "*2*" in texto and "alertas" in texto

    @pytest.mark.asyncio
    async def test_segmento_vacio_no_arma_envio(self, monkeypatch):
        import src.handlers.ms as ms

        monkeypatch.setattr(ms, "is_admin", lambda _id: True)
        api, update = _api(ids=[]), _update_ms("/ms #tspl hola")
        ctx = _context(api)

        await ms.ms_command(update, ctx)

        assert "tspl" in update.message.reply_text.await_args.args[0]
        assert not ctx.bot_data.get("ms_pending")


class TestConfirmarYRegistrar:
    @pytest.mark.asyncio
    async def test_confirmar_vuelve_a_pedir_el_mismo_segmento(self):
        from src.handlers.ms import confirm_callback

        api = _api(ids=[1, 2])
        status = MagicMock(edit_text=AsyncMock())
        query = MagicMock(
            data="ms_confirm:5", edit_message_text=AsyncMock(return_value=status), answer=AsyncMock()
        )
        query.from_user.id = 5
        context = MagicMock(bot=MagicMock(send_message=AsyncMock(), send_photo=AsyncMock()))
        context.bot_data = {
            "ms_pending": {5: {"kind": "text", "text": "x", "segment": "year"}},
            "api_client": api,
        }

        await confirm_callback(MagicMock(callback_query=query), context)

        api.admin_list_user_ids.assert_awaited_once_with("year")
        assert api.log_broadcast.await_args.kwargs["segment"] == "year"
