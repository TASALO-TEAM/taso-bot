# tests/test_qp_handler.py
"""Tests para el comando /qp: cliente QvaPay, formatter y handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User

from src.qvapay_client import QvaPayClient, QVAPAY_COINS
from src.formatters import build_qvapay_message
from src.handlers.qp import qp_command, qp_refresh_callback, get_qvapay_client
from src.cache import cache


def _make_message_update(user_id: int = 12345):
    user = User(id=user_id, is_bot=False, first_name="Test")
    message = MagicMock()
    message.reply_chat_action = AsyncMock()
    message.reply_text = AsyncMock()
    update = MagicMock()
    update.effective_user = user
    update.message = message
    update.callback_query = None
    return update


def _make_callback_update(user_id: int = 12345):
    user = User(id=user_id, is_bot=False, first_name="Test")
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user = user
    update = MagicMock()
    update.effective_user = user
    update.message = None
    update.callback_query = query
    return update


RATES_COMPLETAS = {
    "CUP": 977.73, "MLC": 1.43, "TROPIPAY": 0.91, "ETECSA": 405.19,
    "ZELLE": 1.01, "CLASICA": 1.05, "BOLSATM": 965.03,
    "BANDECPREPAGO": 1.10, "SBERBANK": None,
}


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


# ── build_qvapay_message ──

def test_build_qvapay_message_incluye_todas_las_monedas():
    mensaje = build_qvapay_message(RATES_COMPLETAS)
    assert "Tasa de cambio promedio P2P QvaPay.com x USD:" in mensaje
    assert "💰 CUP: $977.73" in mensaje
    assert "💵 MLC: $1.43" in mensaje
    assert "💶 TROPIPAY: $0.91" in mensaje
    assert "📱 ETECSA: $405.19" in mensaje
    assert "🏦 ZELLE: $1.01" in mensaje
    assert "💷 CLASICA: $1.05" in mensaje
    assert "💸 BOLSATM: $965.03" in mensaje
    assert "🏦 BANDECPREPAGO: $1.10" in mensaje
    assert "Última actualización:" in mensaje


def test_build_qvapay_message_moneda_sin_datos_muestra_cero():
    """None (sin operaciones recientes / fallo puntual) se muestra como $0.00."""
    mensaje = build_qvapay_message(RATES_COMPLETAS)
    assert "🏦 SBERBANK: $0.00" in mensaje


def test_build_qvapay_message_orden_sigue_qvapay_coins():
    mensaje = build_qvapay_message(RATES_COMPLETAS)
    posiciones = [mensaje.index(f"{label}:") for label in QVAPAY_COINS]
    assert posiciones == sorted(posiciones)


# ── QvaPayClient ──

@pytest.mark.asyncio
async def test_fetch_average_calcula_promedio_compra_venta():
    client = QvaPayClient()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"average_buy": 970.0, "average_sell": 985.46})

    with patch.object(client, "_get_client") as mock_get_client:
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_http

        resultado = await client._fetch_average("BANK_CUP")

    assert resultado == pytest.approx(977.73)


@pytest.mark.asyncio
async def test_fetch_average_retorna_none_si_no_hay_operaciones():
    client = QvaPayClient()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"average_buy": None, "average_sell": None})

    with patch.object(client, "_get_client") as mock_get_client:
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_http

        resultado = await client._fetch_average("SBERBANK")

    assert resultado is None


@pytest.mark.asyncio
async def test_fetch_average_retorna_none_en_error_de_red():
    import httpx
    client = QvaPayClient()

    with patch.object(client, "_get_client") as mock_get_client:
        mock_http = MagicMock()
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
        mock_get_client.return_value = mock_http

        resultado = await client._fetch_average("TROPIPAY")

    assert resultado is None


@pytest.mark.asyncio
async def test_get_p2p_rates_consulta_las_9_monedas_en_orden():
    client = QvaPayClient()

    async def fake_fetch(coin_code):
        return {"BANK_CUP": 977.73, "BANK_MLC": 1.43}.get(coin_code)

    with patch.object(client, "_fetch_average", side_effect=fake_fetch):
        rates = await client.get_p2p_rates()

    assert list(rates.keys()) == list(QVAPAY_COINS.keys())
    assert rates["CUP"] == 977.73
    assert rates["MLC"] == 1.43
    assert rates["SBERBANK"] is None  # no mockeado -> fake_fetch devuelve None


# ── qp_command / qp_refresh_callback ──

@pytest.mark.asyncio
async def test_qp_command_envia_mensaje_con_teclado():
    update = _make_message_update()
    ctx = MagicMock()
    ctx.bot_data = {}

    with patch("src.handlers.qp.get_qvapay_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_p2p_rates = AsyncMock(return_value=RATES_COMPLETAS)
        mock_get_client.return_value = mock_client

        await qp_command(update, ctx)

    update.message.reply_text.assert_called_once()
    mensaje = update.message.reply_text.call_args[0][0]
    assert "QvaPay.com" in mensaje
    keyboard = update.message.reply_text.call_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "qp_refresh"


@pytest.mark.asyncio
async def test_qp_command_usa_cache_en_llamada_repetida():
    update1 = _make_message_update()
    update2 = _make_message_update()
    ctx = MagicMock()
    ctx.bot_data = {}

    with patch("src.handlers.qp.get_qvapay_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_p2p_rates = AsyncMock(return_value=RATES_COMPLETAS)
        mock_get_client.return_value = mock_client

        await qp_command(update1, ctx)
        await qp_command(update2, ctx)

    # El segundo llamado debe salir de caché: solo 1 fetch real a QvaPay
    mock_client.get_p2p_rates.assert_called_once()


@pytest.mark.asyncio
async def test_qp_command_error_muestra_mensaje_amigable():
    update = _make_message_update()
    ctx = MagicMock()
    ctx.bot_data = {}

    with patch("src.handlers.qp.get_qvapay_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_p2p_rates = AsyncMock(side_effect=Exception("boom"))
        mock_get_client.return_value = mock_client

        await qp_command(update, ctx)

    update.message.reply_text.assert_called_once()
    mensaje = update.message.reply_text.call_args[0][0]
    assert "No se pudieron obtener" in mensaje


@pytest.mark.asyncio
async def test_qp_refresh_callback_delega_a_qp_command():
    update = _make_callback_update()
    ctx = MagicMock()
    ctx.bot_data = {}

    with patch("src.handlers.qp.get_qvapay_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_p2p_rates = AsyncMock(return_value=RATES_COMPLETAS)
        mock_get_client.return_value = mock_client

        await qp_refresh_callback(update, ctx)

    update.callback_query.answer.assert_called()
    update.callback_query.edit_message_text.assert_called_once()
