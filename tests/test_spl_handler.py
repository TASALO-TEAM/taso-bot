# tests/test_spl_handler.py
"""Tests para el comando /spl (Spotlight de Mercado): caché, fallback sin
noticias, formato del mensaje y botón de refresh.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User, Message, Chat

from src.handlers.spl import spl_command, spl_refresh_callback, _build_keyboard, CACHE_KEY


def _make_message_update(user_id: int = 111):
    """Update con mensaje de texto (comando /spl escrito directamente)."""
    user = User(id=user_id, is_bot=False, first_name="Test")
    chat = Chat(id=user_id, type="private")
    message = MagicMock(spec=Message)
    message.chat = chat
    message.reply_chat_action = AsyncMock()
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.message = message
    update.callback_query = None
    update.effective_user = user
    return update


def _make_callback_update(user_id: int = 222):
    """Update con callback_query (botón 🔄 Actualizar)."""
    user = User(id=user_id, is_bot=False, first_name="Test")
    query = MagicMock()
    query.data = "spl_refresh"
    query.from_user = user
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.message = None
    update.callback_query = query
    update.effective_user = user
    return update


SNAPSHOT_COMPLETO = {
    "fear_greed": {"value": 21, "classification": "Fear", "updated_at": "2026-07-02T00:00:00Z"},
    "altcoin_season": {"value": 47, "label": "Mixto"},
    "global_metrics": {
        "total_market_cap": 2_100_000_000_000,
        "total_volume_24h": 80_000_000_000,
        "market_cap_change_24h": -1.2,
        "volume_change_24h": -10.3,
        "btc_dominance": 58.2,
        "eth_dominance": 12.1,
        "btc_dominance_change_24h": -0.3,
        "eth_dominance_change_24h": 0.1,
    },
    "top_movers": {
        "gainers": [{"symbol": "SOL", "name": "Solana", "percent_change_24h": 12.5, "price": 77.0}],
        "losers": [{"symbol": "XYZ", "name": "Xyz Coin", "percent_change_24h": -8.1, "price": 1.2}],
    },
    "trending": [{"symbol": "SOL", "name": "Solana", "percent_change_24h": 12.5}],
    "btc_technical": {"symbol": "BTCUSDT", "interval": "1d", "recommendation": "BUY", "buy_score": 14, "sell_score": 6, "neutral_score": 3},
    "news": None,  # plan Basic -> siempre None (ver docs/plans/2026-07-02-comando-spl-spotlight.md)
}


# ── spl_command: cache miss ──

@pytest.mark.asyncio
async def test_spl_command_builds_message_on_cache_miss():
    """En cache miss, arma snapshot + llama a Groq + cachea + responde."""
    update = _make_message_update()
    ctx = MagicMock()

    with patch("src.handlers.spl.cache") as mock_cache, \
         patch("src.handlers.spl.get_crypto_client") as mock_get_client, \
         patch("src.handlers.spl.get_groq_market_spotlight", new_callable=AsyncMock) as mock_groq, \
         patch("src.handlers.spl.track_command_usage", new_callable=AsyncMock):

        mock_cache.get.return_value = None
        mock_client = MagicMock()
        mock_client.get_market_snapshot = AsyncMock(return_value=SNAPSHOT_COMPLETO)
        mock_get_client.return_value = mock_client
        mock_groq.return_value = "Texto narrativo del panorama de mercado."

        await spl_command(update, ctx)

        mock_client.get_market_snapshot.assert_called_once()
        mock_groq.assert_called_once_with(SNAPSHOT_COMPLETO)

        # Se cachea el cuerpo completo (bloque de datos duros + narrativa),
        # no solo el texto de la IA — verificamos que la narrativa quede
        # incluida dentro de lo que se guarda en caché.
        mock_cache.set.assert_called_once()
        cached_key, cached_body = mock_cache.set.call_args[0]
        assert cached_key == CACHE_KEY
        assert "Texto narrativo del panorama de mercado." in cached_body

        update.message.reply_text.assert_called_once()
        mensaje = update.message.reply_text.call_args[0][0]
        assert "SPOTLIGHT" in mensaje
        assert "Texto narrativo del panorama de mercado." in mensaje


# ── spl_command: cache hit ──

@pytest.mark.asyncio
async def test_spl_command_uses_cache_on_hit():
    """En cache hit, no debe llamar a CMC ni a Groq de nuevo."""
    update = _make_message_update()
    ctx = MagicMock()

    with patch("src.handlers.spl.cache") as mock_cache, \
         patch("src.handlers.spl.get_crypto_client") as mock_get_client, \
         patch("src.handlers.spl.get_groq_market_spotlight", new_callable=AsyncMock) as mock_groq, \
         patch("src.handlers.spl.track_command_usage", new_callable=AsyncMock):

        mock_cache.get.return_value = "Panorama cacheado."
        mock_client = MagicMock()
        mock_client.get_market_snapshot = AsyncMock()
        mock_get_client.return_value = mock_client

        await spl_command(update, ctx)

        mock_client.get_market_snapshot.assert_not_called()
        mock_groq.assert_not_called()
        mock_cache.set.assert_not_called()

        mensaje = update.message.reply_text.call_args[0][0]
        assert "Panorama cacheado." in mensaje


# ── Fallback sin noticias (plan Basic) ──

@pytest.mark.asyncio
async def test_spl_command_works_without_news_section():
    """Si get_market_news devolvió None (plan Basic), igual se genera el
    spotlight solo con datos de mercado — no debe romperse el comando.
    """
    snapshot_sin_noticias = {**SNAPSHOT_COMPLETO, "news": None}
    update = _make_message_update()
    ctx = MagicMock()

    with patch("src.handlers.spl.cache") as mock_cache, \
         patch("src.handlers.spl.get_crypto_client") as mock_get_client, \
         patch("src.handlers.spl.get_groq_market_spotlight", new_callable=AsyncMock) as mock_groq, \
         patch("src.handlers.spl.track_command_usage", new_callable=AsyncMock):

        mock_cache.get.return_value = None
        mock_client = MagicMock()
        mock_client.get_market_snapshot = AsyncMock(return_value=snapshot_sin_noticias)
        mock_get_client.return_value = mock_client
        mock_groq.return_value = "Panorama solo con datos de mercado."

        await spl_command(update, ctx)

        update.message.reply_text.assert_called_once()
        mensaje = update.message.reply_text.call_args[0][0]
        assert "Panorama solo con datos de mercado." in mensaje


# ── spl_refresh_callback ──

@pytest.mark.asyncio
async def test_spl_refresh_callback_edits_message():
    """El callback de refresh reusa spl_command y edita el mensaje existente."""
    update = _make_callback_update()
    ctx = MagicMock()

    with patch("src.handlers.spl.cache") as mock_cache, \
         patch("src.handlers.spl.get_crypto_client") as mock_get_client, \
         patch("src.handlers.spl.get_groq_market_spotlight", new_callable=AsyncMock) as mock_groq, \
         patch("src.handlers.spl.track_command_usage", new_callable=AsyncMock):

        mock_cache.get.return_value = None
        mock_client = MagicMock()
        mock_client.get_market_snapshot = AsyncMock(return_value=SNAPSHOT_COMPLETO)
        mock_get_client.return_value = mock_client
        mock_groq.return_value = "Panorama actualizado."

        await spl_refresh_callback(update, ctx)

        update.callback_query.answer.assert_called_once()
        update.callback_query.edit_message_text.assert_called_once()
        mensaje = update.callback_query.edit_message_text.call_args[0][0]
        assert "Panorama actualizado." in mensaje


# ── Manejo de errores ──

@pytest.mark.asyncio
async def test_spl_command_shows_error_message_on_exception():
    """Si algo falla (excepción no controlada), responde con mensaje de
    error legible en vez de propagar la excepción al error_handler global.
    """
    update = _make_message_update()
    ctx = MagicMock()

    with patch("src.handlers.spl.cache") as mock_cache, \
         patch("src.handlers.spl.get_crypto_client") as mock_get_client, \
         patch("src.handlers.spl.track_command_usage", new_callable=AsyncMock):

        mock_cache.get.return_value = None
        mock_client = MagicMock()
        mock_client.get_market_snapshot = AsyncMock(side_effect=RuntimeError("boom"))
        mock_get_client.return_value = mock_client

        await spl_command(update, ctx)

        update.message.reply_text.assert_called_once()
        mensaje = update.message.reply_text.call_args[0][0]
        assert "no se pudo generar" in mensaje.lower()


# ── _build_keyboard ──

def test_build_keyboard_has_refresh_button():
    keyboard = _build_keyboard()
    callback_datas = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert "spl_refresh" in callback_datas


# ── build_market_spotlight_data_block (formatters.py) ──

def test_data_block_includes_new_fields():
    """Verifica que el bloque de datos duros incluye Altcoin Season Index
    y el sesgo técnico de TradingView cuando están presentes en el snapshot.
    """
    from src.formatters import build_market_spotlight_data_block

    bloque = build_market_spotlight_data_block(SNAPSHOT_COMPLETO)
    assert "Altcoin Season Index" in bloque
    assert "47/100" in bloque
    assert "Sesgo Técnico BTC" in bloque
    assert "Compra" in bloque  # BUY -> 🐂 Compra
    assert "Fear & Greed" in bloque
    assert "Mayores subidas 24h" in bloque
    assert "Tendencia" in bloque


def test_data_block_handles_missing_optional_sources():
    """Si altcoin_season o btc_technical vinieron en None (fuente caída),
    el bloque no debe romperse ni mencionar esas secciones.
    """
    from src.formatters import build_market_spotlight_data_block

    snapshot_parcial = {**SNAPSHOT_COMPLETO, "altcoin_season": None, "btc_technical": None}
    bloque = build_market_spotlight_data_block(snapshot_parcial)
    assert "Altcoin Season Index" not in bloque
    assert "Sesgo Técnico" not in bloque
    assert "Fear & Greed" in bloque  # el resto sigue presente
