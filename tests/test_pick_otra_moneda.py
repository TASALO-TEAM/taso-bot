"""F6-T5: 'otra moneda' por texto en los selectores de pick."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.ext import ApplicationHandlerStop


def _datas(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def _query_update(data):
    q = MagicMock()
    q.data = data
    q.from_user.id = 7
    q.edit_message_text = AsyncMock()
    q.message.reply_text = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    return u, q


def _text_update(texto):
    msg = MagicMock()
    msg.text = texto
    msg.reply_text = AsyncMock()
    u = MagicMock()
    u.message = msg
    u.effective_user.id = 7
    return u, msg


@pytest.mark.parametrize("flow", ["p", "ta", "graf", "alert"])
def test_selector_de_moneda_ofrece_otra_moneda(flow):
    from src.pick import render

    assert f"pick:{flow}:otra" in _datas(render((flow,))[1])


@pytest.mark.parametrize("sym", ["LINK", "SHIB", "A1", "ABCDEFGHIJ"])
def test_simbolo_libre_valido_se_acepta_en_parse(sym):
    from src.pick import parse

    assert parse(("ta", sym)) == ("ta", sym, None)


@pytest.mark.parametrize("sym", ["link", "A", "ABCDEFGHIJK", "BT C", "BTC;", "otra", ""])
def test_simbolo_libre_invalido_no_pasa_parse(sym):
    from src.pick import parse

    assert parse(("ta", sym)) is None


def test_todo_callback_con_simbolo_largo_cabe_en_64_bytes():
    from src.pick import render

    for flow in ("ta", "graf", "alert"):
        assert all(len(d.encode()) <= 64 for d in _datas(render((flow, "ABCDEFGHIJ"))[1]))


def test_boton_otra_moneda_arma_la_espera_y_pide_el_simbolo():
    from src import pick

    u, q = _query_update("pick:ta:otra")
    ctx = MagicMock()
    ctx.user_data = {"waiting_for_time": True, "tkt_awaiting": "bug", "awaiting_tspl_hour": 1,
                     "explorer_waiting": 1.0}
    asyncio.run(pick.pick_callback(u, ctx, "pick:ta:otra"))
    assert ctx.user_data[pick.ESPERA][0] == "ta"
    # cambia de intencion: el resto de flujos de texto libre quedan cancelados
    assert not ctx.user_data.get("waiting_for_time")
    assert "tkt_awaiting" not in ctx.user_data and "awaiting_tspl_hour" not in ctx.user_data
    assert "explorer_waiting" not in ctx.user_data
    texto = q.edit_message_text.await_args.args[0]
    assert "s\u00edmbolo" in texto.lower()


def test_texto_sin_espera_no_hace_nada_ni_corta_la_cadena():
    from src import pick

    u, msg = _text_update("LINK")
    ctx = MagicMock()
    ctx.user_data = {}
    asyncio.run(pick.pick_text(u, ctx))  # no lanza ApplicationHandlerStop
    msg.reply_text.assert_not_awaited()


def test_espera_caducada_se_ignora_y_se_limpia():
    from src import pick

    u, msg = _text_update("LINK")
    ctx = MagicMock()
    ctx.user_data = {pick.ESPERA: ("ta", time.monotonic() - pick.ESPERA_TTL - 1)}
    asyncio.run(pick.pick_text(u, ctx))
    msg.reply_text.assert_not_awaited()
    assert pick.ESPERA not in ctx.user_data


def test_simbolo_valido_en_ta_muestra_temporalidades_y_corta_la_cadena():
    from src import pick

    u, msg = _text_update("  link ")
    ctx = MagicMock()
    ctx.user_data = {pick.ESPERA: ("ta", time.monotonic())}
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(pick.pick_text(u, ctx))
    assert pick.ESPERA not in ctx.user_data
    markup = msg.reply_text.await_args.kwargs["reply_markup"]
    assert "pick:ta:LINK:1h" in _datas(markup)


def test_simbolo_valido_en_p_ejecuta_p_command(monkeypatch):
    from src import pick
    from src.handlers import p as p_mod

    llamado = {}

    async def fake(update, context):
        llamado["args"] = list(context.args)

    monkeypatch.setattr(p_mod, "p_command", fake)
    u, msg = _text_update("shib")
    ctx = MagicMock()
    ctx.user_data = {pick.ESPERA: ("p", time.monotonic())}
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(pick.pick_text(u, ctx))
    assert llamado["args"] == ["SHIB"]


def test_simbolo_invalido_avisa_mantiene_la_espera_y_corta_la_cadena():
    from src import pick

    u, msg = _text_update("esto no es una moneda!!")
    ctx = MagicMock()
    ctx.user_data = {pick.ESPERA: ("ta", time.monotonic())}
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(pick.pick_text(u, ctx))
    assert pick.ESPERA in ctx.user_data  # puede reintentar
    msg.reply_text.assert_awaited_once()


def test_el_texto_del_usuario_no_se_registra(caplog):
    from src import pick

    caplog.set_level("DEBUG")
    u, _ = _text_update("secreto$$")
    ctx = MagicMock()
    ctx.user_data = {pick.ESPERA: ("ta", time.monotonic())}
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(pick.pick_text(u, ctx))
    assert "secreto" not in caplog.text


def test_register_pone_el_handler_antes_que_el_explorador():
    from src import pick

    app = MagicMock()
    pick.register(app)
    args, kwargs = app.add_handler.call_args
    assert kwargs.get("group") == -2
