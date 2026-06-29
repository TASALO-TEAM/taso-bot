# tests/test_p_handler.py
"""Tests para los callbacks de /p: refresh, ver más (p_more), ver menos (p_less)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User

from src.handlers.p import p_more_callback, p_less_callback, _build_keyboard


def _make_callback_update(callback_data: str, user_id: int = 12345):
    user = User(id=user_id, is_bot=False, first_name="Test")
    query = MagicMock()
    query.data = callback_data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user = user
    return Update(update_id=1, callback_query=query)


DATOS_CON_ENRICHMENT = {
    "symbol": "BTC",
    "price": 60000.0,
    "price_eth": 20.0,
    "price_btc": 1.0,
    "high_24h": 61000.0,
    "low_24h": 59000.0,
    "percent_change_1h": 0.1,
    "percent_change_24h": 1.5,
    "percent_change_7d": 3.0,
    "market_cap_rank": 1,
    "market_cap": 1_200_000_000_000,
    "volume_24h": 30_000_000_000,
    "primary_source": "coinmarketcap",
    "enrichment": {
        "ath": 73750.07, "ath_change_pct": -18.45, "ath_date": "2024-03-10T00:00:00Z",
        "atl": 67.81, "atl_date": "2013-07-06T00:00:00Z",
        "circulating_supply": 19_800_000, "total_supply": 19_800_000, "max_supply": 21_000_000,
        "category": "Smart Contract Platform", "sentiment_up_pct": 78.3, "market_cap_rank": 1,
    },
}

DATOS_SIN_ENRICHMENT = {**DATOS_CON_ENRICHMENT, "enrichment": None}


# ── p_more_callback ──

@pytest.mark.asyncio
async def test_p_more_expands_message_with_enrichment():
    """p_more_callback edita el mensaje agregando el bloque de CoinGecko."""
    update = _make_callback_update("p_more|BTC")
    ctx = MagicMock()

    with patch("src.handlers.p.get_crypto_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_crypto_data = AsyncMock(return_value=DATOS_CON_ENRICHMENT)
        mock_get_client.return_value = mock_client

        await p_more_callback(update, ctx)

        update.callback_query.edit_message_text.assert_called_once()
        call_args = update.callback_query.edit_message_text.call_args
        mensaje = call_args[0][0]
        assert "Info adicional (CoinGecko)" in mensaje
        assert "*BTC*" in mensaje


@pytest.mark.asyncio
async def test_p_more_shows_alert_when_no_enrichment():
    """p_more_callback avisa con alert si ya no hay datos de enriquecimiento."""
    update = _make_callback_update("p_more|BTC")
    ctx = MagicMock()

    with patch("src.handlers.p.get_crypto_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_crypto_data = AsyncMock(return_value=DATOS_SIN_ENRICHMENT)
        mock_get_client.return_value = mock_client

        await p_more_callback(update, ctx)

        update.callback_query.answer.assert_called_once()
        update.callback_query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_p_more_shows_alert_when_data_fetch_fails():
    """p_more_callback avisa con alert si get_crypto_data devuelve None."""
    update = _make_callback_update("p_more|BTC")
    ctx = MagicMock()

    with patch("src.handlers.p.get_crypto_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_crypto_data = AsyncMock(return_value=None)
        mock_get_client.return_value = mock_client

        await p_more_callback(update, ctx)

        update.callback_query.answer.assert_called_once_with(
            "⚠️ Ya no se pueden obtener datos", show_alert=True
        )


# ── p_less_callback ──

@pytest.mark.asyncio
async def test_p_less_collapses_message():
    """p_less_callback edita el mensaje quitando el bloque extendido."""
    update = _make_callback_update("p_less|BTC")
    ctx = MagicMock()

    with patch("src.handlers.p.get_crypto_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_crypto_data = AsyncMock(return_value=DATOS_CON_ENRICHMENT)
        mock_get_client.return_value = mock_client

        await p_less_callback(update, ctx)

        update.callback_query.edit_message_text.assert_called_once()
        mensaje = update.callback_query.edit_message_text.call_args[0][0]
        assert "Info adicional" not in mensaje
        assert "*BTC*" in mensaje


# ── _build_keyboard ──

def test_build_keyboard_includes_ver_mas_when_enrichment_available():
    keyboard = _build_keyboard("BTC", has_enrichment=True, expanded=False)
    callback_datas = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert "p_more|BTC" in callback_datas
    assert "p_less|BTC" not in callback_datas


def test_build_keyboard_includes_ver_menos_when_expanded():
    keyboard = _build_keyboard("BTC", has_enrichment=True, expanded=True)
    callback_datas = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert "p_less|BTC" in callback_datas
    assert "p_more|BTC" not in callback_datas


def test_build_keyboard_omits_toggle_when_no_enrichment():
    """Sin datos de CoinGecko, no debe aparecer ningún botón Ver más/Ver menos."""
    keyboard = _build_keyboard("XYZ", has_enrichment=False, expanded=False)
    callback_datas = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert not any(cd.startswith("p_more|") or cd.startswith("p_less|") for cd in callback_datas)
    # Pero siempre deben estar refresh y TA
    assert "p_refresh_XYZ" in callback_datas
