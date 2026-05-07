# src/core/ai_logic.py
# Improved Groq LLM integration for trading analysis
# Uses async httpx, retry logic, structured logging, and robust error handling.
# Requires GROQ_API_KEY environment variable.

import asyncio
import logging
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import settings

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"  # Modelo válido en Groq
DEFAULT_TIMEOUT = 15
MAX_RETRIES = 3

# ── Prompt Template ──────────────────────────────────────────────────────────
CRYPTO_ANALYSIS_PROMPT = """Eres un Analista Experto en Inversiones Institucionales, Trading y criptomonedas.

Tarea: Interpreta el reporte técnico a continuación y genera un análisis narrativo profesional en español.

=== REPORTE TÉCNICO ===
{symbol} ({timeframe}) — Fuente: {source}

{report_text}
=== FIN REPORTE ===

INSTRUCCIONES:
1. Analiza y tendencia: Resume el escenario actual y la tendencia dominante.
2. Fuerza de la tendencia: Evalúa si es fuerte, moderada o débil.
3. Osciladores y momentum: Interpreta RSI, MFI, CCI, ADX, WILLR, OBV.
4. Niveles de soporte y resistencia: Destaca los niveles clave.
5. Riesgo y oportunidad: Identifica riesgos y oportunidades concretas.
6. Recomendación: Acción sugerida (COMPRAR/VENDER/MANTENER) con justificación.
7. Conclusión: Resumen ejecutivo en 1-2 líneas.

FORMATO EXACTO DE SALIDA (usa estos títulos con asteriscos exactamente como se muestra):
📚 *Análisis y Tendencia*
[Texto breve]

📚 *Fuerza de la Tendencia*
[Texto breve]

📚 *Osciladores y Momentum*
[Texto breve]

📚 *Niveles de Soporte y Resistencia*
[Texto breve]

📚 *Riesgo y Oportunidad*
[Texto breve]

📚 *Recomendación*
[Texto breve]

📚 *Conclusión*
[Texto breve]

REGLAS:
- Base exclusivamente en los datos proporcionados (no inventes números).
- Máximo 1200 caracteres en total (aproximadamente 250-300 palabras).
- Usa emojis moderadamente (📈📉⚠️✅).
- No repitas valores numéricos ya mostrados en el reporte.
- NO uses otros formatos de Markdown (como _italic_, `code`, enlaces, etc.). Solo los títulos con *...* que están indicados.
- Evita caracteres especiales que puedan romper el parseo de Telegram (como ~, `, _, [], () no formateados).
- Incluye al final el disclaimer: "*Análisis generado por IA — no es asesoramiento financiero.*"
"""


# ── Utilities ─────────────────────────────────────────────────────────────────
MAX_RESPONSE_CHARS = 3500  # Límite seguro para Telegram (deja espacio para encabezado)


def _escape_telegram_markdown(text: str) -> str:
    """
    Escapa caracteres especiales de Telegram MarkdownV2,
    preservando los asteriscos (*) que se usan para negrita en los títulos.
    """
    if not text:
        return ""
    # Escapar backslash primero
    text = text.replace("\\", "\\\\")
    # Caracteres que deben escaparse en MarkdownV2 (excepto asterisco)
    specials = r'_`[]()~>#+-=|{}.!'
    for ch in specials:
        text = text.replace(ch, f'\\{ch}')
    return text


def _truncate_smart(text: str, max_chars: int = MAX_RESPONSE_CHARS) -> str:
    """Trunca el texto en el último espacio antes del límite."""
    if len(text) <= max_chars:
        return text
    cut = text.rfind(' ', 0, max_chars)
    if cut == -1:
        cut = max_chars
    return text[:cut] + "..."


# ── HTTP Client ───────────────────────────────────────────────────────────────
class GroqAPIError(Exception):
    """Custom exception for Groq API errors."""
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)),
)
async def _call_groq_async(payload: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Make async HTTP call to Groq API with retry logic.
    Raises: GroqAPIError on failure after retries.
    """
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(GROQ_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


# ── Public API ────────────────────────────────────────────────────────────────
async def get_groq_crypto_analysis(
    symbol: str,
    timeframe: str,
    technical_report_text: str,
    source: str = "Unknown"
) -> str:
    """
    Get AI-powered trading analysis from Groq LLM.

    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        timeframe: Timeframe (e.g., '4h', '1d')
        technical_report_text: Plain text technical report (Markdown okay)
        source: Data source name (Binance, TradingView, etc.)

    Returns:
        AI analysis string (narrative in Spanish) or error message.
    """
    if not settings.groq_api_key:
        logger.error("GROQ_API_KEY not configured")
        return "⚠️ *Error:* Variable de entorno GROQ_API_KEY no configurada."

    # Build prompt
    prompt = CRYPTO_ANALYSIS_PROMPT.format(
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        report_text=technical_report_text,
    )

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": "Eres un analista financiero profesional que explica conceptos técnicos en español de forma clara y concisa."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.6,
        "max_tokens": 1024,
    }

    try:
        start = asyncio.get_event_loop().time()
        data = await _call_groq_async(payload)
        elapsed = asyncio.get_event_loop().time() - start

        choices = data.get("choices", [])
        if not choices:
            logger.warning("Groq returned empty choices for %s %s", symbol, timeframe)
            return "⚠️ La IA no generó respuesta (respuesta vacía)."

        content = choices[0].get("message", {}).get("content", "").strip()
        if not content:
            logger.warning("Groq returned empty content for %s %s", symbol, timeframe)
            return "⚠️ La IA devolvió contenido vacío."

        # Log success
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        logger.info(
            "✅ Groq analysis OK for %s %s — tokens: p=%d c=%d total=%d (%.1fs)",
            symbol, timeframe, prompt_tokens, completion_tokens,
            prompt_tokens + completion_tokens, elapsed,
        )

        # Escape and truncate before returning
        content = _escape_telegram_markdown(content)
        content = _truncate_smart(content, MAX_RESPONSE_CHARS)

        # Append disclaimer if not already present
        if "Análisis generado por IA" not in content:
            content += "\n\n*Análisis generado por IA — no es asesoramiento financiero.*"

        return content

    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response else "??"
        logger.error("Groq HTTP error %s for %s %s: %s", status, symbol, timeframe, e)
        if status == 401:
            return "⚠️ Error de autenticación con la IA (API key inválida)."
        elif status == 429:
            return "⚠️ Límite de tasa excedido en la IA. Intenta en 1 minuto."
        else:
            return f"⚠️ Error HTTP {status} de la IA. Intenta más tarde."

    except httpx.TimeoutException:
        logger.error("Groq timeout for %s %s", symbol, timeframe)
        return "⚠️ La IA tardó demasiado en responder. Intenta de nuevo."

    except httpx.NetworkError:
        logger.error("Groq network error for %s %s", symbol, timeframe)
        return "⚠️ Error de red al contactar la IA."

    except Exception as e:
        logger.exception("Unexpected error in get_groq_crypto_analysis")
        return f"⚠️ Error inesperado: {e}"

