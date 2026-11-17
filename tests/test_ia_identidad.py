"""F5-T2/T3/T4: identidad TASALO IA en un solo lugar, /ta con sesgo en vez de COMPRAR/VENDER/MANTENER."""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.core.ai_logic as ai_logic
from src.core import ia_identidad as ia

OLD_P = "Análisis generado por IA. No constituye asesoramiento financiero."
OLD_TA = "*Análisis generado por IA — no es asesoramiento financiero.*"

PROMPTS = [
    ai_logic.CRYPTO_ANALYSIS_PROMPT,
    ai_logic.PRICE_SPOTLIGHT_PROMPT,
    ai_logic.MARKET_SPOTLIGHT_PROMPT,
    ai_logic.TSPL_DIGEST_PROMPT,
]


def _settings():
    s = MagicMock()
    s.groq_api_key = "gsk_test"
    s.groq_api_keys = ["gsk_test"]
    return s


def _resp(texto):
    return {"choices": [{"message": {"content": texto}, "finish_reason": "stop"}], "usage": {}}


def _llamar_ta():
    return ai_logic.get_groq_crypto_analysis("BTCUSDT", "4h", "reporte")


def _llamar_p():
    return ai_logic.get_groq_price_spotlight({"symbol": "BTC"})


def _llamar_spl():
    return ai_logic.get_groq_market_spotlight({})


LLAMADAS = [_llamar_ta, _llamar_p, _llamar_spl]


async def _correr(llamar, texto):
    mock = AsyncMock(return_value=_resp(texto))
    with patch("src.core.ai_logic.settings", _settings()), \
         patch("src.core.ai_logic._format_price_spotlight_data", return_value="x"), \
         patch("src.core.ai_logic._format_market_snapshot_text", return_value="x"), \
         patch("src.core.ai_logic._call_groq_async", mock):
        salida = await llamar()
    return salida, mock.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("llamar", LLAMADAS)
async def test_el_system_message_firma_como_tasalo_ia(llamar):
    _, payload = await _correr(llamar, "Texto de prueba.")
    assert "TASALO IA" in payload["messages"][0]["content"]


@pytest.mark.parametrize("prompt", PROMPTS)
def test_todo_prompt_se_presenta_como_tasalo_ia(prompt):
    assert "TASALO IA" in prompt


def test_ta_no_pide_comprar_vender_mantener_y_pasa_a_sesgo():
    p = ai_logic.CRYPTO_ANALYSIS_PROMPT
    assert not re.search(r"COMPRAR|VENDER|MANTENER", p)
    assert "Sesgo y Escenarios" in p
    assert p.count("📚 *") == 7  # los siete títulos que espera el formato


def test_digest_usa_tuteo_y_sigue_siendo_formateable():
    assert not re.search(r"\b(Elegi|traducilo|Escribi|podes|cerra)\b", ai_logic.TSPL_DIGEST_PROMPT)
    ai_logic.TSPL_DIGEST_PROMPT.format(articulos_text="a", market_context="b")


@pytest.mark.parametrize("llamar", LLAMADAS)
@pytest.mark.asyncio
async def test_descargo_unico_aunque_el_modelo_agregue_el_suyo(llamar):
    salida, _ = await _correr(llamar, f"Cuerpo del análisis.\n\n{OLD_P}\n{OLD_TA}")
    assert ia.DESCARGO in salida
    assert salida.count("asesoramiento financiero") == 1
    assert "No constituye" not in salida


def test_el_descargo_nombra_a_tasalo_ia_y_es_el_mismo_texto_en_todo_el_bot():
    assert "TASALO IA" in ia.DESCARGO
    assert "no asesoramiento financiero" in ia.DESCARGO.lower()
    assert ia.descargo("_") == f"_{ia.DESCARGO}_" and ia.descargo("*") == f"*{ia.DESCARGO}*"


@pytest.mark.parametrize("sucio", [OLD_P, OLD_TA, f"_{OLD_P}_", "análisis generado por IA, no es asesoramiento financiero"])
def test_quitar_descargo_limpia_cualquier_variante_y_respeta_el_cuerpo(sucio):
    assert ia.quitar_descargo(f"Cuerpo.\n\n{sucio}") == "Cuerpo."
    assert ia.quitar_descargo("Un análisis sin aviso.") == "Un análisis sin aviso."
