"""Explorador: analisis de TASALO IA (F4-T6). Sin red: IA y consultas van con mocks.

Regla de privacidad (D-026): a la IA solo llegan cifras agregadas; nunca la direccion,
el hash, el usuario de Hive ni nombres de cuentas de las transferencias.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core import ai_logic, ia_identidad
from src.explorer import analisis
from src.explorer import handler as h
from src.explorer.classify import Entrada
from src.explorer.guard import UserLimiter

BTC = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
TXID = "ab" * 32
HIVE_TX = "cd" * 20
CUENTA = "blocktrades"

DIR = {"direccion": BTC, "saldo_sats": 5_000_000_000, "pendiente_sats": 0, "recibido_sats": 5_000_000_000,
       "gastado_sats": 0, "tx_count": 1, "tx_pendientes": 0}
TXS = [{"txid": TXID, "confirmada": True, "altura": 100, "fecha": "2026-11-01 10:00 UTC", "neto_sats": 10_000_000},
       {"txid": "ef" * 32, "confirmada": False, "altura": None, "fecha": None, "neto_sats": -5_000_000}]
TX = {"txid": TXID, "confirmada": True, "altura": 900_000, "confirmaciones": 3, "fecha": "2026-11-01 10:00 UTC",
      "tamano": 250, "peso": 1000, "fee_sats": 500, "entradas": 1, "salidas": 2, "total_salidas_sats": 100_000_000}
CUENTA_D = {"nombre": CUENTA, "creada": "2016-03-30T00:00:00", "hive": 1.5, "hbd": 2.0, "hp": 3.0, "posts": 40,
            "ultimo_post": "2026-11-01"}
HTX = {"id": HIVE_TX, "bloque": 123, "total_operaciones": 2,
       "operaciones": [{"tipo": "transfer", "transferencia": {"de": "alice", "a": "bob", "monto": 10.0, "moneda": "HIVE"}},
                       {"tipo": "custom_json\n<b>x</b>"}]}
PRECIO = (100_000.0, "CoinMarketCap", "12:03 UTC")


def _e(tipo, valor, **kw):
    return Entrada(tipo=tipo, valor=valor, **kw)


# -- contexto: solo cifras, nunca identificadores --------------------------------------

def test_contexto_direccion_lleva_cifras_y_no_la_direccion_ni_txids():
    c = analisis.contexto(_e("btc_address", BTC, red="mainnet", detalle=(("formato", "p2pkh"),)), DIR, TXS, PRECIO)
    assert "50.00000000 BTC" in c and "Transacciones: 1" in c
    assert "+0.10000000" in c and "-0.05000000" in c
    assert "CoinMarketCap" in c and "12:03 UTC" in c
    assert BTC not in c and TXID not in c and "ef" * 32 not in c


def test_contexto_direccion_sin_precio_no_inventa_usd():
    c = analisis.contexto(_e("btc_address", BTC), DIR, None, None)
    assert "USD" not in c


def test_contexto_tx_btc_calcula_tarifa_y_no_lleva_el_hash():
    c = analisis.contexto(_e("btc_tx", TXID), TX, None, None)
    assert "3 confirmaciones" in c and "500 sats" in c
    assert "2.00 sat/vB" in c            # 500 / (1000 / 4) = 2
    assert TXID not in c


def test_contexto_tx_btc_sin_confirmar():
    d = dict(TX, confirmada=False, altura=None, confirmaciones=None)
    assert "sin confirmar" in analisis.contexto(_e("btc_tx", TXID), d, None, None).lower()


def test_contexto_cuenta_hive_da_antiguedad_y_no_el_nombre():
    c = analisis.contexto(_e("hive_account", CUENTA), CUENTA_D, None, None)
    assert "Publicaciones: 40" in c and "anos" in c
    assert CUENTA not in c


def test_contexto_tx_hive_agrega_transferencias_sin_nombres_ni_id():
    c = analisis.contexto(_e("hive_tx", HIVE_TX), HTX, None, None)
    assert "10.000 HIVE" in c and "Operaciones: 2" in c
    assert "alice" not in c and "bob" not in c and HIVE_TX not in c


def test_tipos_de_operacion_se_limpian():
    c = analisis.contexto(_e("hive_tx", HIVE_TX), HTX, None, None)
    assert "<" not in c and ">" not in c and "\n<" not in c
    assert "custom_json" in c


@pytest.mark.parametrize("tipo", ["ln_invoice", "lnurl", "lightning_address", "evm_address", "evm_tx", "desconocido"])
def test_lo_que_no_se_consulta_no_tiene_contexto(tipo):
    assert analisis.contexto(_e(tipo, "x"), None, None, None) is None


def test_datos_incompletos_no_rompen():
    assert analisis.contexto(_e("btc_address", BTC), {}, None, None) is None


# -- get_explorer_analysis -------------------------------------------------------------

def _resp(txt):
    return {"choices": [{"message": {"content": txt}}]}


def _ia(txt="*Panorama* sin consejos"):
    with patch("src.core.ai_logic._call_ai_async", AsyncMock(return_value=_resp(txt))) as m:
        out = asyncio.run(ai_logic.get_explorer_analysis("Tipo: direccion Bitcoin"))
    return out, m


def test_analisis_usa_identidad_prompt_neutral_y_agrega_el_descargo():
    out, m = _ia()
    payload = m.await_args.args[0]
    user = payload["messages"][1]["content"]
    assert "Tipo: direccion Bitcoin" in user
    assert "identidad" in user.lower() and "no" in user.lower()
    assert "TASALO IA" in payload["messages"][0]["content"]
    assert out.endswith(ia_identidad.descargo("_"))


def test_analisis_contexto_vacio_no_llama_a_la_ia():
    with patch("src.core.ai_logic._call_ai_async", AsyncMock()) as m:
        out = asyncio.run(ai_logic.get_explorer_analysis("   "))
    m.assert_not_awaited()
    assert out.startswith("\u26a0")


def test_analisis_contenido_vacio_es_error_legible():
    out, _ = _ia("")
    assert out.startswith("\u26a0")


def test_analisis_429_es_error_legible_y_no_filtra_detalle():
    import httpx

    resp = httpx.Response(429, request=httpx.Request("POST", "https://x/secret?k=abc"))
    err = httpx.HTTPStatusError("boom https://x/secret?k=abc", request=resp.request, response=resp)
    with patch("src.core.ai_logic._call_ai_async", AsyncMock(side_effect=err)):
        out = asyncio.run(ai_logic.get_explorer_analysis("Tipo: x"))
    assert out.startswith("\u26a0") and "secret" not in out and "abc" not in out


# -- handler: boton y callback ---------------------------------------------------------

def _upd(texto, uid=7):
    m = MagicMock()
    m.text = texto
    m.reply_text = AsyncMock()
    m.reply_chat_action = AsyncMock()
    u = MagicMock()
    u.message = m
    u.effective_user.id = uid
    return u, m


def _ctx(**ud):
    c = MagicMock()
    c.args = None
    c.user_data = dict(ud)
    return c


@pytest.fixture(autouse=True)
def _aislar(monkeypatch):
    monkeypatch.setattr(h, "LIMITER", UserLimiter(max_calls=50, window=60.0))
    monkeypatch.setattr(h, "IA_LIMITER", UserLimiter(max_calls=3, window=60.0))
    monkeypatch.setattr(h, "_consultar", AsyncMock(return_value=(DIR, TXS, PRECIO)))
    monkeypatch.setattr(h.ai_logic, "_ia_configurada", lambda: True)


def _consulta(texto=BTC, ia=True, monkeypatch=None, **ud):
    u, m = _upd(texto)
    c = _ctx(**ud)
    asyncio.run(h.explorer_text(u, c))
    return m, c


def _botones(m):
    kb = m.reply_text.await_args.kwargs.get("reply_markup")
    return [b for fila in kb.inline_keyboard for b in fila] if kb else []


def test_el_resultado_trae_boton_de_analisis_y_guarda_el_contexto_sin_la_direccion():
    m, c = _consulta()
    bs = _botones(m)
    assert len(bs) == 1 and "TASALO IA" in bs[0].text
    assert bs[0].callback_data.startswith("explorer:ia:") and len(bs[0].callback_data.encode()) <= 64
    guardado = c.user_data[h._IA_CTX]
    assert BTC not in guardado["ctx"] and TXID not in guardado["ctx"]


def test_sin_ia_configurada_no_hay_boton(monkeypatch):
    monkeypatch.setattr(h.ai_logic, "_ia_configurada", lambda: False)
    m, c = _consulta()
    assert _botones(m) == [] and h._IA_CTX not in c.user_data


def test_evm_se_consulta_pero_no_tiene_boton(monkeypatch):
    datos = {"redes": [{"red": "Ethereum", "simbolo": "ETH", "saldo_wei": 10**18, "nonce": 1, "tipo": "cuenta"}]}
    monkeypatch.setattr(h, "_consultar", AsyncMock(return_value=(datos, None, None)))
    m, c = _consulta("0x" + "ab" * 20)
    assert _botones(m) == [] and h._IA_CTX not in c.user_data


def _q(data, uid=7):
    q = MagicMock()
    q.data = data
    q.from_user.id = uid
    q.message.reply_text = AsyncMock()
    q.message.chat.send_action = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    return u, q


def _pulsa(c, data, texto="Analisis de prueba", uid=7):
    u, q = _q(data, uid)
    ia = AsyncMock(return_value=texto)
    with patch("src.explorer.handler.ai_logic.get_explorer_analysis", ia):
        asyncio.run(h.explorer_callback(u, c, data))
    return q, ia


def _con_contexto():
    m, c = _consulta()
    return c, _botones(m)[0].callback_data


def test_pulsar_el_boton_llama_a_la_ia_solo_con_el_contexto_y_responde():
    c, data = _con_contexto()
    q, ia = _pulsa(c, data)
    ia.assert_awaited_once()
    assert BTC not in ia.await_args.args[0]
    assert q.message.reply_text.await_args.args[0] == "Analisis de prueba"


def test_segunda_pulsacion_reutiliza_el_texto_sin_gastar_ia():
    c, data = _con_contexto()
    _pulsa(c, data)
    q, ia = _pulsa(c, data)
    ia.assert_not_awaited()
    q.message.reply_text.assert_awaited_once()


def test_boton_viejo_con_otro_numero_caduca_sin_llamar_a_la_ia():
    c, data = _con_contexto()
    viejo = data.rsplit(":", 1)[0] + ":" + str((int(data.rsplit(":", 1)[1]) + 1) % 100)
    q, ia = _pulsa(c, viejo)
    ia.assert_not_awaited()
    assert "caduc" in q.message.reply_text.await_args.args[0].lower()


def test_sin_contexto_o_caducado_pide_repetir_la_consulta():
    c, data = _con_contexto()
    c.user_data[h._IA_CTX]["t"] = time.monotonic() - 10_000
    q, ia = _pulsa(c, data)
    ia.assert_not_awaited()
    assert "caduc" in q.message.reply_text.await_args.args[0].lower()
    q2, ia2 = _pulsa(_ctx(), data)
    ia2.assert_not_awaited()


def test_limite_de_llamadas_a_la_ia(monkeypatch):
    monkeypatch.setattr(h, "IA_LIMITER", UserLimiter(max_calls=1, window=60.0))
    h.IA_LIMITER.allow(7)   # el cupo ya esta gastado
    c, data = _con_contexto()
    q, ia = _pulsa(c, data)
    ia.assert_not_awaited()
    q.message.reply_text.assert_awaited_once()


def test_error_de_la_ia_no_se_guarda_para_que_el_siguiente_toque_reintente():
    c, data = _con_contexto()
    q, ia = _pulsa(c, data, texto="\u26a0\ufe0f La IA tardo demasiado")
    _, ia2 = _pulsa(c, data)
    ia2.assert_awaited_once()


def test_botones_con_numero_raro_se_ignoran():
    c, _ = _con_contexto()
    for malo in ("explorer:ia:\u00b2", "explorer:ia:", "explorer:ia:1:2", "explorer:ia:abc"):
        q, ia = _pulsa(c, malo)
        ia.assert_not_awaited()


def test_markdown_malo_del_modelo_se_reenvia_como_texto_plano():
    from telegram.error import BadRequest

    c, data = _con_contexto()
    u, q = _q(data)
    q.message.reply_text = AsyncMock(side_effect=[BadRequest("can't parse entities"), None])
    with patch("src.explorer.handler.ai_logic.get_explorer_analysis", AsyncMock(return_value="*roto")):
        asyncio.run(h.explorer_callback(u, c, data))
    assert q.message.reply_text.await_count == 2
