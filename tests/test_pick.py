"""F6-T5: selectores por botones para /p, /ta y /graf (sin escribir argumentos)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest


def _datas(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def _update(data):
    q = MagicMock()
    q.data = data
    q.from_user.id = 7
    q.edit_message_text = AsyncMock()
    q.message.reply_text = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    return u, q


@pytest.mark.parametrize("flow", ["p", "ta", "graf"])
def test_selector_de_moneda_tiene_monedas_e_inicio(flow):
    from src.pick import COINS, render

    texto, markup = render((flow,))
    datas = _datas(markup)
    assert texto
    for c in COINS:
        assert f"pick:{flow}:{c}" in datas
    assert "menu:home" in datas


@pytest.mark.parametrize("flow", ["ta", "graf"])
def test_selector_de_temporalidad_tiene_atras_e_inicio(flow):
    from src.pick import TFS, render

    _, markup = render((flow, "BTC"))
    datas = _datas(markup)
    for tf in TFS:
        assert f"pick:{flow}:BTC:{tf}" in datas
    assert f"pick:{flow}" in datas  # Atras a las monedas
    assert "menu:home" in datas


def test_todo_callback_cabe_en_64_bytes():
    from src.pick import COINS, FLOWS, render

    for flow in FLOWS:
        todos = _datas(render((flow,))[1])
        if flow != "p":
            for c in COINS:
                todos += _datas(render((flow, c))[1])
        assert all(len(d.encode()) <= 64 for d in todos)


@pytest.mark.parametrize(
    "args",
    [(), ("x",), ("p", "ZZZ"), ("ta", "BTC", "9x"), ("ta", "BTC", "1h", "extra"), ("p", "BTC", "1h"), ("graf", "btc;rm")],
)
def test_entrada_invalida_no_se_resuelve(args):
    from src.pick import parse

    assert parse(args) is None


def test_parse_acepta_lo_valido():
    from src.pick import parse

    assert parse(("p",)) == ("p", None, None)
    assert parse(("ta", "BTC")) == ("ta", "BTC", None)
    assert parse(("p", "BTC")) == ("p", "BTC", None)
    assert parse(("graf", "ETH", "4h")) == ("graf", "ETH", "4h")


def test_pantalla_edita_el_mensaje_en_sitio():
    from src.pick import pick_callback

    u, q = _update("pick:ta")
    asyncio.run(pick_callback(u, MagicMock(), "pick:ta"))
    q.edit_message_text.assert_awaited_once()
    assert "pick:ta:BTC" in _datas(q.edit_message_text.call_args.kwargs["reply_markup"])


def test_message_not_modified_se_ignora():
    from src.pick import pick_callback

    u, q = _update("pick:ta")
    q.edit_message_text.side_effect = BadRequest("Message is not modified")
    asyncio.run(pick_callback(u, MagicMock(), "pick:ta"))
    q.message.reply_text.assert_not_awaited()


def test_p_con_moneda_ejecuta_p_command(monkeypatch):
    import src.handlers.p as p
    from src.pick import pick_callback

    llamado = AsyncMock()
    monkeypatch.setattr(p, "p_command", llamado)
    u, _ = _update("pick:p:BTC")
    ctx = MagicMock()
    asyncio.run(pick_callback(u, ctx, "pick:p:BTC"))
    llamado.assert_awaited_once()
    assert ctx.args == ["BTC"]


def test_ta_con_moneda_y_tf_ejecuta_ta_command(monkeypatch):
    import src.handlers.ta as ta
    from src.pick import pick_callback

    llamado = AsyncMock()
    monkeypatch.setattr(ta, "ta_command", llamado)
    u, _ = _update("pick:ta:ETH:4h")
    asyncio.run(pick_callback(u, MagicMock(), "pick:ta:ETH:4h"))
    kw = llamado.call_args.kwargs
    assert kw["override_args"] == ["ETH", "USDT", "4h"]
    assert kw["override_source"] == "BINANCE"


def test_graf_con_moneda_y_tf_ejecuta_do_graf(monkeypatch):
    import src.handlers.trading as tr
    from src.pick import pick_callback

    llamado = AsyncMock()
    monkeypatch.setattr(tr, "_do_graf", llamado)
    u, _ = _update("pick:graf:SOL:1d")
    asyncio.run(pick_callback(u, MagicMock(), "pick:graf:SOL:1d"))
    kw = llamado.call_args.kwargs
    assert (kw["base"], kw["quote"], kw["timeframe"], kw["is_callback"]) == ("SOL", "USDT", "1d", True)


def test_dato_falso_cae_en_la_bienvenida_sin_ejecutar_nada(monkeypatch):
    import src.handlers.ta as ta
    import src.pick as pick

    llamado = AsyncMock()
    monkeypatch.setattr(ta, "ta_command", llamado)
    u, q = _update("pick:ta:ZZZ:4h")
    asyncio.run(pick.pick_callback(u, MagicMock(), "pick:ta:ZZZ:4h"))
    llamado.assert_not_awaited()
    q.edit_message_text.assert_awaited_once()  # bienvenida


def test_registrado_por_el_contrato():
    from src.commands import COMANDOS
    from src.pick import pick_callback

    assert any("pick" in c.rutas() and c.callback is pick_callback for c in COMANDOS)


def test_los_botones_de_ayuda_de_p_y_ta_abren_el_selector():
    from src.handlers.start import PICK_DESDE_START

    assert PICK_DESDE_START == {"p_help": "p", "ta_help": "ta", "alert_help": "alert"}


def test_el_router_real_despacha_pick():
    from src.handlers import callback_router as r

    u, q = _update("pick:ta")
    q.answer = AsyncMock()
    q.message.chat_id = 1
    q.message.message_id = 2
    asyncio.run(r.callback_router(u, MagicMock()))
    q.edit_message_text.assert_awaited_once()
    assert "pick:ta:BTC" in _datas(q.edit_message_text.call_args.kwargs["reply_markup"])


# --- /alert por botones: moneda -> nivel (%) sobre el precio actual ---


def _alerta_falsa(monkeypatch, precio):
    import src.handlers.alert as al

    crypto = MagicMock()
    crypto.get_crypto_data = AsyncMock(return_value={"price": precio} if precio else None)
    api = MagicMock()
    api.create_price_alert = AsyncMock(return_value=True)
    monkeypatch.setattr(al, "get_crypto_client", lambda: crypto)
    monkeypatch.setattr(al, "_get_api_client", lambda ctx: api)
    return api


def test_alert_pantallas_moneda_y_nivel():
    from src.pick import COINS, LEVELS, render

    _, m1 = render(("alert",))
    d1 = _datas(m1)
    for c in COINS:
        assert f"pick:alert:{c}" in d1
    assert "alert_back" in d1 and "menu:home" in d1  # Atras a "mis alertas"

    _, m2 = render(("alert", "BTC"))
    d2 = _datas(m2)
    for k in LEVELS:
        assert f"pick:alert:BTC:{k}" in d2
    assert "pick:alert" in d2 and "menu:home" in d2
    assert all(len(d.encode()) <= 64 for d in d1 + d2)


@pytest.mark.parametrize("args", [("alert", "BTC", "m99"), ("alert", "ZZZ"), ("alert", "BTC", "1h"), ("ta", "BTC", "p5")])
def test_alert_entrada_invalida(args):
    from src.pick import parse

    assert parse(args) is None


def test_alert_crea_con_el_nivel_elegido(monkeypatch):
    from src.pick import pick_callback

    api = _alerta_falsa(monkeypatch, 100.0)
    u, q = _update("pick:alert:BTC:p10")
    asyncio.run(pick_callback(u, MagicMock(), "pick:alert:BTC:p10"))
    uid, coin, objetivo, actual = api.create_price_alert.call_args.args
    assert (uid, coin, actual) == (7, "BTC", 100.0)
    assert objetivo == pytest.approx(110.0)
    texto = q.edit_message_text.call_args.args[0]
    assert "Alerta creada" in texto
    assert "alert_back" in _datas(q.edit_message_text.call_args.kwargs["reply_markup"])


def test_alert_nivel_negativo_baja_el_objetivo(monkeypatch):
    from src.pick import pick_callback

    api = _alerta_falsa(monkeypatch, 200.0)
    u, _ = _update("pick:alert:ETH:m5")
    asyncio.run(pick_callback(u, MagicMock(), "pick:alert:ETH:m5"))
    assert api.create_price_alert.call_args.args[2] == pytest.approx(190.0)


def test_alert_sin_precio_no_crea_y_avisa(monkeypatch):
    from src.pick import pick_callback

    api = _alerta_falsa(monkeypatch, None)
    u, q = _update("pick:alert:BTC:p5")
    asyncio.run(pick_callback(u, MagicMock(), "pick:alert:BTC:p5"))
    api.create_price_alert.assert_not_awaited()
    assert "precio actual" in q.edit_message_text.call_args.args[0].lower()


def test_alert_error_de_la_api_avisa(monkeypatch):
    from src.pick import pick_callback

    api = _alerta_falsa(monkeypatch, 100.0)
    api.create_price_alert.return_value = None
    u, q = _update("pick:alert:BTC:p5")
    asyncio.run(pick_callback(u, MagicMock(), "pick:alert:BTC:p5"))
    assert "Alerta creada" not in q.edit_message_text.call_args.args[0]


def test_crear_alerta_desde_el_menu_abre_el_selector():
    from src.handlers.alert import alert_create_callback

    u, q = _update("alert_create")
    q.answer = AsyncMock()
    asyncio.run(alert_create_callback(u, MagicMock()))
    assert "pick:alert:BTC" in _datas(q.edit_message_text.call_args.kwargs["reply_markup"])
