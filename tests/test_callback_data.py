"""F6-T3: callback_data v2 (parser central) y compatibilidad con el formato viejo."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.callback_data import MAX_BYTES, build, parse_v2

# Formatos viejos reales (tres separadores) y el namespace que el router les da hoy.
LEGACY = {
    "start_tasalo": "start",
    "tasalo_refresh": "tasalo",
    "toque_refresh": "toque",
    "toqueimg_refresh": "toqueimg",
    "alert_create": "alert",
    "alert_delete_12": "alert",
    "alert_lvl|tok|1": "alert",
    "alert_menu|tok": "alert",
    "p_refresh_BTC": "p",
    "ta_quick|BTC|4h": "ta",
    "ai_analyze|BINANCE|BTC|USDT|1h": "ai",
    "ai_panorama|BTC": "ai",
    "graf_tf|BTC|USDT|1h": "graf",
    "graf_from_ta|BTC|USDT|1h": "graf",
    "mapa_cripto24": "mapa",
    "year_sub_custom": "year_sub",
    "tspl_sub_9": "tspl",
    "news_refresh_x": "news",
    "status_cmd:1:24h": "status",
    "ms_confirm:1": "ms",
    "msapp_confirm:1": "msapp",
    "tkt_bug:5": "tkt",
}


def test_build_basico():
    assert build("mapa", "24h") == "mapa:24h"
    assert build("start") == "start"
    assert build("p", "BTC", 4) == "p:BTC:4"


@pytest.mark.parametrize("ns", ["", "Mapa", "a_b", "a:b", "a|b", "ñ"])
def test_build_rechaza_namespace_invalido(ns):
    with pytest.raises(ValueError):
        build(ns, "x")


def test_build_rechaza_argumento_con_separador():
    with pytest.raises(ValueError):
        build("p", "a:b")


def test_build_rechaza_mas_de_64_bytes_contando_utf8():
    assert len(build("p", "x" * (MAX_BYTES - 2)).encode()) == MAX_BYTES
    with pytest.raises(ValueError):
        build("p", "x" * (MAX_BYTES - 1))
    with pytest.raises(ValueError):
        build("p", "ñ" * 32)  # 32 caracteres = 64 bytes + el namespace


@pytest.mark.parametrize("data", ["mapa:24h", "mapa", "p:BTC:4", "ns:", "a:b:c:d"])
def test_parse_ida_y_vuelta(data):
    ns, args = parse_v2(data)
    assert build(ns, *args) == data


def test_parse_devuelve_namespace_y_argumentos():
    assert parse_v2("mapa:24h") == ("mapa", ("24h",))
    assert parse_v2("mapa") == ("mapa", ())
    assert parse_v2("ns:") == ("ns", ("",))


@pytest.mark.parametrize("data", list(LEGACY))
def test_parse_no_confunde_formatos_viejos(data):
    assert parse_v2(data) is None


@pytest.mark.parametrize("data,esperado", list(LEGACY.items()))
def test_router_resuelve_igual_los_formatos_viejos(data, esperado):
    from src.handlers import callback_router as r

    assert r._resolve_namespace(data) == esperado


def test_router_resuelve_namespace_v2_conocido():
    from src.handlers import callback_router as r

    assert r._resolve_namespace("mapa:24h") == "mapa"
    assert r._resolve_namespace("zzz:1") == "zzz:1"  # desconocido: sin cambios


def test_router_despacha_v2_a_un_comando_extra(monkeypatch):
    from src import commands
    from src.handlers import callback_router as r

    visto = []

    async def cb(update, context, data):
        visto.append(data)

    monkeypatch.setattr(
        commands, "COMANDOS", commands.COMANDOS + (commands.Cmd("zzz", None, "d", callback=cb),)
    )
    q = MagicMock()
    q.data = "zzz:abc:1"
    q.from_user.id = 1
    q.answer = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    asyncio.run(r.callback_router(u, MagicMock()))
    assert visto == ["zzz:abc:1"]


def test_peor_caso_realista_de_ai_analyze_cabe():
    data = f"ai_analyze|BINANCE|{'1000000MOG'}|FDUSD|1h"
    assert len(data.encode()) <= MAX_BYTES
