# src/core/ai_logic.py
# Improved Groq LLM integration for trading analysis
# Uses async httpx, retry logic, structured logging, and robust error handling.
# Requires GROQ_API_KEY environment variable.

import asyncio
import itertools
import json
import logging
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import settings

logger = logging.getLogger(__name__)

# Rotación round-robin de keys de Groq (mismo patrón que CoinGeckoClient en
# este repo y core/ai_client.py en taso-gcg). Se inicializa perezosamente
# en el primer uso porque `settings` es un lazy singleton (get_settings())
# y las keys pueden no estar disponibles todavía en tiempo de import.
_groq_key_cycle = None


def _next_groq_key() -> Optional[str]:
    """Devuelve la siguiente API key de Groq en la rotación, o None si no
    hay ninguna configurada. Con 1 sola key, siempre devuelve esa misma key
    (comportamiento idéntico al anterior)."""
    global _groq_key_cycle
    if _groq_key_cycle is None:
        keys = settings.groq_api_keys
        if not keys:
            return None
        _groq_key_cycle = itertools.cycle(keys)
    return next(_groq_key_cycle)

# ── Configuration ────────────────────────────────────────────────────────────
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile deprecado por Groq (17-jun-2026)
DEFAULT_TIMEOUT = 25  # antes 15 — margen para razonamiento + generación en gpt-oss-120b
MAX_RETRIES = 3
# gpt-oss-120b es un modelo de razonamiento; sin este parámetro Groq aplica
# 'medium' por defecto y los tokens de chain-of-thought compiten por el
# mismo presupuesto que max_completion_tokens. Las 4 tareas de este módulo
# son redacción/curación a partir de datos ya resueltos, no razonamiento
# multi-paso, así que 'low' libera presupuesto para el contenido real.
DEFAULT_REASONING_EFFORT = "low"

# ── Prompt Template — Análisis Técnico Profesional (/ta) ─────────────────────
CRYPTO_ANALYSIS_PROMPT = """Eres un analista técnico senior con experiencia en mesas de trading
institucionales. Tu trabajo es traducir un reporte de indicadores crudos en
un análisis claro y accionable para un trader que ya conoce los conceptos
básicos pero no tiene tiempo de interpretar cada número por separado.

=== REPORTE TÉCNICO ===
{symbol} ({timeframe}) — Fuente: {source}

{report_text}
=== FIN REPORTE ===

CÓMO INTERPRETAR LOS DATOS:
- RSI: >70 sobrecompra, <30 sobreventa, 45-55 zona neutral/indecisión.
- MFI: similar al RSI pero pondera volumen; útil para confirmar o contradecir al RSI.
- CCI: >100 momentum alcista fuerte, <-100 momentum bajista fuerte.
- ADX: >25 tendencia con fuerza real, <20 mercado lateral/sin tendencia clara.
- Williams %R (WR): valores cercanos a 0 sugieren sobrecompra, cercanos a -100 sobreventa.
- OBV: confirma o diverge del movimiento de precio según si acompaña o no la tendencia.
- MACD histograma: positivo y creciente refuerza la tendencia alcista; negativo y decreciente, la bajista.
- Pivotes (R1-R3, S1-S3): zonas donde el precio históricamente reacciona, no garantías.
- Si dos o más osciladores se contradicen entre sí, dilo explícitamente — es información valiosa, no un error a ocultar.

TAREA — analiza el reporte y cubre estos siete puntos, en este orden:
1. Análisis y tendencia: contexto general y dirección dominante del precio.
2. Fuerza de la tendencia: usa el ADX y el score compra/venta para calificarla (fuerte/moderada/débil) y justifica por qué.
3. Osciladores y momentum: interpreta RSI, MFI, CCI, WR y OBV en conjunto — señala si confirman o contradicen la tendencia.
4. Niveles de soporte y resistencia: cuáles son los más relevantes ahora mismo y qué pasaría si se rompen.
5. Riesgo y oportunidad: qué podría invalidar la lectura actual, y dónde está el mejor punto de entrada/salida si la tendencia se mantiene.
6. Recomendación: una acción concreta (COMPRAR / VENDER / MANTENER) con la justificación más fuerte que la respalde, no una lista de razones.
7. Conclusión: una o dos frases que resuman el panorama completo.

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
- Basa el análisis exclusivamente en los datos del reporte (no inventes cifras ni niveles que no aparezcan ahí).
- Sé directo y específico: evita relleno como "es importante monitorear el mercado" sin aportar nada concreto.
- Máximo 1200 caracteres en total (aproximadamente 250-300 palabras).
- Usa emojis moderadamente, solo donde aporten claridad (📈📉⚠️✅).
- No repitas los valores numéricos exactos ya mostrados en el reporte; interprétalos en vez de citarlos de nuevo.
- Formato de texto permitido: SOLO asteriscos *así* para los siete títulos indicados arriba. No uses guion bajo, backticks, enlaces ni ningún otro formato Markdown.
- No uses los caracteres . ! - dentro de listas o numeración manual (1. 2. 3.) en el cuerpo del texto, ya que rompen el parseo; si necesitas enumerar, usa palabras ("primero", "en segundo lugar") en vez de números con punto.
- No incluyas tú mismo el disclaimer final — se añade automáticamente después de tu respuesta.
"""


# ── Prompt Template — Spotlight de Mercado (/p) ──────────────────────────────
PRICE_SPOTLIGHT_PROMPT = """Eres un analista profesional de criptomonedas.

Tu tarea NO es hacer un análisis técnico tradicional.

Debes generar un comentario estilo "Spotlight" similar al que aparece en CoinMarketCap.

Recibirás datos de una criptomoneda provenientes de CoinMarketCap y/o CoinGecko.

=== DATOS DE MERCADO ===
{market_data_text}
=== FIN DATOS ===

Analiza:
- comportamiento del precio
- variación 1h, 24h y 7d (si está disponible)
- capitalización de mercado
- volumen
- distancia respecto al ATH (si está disponible)
- oferta circulante y máxima (si está disponible)
- sentimiento del mercado (si está disponible)
- posición en el ranking
- cualquier otro dato disponible

No inventes información ni uses datos que no aparezcan arriba.

No menciones indicadores técnicos como RSI, MACD o medias móviles porque no están disponibles.

Explica qué significan los datos para un inversor promedio.

El análisis debe sentirse humano y conversacional.

Debe responder preguntas implícitas como:
¿Qué está pasando? ¿Por qué es importante? ¿Qué transmite el mercado?
¿Qué podría significar para las próximas sesiones?

No hagas predicciones absolutas. Utiliza expresiones como: podría indicar...,
sugiere..., parece reflejar..., el mercado muestra..., los inversores parecen...

Evita lenguaje exagerado. No uses emojis dentro de los párrafos.

FORMATO DE SALIDA (muy importante):
- Escribe el análisis en 3 párrafos cortos y separados, NO un bloque único.
- Cada párrafo debe tratar una idea distinta, por ejemplo:
  1) Qué está pasando con el precio y el momentum reciente.
  2) Qué dicen la capitalización, el volumen y/o el ranking sobre la posición del activo.
  3) Qué transmite el sentimiento del mercado o la distancia al ATH/ATL para el inversor.
- Separa cada párrafo con una línea en blanco (doble salto de línea).
- Cada párrafo debe tener entre 2 y 4 frases.
- No uses títulos, encabezados ni numeración para los párrafos.

La respuesta debe ocupar entre 120 y 180 palabras en total, en español.

Termina el último párrafo con una conclusión breve de una sola frase.

NO incluyas tú mismo la línea del disclaimer final — se añade automáticamente
después de tu respuesta. Termina tu texto justo después de la conclusión.
"""



# ── Utilities ─────────────────────────────────────────────────────────────────
MAX_RESPONSE_CHARS = 3500  # Límite seguro para Telegram (deja espacio para encabezado)


def _sanitize_telegram_markdown_v1(text: str) -> str:
    """Sanea texto para Telegram Markdown v1 (legacy), preservando los
    asteriscos *así* que usamos para los títulos en negrita.

    IMPORTANTE: el bot envía estos mensajes con ParseMode.MARKDOWN (v1),
    NO MarkdownV2. En v1 caracteres como '.', '!', '-' son texto normal y
    NO deben escaparse con backslash — escaparlos (como hacía la versión
    anterior de esta función) produce los "\\." literales visibles en el
    mensaje final, que es exactamente el bug que se corrige aquí.

    Lo único que realmente rompe el parseo en Markdown v1 es un número
    impar de '_', '*' o '`' sueltos en el texto (abren un span de formato
    que nunca se cierra). Esta función neutraliza esos casos sin tocar el
    resto de la puntuación.

    Args:
        text: Texto crudo devuelto por el modelo.

    Returns:
        Texto seguro para enviar con parse_mode=ParseMode.MARKDOWN.
    """
    if not text:
        return ""

    # Backticks y guion bajo: no se usan intencionalmente en este prompt,
    # así que cualquier aparición es accidental — se neutralizan reemplazándolos
    # por su equivalente visual sin función de formato.
    text = text.replace("`", "'")
    text = text.replace("_", "-")

    # Asteriscos: se usan SOLO para los 7 títulos "📚 *Título*". Cualquier
    # asterisco que no forme parte de un título es ruido del modelo (p.ej.
    # "**énfasis**" en vez de un título) y puede dejar un número impar de
    # '*', rompiendo el formato de todo lo que sigue. Se cuenta y, si es
    # impar, se elimina el último asterisco suelto para balancear.
    if text.count("*") % 2 != 0:
        idx = text.rfind("*")
        text = text[:idx] + text[idx + 1:]

    return text.strip()


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
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
)
async def _call_groq_async(payload: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Make async HTTP call to Groq API con rotación de keys + retry logic.

    Rotación: si una key devuelve 429 (rate limit) y hay más keys
    disponibles (GROQ_API_KEY con varias separadas por coma), se reintenta
    con la siguiente antes de rendirse (hasta len(settings.groq_api_keys)
    intentos). Con 0 o 1 key, comportamiento idéntico al anterior.

    Cualquier otro status HTTP (400, 401, 500...) se loguea con el cuerpo
    de la respuesta (antes solo se veía el status code) y se relanza de
    inmediato — rotar de key no arregla un bad request. Timeout/NetworkError
    siguen usando el retry con backoff de tenacity (decorador de arriba),
    sin rotar de key.

    Raises: httpx.HTTPStatusError si todas las keys fallan o si el error
    no es 429.
    """
    keys = settings.groq_api_keys
    attempts = max(len(keys), 1)
    last_exc: Optional[httpx.HTTPStatusError] = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(attempts):
            api_key = _next_groq_key() or settings.groq_api_key
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            try:
                response = await client.post(GROQ_API_URL, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else None
                if status == 429 and attempt < attempts - 1:
                    logger.warning(
                        "⚠️ Groq 429 (rate limit) con key ...%s, probando siguiente key (intento %d/%d)",
                        (api_key or "")[-4:], attempt + 2, attempts,
                    )
                    last_exc = e
                    continue
                # Cualquier otro status (o 429 sin más keys disponibles):
                # loguear el cuerpo de la respuesta para diagnóstico y
                # relanzar de inmediato, sin gastar más intentos.
                try:
                    body = e.response.text[:500] if e.response is not None else ""
                except Exception:
                    body = ""
                logger.error(
                    "❌ Groq HTTP error %s (key ...%s): %s",
                    status, (api_key or "")[-4:], body or str(e),
                )
                raise
        # No debería llegar aquí (el loop siempre retorna o lanza), pero por
        # si acaso: relanzar el último error visto.
        if last_exc:
            raise last_exc
        raise RuntimeError("Groq: no se pudo completar la llamada (sin API keys configuradas)")


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
        "max_completion_tokens": 1024,
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
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

        # Sanear (Markdown v1 — ver _sanitize_telegram_markdown_v1) y truncar
        content = _sanitize_telegram_markdown_v1(content)
        content = _truncate_smart(content, MAX_RESPONSE_CHARS)

        # Quitar cualquier disclaimer que el modelo haya añadido por su cuenta
        for variant in (
            "Análisis generado por IA — no es asesoramiento financiero.",
            "*Análisis generado por IA — no es asesoramiento financiero.*",
        ):
            content = content.replace(variant, "").strip()

        # Disclaimer siempre añadido por el código, con salto de línea propio
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


# ── Public API — Price Spotlight (/p) ───────────────────────────────────────

def _format_price_spotlight_data(price_data: dict) -> str:
    """Convierte el dict de get_crypto_data() en texto plano para el prompt.

    Solo incluye campos presentes y con valor (evita "None" o "N/A" sueltos
    que podrían confundir al modelo y hacerle inventar contexto).

    Args:
        price_data: Dict devuelto por CryptoApiClient.get_crypto_data()

    Returns:
        Texto formateado en líneas "Etiqueta: valor" listo para el prompt.
    """
    lines = []

    symbol = price_data.get("symbol", "N/A")
    price = price_data.get("price")
    source = price_data.get("primary_source", "desconocida")

    lines.append(f"Símbolo: {symbol}")
    lines.append(f"Fuente principal: {source}")
    if price is not None:
        lines.append(f"Precio actual: ${price:,.4f} USD")

    high_24h = price_data.get("high_24h") or 0
    low_24h = price_data.get("low_24h") or 0
    if high_24h > 0:
        lines.append(f"Máximo 24h: ${high_24h:,.4f}")
        lines.append(f"Mínimo 24h: ${low_24h:,.4f}")

    pct_1h = price_data.get("percent_change_1h")
    pct_24h = price_data.get("percent_change_24h")
    pct_7d = price_data.get("percent_change_7d")
    if pct_1h is not None:
        lines.append(f"Variación 1h: {pct_1h:+.2f}%")
    if pct_24h is not None:
        lines.append(f"Variación 24h: {pct_24h:+.2f}%")
    if pct_7d is not None:
        lines.append(f"Variación 7d: {pct_7d:+.2f}%")

    rank = price_data.get("market_cap_rank") or 0
    mcap = price_data.get("market_cap") or 0
    volume = price_data.get("volume_24h") or 0
    if rank > 0:
        lines.append(f"Ranking por capitalización: #{rank}")
    if mcap > 0:
        lines.append(f"Capitalización de mercado: ${mcap:,.0f} USD")
    if volume > 0:
        lines.append(f"Volumen 24h: ${volume:,.0f} USD")

    enrichment = price_data.get("enrichment") or {}

    ath = enrichment.get("ath")
    ath_change_pct = enrichment.get("ath_change_pct")
    if ath:
        lines.append(f"ATH (máximo histórico): ${ath:,.4f} USD")
        if ath_change_pct is not None:
            lines.append(f"Distancia respecto al ATH: {ath_change_pct:.2f}%")

    atl = enrichment.get("atl")
    if atl is not None:
        lines.append(f"ATL (mínimo histórico): ${atl:,.4f} USD")

    circulating = enrichment.get("circulating_supply")
    max_supply = enrichment.get("max_supply")
    total_supply = enrichment.get("total_supply")
    if circulating:
        lines.append(f"Oferta circulante: {circulating:,.0f}")
    if max_supply:
        lines.append(f"Oferta máxima: {max_supply:,.0f}")
    elif total_supply:
        lines.append(f"Oferta total: {total_supply:,.0f}")

    category = enrichment.get("category")
    if category:
        lines.append(f"Categoría del proyecto: {category}")

    sentiment = enrichment.get("sentiment_up_pct")
    if sentiment is not None:
        lines.append(f"Sentimiento positivo de la comunidad: {sentiment:.1f}%")

    return "\n".join(lines)


def _normalize_spotlight_paragraphs(text: str) -> str:
    """Garantiza que el comentario de Spotlight quede en párrafos separados.

    El modelo a veces ignora la instrucción de doble salto de línea y
    devuelve todo en un único bloque. Esta función:
      1. Si ya hay líneas en blanco entre párrafos, las normaliza (colapsa
         3+ saltos seguidos a exactamente 2).
      2. Si NO hay ninguna línea en blanco (un solo bloque de texto),
         intenta partir el texto en frases y agruparlas en párrafos de
         2-3 frases para evitar el muro de texto.

    Args:
        text: Texto crudo devuelto por el modelo (ya sin el disclaimer).

    Returns:
        Texto con párrafos separados por doble salto de línea.
    """
    text = text.strip()
    if not text:
        return text

    # Caso 1: el modelo ya separó en párrafos (al menos una línea en blanco)
    if "\n\n" in text:
        # Colapsar 3+ saltos seguidos a exactamente 2
        import re as _re
        return _re.sub(r"\n{3,}", "\n\n", text)

    # Caso 2: bloque único de texto — partir en frases y agrupar de a 2-3
    import re as _re
    # Split conservando el delimitador (punto seguido de espacio y mayúscula/fin)
    sentences = _re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= 3:
        # Muy corto para dividir en párrafos, dejarlo como un solo bloque
        return text

    paragraphs = []
    chunk_size = 3 if len(sentences) > 6 else 2
    for i in range(0, len(sentences), chunk_size):
        paragraphs.append(" ".join(sentences[i:i + chunk_size]))

    return "\n\n".join(paragraphs)


async def get_groq_price_spotlight(price_data: dict) -> str:
    """Genera un comentario "Spotlight" de mercado (estilo CoinMarketCap)
    para el comando /p, a partir de los datos ya obtenidos de CMC/CoinGecko.

    A diferencia de get_groq_crypto_analysis() (usado en /ta), este NO hace
    análisis técnico: es un comentario narrativo y conversacional pensado
    para inversores promedio, basado solo en datos de mercado fundamentales
    (precio, variación, capitalización, ATH/ATL, supply, sentiment, ranking).

    Args:
        price_data: Dict devuelto por CryptoApiClient.get_crypto_data()

    Returns:
        Texto del análisis (español) o mensaje de error legible.
    """
    if not settings.groq_api_key:
        logger.error("GROQ_API_KEY not configured")
        return "⚠️ *Error:* Variable de entorno GROQ_API_KEY no configurada."

    symbol = price_data.get("symbol", "N/A")
    market_data_text = _format_price_spotlight_data(price_data)

    prompt = PRICE_SPOTLIGHT_PROMPT.format(market_data_text=market_data_text)

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": "Eres un analista de mercado de criptomonedas que escribe comentarios breves, claros y conversacionales en español, sin tecnicismos de trading."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_completion_tokens": 512,
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
    }

    try:
        start = asyncio.get_event_loop().time()
        data = await _call_groq_async(payload)
        elapsed = asyncio.get_event_loop().time() - start

        choices = data.get("choices", [])
        if not choices:
            logger.warning("Groq (spotlight) returned empty choices for %s", symbol)
            return "⚠️ La IA no generó respuesta (respuesta vacía)."

        content = choices[0].get("message", {}).get("content", "").strip()
        if not content:
            logger.warning("Groq (spotlight) returned empty content for %s", symbol)
            return "⚠️ La IA devolvió contenido vacío."

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        logger.info(
            "✅ Groq price spotlight OK for %s — tokens: p=%d c=%d total=%d (%.1fs)",
            symbol, prompt_tokens, completion_tokens,
            prompt_tokens + completion_tokens, elapsed,
        )

        # El prompt no usa Markdown de Telegram (sin *titulos*), así que no
        # se aplica _escape_telegram_markdown aquí — solo truncado de seguridad.
        content = _truncate_smart(content, MAX_RESPONSE_CHARS)

        # Quitar cualquier disclaimer que el modelo haya añadido por su cuenta
        # (se le pidió que no lo hiciera, pero por seguridad se limpia aquí)
        for variant in (
            "Análisis generado por IA. No constituye asesoramiento financiero.",
            "Análisis generado por IA — no es asesoramiento financiero.",
        ):
            content = content.replace(variant, "").strip()

        # Asegurar separación visual en párrafos (evita el "muro de texto")
        content = _normalize_spotlight_paragraphs(content)

        # Disclaimer siempre añadido por el código (no por el modelo),
        # con su propio salto de línea y formato en cursiva para que se
        # distinga visualmente del cuerpo del análisis.
        content += "\n\n_Análisis generado por IA. No constituye asesoramiento financiero._"

        return content

    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response else "??"
        logger.error("Groq HTTP error %s (spotlight) for %s: %s", status, symbol, e)
        if status == 401:
            return "⚠️ Error de autenticación con la IA (API key inválida)."
        elif status == 429:
            return "⚠️ Límite de tasa excedido en la IA. Intenta en 1 minuto."
        else:
            return f"⚠️ Error HTTP {status} de la IA. Intenta más tarde."

    except httpx.TimeoutException:
        logger.error("Groq timeout (spotlight) for %s", symbol)
        return "⚠️ La IA tardó demasiado en responder. Intenta de nuevo."

    except httpx.NetworkError:
        logger.error("Groq network error (spotlight) for %s", symbol)
        return "⚠️ Error de red al contactar la IA."

    except Exception as e:
        logger.exception("Unexpected error in get_groq_price_spotlight")
        return f"⚠️ Error inesperado: {e}"


# ── Prompt Template — Spotlight de Mercado (/spl) ──────────────────────────────────────
MARKET_SPOTLIGHT_PROMPT = """Eres un analista profesional de mercado de criptomonedas.

Tu tarea es generar un comentario tipo "Spotlight" de mercado, similar al
que aparece en la portada de CoinMarketCap, pero basado UNICAMENTE en los
datos que recibes abajo. NO es un análisis de una moneda específica, es un
panorama general del mercado cripto.

=== DATOS DE MERCADO ===
{snapshot_text}
=== FIN DATOS ===

Instrucciones:
- Si hay titulares de noticias reales en los datos (sección "Noticias"),
  puedes referenciarlos brevemente.
- Si NO aparece la sección "Noticias", NO inventes eventos ni titulares:
  concentra el comentario en el sentimiento (Fear and Greed, Altcoin
  Season Index), la dominancia, el sesgo técnico de TradingView si está
  disponible, y los movimientos de gainers/losers/tendencias.
- No inventes cifras que no aparezcan en los datos.
- Explica qué podrían significar los datos para un inversor promedio.
- Si el sesgo técnico de TradingView está disponible, puedes mencionar si
  coincide o contrasta con el sentimiento de Fear and Greed (por ejemplo,
  sesgo técnico alcista con sentimiento de miedo puede leerse como
  posible divergencia).
- Usa expresiones moderadas: podría indicar, sugiere, el mercado
  muestra, los inversores parecen. Nunca uses predicciones absolutas.
- No uses emojis dentro de los párrafos ni de los bullets.

FORMATO DE SALIDA (muy importante):
- Un párrafo de apertura de 2 a 4 frases sobre el sentimiento general y
  el movimiento más destacado del día.
- Una línea en blanco.
- Una lista de 3 a 5 bullets (cada línea empieza con un guion "-") con
  los datos o movimientos más relevantes.
- Si hay titulares reales disponibles, cierra con una línea en blanco y
  un mini párrafo de una o dos frases tipo pregunta-respuesta breve
  sobre lo que transmiten esas noticias. Si no hay titulares, omite esta
  parte por completo, no la inventes.
- No uses títulos, encabezados ni asteriscos para negritas.

La respuesta debe tener entre 100 y 220 palabras en total, en español.

NO incluyas tu mismo la línea del disclaimer final — se añade
automáticamente después de tu respuesta. Termina tu texto justo después
de los bullets (o del cierre pregunta-respuesta si aplica).
"""


def _format_market_snapshot_text(snapshot: dict) -> str:
    """Convierte el dict de CryptoApiClient.get_market_snapshot() en texto
    plano para el prompt de /spl.

    Omite por completo las secciones cuya fuente falló (None) en vez de
    mostrar "N/A", para que el modelo no las mencione ni las eche de menos.

    Args:
        snapshot: Dict devuelto por CryptoApiClient.get_market_snapshot()

    Returns:
        Texto formateado en bloques, listo para insertarse en el prompt.
    """
    lines: list[str] = []

    fear_greed = snapshot.get("fear_greed")
    if fear_greed and fear_greed.get("value") is not None:
        lines.append(
            f"Indice Fear and Greed: {fear_greed['value']} "
            f"({fear_greed.get('classification', 'N/A')})"
        )

    altcoin_season = snapshot.get("altcoin_season")
    if altcoin_season and altcoin_season.get("value") is not None:
        lines.append(
            f"Altcoin Season Index: {altcoin_season['value']}/100 "
            f"({altcoin_season.get('label', 'N/A')})"
        )

    global_metrics = snapshot.get("global_metrics")
    if global_metrics:
        mcap = global_metrics.get("total_market_cap")
        vol = global_metrics.get("total_volume_24h")
        change = global_metrics.get("market_cap_change_24h")
        btc_dom = global_metrics.get("btc_dominance")
        eth_dom = global_metrics.get("eth_dominance")
        if mcap:
            lines.append(f"Capitalizacion total del mercado: ${mcap:,.0f} USD")
        if change is not None:
            lines.append(f"Variacion de la capitalizacion total (24h): {change:+.2f}%")
        if vol:
            lines.append(f"Volumen total 24h: ${vol:,.0f} USD")
        if btc_dom is not None:
            lines.append(f"Dominancia de Bitcoin: {btc_dom:.1f}%")
        if eth_dom is not None:
            lines.append(f"Dominancia de Ethereum: {eth_dom:.1f}%")

    top_movers = snapshot.get("top_movers") or {}
    gainers = top_movers.get("gainers") or []
    losers = top_movers.get("losers") or []
    if gainers:
        lines.append("Mayores subidas 24h (top 200 por capitalizacion):")
        for coin in gainers:
            lines.append(
                f"  - {coin.get('name')} ({coin.get('symbol')}): "
                f"{coin.get('percent_change_24h', 0):+.2f}%"
            )
    if losers:
        lines.append("Mayores bajadas 24h (top 200 por capitalizacion):")
        for coin in losers:
            lines.append(
                f"  - {coin.get('name')} ({coin.get('symbol')}): "
                f"{coin.get('percent_change_24h', 0):+.2f}%"
            )

    trending = snapshot.get("trending") or []
    if trending:
        lines.append("Monedas en tendencia (mas buscadas):")
        for coin in trending:
            lines.append(f"  - {coin.get('name')} ({coin.get('symbol')})")

    btc_technical = snapshot.get("btc_technical")
    if btc_technical and btc_technical.get("recommendation"):
        lines.append(
            f"Sesgo tecnico TradingView para BTC (1D): "
            f"{btc_technical['recommendation']} "
            f"(compra={btc_technical.get('buy_score', 0)}, "
            f"venta={btc_technical.get('sell_score', 0)})"
        )

    news = snapshot.get("news") or []
    if news:
        lines.append("Noticias:")
        for item in news:
            title = item.get("title")
            if title:
                lines.append(f"  - {title}")

    return "\n".join(lines)


async def get_groq_market_spotlight(snapshot: dict) -> str:
    """Genera un comentario "Spotlight" de MERCADO (no de una moneda
    específica) para el comando /spl, a partir del snapshot ya obtenido de
    CryptoApiClient.get_market_snapshot().

    Args:
        snapshot: Dict devuelto por CryptoApiClient.get_market_snapshot()

    Returns:
        Texto del comentario (español) o mensaje de error legible.
    """
    if not settings.groq_api_key:
        logger.error("GROQ_API_KEY not configured")
        return "⚠️ *Error:* Variable de entorno GROQ_API_KEY no configurada."

    snapshot_text = _format_market_snapshot_text(snapshot)
    if not snapshot_text.strip():
        logger.warning("Snapshot de mercado vacio, no se genera spotlight")
        return "⚠️ No hay suficientes datos de mercado disponibles en este momento. Intenta de nuevo en unos minutos."

    prompt = MARKET_SPOTLIGHT_PROMPT.format(snapshot_text=snapshot_text)

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": "Eres un analista de mercado de criptomonedas que escribe comentarios breves, claros y conversacionales en español, sin tecnicismos de trading."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_completion_tokens": 512,
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
    }

    try:
        start = asyncio.get_event_loop().time()
        data = await _call_groq_async(payload)
        elapsed = asyncio.get_event_loop().time() - start

        choices = data.get("choices", [])
        if not choices:
            logger.warning("Groq (market spotlight) returned empty choices")
            return "⚠️ La IA no genero respuesta (respuesta vacia)."

        content = choices[0].get("message", {}).get("content", "").strip()
        if not content:
            logger.warning("Groq (market spotlight) returned empty content")
            return "⚠️ La IA devolvio contenido vacio."

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        logger.info(
            "✅ Groq market spotlight OK — tokens: p=%d c=%d total=%d (%.1fs)",
            prompt_tokens, completion_tokens,
            prompt_tokens + completion_tokens, elapsed,
        )

        content = _sanitize_telegram_markdown_v1(content)
        content = _truncate_smart(content, MAX_RESPONSE_CHARS)

        import re as _re
        content = _re.sub(r"\n{3,}", "\n\n", content.strip())

        content += "\n\n_Análisis generado por IA. No constituye asesoramiento financiero._"

        return content

    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response else "??"
        logger.error("Groq HTTP error %s (market spotlight): %s", status, e)
        if status == 401:
            return "⚠️ Error de autenticación con la IA (API key inválida)."
        elif status == 429:
            return "⚠️ Límite de tasa excedido en la IA. Intenta en 1 minuto."
        else:
            return f"⚠️ Error HTTP {status} de la IA. Intenta más tarde."

    except httpx.TimeoutException:
        logger.error("Groq timeout (market spotlight)")
        return "⚠️ La IA tardó demasiado en responder. Intenta de nuevo."

    except httpx.NetworkError:
        logger.error("Groq network error (market spotlight)")
        return "⚠️ Error de red al contactar la IA."

    except Exception as e:
        logger.exception("Unexpected error in get_groq_market_spotlight")
        return f"⚠️ Error inesperado: {e}"


# ── Prompt Template — Digest de Noticias (/tspl) ────────────────────────────
TSPL_DIGEST_PROMPT = """Eres un editor de un newsletter cripto diario en espanol,
estilo "TASALO Spotlight". Tu trabajo es curar y redactar un resumen de las
noticias del dia a partir de titulares y descripciones crudas, siempre en
espanol, sin importar en que idioma vengan los articulos originales.

=== DATOS DE MERCADO REALES (usalos tal cual, no inventes otras cifras) ===
{market_context}
=== FIN DATOS DE MERCADO ===

=== ARTICULOS CRUDOS (titulo + descripcion, pueden venir en espanol o ingles) ===
{articulos_text}
=== FIN ARTICULOS ===

TAREA:
1. Elegi entre 4 y 6 articulos realmente relevantes (regulacion, mercados,
   instituciones, tecnologia cripto) - ignora contenido irrelevante o
   generico (ej. articulos de bolsa/petroleo/acciones que solo mencionan
   cripto de pasada).
2. Para cada uno, escribi un titulo breve en espanol (si el original esta
   en ingles, traducilo) y un parrafo de 2-4 frases con el contexto real
   (cifras, nombres, cargos, instituciones) tal como aparecen en la
   descripcion original - no inventes datos que no esten ahi.
3. Elegi un emoji representativo para cada noticia (regulacion, internacional,
   legislacion, mercados/exchanges, IA/tecnologia, institucional/ETF,
   seguridad, etc.).
4. Escribi un "lede" de 3-4 frases con el panorama general del dia. Si hay
   DATOS DE MERCADO REALES arriba, la PRIMERA frase tiene que abrir con el
   Fear & Greed y el precio de BTC de esos datos (forma: "El indicador
   Miedo y Codicia se situa en {{valor}} ({{clasificacion}}) y el BTC en
   {{precio}} dolares {{momento del dia}}."), y seguir con 2-3 frases de
   color sobre el movimiento del mercado segun el signo/magnitud del
   cambio 24h y las noticias elegidas - sin inventar otros niveles de
   precio. Si NO hay datos de mercado, arranca el lede directo con el
   panorama de las noticias, sin mencionar Fear & Greed ni precio de BTC.
5. Escribi un "teaser" de 2-3 frases cortas tipo gancho (una por cada
   noticia mas fuerte del dia, sin el detalle completo - eso va en
   "items") y cerra siempre con la frase exacta "Vamos a empezar." como
   ultima oracion.
6. Escribi un "radar" de 1-2 frases sobre que vigilar en los proximos dias
   segun lo que sugieren estas noticias.

Responde EXCLUSIVAMENTE con un objeto JSON valido, sin texto antes ni
despues, sin bloque de codigo markdown, con esta forma exacta:

{{"lede": "...", "teaser": "...", "items": [{{"emoji": "string", "titulo": "...", "parrafo": "..."}}], "radar": "..."}}

Reglas del JSON:
- Todo el contenido (lede, teaser, titulo, parrafo, radar) en espanol.
- "items" debe tener entre 4 y 6 elementos.
- No uses asteriscos, guiones bajos ni ningun formato Markdown dentro de
  los textos - solo texto plano.
- No inventes cifras, nombres ni cargos que no esten en los articulos
  originales ni en los DATOS DE MERCADO REALES.
"""


def _format_tspl_market_context(market_data: Optional[dict]) -> str:
    """Convierte Fear & Greed + precio de BTC (datos reales, no generados
    por IA) en texto plano para el prompt del digest de /tspl.

    Se deja explicito cuando no hay datos disponibles para que el prompt
    (paso 4 de TAREA) sepa que debe omitir la apertura numerica en vez de
    inventarla.

    Args:
        market_data: Dict con fng_value, fng_classification, btc_price,
            btc_change_24h, momento_dia (ver
            services/tspl_digest_scheduler.py), o None si la consulta de
            mercado fallo por completo.
    """
    sin_datos = "(no disponibles - no menciones Fear & Greed ni precio de BTC en el lede)"
    if not market_data:
        return sin_datos

    lines = []

    fng_value = market_data.get("fng_value")
    if fng_value is not None:
        lines.append(f"Fear & Greed: {fng_value} ({market_data.get('fng_classification') or 'N/A'})")

    btc_price = market_data.get("btc_price")
    if btc_price:
        lines.append(f"Precio BTC: ${btc_price:,.0f} dolares")

    btc_change = market_data.get("btc_change_24h")
    if btc_change is not None:
        signo = "sube" if btc_change >= 0 else "baja"
        lines.append(f"Cambio BTC 24h: {signo} {abs(btc_change):.2f}%")

    momento_dia = market_data.get("momento_dia")
    if momento_dia:
        lines.append(f"Momento del dia a usar en la frase de apertura: {momento_dia}")

    return "\n".join(lines) if lines else sin_datos


def _extract_json_object(raw: str) -> Optional[dict]:
    """Extrae y parsea el primer objeto JSON de una respuesta de Groq.

    El modelo a veces envuelve el JSON en un bloque de codigo markdown
    (```json ... ```) pese a que se le pide no hacerlo - esta funcion lo
    tolera igual, quedandose solo con el fragmento entre la primera '{'
    y la ultima '}'.

    Returns:
        El dict parseado, o None si no se pudo extraer/parsear JSON valido.
    """
    if not raw:
        return None

    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _format_tspl_articles_text(articles: list[dict]) -> str:
    """Convierte la lista de articulos normalizados de NewsData.io en texto
    plano para el prompt del digest."""
    lines = []
    for i, art in enumerate(articles, start=1):
        title = art.get("title") or ""
        desc = art.get("description") or ""
        source = art.get("source_name") or "Fuente desconocida"
        lines.append(f"{i}. [{source}] {title}\n   {desc}")
    return "\n\n".join(lines)


async def get_groq_tspl_digest(articles: list[dict], market_data: Optional[dict] = None) -> Optional[dict]:
    """Genera el digest curado de noticias para /tspl a partir de articulos
    crudos de NewsData.io (title + description).

    A diferencia del resto de funciones de este modulo, esta pide una
    respuesta en JSON estructurado (no texto/Markdown para Telegram), ya
    que el resultado se cachea y se usa para armar la plantilla completa
    de /tspl (ver src/handlers/tspl.py).

    Reintenta UNA vez si el JSON viene invalido (Groq a veces agrega texto
    extra pese a las instrucciones); si la segunda vez tambien falla,
    retorna None para que el caller use el fallback de "solo datos de
    mercado, sin seccion de noticias" en vez de romper /tspl.

    Args:
        articles: Lista de dicts normalizados (title, description, ...)
            devueltos por NewsDataClient.get_crypto_news().
        market_data: Fear & Greed + precio BTC reales (ver
            services/tspl_digest_scheduler.py._fetch_tspl_market_context),
            usados para anclar la primera frase del "lede" a cifras reales
            en vez de dejar que Groq las invente. None si la consulta de
            mercado fallo (el lede sale sin la apertura numerica).

    Returns:
        Dict con forma {"lede": str, "teaser": str, "items": [{"emoji",
        "titulo", "parrafo"}], "radar": str}, o None si no hay key
        configurada, no hay articulos, o Groq no devolvio JSON valido tras
        el reintento.
    """
    if not settings.groq_api_key:
        logger.error("GROQ_API_KEY not configured (tspl digest)")
        return None

    if not articles:
        logger.warning("Sin articulos para generar digest de /tspl")
        return None

    articulos_text = _format_tspl_articles_text(articles)
    market_context = _format_tspl_market_context(market_data)
    prompt = TSPL_DIGEST_PROMPT.format(articulos_text=articulos_text, market_context=market_context)

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": "Eres un editor de noticias cripto que responde exclusivamente con JSON valido, sin texto adicional."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_completion_tokens": 2048,
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
    }

    for attempt in range(2):
        try:
            start = asyncio.get_event_loop().time()
            data = await _call_groq_async(payload)
            elapsed = asyncio.get_event_loop().time() - start

            choices = data.get("choices", [])
            if not choices:
                logger.warning("Groq (tspl digest) returned empty choices (intento %d)", attempt + 1)
                continue

            content = choices[0].get("message", {}).get("content", "").strip()
            parsed = _extract_json_object(content)
            finish_reason = choices[0].get("finish_reason", "??")

            if parsed is None or "items" not in parsed:
                logger.warning(
                    "Groq (tspl digest) devolvio JSON invalido/incompleto (intento %d, finish_reason=%s): %r",
                    attempt + 1, finish_reason, content[:300],
                )
                continue

            usage = data.get("usage", {})
            logger.info(
                "OK Groq tspl digest - items=%d tokens=%d (%.1fs)",
                len(parsed.get("items", [])),
                usage.get("total_tokens", 0),
                elapsed,
            )
            return parsed

        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response else "??"
            logger.error("Groq HTTP error %s (tspl digest, intento %d): %s", status, attempt + 1, e)
        except httpx.TimeoutException:
            logger.error("Groq timeout (tspl digest, intento %d)", attempt + 1)
        except httpx.NetworkError:
            logger.error("Groq network error (tspl digest, intento %d)", attempt + 1)
        except Exception:
            logger.exception("Unexpected error in get_groq_tspl_digest (intento %d)", attempt + 1)

    logger.error("Groq tspl digest fallo tras 2 intentos, retornando None")
    return None


