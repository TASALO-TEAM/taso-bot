"""Handler /mapa: parseo de la vista, texto de analisis y flujo de envio (sin red)."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from telegram.error import BadRequest

from src.handlers import mapa
from src.heatmap.data import HeatmapError, Snapshot
from src.heatmap.render import Celda

HAVANA = ZoneInfo("America/Havana")
AHORA = datetime(2026, 11, 15, 12, 0, tzinfo=HAVANA)


def _cripto(obsoleto=None):
    celdas = (
        Celda("BTC", 2e12, 2.0),
        Celda("ETH", 5e11, -1.0),
        Celda("SOL", 1e11, 10.0),
        Celda("ADA", 1e10, None),
    )
    return Snapshot(celdas, "Fuente: CoinMarketCap", 5.0, obsoleto_min=obsoleto)


def _forex(fecha="2026-11-13"):
    celdas = (Celda("EUR", 1.0, -0.99), Celda("JPY", 1.0, 1.01), Celda("GBP", 1.0, 0.2))
    return Snapshot(celdas, "Fuente: BCE", 1.0, fecha_dato=fecha)


@pytest.mark.parametrize(
    "data, esperado",
    [
        ("mapa_cripto_24h", ("cripto", "24h")),
        ("mapa_cripto_7d", ("cripto", "7d")),
        ("mapa_forex", ("forex", None)),
        ("mapa_cripto_1h", None),
        ("mapa_", None),
        ("mapa_x" * 40, None),
        ("start_forex", None),
    ],
)
def test_parse_vista(data, esperado):
    assert mapa.parse_vista(data) == esperado


def _seccion(txt, titulo):
    """Lineas de la seccion `titulo` (hasta la siguiente linea en blanco)."""
    return txt.split(titulo)[1].split("\n\n")[0].split("\n")[1:]


def test_caption_cripto_resume_mercado_ganadores_y_perdedores():
    txt = mapa.armar_caption(("cripto", "24h"), _cripto(), AHORA)
    assert "<b>+1.73%</b>" in txt  # ponderado por capitalizacion, ADA (sin dato) no cuenta
    assert "2 suben" in txt and "1 bajan" in txt
    assert _seccion(txt, "Mayores subas") == ["• SOL +10.00%", "• BTC +2.00%"]
    assert _seccion(txt, "Mayores bajas") == ["• ETH -1.00%"]
    assert "ADA" not in txt
    assert "⚠️" not in txt
    assert len(txt) <= 1024  # limite de caption de Telegram


def test_caption_escapa_html_de_simbolos_externos():
    celdas = (Celda("A<b>&", 1e9, 3.0), Celda("ETH", 1e9, -1.0))
    snap = Snapshot(celdas, "Fuente: CoinMarketCap", 5.0)
    txt = mapa.armar_caption(("cripto", "24h"), snap, AHORA)
    assert "A&lt;b&gt;&amp;" in txt
    assert "A<b>&" not in txt


def test_caption_avisa_si_el_dato_es_viejo():
    txt = mapa.armar_caption(("cripto", "24h"), _cripto(obsoleto=12), AHORA)
    assert "hace 12 min" in txt


def test_caption_forex_muestra_fecha_real_y_aclara_si_no_es_hoy():
    txt = mapa.armar_caption(("forex", None), _forex(), AHORA)
    assert "13 nov 2026" in txt
    assert "último día hábil" in txt
    assert _seccion(txt, "Más fuertes")[0] == "• JPY +1.01%"
    assert _seccion(txt, "Más débiles")[0] == "• EUR -0.99%"
    hoy = mapa.armar_caption(("forex", None), _forex("2026-11-15"), AHORA)
    assert "último día hábil" not in hoy


def test_teclado_tiene_las_tres_vistas_y_actualizar_con_la_vista_actual():
    kb = mapa.armar_teclado(("cripto", "7d"))
    datos = [b.callback_data for fila in kb.inline_keyboard for b in fila]
    assert datos == ["mapa_cripto_24h", "mapa_cripto_7d", "mapa_forex", "mapa_acciones", "mapa_cripto_7d"]
    assert all(len(d) <= 64 for d in datos)


def test_teclado_marca_la_vista_activa_y_las_etiquetas_caben():
    kb = mapa.armar_teclado(("cripto", "7d"))
    etiquetas = [b.text for b in kb.inline_keyboard[0]]
    assert etiquetas == ["₿ 24 h", "✅ 7 d", "💱 Forex"]
    assert all(len(e) <= 10 for e in etiquetas)  # sin truncar con 3 botones por fila
    forex = [b.text for b in mapa.armar_teclado(("forex", None)).inline_keyboard[0]]
    assert forex == ["₿ 24 h", "₿ 7 d", "✅ Forex"]


def _update_mensaje(texto="/mapa"):
    u = MagicMock()
    u.callback_query = None
    u.message.reply_photo = AsyncMock()
    u.message.reply_text = AsyncMock()
    u.message.reply_chat_action = AsyncMock()
    u.effective_user.id = 7
    u.effective_user.username = "x"
    return u


def _ctx(args):
    c = MagicMock()
    c.args = args
    return c


@pytest.fixture
def parches():
    mapa.reset_cache_png()
    with patch.object(mapa, "obtener_cripto", new=AsyncMock(return_value=_cripto())) as oc, \
         patch.object(mapa, "obtener_forex", new=AsyncMock(return_value=_forex())) as of, \
         patch.object(mapa, "render_mapa", return_value=b"PNG") as rm, \
         patch.object(mapa, "get_crypto_client", return_value=MagicMock()), \
         patch.object(mapa, "track_command_usage", new=AsyncMock()):
        yield oc, of, rm


def test_comando_sin_argumentos_envia_cripto_24h(parches):
    oc, of, rm = parches
    u = _update_mensaje()
    asyncio.run(mapa.mapa_command(u, _ctx([])))
    oc.assert_awaited_once()
    assert oc.await_args.args[1] == "24h"
    of.assert_not_awaited()
    kw = u.message.reply_photo.await_args.kwargs
    assert kw["photo"] == b"PNG"
    assert "Mayores subas" in kw["caption"]
    assert kw["parse_mode"] == "HTML"
    assert kw["reply_markup"] is not None


def test_comando_forex(parches):
    oc, of, rm = parches
    u = _update_mensaje()
    asyncio.run(mapa.mapa_command(u, _ctx(["forex"])))
    of.assert_awaited_once()
    oc.assert_not_awaited()


def test_comando_argumento_invalido_explica_el_uso_sin_llamar_a_la_api(parches):
    oc, of, rm = parches
    u = _update_mensaje()
    asyncio.run(mapa.mapa_command(u, _ctx(["bitcoin*"])))
    u.message.reply_text.assert_awaited_once()
    assert "/mapa" in u.message.reply_text.await_args.args[0]
    oc.assert_not_awaited()
    u.message.reply_photo.assert_not_awaited()


def test_error_de_datos_responde_mensaje_fijo_sin_detalle_interno(parches):
    oc, of, rm = parches
    oc.side_effect = HeatmapError("secreto interno 123")
    u = _update_mensaje()
    asyncio.run(mapa.mapa_command(u, _ctx([])))
    texto = u.message.reply_text.await_args.args[0]
    assert "secreto" not in texto and "123" not in texto
    u.message.reply_photo.assert_not_awaited()


def test_render_repetido_con_el_mismo_snapshot_se_reutiliza(parches):
    oc, of, rm = parches
    for _ in range(3):
        asyncio.run(mapa.mapa_command(_update_mensaje(), _ctx([])))
    assert rm.call_count == 1


def _update_callback(data):
    u = MagicMock()
    q = u.callback_query
    q.data = data
    q.answer = AsyncMock()
    q.edit_message_media = AsyncMock()
    q.from_user.id = 7
    u.effective_user.id = 7
    return u, q


def test_callback_cambia_de_vista_editando_la_imagen(parches):
    oc, of, rm = parches
    u, q = _update_callback("mapa_forex")
    asyncio.run(mapa.mapa_callback(u, _ctx([])))
    of.assert_awaited_once()
    q.edit_message_media.assert_awaited_once()
    assert q.edit_message_media.await_args.kwargs["media"].parse_mode == "HTML"


def test_callback_con_datos_invalidos_no_toca_la_api(parches):
    oc, of, rm = parches
    u, q = _update_callback("mapa_cripto_999")
    asyncio.run(mapa.mapa_callback(u, _ctx([])))
    oc.assert_not_awaited()
    q.edit_message_media.assert_not_awaited()


def test_callback_message_not_modified_se_responde_sin_error(parches):
    oc, of, rm = parches
    u, q = _update_callback("mapa_cripto_24h")
    q.edit_message_media.side_effect = BadRequest("Message is not modified")
    asyncio.run(mapa.mapa_callback(u, _ctx([])))
    q.answer.assert_awaited()


def test_callback_sin_datos_avisa_con_mensaje_fijo(parches):
    oc, of, rm = parches
    oc.side_effect = HeatmapError("detalle interno")
    u, q = _update_callback("mapa_cripto_24h")
    q.message.reply_text = AsyncMock()
    asyncio.run(mapa.mapa_callback(u, _ctx([])))
    texto = q.message.reply_text.await_args.args[0]
    assert "detalle" not in texto
    q.edit_message_media.assert_not_awaited()


def test_callback_con_otro_badrequest_se_propaga(parches):
    oc, of, rm = parches
    u, q = _update_callback("mapa_cripto_24h")
    q.edit_message_media.side_effect = BadRequest("Chat not found")
    with pytest.raises(BadRequest):
        asyncio.run(mapa.mapa_callback(u, _ctx([])))


def _caida(pct, tope=None):
    """BTC 1e12 y ETH 5e11 con la misma variacion `pct`."""
    return Snapshot((Celda("BTC", 1e12, pct), Celda("ETH", 5e11, pct)), "Fuente: CoinMarketCap", 5.0)


def test_monto_usa_mil_millones_y_billones_en_espanol():
    assert mapa._monto(2.3e11) == "$230.0 mil millones"
    assert mapa._monto(-1.5e12) == "$1.5 billones"
    assert mapa._monto(4.2e8) == "$420.0 millones"


def test_caption_incluye_capital_del_top_100_con_signo():
    txt = mapa.armar_caption(("cripto", "24h"), _cripto(), AHORA)
    assert "Capital del top 100: <b>+$" in txt
    txt = mapa.armar_caption(("cripto", "24h"), _caida(-1.0), AHORA)
    assert "Capital del top 100: <b>-$" in txt


def test_caption_lista_principales_con_cayo_subio_y_cashtag():
    txt = mapa.armar_caption(("cripto", "24h"), _cripto(), AHORA)
    assert _seccion(txt, "Principales") == [
        "• $BTC subió 2.00%", "• $ETH cayó 1.00%", "• $SOL subió 10.00%",
    ]


def test_ultima_hora_solo_si_el_movimiento_es_grande_y_calcula_el_monto():
    # -10 % en todo: capital previo 1.667e12 -> se borran ~$166.7 mil millones
    txt = mapa.armar_caption(("cripto", "24h"), _caida(-10.0), AHORA)
    assert "ÚLTIMA HORA" in txt
    assert "$166.7 mil millones borrados del capital del top 100" in txt
    assert "las últimas 24 horas" in txt
    # movimiento normal: sin titular
    assert "ÚLTIMA HORA" not in mapa.armar_caption(("cripto", "24h"), _caida(-1.0), AHORA)
    # en 7 d el umbral es mayor (10 %): -6 % no dispara, -12 % si
    assert "ÚLTIMA HORA" not in mapa.armar_caption(("cripto", "7d"), _caida(-6.0), AHORA)
    sube = mapa.armar_caption(("cripto", "7d"), _caida(12.0), AHORA)
    assert "ÚLTIMA HORA" in sube and "añadidos al capital" in sube and "los últimos 7 días" in sube


def test_variacion_de_menos_100_no_rompe_el_calculo():
    snap = Snapshot((Celda("BTC", 1e12, -100.0), Celda("ETH", 5e11, 1.0)), "Fuente: CoinMarketCap", 5.0)
    assert "Capital del top 100" in mapa.armar_caption(("cripto", "24h"), snap, AHORA)


def test_caption_con_titular_sigue_dentro_del_limite_de_telegram():
    assert len(mapa.armar_caption(("cripto", "24h"), _caida(-10.0), AHORA)) <= 1024


# --- Vista de acciones S&P 500 ---

def _acciones(obsoleto=None):
    celdas = (
        Celda("AAPL", 5e12, -1.0),
        Celda("NVDA", 4e12, -4.0),
        Celda("XOM", 5e11, 2.5),
        Celda("ZZZ", 1e11, None),
    )
    return Snapshot(celdas, "Fuente: TradingView", 3.0, obsoleto_min=obsoleto)


def test_parse_vista_acciones():
    assert mapa.parse_vista("mapa_acciones") == ("acciones", None)


def test_vista_desde_args_acciones():
    assert mapa._vista_desde_args(["acciones"]) == ("acciones", None)
    assert mapa._vista_desde_args(["acciones", "7d"]) is None


def test_teclado_incluye_acciones_y_marca_la_activa():
    tec = mapa.armar_teclado(("acciones", None))
    botones = [b for fila in tec.inline_keyboard for b in fila]
    datos = [b.callback_data for b in botones]
    assert "mapa_acciones" in datos and all(len(d.encode()) <= 64 for d in datos)
    activo = next(b for b in botones if b.callback_data == "mapa_acciones" and "Actualizar" not in b.text)
    assert "\u2705" in activo.text


def test_caption_acciones_escapa_html_y_usa_mercado_ponderado():
    txt = mapa.armar_caption(("acciones", None), _acciones(), AHORA)
    assert "S&amp;P 500" in txt and "S&P 500" not in txt
    assert "Mercado" in txt and "suben" in txt and "bajan" in txt
    assert "NVDA -4.00%" in txt and "XOM +2.50%" in txt
    assert len(txt) <= 1024


def test_caption_acciones_avisa_dato_viejo():
    assert "hace 7 min" in mapa.armar_caption(("acciones", None), _acciones(obsoleto=7), AHORA)


def test_textos_imagen_acciones():
    titulo, sub, gen = mapa._textos_imagen(("acciones", None), AHORA)
    assert "S&P 500" in titulo and "capitalizaci" in sub and "Cuba" in gen
