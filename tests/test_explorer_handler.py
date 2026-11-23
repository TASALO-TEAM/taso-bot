"""Integracion del explorador (F4-T7): /explorar, boton del menu y texto libre en privado."""

import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import commands
from src.explorer import handler as h
from src.explorer import sources
from src.explorer.guard import UserLimiter

BTC = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"   # genesis, checksum valido
EVM = "0x" + "ab" * 20
DATOS_BTC = {"saldo_sats": 5_000_000_000, "recibido_sats": 5_000_000_000, "gastado_sats": 0,
             "tx_count": 1, "pendiente_sats": 0, "tx_pendientes": 0}
DATOS_HIVE = {"nombre": "blocktrades", "hive": 1.0, "hbd": 2.0, "hp": 3.0, "posts": 4}


def _upd(texto, uid=7):
    m = MagicMock()
    m.text = texto
    m.reply_text = AsyncMock()
    m.reply_chat_action = AsyncMock()
    u = MagicMock()
    u.message = m
    u.effective_user.id = uid
    return u, m


def _ctx(args=None, **user_data):
    c = MagicMock()
    c.args = args
    c.user_data = dict(user_data)
    return c


@pytest.fixture(autouse=True)
def _aislar(monkeypatch):
    monkeypatch.setattr(h, "LIMITER", UserLimiter(max_calls=5, window=60.0))
    consulta = AsyncMock(return_value=(DATOS_BTC, None, None))
    monkeypatch.setattr(h, "_consultar", consulta)
    return consulta


def _run(coro):
    return asyncio.run(coro)


def test_texto_desconocido_en_privado_no_responde_nada():
    u, m = _upd("hola, buenas tardes")
    _run(h.explorer_text(u, _ctx()))
    m.reply_text.assert_not_awaited()


def test_direccion_btc_valida_se_consulta_y_se_responde_en_html(_aislar):
    u, m = _upd(BTC)
    _run(h.explorer_text(u, _ctx()))
    _aislar.assert_awaited_once()
    texto = m.reply_text.await_args.args[0]
    kw = m.reply_text.await_args.kwargs
    assert BTC in texto and "50.00000000 BTC" in texto
    assert kw["parse_mode"] == "HTML" and kw["disable_web_page_preview"] is True


@pytest.mark.parametrize("flag", ["waiting_for_time", "tkt_awaiting", "awaiting_tspl_hour", "awaiting_year_hour"])
def test_con_un_flag_pendiente_de_otro_flujo_no_actua(flag, _aislar):
    u, m = _upd(BTC)
    _run(h.explorer_text(u, _ctx(**{flag: True})))
    _aislar.assert_not_awaited()
    m.reply_text.assert_not_awaited()


def test_limite_por_usuario(monkeypatch, _aislar):
    monkeypatch.setattr(h, "LIMITER", UserLimiter(max_calls=1, window=60.0))
    u, m = _upd(BTC)
    _run(h.explorer_text(u, _ctx()))
    _run(h.explorer_text(u, _ctx()))
    assert _aislar.await_count == 1
    assert "demasiadas consultas" in m.reply_text.await_args.args[0]


def test_el_limite_es_por_usuario(monkeypatch, _aislar):
    monkeypatch.setattr(h, "LIMITER", UserLimiter(max_calls=1, window=60.0))
    for uid in (1, 2):
        u, _ = _upd(BTC, uid)
        _run(h.explorer_text(u, _ctx()))
    assert _aislar.await_count == 2


def test_error_de_la_fuente_da_mensaje_fijo(_aislar):
    _aislar.side_effect = sources.ExplorerError("no_encontrado")
    u, m = _upd(BTC)
    _run(h.explorer_text(u, _ctx()))
    assert "No encontré ese dato" in m.reply_text.await_args.args[0]


def test_fallo_inesperado_no_filtra_detalle_ni_la_entrada_completa(_aislar, caplog):
    _aislar.side_effect = RuntimeError(f"boom https://x/api/address/{BTC}")
    u, m = _upd(BTC)
    with caplog.at_level(logging.DEBUG):
        _run(h.explorer_text(u, _ctx()))
    enviado = m.reply_text.await_args.args[0]
    assert "boom" not in enviado and BTC not in enviado
    assert BTC not in caplog.text


def test_la_consulta_exitosa_tampoco_loguea_la_entrada_completa(_aislar, caplog):
    u, _ = _upd(BTC)
    with caplog.at_level(logging.DEBUG):
        _run(h.explorer_text(u, _ctx()))
    assert BTC not in caplog.text


def test_evm_no_ofrece_boton_de_ia(_aislar):
    _aislar.return_value = ({"direccion": EVM, "redes": [], "sin_respuesta": []}, None, None)
    u, m = _upd(EVM)
    _run(h.explorer_text(u, _ctx()))
    assert m.reply_text.await_args.kwargs.get("reply_markup") is None


def test_explorar_sin_argumentos_pide_la_entrada_y_arma_la_espera():
    u, m = _upd("/explorar")
    ctx = _ctx(args=[])
    _run(h.explorar_command(u, ctx))
    assert "Envíame" in m.reply_text.await_args.args[0]
    assert h._ESPERA in ctx.user_data


def test_explorar_con_nombre_de_hive_suelto_lo_acepta(_aislar):
    _aislar.return_value = (DATOS_HIVE, None, None)
    u, m = _upd("/explorar blocktrades")
    _run(h.explorar_command(u, _ctx(args=["blocktrades"])))
    assert _aislar.await_args.args[0].tipo == "hive_account"
    assert "blocktrades" in m.reply_text.await_args.args[0]


def test_explorar_con_basura_responde_la_ayuda(_aislar):
    u, m = _upd("/explorar !!!")
    _run(h.explorar_command(u, _ctx(args=["!!!"])))
    _aislar.assert_not_awaited()
    assert "No reconocí ese texto" in m.reply_text.await_args.args[0]


def test_nombre_hive_suelto_solo_se_acepta_tras_abrir_el_explorador(_aislar):
    _aislar.return_value = (DATOS_HIVE, None, None)
    u, m = _upd("blocktrades")
    _run(h.explorer_text(u, _ctx()))
    m.reply_text.assert_not_awaited()
    ctx = _ctx(**{h._ESPERA: time.monotonic()})
    _run(h.explorer_text(u, ctx))
    assert _aislar.await_args.args[0].tipo == "hive_account"
    assert h._ESPERA not in ctx.user_data   # la espera se consume


def test_la_espera_caduca(_aislar):
    u, m = _upd("blocktrades")
    ctx = _ctx(**{h._ESPERA: time.monotonic() - 10_000})
    _run(h.explorer_text(u, ctx))
    _aislar.assert_not_awaited()
    m.reply_text.assert_not_awaited()


def test_esperando_y_llega_basura_se_explica_que_se_puede_consultar():
    u, m = _upd("???")
    _run(h.explorer_text(u, _ctx(**{h._ESPERA: time.monotonic()})))
    assert "No reconocí ese texto" in m.reply_text.await_args.args[0]


def test_boton_del_menu_edita_el_mensaje_con_navegacion_y_arma_la_espera():
    q = MagicMock()
    q.edit_message_text = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    ctx = _ctx()
    _run(h.explorer_callback(u, ctx, "explorer_open"))
    texto = q.edit_message_text.await_args.args[0]
    datas = [b.callback_data for f in q.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard for b in f]
    assert "Envíame" in texto
    assert datas == ["menu:mercado", "menu:home"]
    assert h._ESPERA in ctx.user_data


def test_registro_por_el_contrato_y_en_el_menu_de_mercado():
    c = next(c for c in commands.COMANDOS if c.name == "explorar")
    assert c.namespaces == ("explorer",) and c.callback is not None and c.menu[0] == "mercado"
    assert "explorer_open" in [e.callback_data for e in commands.menu_entries("mercado")]
    from src.handlers.callback_router import get_callback_handler

    get_callback_handler()   # sin colisiones de namespaces


def test_el_router_real_despacha_explorer_open_hasta_el_explorador():
    from src.handlers import callback_router as r

    q = MagicMock()
    q.data = "explorer_open"
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.from_user.id = 7
    q.message.chat_id = 1
    q.message.message_id = 2
    u = MagicMock()
    u.callback_query = q
    ctx = _ctx()
    _run(r.callback_router(u, ctx))
    q.edit_message_text.assert_awaited_once()
    assert "Envíame" in q.edit_message_text.await_args.args[0]
    assert h._ESPERA in ctx.user_data


def test_register_pone_el_handler_de_texto_antes_que_los_otros_y_solo_en_privado():
    app = MagicMock()
    h.register(app)
    (handler,), kw = app.add_handler.call_args
    assert kw["group"] == -1
    assert "private" in repr(handler.filters).lower()


def _cmc(price=65000.5, last="2026-11-16T22:15:00.000Z"):
    cli = MagicMock()
    cli._get_from_cmc = AsyncMock(return_value={"BTC": {"quote": {"USD": {"price": price, "last_updated": last}}}})
    return cli


class _Cache:
    def __init__(self):
        self.d = {}

    def get(self, k, ttl=60):
        return self.d.get(k)

    def set(self, k, v):
        self.d[k] = v


def test_precio_btc_trae_fuente_y_hora_y_se_cachea(monkeypatch):
    cli = _cmc()
    monkeypatch.setattr(h, "cache", _Cache())
    monkeypatch.setattr("src.handlers.p.get_crypto_client", lambda: cli)
    assert _run(h._precio_btc()) == (65000.5, "CoinMarketCap", "22:15 UTC")
    _run(h._precio_btc())
    assert cli._get_from_cmc.await_count == 1


@pytest.mark.parametrize("malo", [None, {}, {"BTC": {"quote": {"USD": {"price": "x"}}}},
                                  {"BTC": {"quote": {"USD": {"price": float("nan")}}}},
                                  {"BTC": {"quote": {"USD": {"price": 0}}}}])
def test_precio_btc_invalido_da_none(monkeypatch, malo):
    cli = MagicMock()
    cli._get_from_cmc = AsyncMock(return_value=malo)
    monkeypatch.setattr(h, "cache", _Cache())
    monkeypatch.setattr("src.handlers.p.get_crypto_client", lambda: cli)
    assert _run(h._precio_btc()) is None


# ── _consultar: la fuente principal manda; txs y precio son opcionales ──

@pytest.fixture
def real(monkeypatch):
    """Devuelve el _consultar real (el autouse lo reemplaza por un mock)."""
    import importlib
    return importlib.import_module("src.explorer.handler")._consultar_real


def _fuentes(monkeypatch, addr=None, txs=None, tx=None, precio=None, cuenta=None, htx=None):
    monkeypatch.setattr(sources, "btc_address", addr or AsyncMock(return_value=DATOS_BTC))
    monkeypatch.setattr(sources, "btc_address_txs", txs or AsyncMock(return_value=[{"txid": "a" * 64}]))
    monkeypatch.setattr(sources, "btc_tx", tx or AsyncMock(return_value={"x": 1}))
    monkeypatch.setattr(sources, "hive_cuenta", cuenta or AsyncMock(return_value=DATOS_HIVE))
    monkeypatch.setattr(sources, "hive_tx", htx or AsyncMock(return_value={"y": 1}))
    monkeypatch.setattr(h, "_precio_btc", precio or AsyncMock(return_value=(1.0, "CMC", "00:00 UTC")))


def _entrada(valor, tipo):
    from src.explorer.classify import Entrada
    return Entrada(tipo, valor)


def test_consultar_direccion_devuelve_datos_txs_y_precio(real, monkeypatch):
    _fuentes(monkeypatch)
    datos, txs, precio = _run(real(_entrada(BTC, "btc_address")))
    assert datos == DATOS_BTC and txs and precio == (1.0, "CMC", "00:00 UTC")


def test_si_fallan_txs_y_precio_igual_hay_resultado(real, monkeypatch):
    _fuentes(monkeypatch, txs=AsyncMock(side_effect=sources.ExplorerError("fuente_no_disponible")),
             precio=AsyncMock(side_effect=RuntimeError("cmc")))
    datos, txs, precio = _run(real(_entrada(BTC, "btc_address")))
    assert datos == DATOS_BTC and txs is None and precio is None


def test_si_falla_la_fuente_principal_se_propaga(real, monkeypatch):
    _fuentes(monkeypatch, addr=AsyncMock(side_effect=sources.ExplorerError("no_encontrado")))
    with pytest.raises(sources.ExplorerError):
        _run(real(_entrada(BTC, "btc_address")))


def test_consultar_hive_no_pide_precio(real, monkeypatch):
    precio = AsyncMock()
    _fuentes(monkeypatch, precio=precio)
    assert _run(real(_entrada("blocktrades", "hive_account")))[0] == DATOS_HIVE
    assert _run(real(_entrada("a" * 40, "hive_tx")))[0] == {"y": 1}
    precio.assert_not_awaited()
