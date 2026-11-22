"""taso-bot#72 Fase 3: historial de difusiones (POST/GET /admin/stats/broadcasts).

Cada /ms masivo queda registrado en la API con sus contadores (nunca el texto) y
`/ms historial` muestra las ultimas.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from telegram.error import Forbidden


def _item(**over):
    base = {
        "created_at": "2026-11-22T18:30:00+00:00", "admin_id": 5, "kind": "text",
        "segment": "todos", "recipients": 10, "ok": 8, "blocked": 1, "errors": 1,
        "duration_s": 2.5,
    }
    base.update(over)
    return base


def _hora_cuba(dt_utc):
    return dt_utc.astimezone(ZoneInfo("America/Havana")).strftime("%d/%m %H:%M")


_18_30_UTC = datetime(2026, 11, 22, 18, 30, tzinfo=timezone.utc)


def _bot_que_bloquean(bloqueados):
    async def enviar(chat_id, **kwargs):
        if chat_id in bloqueados:
            raise Forbidden("Forbidden: bot was blocked by the user")

    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=enviar)
    bot.send_photo = AsyncMock(side_effect=enviar)
    return bot


class TestClienteLogBroadcast:
    @pytest.mark.asyncio
    async def test_envia_los_contadores_al_endpoint_admin(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        http = MagicMock()
        http.post = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
        client._get_client = MagicMock(return_value=http)

        await client.log_broadcast(
            admin_id=5, kind="photo", segment="todos", recipients=10,
            ok=8, blocked=1, errors=1, duration_s=2.5,
        )

        args, kwargs = http.post.call_args
        assert args[0] == "http://test:8000/api/v1/admin/stats/broadcasts"
        assert kwargs["json"] == {
            "admin_id": 5, "kind": "photo", "segment": "todos", "recipients": 10,
            "ok": 8, "blocked": 1, "errors": 1, "duration_s": 2.5,
        }
        assert kwargs["headers"] == client._admin_headers

    @pytest.mark.asyncio
    async def test_un_fallo_de_red_no_propaga(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        http = MagicMock()
        http.post = AsyncMock(side_effect=RuntimeError("caido"))
        client._get_client = MagicMock(return_value=http)

        await client.log_broadcast(
            admin_id=5, kind="text", segment="todos", recipients=1,
            ok=1, blocked=0, errors=0, duration_s=0.1,
        )  # no debe lanzar


class TestClienteListBroadcasts:
    @pytest.mark.asyncio
    async def test_devuelve_la_lista_y_pide_el_limite(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        client._get_with_retry = AsyncMock(return_value={"ok": True, "data": [_item()]})

        assert await client.list_broadcasts(limit=5) == [_item()]

        args, kwargs = client._get_with_retry.call_args
        assert args[0] == "http://test:8000/api/v1/admin/stats/broadcasts"
        assert kwargs["params"] == {"limit": 5}
        assert kwargs["headers"] == client._admin_headers

    @pytest.mark.asyncio
    async def test_un_error_devuelve_lista_vacia(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        client._get_with_retry = AsyncMock(side_effect=RuntimeError("caido"))

        assert await client.list_broadcasts() == []

    @pytest.mark.asyncio
    async def test_sin_admin_key_devuelve_lista_vacia(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="")
        client._get_with_retry = AsyncMock()

        assert await client.list_broadcasts() == []
        client._get_with_retry.assert_not_awaited()


class TestRunBroadcastRegistra:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload,kind",
        [
            ({"kind": "text", "text": "hola"}, "text"),
            ({"kind": "photo", "photo_file_id": "f", "caption": "c"}, "photo"),
        ],
    )
    async def test_registra_los_contadores_al_terminar(self, payload, kind):
        from src.handlers.ms import _run_broadcast

        api = MagicMock(set_user_reachability=AsyncMock(), log_broadcast=AsyncMock())
        status = MagicMock(edit_text=AsyncMock())

        await _run_broadcast(
            _bot_que_bloquean({2}), payload, [1, 2, 3], status, api, admin_id=5
        )

        api.log_broadcast.assert_awaited_once()
        kw = api.log_broadcast.await_args.kwargs
        assert (kw["admin_id"], kw["kind"], kw["segment"]) == (5, kind, "todos")
        assert (kw["recipients"], kw["ok"], kw["blocked"], kw["errors"]) == (3, 2, 1, 0)
        assert kw["duration_s"] >= 0

    @pytest.mark.asyncio
    async def test_no_registra_sin_admin_id(self):
        from src.handlers.ms import _run_broadcast

        api = MagicMock(set_user_reachability=AsyncMock(), log_broadcast=AsyncMock())
        status = MagicMock(edit_text=AsyncMock())

        await _run_broadcast(
            _bot_que_bloquean(set()), {"kind": "text", "text": "hola"}, [1], status, api
        )

        api.log_broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sin_api_client_sigue_funcionando(self):
        from src.handlers.ms import _run_broadcast

        status = MagicMock(edit_text=AsyncMock())

        await _run_broadcast(
            _bot_que_bloquean(set()), {"kind": "text", "text": "hola"}, [1], status,
            None, admin_id=5,
        )  # no debe lanzar

        status.edit_text.assert_awaited()

    @pytest.mark.asyncio
    async def test_confirmar_pasa_el_admin_que_difunde(self):
        from src.handlers.ms import confirm_callback

        api = MagicMock(
            admin_list_user_ids=AsyncMock(return_value=[1, 2]),
            set_user_reachability=AsyncMock(),
            log_broadcast=AsyncMock(),
        )
        status = MagicMock(edit_text=AsyncMock())
        query = MagicMock(
            data="ms_confirm:5", edit_message_text=AsyncMock(return_value=status),
            answer=AsyncMock(),
        )
        query.from_user.id = 5
        update = MagicMock(callback_query=query)
        context = MagicMock(bot=_bot_que_bloquean(set()))
        context.bot_data = {"ms_pending": {5: {"kind": "text", "text": "x"}}, "api_client": api}

        await confirm_callback(update, context)

        kw = api.log_broadcast.await_args.kwargs
        assert (kw["admin_id"], kw["recipients"]) == (5, 2)


class TestHistoryText:
    def test_formatea_la_hora_de_cuba_y_los_contadores(self):
        from src.handlers.ms import _history_text

        texto = _history_text(
            [_item(), _item(kind="photo", recipients=3, ok=3, blocked=0, errors=0, duration_s=0.4)]
        )

        assert _hora_cuba(_18_30_UTC) in texto
        assert "10 dest." in texto and "3 dest." in texto
        assert "foto" in texto and "texto" in texto
        assert "2.5s" in texto and "0.4s" in texto

    def test_una_fecha_sin_zona_se_toma_como_utc(self):
        from src.handlers.ms import _history_text

        texto = _history_text([_item(created_at="2026-11-22T18:30:00")])

        assert _hora_cuba(_18_30_UTC) in texto

    def test_acepta_el_formato_real_de_la_api_con_z_y_microsegundos(self):
        from src.handlers.ms import _history_text

        texto = _history_text([_item(created_at="2026-11-22T18:30:00.123456Z")])

        assert _hora_cuba(_18_30_UTC) in texto

    def test_sin_difusiones_lo_dice(self):
        from src.handlers.ms import _history_text

        assert "no hay difusiones" in _history_text([])


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


def _api(**over):
    api = MagicMock(
        admin_key="k",
        list_broadcasts=AsyncMock(return_value=[_item()]),
        admin_list_user_ids=AsyncMock(return_value=[1, 2, 3]),
    )
    for k, v in over.items():
        setattr(api, k, v)
    return api


class TestMsHistorial:
    @pytest.mark.asyncio
    async def test_muestra_las_ultimas_difusiones_sin_preparar_un_envio(self, monkeypatch):
        import src.handlers.ms as ms

        monkeypatch.setattr(ms, "is_admin", lambda _id: True)
        api, update = _api(), _update_ms("/ms historial")
        ctx = _context(api)

        await ms.ms_command(update, ctx)

        api.list_broadcasts.assert_awaited_once_with(ms.HISTORY_LIMIT)
        texto = update.message.reply_text.await_args.args[0]
        assert "10 dest." in texto
        api.admin_list_user_ids.assert_not_awaited()
        assert not ctx.bot_data.get("ms_pending")

    @pytest.mark.asyncio
    async def test_un_no_admin_no_ve_el_historial(self, monkeypatch):
        import src.handlers.ms as ms

        monkeypatch.setattr(ms, "is_admin", lambda _id: False)
        api, update = _api(), _update_ms("/ms historial")

        await ms.ms_command(update, _context(api))

        api.list_broadcasts.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_historial_con_mas_texto_sigue_siendo_una_difusion(self, monkeypatch):
        import src.handlers.ms as ms

        monkeypatch.setattr(ms, "is_admin", lambda _id: True)
        api, update = _api(), _update_ms("/ms historial de ayer")

        await ms.ms_command(update, _context(api))

        api.list_broadcasts.assert_not_awaited()
        api.admin_list_user_ids.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_historial_como_reply_sigue_siendo_una_difusion(self, monkeypatch):
        import src.handlers.ms as ms

        monkeypatch.setattr(ms, "is_admin", lambda _id: True)
        reply = MagicMock(photo=None, text="otro texto", caption=None)
        api, update = _api(), _update_ms("/ms historial", reply=reply)

        await ms.ms_command(update, _context(api))

        api.list_broadcasts.assert_not_awaited()
        api.admin_list_user_ids.assert_awaited_once()
