"""taso-bot M3: /liq (liquidaciones de futuros). Datos de GET /api/v1/liquidaciones (taso-api#27)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram.error import BadRequest

SINCE = "2026-11-25T21:28:00Z"
COBERTURA_COMPLETA = "2026-11-25T21:20:00Z"  # anterior al inicio de la ventana
COBERTURA_PARCIAL = "2026-11-25T22:18:00Z"  # el colector arranco despues


def _respuesta(items, by="symbol", window="1h", coverage=COBERTURA_COMPLETA):
    return {
        "ok": True,
        "data": items,
        "meta": {"window": window, "by": by, "since": SINCE, "coverage_from": coverage,
                 "sources": ["binance", "bybit", "okx"]},
    }


def _item(key, long_usd, short_usd):
    return {"key": key, "long_usd": long_usd, "short_usd": short_usd, "total_usd": long_usd + short_usd}


class TestClienteLiquidaciones:
    @pytest.mark.asyncio
    async def test_pide_ventana_y_agrupacion_y_devuelve_el_json(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        client._get_with_retry = AsyncMock(return_value=_respuesta([_item("BTC", 10, 0)]))

        data = await client.get_liquidations("4h", "exchange")

        assert data["data"][0]["key"] == "BTC"
        args = client._get_with_retry.call_args
        assert args.args[0] == "http://test:8000/api/v1/liquidaciones"
        assert args.kwargs["params"] == {"window": "4h", "by": "exchange"}

    @pytest.mark.asyncio
    async def test_error_de_red_devuelve_none(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        client._get_with_retry = AsyncMock(side_effect=RuntimeError("caido"))

        assert await client.get_liquidations("1h", "symbol") is None

    @pytest.mark.asyncio
    async def test_respuesta_sin_ok_devuelve_none(self):
        from src.api_client import TasaloApiClient

        client = TasaloApiClient(api_url="http://test:8000", admin_key="k")
        client._get_with_retry = AsyncMock(return_value={"ok": False})

        assert await client.get_liquidations("1h", "symbol") is None


class TestUsd:
    @pytest.mark.parametrize("valor,esperado", [
        (0, "$0"), (950.4, "$950"), (76631.75, "$76.6 mil"),
        (2_500_000, "$2.5 millones"), (3_200_000_000, "$3.2 mil millones"),
    ])
    def test_escala_en_espanol(self, valor, esperado):
        from src.handlers.liq import _usd

        assert _usd(valor) == esperado


class TestArgumentos:
    @pytest.mark.parametrize("args,esperado", [
        ([], ("1h", "symbol")),
        (["4h"], ("4h", "symbol")),
        (["24h", "exchange"], ("24h", "exchange")),
        (["exchange"], ("1h", "exchange")),
        (["monedas", "5m"], ("5m", "symbol")),
    ])
    def test_validos(self, args, esperado):
        from src.handlers.liq import parse_args

        assert parse_args(args) == esperado

    @pytest.mark.parametrize("args", [["12h"], ["1h", "x"], ["1h", "exchange", "extra"], ["';drop"]])
    def test_invalidos_devuelven_none(self, args):
        from src.handlers.liq import parse_args

        assert parse_args(args) is None


class TestTexto:
    def test_total_barra_y_filas_por_moneda(self):
        from src.handlers.liq import armar_texto

        texto = armar_texto(_respuesta([_item("BTC", 75_000, 25_000), _item("ETH", 0, 40_000)]))

        assert "Liquidaciones de futuros" in texto and "1 h" in texto
        assert "$140.0 mil" in texto  # total
        assert "Longs" in texto and "Shorts" in texto
        assert "54%" in texto and "46%" in texto  # 75 mil / 140 mil longs
        assert "🟥" in texto and "🟩" in texto
        assert "BTC" in texto and "ETH" in texto
        assert texto.index("BTC") < texto.index("ETH")  # respeta el orden de la API (mayor primero)

    def test_solo_las_8_mayores_monedas(self):
        from src.handlers.liq import armar_texto

        items = [_item(f"C{i}", 1000 - i, 0) for i in range(12)]
        texto = armar_texto(_respuesta(items))

        assert "C7" in texto and "C8" not in texto

    def test_vista_exchange_lista_todos(self):
        from src.handlers.liq import armar_texto

        items = [_item("binance", 100_000, 50_000), _item("bybit", 1, 1), _item("okx", 1, 1), _item("gate", 1, 1)]
        texto = armar_texto(_respuesta(items, by="exchange"))

        assert "por exchange" in texto
        assert all(n in texto for n in ("binance", "bybit", "okx", "gate"))

    def test_sin_datos(self):
        from src.handlers.liq import armar_texto

        texto = armar_texto(_respuesta([]))

        assert "Sin liquidaciones" in texto
        assert "🟥" not in texto

    def test_clave_externa_se_escapa(self):
        from src.handlers.liq import armar_texto

        texto = armar_texto(_respuesta([_item("<b>X&Y", 1000, 0)]))

        assert "<b>X" not in texto  # no se cuela HTML del proveedor

    def test_cobertura_parcial_avisa_desde_cuando_hay_datos(self):
        from src.handlers.liq import armar_texto

        texto = armar_texto(_respuesta([_item("BTC", 1000, 0)], coverage=COBERTURA_PARCIAL))

        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        # La hora local depende de la tzdata (Cuba cambia de horario): se calcula, no se fija.
        esperada = datetime(2026, 11, 25, 22, 18, tzinfo=timezone.utc).astimezone(ZoneInfo("America/Havana"))
        assert f"Datos desde las {esperada:%H:%M}" in texto

    def test_cobertura_completa_no_avisa(self):
        from src.handlers.liq import armar_texto

        assert "Datos desde" not in armar_texto(_respuesta([_item("BTC", 1000, 0)]))

    def test_aviso_de_exchanges_incluidos(self):
        from src.handlers.liq import armar_texto

        texto = armar_texto(_respuesta([_item("BTC", 1000, 0)]))

        assert "Binance, Bybit y OKX" in texto

    def test_total_cero_no_divide_por_cero(self):
        from src.handlers.liq import armar_texto

        texto = armar_texto(_respuesta([_item("BTC", 0, 0)]))

        assert "$0" in texto


class TestTeclado:
    def _datas(self, kb):
        return [b.callback_data for fila in kb.inline_keyboard for b in fila]

    def test_ventanas_vistas_y_actualizar(self):
        from src.handlers.liq import armar_teclado

        datas = self._datas(armar_teclado("1h", "symbol"))

        for w in ("5m", "15m", "1h", "4h", "24h"):
            assert f"liq:{w}:m" in datas
        assert "liq:1h:e" in datas  # cambiar a exchanges conserva la ventana
        assert all(len(d.encode()) <= 64 for d in datas)

    def test_marca_la_ventana_y_vista_activas(self):
        from src.handlers.liq import armar_teclado

        kb = armar_teclado("4h", "exchange")
        botones = [(b.callback_data, b.text) for fila in kb.inline_keyboard for b in fila]

        assert ("liq:4h:e", "\u2705 Exchanges") in botones  # vista activa
        assert ("liq:4h:e", "\u2705 4 h") in botones  # ventana activa, conserva la vista
        assert ("liq:4h:m", "Monedas") in botones
        assert not any(t.startswith("\u2705") and "1 h" in t for _, t in botones)


def _ctx(api):
    ctx = MagicMock()
    ctx.bot_data = {"api_client": api}
    ctx.args = []
    return ctx


def _api(respuesta):
    api = MagicMock()
    api.get_liquidations = AsyncMock(return_value=respuesta)
    return api


class TestComando:
    @pytest.mark.asyncio
    async def test_responde_con_texto_html_y_teclado(self):
        from src.handlers.liq import liq_command

        update = MagicMock()
        update.effective_user.id = 7
        update.message.reply_text = AsyncMock()
        api = _api(_respuesta([_item("BTC", 1000, 0)]))

        await liq_command(update, _ctx(api))

        api.get_liquidations.assert_awaited_once_with("1h", "symbol")
        kw = update.message.reply_text.call_args.kwargs
        assert kw["parse_mode"] == "HTML" and kw["reply_markup"] is not None

    @pytest.mark.asyncio
    async def test_argumentos_invalidos_muestran_el_uso_sin_llamar_a_la_api(self):
        from src.handlers.liq import liq_command

        update = MagicMock()
        update.message.reply_text = AsyncMock()
        api = _api(None)
        ctx = _ctx(api)
        ctx.args = ["12h"]

        await liq_command(update, ctx)

        api.get_liquidations.assert_not_awaited()
        assert "Uso:" in update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_api_caida_da_mensaje_amable(self):
        from src.handlers.liq import liq_command

        update = MagicMock()
        update.effective_user.id = 7
        update.message.reply_text = AsyncMock()

        await liq_command(update, _ctx(_api(None)))

        assert "No pude obtener" in update.message.reply_text.call_args.args[0]


def _cb_update(data):
    u = MagicMock()
    u.callback_query.data = data
    u.callback_query.edit_message_text = AsyncMock()
    u.callback_query.answer = AsyncMock()
    return u


class TestCallback:
    @pytest.mark.asyncio
    async def test_cambia_ventana_editando_el_mismo_mensaje(self):
        from src.handlers.liq import liq_callback

        update = _cb_update("liq:4h:e")
        api = _api(_respuesta([_item("binance", 1000, 0)], by="exchange", window="4h"))

        await liq_callback(update, _ctx(api), "liq:4h:e")

        api.get_liquidations.assert_awaited_once_with("4h", "exchange")
        kw = update.callback_query.edit_message_text.call_args.kwargs
        assert kw["parse_mode"] == "HTML"

    @pytest.mark.asyncio
    async def test_liq_open_del_menu_abre_la_vista_por_defecto(self):
        from src.handlers.liq import liq_callback

        update = _cb_update("liq_open")
        api = _api(_respuesta([_item("BTC", 1000, 0)]))

        await liq_callback(update, _ctx(api), "liq_open")

        api.get_liquidations.assert_awaited_once_with("1h", "symbol")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("data", ["liq:12h:m", "liq:1h:z", "liq:x", "liq:1h:m:extra"])
    async def test_callback_invalido_se_ignora(self, data):
        from src.handlers.liq import liq_callback

        update = _cb_update(data)
        api = _api(_respuesta([]))

        await liq_callback(update, _ctx(api), data)

        api.get_liquidations.assert_not_awaited()
        update.callback_query.edit_message_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_modified_no_es_un_error(self):
        from src.handlers.liq import liq_callback

        update = _cb_update("liq:1h:m")
        update.callback_query.edit_message_text.side_effect = BadRequest("Message is not modified")
        api = _api(_respuesta([_item("BTC", 1000, 0)]))

        await liq_callback(update, _ctx(api), "liq:1h:m")  # no lanza

    @pytest.mark.asyncio
    async def test_otro_error_de_telegram_si_se_propaga(self):
        from src.handlers.liq import liq_callback

        update = _cb_update("liq:1h:m")
        update.callback_query.edit_message_text.side_effect = BadRequest("Chat not found")
        api = _api(_respuesta([_item("BTC", 1000, 0)]))

        with pytest.raises(BadRequest):
            await liq_callback(update, _ctx(api), "liq:1h:m")

    @pytest.mark.asyncio
    async def test_api_caida_en_callback_edita_con_aviso(self):
        from src.handlers.liq import liq_callback

        update = _cb_update("liq:1h:m")

        await liq_callback(update, _ctx(_api(None)), "liq:1h:m")

        assert "No pude obtener" in update.callback_query.edit_message_text.call_args.args[0]


class TestRegistro:
    def test_comando_registrado_con_su_namespace(self):
        from src.commands import COMANDOS

        cmd = next(c for c in COMANDOS if c.name == "liq")
        assert not cmd.admin and cmd.rutas() == ("liq",)
        assert len(cmd.descripcion) <= 256

    def test_help_tiene_ficha_y_lista(self):
        from src.handlers import help as h

        assert "liq" in h.HELP_TOPICS and "/liq" in h.SUMMARY_TEXT
