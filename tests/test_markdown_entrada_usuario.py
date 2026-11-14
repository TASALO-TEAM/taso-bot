# tests/test_markdown_entrada_usuario.py
"""H-039: el texto que escribe el usuario no debe romper el Markdown de las respuestas.

Antes, /p, /alert, /graf y /ta reflejaban el simbolo tal cual dentro de *...* o _..._.
Con un simbolo como "A*B" Telegram rechazaba el mensaje (BadRequest), el usuario no
recibia respuesta y error_handler avisaba al grupo de soporte.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import User


def _msg_update(user_id: int = 1):
    sent = MagicMock()
    sent.edit_text = AsyncMock()
    msg = MagicMock()
    msg.reply_text = AsyncMock(return_value=sent)
    msg.reply_chat_action = AsyncMock()
    update = MagicMock()
    update.effective_user = User(id=user_id, is_bot=False, first_name="Test")
    update.message = msg
    update.effective_message = msg
    update.callback_query = None
    return update, msg, sent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "datos, simbolo, esperado",
    [
        ({"not_found": True}, "A*B", "A\\*B"),
        (None, "A_B", "A\\_B"),
    ],
)
async def test_p_escapa_el_simbolo_del_usuario(datos, simbolo, esperado):
    from src.handlers.p import p_command

    update, msg, _ = _msg_update()
    ctx = MagicMock()
    ctx.args = [simbolo]
    cliente = MagicMock()
    cliente.get_crypto_data = AsyncMock(return_value=datos)

    with patch("src.handlers.p.get_crypto_client", return_value=cliente), \
         patch("src.handlers.p.track_command_usage", new=AsyncMock()), \
         patch("src.handlers.p.get_ad_block", new=AsyncMock(return_value="")):
        await p_command(update, ctx)

    assert esperado in msg.reply_text.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("precio", ["nan", "inf", "-inf", "1e999"])
async def test_alert_rechaza_precios_no_finitos(precio):
    from src.handlers.alert import alert_command

    update, msg, _ = _msg_update()
    ctx = MagicMock()
    ctx.args = ["BTC", precio]
    cliente = MagicMock()
    cliente.get_crypto_data = AsyncMock()

    with patch("src.handlers.alert.get_crypto_client", return_value=cliente), \
         patch("src.handlers.alert._get_api_client", return_value=MagicMock()), \
         patch("src.handlers.alert.track_command_usage", new=AsyncMock()):
        await alert_command(update, ctx)

    assert "inválido" in msg.reply_text.call_args.args[0]
    cliente.get_crypto_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_alert_precio_invalido_no_repite_el_texto_del_usuario():
    from src.handlers.alert import alert_command

    update, msg, _ = _msg_update()
    ctx = MagicMock()
    ctx.args = ["BTC", "x`y"]

    with patch("src.handlers.alert.get_crypto_client", return_value=MagicMock()), \
         patch("src.handlers.alert._get_api_client", return_value=MagicMock()), \
         patch("src.handlers.alert.track_command_usage", new=AsyncMock()):
        await alert_command(update, ctx)

    texto = msg.reply_text.call_args.args[0]
    assert "inválido" in texto
    assert "x`y" not in texto


@pytest.mark.asyncio
async def test_alert_escapa_la_moneda_cuando_no_hay_precio():
    from src.handlers.alert import alert_command

    update, msg, _ = _msg_update()
    ctx = MagicMock()
    ctx.args = ["A*B", "100"]
    cliente = MagicMock()
    cliente.get_crypto_data = AsyncMock(return_value=None)

    with patch("src.handlers.alert.get_crypto_client", return_value=cliente), \
         patch("src.handlers.alert._get_api_client", return_value=MagicMock()), \
         patch("src.handlers.alert.track_command_usage", new=AsyncMock()):
        await alert_command(update, ctx)

    assert "A\\*B" in msg.reply_text.call_args.args[0]


@pytest.mark.asyncio
async def test_graf_escapa_el_simbolo_en_espera_y_en_error():
    from src.handlers.trading import _do_graf

    update, msg, sent = _msg_update()
    ctx = MagicMock()

    with patch("src.handlers.trading._get_binance_klines_for_chart", return_value=(None, None)):
        await _do_graf(update, ctx, base="A*B", quote="USDT", timeframe="1h")

    assert "A\\*BUSDT" in msg.reply_text.call_args.args[0]
    assert "A\\*BUSDT" in sent.edit_text.call_args.args[0]


@pytest.mark.asyncio
async def test_ta_escapa_el_simbolo_en_espera_y_en_error():
    from src.handlers.ta import ta_command

    update, msg, sent = _msg_update()
    ctx = MagicMock()
    ctx.args = ["A*B"]

    with patch("src.handlers.ta.get_binance_klines", return_value=None), \
         patch("src.handlers.ta.get_tradingview_analysis_enhanced", return_value=None):
        await ta_command(update, ctx)

    assert "A\\*BUSDT" in msg.reply_text.call_args_list[0].args[0]
    assert "A\\*BUSDT" in sent.edit_text.call_args.args[0]
