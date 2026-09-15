# tests/test_tspl_blog_handler.py
"""Tests para el subcomando `/tspl blog`: dispatch desde tspl_command,
contenido del post (imagen fija + datos de mercado ampliados, sin HTML
embebido) y entrega como mensaje <pre> (corto) o archivo .txt (largo)."""

import html as html_lib

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User, Message, Chat
from telegram.constants import ParseMode

from src.handlers.tspl import (
    tspl_command,
    tspl_blog_command,
    _build_blog_content,
    _build_blog_news_section,
    _telegram_text_length,
    BLOG_HEADER_IMAGE_URL,
    BLOG_MESSAGE_SAFE_LIMIT,
)
from src.formatters import build_tspl_market_bullets


def _make_message_update(user_id: int = 111, args: list | None = None):
    """Update con mensaje de texto (comando /tspl blog escrito directamente)."""
    user = User(id=user_id, is_bot=False, first_name="Test")
    chat = Chat(id=user_id, type="private")
    message = MagicMock(spec=Message)
    message.chat = chat
    message.reply_chat_action = AsyncMock()
    message.reply_text = AsyncMock()
    message.reply_document = AsyncMock()

    update = MagicMock(spec=Update)
    update.message = message
    update.callback_query = None
    update.effective_user = user

    ctx = MagicMock()
    ctx.args = args or []
    return update, ctx


DIGEST_COMPLETO = {
    "lede": "El indicador Miedo y Codicia se sitúa en 68 (Greed).",
    "teaser": "Hoy destacan alertas de seguridad y movimientos en varios tokens. Vamos a empezar.",
    "items": [
        {"emoji": "🛡️", "titulo": "Alerta de seguridad", "parrafo": "Detalle de la alerta."},
        {"emoji": "📊", "titulo": "JST resiste", "parrafo": "Detalle de JST."},
    ],
    "radar": "Vigilar CPI y la decisión del FOMC.",
}

SNAPSHOT_COMPLETO = {
    "fear_greed": {"value": 68, "classification": "Greed"},
    "altcoin_season": {"value": 41, "label": "Mixto"},
    "global_metrics": {
        "total_market_cap": 2_650_000_000_000,
        "total_volume_24h": 95_440_000_000,
        "market_cap_change_24h": 1.03,
        "volume_change_24h": 12.38,
        "btc_dominance": 58.65,
        "btc_dominance_change_24h": -0.35,
    },
    "btc_technical": {"recommendation": "BUY", "buy_score": 14, "sell_score": 6, "neutral_score": 3},
    "top_movers": {
        "gainers": [{"symbol": "SOL", "name": "Solana", "percent_change_24h": 8.2}],
        "losers": [{"symbol": "XYZ", "name": "Xyz Coin", "percent_change_24h": -6.4}],
    },
    "trending": [{"symbol": "SOL", "name": "Solana"}],
}


# ── Dispatch desde /tspl ──

@pytest.mark.asyncio
async def test_tspl_command_dispatches_to_blog_subcommand():
    """`/tspl blog` debe despachar a tspl_blog_command en vez de correr el
    flujo normal de Telegram (que arma teclado + edita/responde mensaje)."""
    update, ctx = _make_message_update(args=["blog"])

    with patch("src.handlers.tspl.tspl_blog_command", new_callable=AsyncMock) as mock_blog:
        await tspl_command(update, ctx)
        mock_blog.assert_called_once_with(update, ctx)


@pytest.mark.asyncio
async def test_tspl_command_is_case_insensitive_for_blog():
    """`/tspl BLOG` (mayúsculas) también debe despachar al subcomando."""
    update, ctx = _make_message_update(args=["BLOG"])

    with patch("src.handlers.tspl.tspl_blog_command", new_callable=AsyncMock) as mock_blog:
        await tspl_command(update, ctx)
        mock_blog.assert_called_once()


# ── tspl_blog_command: envío corto → mensaje <pre> ──

@pytest.mark.asyncio
async def test_tspl_blog_command_sends_pre_block_message_when_short():
    """Con digest y snapshot típicos (contenido bajo el límite), lo manda
    como mensaje de texto envuelto en <pre> con parse_mode=HTML, no como
    archivo."""
    update, ctx = _make_message_update()

    with patch("src.handlers.tspl._get_or_build_digest", new_callable=AsyncMock) as mock_digest, \
         patch("src.handlers.tspl._get_or_build_market_snapshot", new_callable=AsyncMock) as mock_snapshot, \
         patch("src.handlers.tspl.track_command_usage", new_callable=AsyncMock):

        mock_digest.return_value = DIGEST_COMPLETO
        mock_snapshot.return_value = SNAPSHOT_COMPLETO

        await tspl_blog_command(update, ctx)

        update.message.reply_document.assert_not_called()
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        mensaje = args[0]

        assert mensaje.startswith("<pre>")
        assert mensaje.endswith("</pre>")
        assert kwargs["parse_mode"] == ParseMode.HTML

        # Desescapamos para verificar el contenido real (algunos textos,
        # como "Fear & Greed", llevan un "&" que queda como "&amp;" en el
        # mensaje escapado).
        contenido = html_lib.unescape(mensaje[len("<pre>"):-len("</pre>")])
        assert BLOG_HEADER_IMAGE_URL in contenido
        assert "TASALO Spotlight" in contenido
        assert "Lo más importante del día" in contenido
        assert "Resumen del mercado" in contenido
        assert "En el radar" in contenido
        # Datos ampliados que no entran en el mensaje corto de Telegram:
        assert "Sesgo técnico BTC" in contenido
        assert "Mayores subidas 24h" in contenido
        assert "Tendencia" in contenido
        # Markdown estándar (negrita doble), no Markdown v1 de Telegram:
        assert "**Fear & Greed:**" in contenido
        # Sin HTML embebido en el contenido generado.
        assert "<center>" not in contenido
        assert "<div" not in contenido


@pytest.mark.asyncio
async def test_tspl_blog_command_falls_back_to_txt_file_when_long():
    """Si el contenido supera BLOG_MESSAGE_SAFE_LIMIT, cae a un documento
    .txt en vez de mandar el mensaje (evita el límite real de Telegram)."""
    update, ctx = _make_message_update()
    contenido_largo = "x" * (BLOG_MESSAGE_SAFE_LIMIT + 500)

    with patch("src.handlers.tspl._get_or_build_digest", new_callable=AsyncMock) as mock_digest, \
         patch("src.handlers.tspl._get_or_build_market_snapshot", new_callable=AsyncMock) as mock_snapshot, \
         patch("src.handlers.tspl._build_blog_content", return_value=contenido_largo), \
         patch("src.handlers.tspl.track_command_usage", new_callable=AsyncMock):

        mock_digest.return_value = DIGEST_COMPLETO
        mock_snapshot.return_value = SNAPSHOT_COMPLETO

        await tspl_blog_command(update, ctx)

        update.message.reply_text.assert_not_called()
        update.message.reply_document.assert_called_once()
        _, kwargs = update.message.reply_document.call_args
        assert kwargs["filename"].endswith(".txt")
        assert kwargs["document"].getvalue().decode("utf-8") == contenido_largo


@pytest.mark.asyncio
async def test_tspl_blog_command_shows_error_when_no_data():
    """Si digest y snapshot fallan a la vez, avisa por texto y no intenta
    mandar ningún archivo ni mensaje <pre>."""
    update, ctx = _make_message_update()

    with patch("src.handlers.tspl._get_or_build_digest", new_callable=AsyncMock) as mock_digest, \
         patch("src.handlers.tspl._get_or_build_market_snapshot", new_callable=AsyncMock) as mock_snapshot, \
         patch("src.handlers.tspl.track_command_usage", new_callable=AsyncMock) as mock_track:

        mock_digest.return_value = None
        mock_snapshot.return_value = None

        await tspl_blog_command(update, ctx)

        update.message.reply_document.assert_not_called()
        update.message.reply_text.assert_called_once()
        mock_track.assert_called_once()
        assert mock_track.call_args.kwargs.get("success") is False


# ── _build_blog_content / _build_blog_news_section ──

def test_build_blog_content_is_pure_markdown_no_html():
    contenido = _build_blog_content(DIGEST_COMPLETO, SNAPSHOT_COMPLETO)
    assert contenido.startswith(f"![]({BLOG_HEADER_IMAGE_URL})")
    assert "<center>" not in contenido
    assert "<div" not in contenido
    assert "<sub>" not in contenido
    assert "@tasalobot" in contenido
    assert "---" in contenido  # separador antes de la firma


def test_build_blog_content_uses_real_markdown_bullets():
    """El resumen de mercado del blog debe usar "- " (lista real de
    Markdown, se ve como <ul> en el editor) en vez de "• " (carácter
    literal que Telegram muestra bien pero que el editor del blog no
    interpreta como lista, quedando todo apiñado)."""
    contenido = _build_blog_content(DIGEST_COMPLETO, SNAPSHOT_COMPLETO)
    assert "- 💰 **Capitalización:**" in contenido
    assert "•" not in contenido


def test_build_blog_content_falls_back_without_digest():
    """Sin digest (Groq/NewsData fallaron), igual arma el post solo con
    datos de mercado, sin romper."""
    contenido = _build_blog_content(None, SNAPSHOT_COMPLETO)
    assert "TASALO Spotlight" in contenido
    assert "no está disponible en este momento" in contenido  # lede de fallback
    assert "(noticias no disponibles en este momento)" in contenido  # sección de noticias
    assert "Resumen del mercado" in contenido


def test_build_blog_news_section_uses_h3_headers():
    seccion = _build_blog_news_section(DIGEST_COMPLETO)
    assert "### 🛡️ Alerta de seguridad" in seccion
    assert "### 📊 JST resiste" in seccion


def test_build_blog_news_section_handles_missing_digest():
    assert "no disponibles" in _build_blog_news_section(None)


# ── _telegram_text_length: UTF-16 code units vs len() de Python ──

def test_telegram_text_length_counts_utf16_code_units():
    """Un emoji fuera del BMP (ej. 📊, U+1F4CA) cuenta 1 en len() de
    Python pero 2 code units en UTF-16 — que es lo que Telegram usa."""
    texto = "📊"
    assert len(texto) == 1
    assert _telegram_text_length(texto) == 2


def test_telegram_text_length_matches_len_for_ascii():
    texto = "hola mundo"
    assert _telegram_text_length(texto) == len(texto)


# ── build_tspl_market_bullets (formatters.py): modo extended ──

def test_market_bullets_default_matches_previous_telegram_output():
    """extended=False (default) debe seguir dando exactamente el mismo
    bloque de 5 bullets que ya usa /tspl en Telegram, con negrita simple."""
    bloque = build_tspl_market_bullets(SNAPSHOT_COMPLETO)
    assert "*Capitalización:*" in bloque
    assert "**Capitalización:**" not in bloque
    assert "Sesgo técnico BTC" not in bloque
    assert "Mayores subidas" not in bloque


def test_market_bullets_extended_adds_movers_and_technical():
    bloque = build_tspl_market_bullets(SNAPSHOT_COMPLETO, extended=True, bold="**")
    assert "**Sesgo técnico BTC (TradingView, 1D):** 🐂 Compra" in bloque
    assert "Solana (SOL) +8.20%" in bloque
    assert "Xyz Coin (XYZ) -6.40%" in bloque
    assert "**Tendencia:** Solana (SOL)" in bloque


def test_market_bullets_default_bullet_marker_is_literal_dot():
    """Por defecto (uso en Telegram) el marcador sigue siendo "•",
    porque Telegram no interpreta "-" como lista, solo lo muestra literal."""
    bloque = build_tspl_market_bullets(SNAPSHOT_COMPLETO)
    assert bloque.startswith("• ")
    assert "\n- " not in bloque


def test_market_bullets_custom_bullet_marker():
    """bullet="-" (uso en el blog) reemplaza el "•" por un guion real de
    lista de Markdown en todas las líneas, incluidas las de extended."""
    bloque = build_tspl_market_bullets(SNAPSHOT_COMPLETO, extended=True, bold="**", bullet="-")
    assert "•" not in bloque
    assert "- 💰 **Capitalización:**" in bloque
    assert "- 📈 **Sesgo técnico BTC" in bloque


def test_market_bullets_extended_handles_missing_optional_sources():
    """Si top_movers/trending/btc_technical faltan, no debe romper ni
    agregar líneas vacías."""
    snapshot_parcial = {
        **SNAPSHOT_COMPLETO,
        "btc_technical": None,
        "top_movers": None,
        "trending": None,
    }
    bloque = build_tspl_market_bullets(snapshot_parcial, extended=True, bold="**")
    assert "Sesgo técnico" not in bloque
    assert "Mayores subidas" not in bloque
    assert "Tendencia" not in bloque
    assert "**Fear & Greed:**" in bloque  # el resto sigue presente
