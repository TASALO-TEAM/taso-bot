"""Formateo de texto para mensajes del bot TASALO.

Módulo responsable de formatear las tasas de cambio con el diseño modernizado
de TASALO, usando separadores unicode, emojis de banderas e indicadores de cambio.

Soporta Bot API 9.5+ MessageEntity.DATE_TIME para formateo automático de
timestamps según la zona horaria del usuario (PTB 22.7+).
"""

import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

from telegram import MessageEntity

logger = logging.getLogger(__name__)

# ── Bot API 9.5 DATE_TIME entity support ──
# PTB 22.7+ has the constant MessageEntity.DATE_TIME, but Telegram's API
# server may not fully support the unix_time field yet (returns parse error).
# DISABLED until Telegram API support is confirmed working.
HAS_DATETIME_ENTITY = False  # hasattr(MessageEntity, "DATE_TIME")


# =============================================================================
# CONSTANTES DE FORMATO
# =============================================================================

# Separadores (legacy style - ~20 caracteres para mejor legibilidad en móvil)
SEPARATOR_THICK = "—" * 20  # Separador principal entre secciones
SEPARATOR_THIN = "•••"  # Separador secundario estilo legacy

# Indicadores de cambio
INDICATOR_UP = "🔺"  # Precio sube
INDICATOR_DOWN = "🔻"  # Precio baja
INDICATOR_NEUTRAL = ""  # Sin cambio (legacy no usa indicador para neutral)

# Fuentes
SOURCES_LABELS = {
    "eltoque": "elToque.com",
    "cadeca": "cadeca.cu",
    "bcc": "bc.gob.cu",
    "binance": "binance.com",
}


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================


def get_change_indicator(change: Optional[str]) -> str:
    """Retorna el indicador visual según el cambio.

    Args:
        change: Valor del cambio ("up", "down", "neutral") o None

    Returns:
        String con el indicador unicode correspondiente
    """
    if change == "up":
        return INDICATOR_UP
    elif change == "down":
        return INDICATOR_DOWN
    else:
        return INDICATOR_NEUTRAL


def format_rate_value(rate: float) -> str:
    """Formatea un valor de tasa con 2 decimales.

    Args:
        rate: Valor numérico de la tasa

    Returns:
        String formateado con 2 decimales
    """
    return f"{rate:,.2f}"


def parse_iso_datetime(iso_string: Optional[str]) -> str:
    """Parsea datetime ISO a formato legible.

    Args:
        iso_string: datetime en formato ISO 8601

    Returns:
        String formateado como "YYYY-MM-DD HH:MM"
    """
    if not iso_string:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        # Manejar formato con o sin timezone
        iso_string = iso_string.replace("Z", "+00:00")
        if "+" in iso_string:
            iso_string = iso_string.split("+")[0]

        dt = datetime.fromisoformat(iso_string)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return datetime.now().strftime("%Y-%m-%d %H:%M")


def parse_iso_datetime_extended(iso_string: Optional[str]) -> str:
    """Parsea datetime ISO a formato extendido para /toque.

    Formato: DD/M/YYYY HH:MM:SS (ej: 23/3/2026 20:32:44)

    Args:
        iso_string: datetime en formato ISO 8601

    Returns:
        String formateado como "DD/M/YYYY HH:MM:SS"
    """
    if not iso_string:
        now = datetime.now()
        return f"{now.day}/{now.month}/{now.year} {now.hour}:{now.minute}:{now.second}"

    try:
        # Manejar formato con o sin timezone
        iso_string = iso_string.replace("Z", "+00:00")
        if "+" in iso_string:
            iso_string = iso_string.split("+")[0]

        dt = datetime.fromisoformat(iso_string)
        # Formato: DD/M/YYYY HH:MM:SS (sin leading zeros en día/mes)
        return f"{dt.day}/{dt.month}/{dt.year} {dt.hour}:{dt.minute}:{dt.second}"
    except (ValueError, AttributeError):
        now = datetime.now()
        return f"{now.day}/{now.month}/{now.year} {now.hour}:{now.minute}:{now.second}"


# =============================================================================
# CONSTRUCTORES DE BLOQUES
# =============================================================================


def build_eltoque_block(data: Dict[str, Any]) -> str:
    """Construye el bloque de Mercado Informal (El Toque) estilo legacy.

    Formato legacy:
        📊 *MERCADO INFORMAL (El Toque)*
        —————————————————
         EUR:   580.00  CUP 
         USD:   515.00  CUP 
         MLC:   420.00  CUP 
         BTC:   516.00  CUP 
         TRX:   185.00  CUP 
         USDT:   560.00  CUP 

    Args:
        data: Dict con datos de la API (campo 'data.eltoque')

    Returns:
        String formateado con el bloque completo
    """
    lines = []

    # Header
    lines.append("📊 *MERCADO INFORMAL (El Toque)*")
    lines.append(SEPARATOR_THICK)

    eltoque_data = data.get("eltoque", {})

    if not eltoque_data:
        logger.warning("⚠️ ElToque data empty or missing")
        lines.append("Datos no disponibles")
        lines.append("")
        return "\n".join(lines)

    logger.debug("📊 ElToque data: %d currencies", len(eltoque_data))

    # Ordenar monedas: legacy order - EUR, USD, MLC, BTC, TRX, USDT
    priority = ["EUR", "USD", "MLC", "BTC", "TRX", "USDT"]
    sorted_currencies = sorted(
        eltoque_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
    )

    for currency in sorted_currencies:
        currency_info = eltoque_data[currency]

        # Extraer tasa y cambio
        if isinstance(currency_info, dict):
            rate = currency_info.get("rate", 0)
            change = currency_info.get("change", None)
            prev_rate = currency_info.get("prev_rate")
        else:
            rate = currency_info
            change = None
            prev_rate = None

        # Formatear línea
        rate_str = format_rate_value(rate)
        
        # Calcular indicador y cambio
        indicator = ""
        change_str = ""
        if change == "up" and prev_rate is not None:
            diff = rate - prev_rate
            indicator = " " + INDICATOR_UP
            change_str = f" +{diff:,.2f}"
            logger.debug("📈 %s change indicator: %s %.2f", currency, INDICATOR_UP, diff)
        elif change == "down" and prev_rate is not None:
            diff = rate - prev_rate
            indicator = " " + INDICATOR_DOWN
            change_str = f" {diff:,.2f}"
            logger.debug("📉 %s change indicator: %s %.2f", currency, INDICATOR_DOWN, diff)
        elif change in ("up", "down") and prev_rate is None:
            logger.debug("⚠️ %s has change=%s but prev_rate is None", currency, change)

        # Formato legacy: " EUR:   580.00  CUP 🔺"
        line = f" *{currency}:*   {rate_str}  CUP{indicator}{change_str}"
        lines.append(line)

    lines.append("")  # Línea vacía al final
    return "\n".join(lines)


def build_cadeca_block(data: Dict[str, Any]) -> str:
    """Construye el bloque de CADECA estilo legacy.

    Formato legacy:
        🏢 *CADECA (Exchange Houses)*
        ↳ _Airports, Ports & Hotels_
        —————————————————
        _Currency_     _Buy_      _Sell_
         *USD*          461.27       506.68
         *EUR*          531.94       584.30

    Args:
        data: Dict con datos de la API (campo 'data.cadeca')

    Returns:
        String formateado con el bloque completo
    """
    lines = []

    # Header
    lines.append("🏢 *CADECA (Exchange Houses)*")
    lines.append("↳ _Airports, Ports & Hotels_")
    lines.append(SEPARATOR_THICK)

    cadeca_data = data.get("cadeca", {})

    # Debug logging
    logger.info(f"🔍 CADECA data received: {cadeca_data}")

    if not cadeca_data:
        logger.warning("⚠️ CADECA data empty or missing")
        lines.append("⚠️ Not available")
        lines.append("")
        return "\n".join(lines)

    logger.debug("📊 CADECA data: %d currencies", len(cadeca_data))

    # Header de columnas
    lines.append("_Currency_     _Buy_      _Sell_")

    # Ordenar monedas: legacy order - EUR, USD, MLC, CAD, MXN, GBP, CHF, RUB, AUD, JPY
    priority = ["EUR", "USD", "MLC", "CAD", "MXN", "GBP", "CHF", "RUB", "AUD", "JPY"]
    sorted_currencies = sorted(
        cadeca_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
    )

    for currency in sorted_currencies:
        currency_info = cadeca_data[currency]

        if isinstance(currency_info, dict):
            buy = currency_info.get("buy")
            sell = currency_info.get("sell")
            change = currency_info.get("change")
            prev_rate = currency_info.get("prev_rate")
        else:
            buy = None
            sell = None
            change = None
            prev_rate = None

        # Formatear compra y venta - mostrar --- solo si es None (no si es 0)
        if buy is not None:
            buy_str = f"{buy:6.2f}"
        else:
            buy_str = "  ---"
            
        if sell is not None:
            sell_str = f"{sell:6.2f}"
        else:
            sell_str = "  ---"

        # Indicador solo si hay cambio significativo
        indicator = ""
        if change == "up":
            indicator = " " + INDICATOR_UP
            logger.debug("📈 %s CADECA indicator: %s", currency, INDICATOR_UP)
        elif change == "down":
            indicator = " " + INDICATOR_DOWN
            logger.debug("📉 %s CADECA indicator: %s", currency, INDICATOR_DOWN)

        # Formato legacy: columna alineada
        line = f" *{currency}*          {buy_str}       {sell_str}{indicator}"
        lines.append(line)

    lines.append("")  # Linea vacia al final
    return "\n".join(lines)


def build_bcc_block(data: Dict[str, Any]) -> str:
    """Construye el bloque del Banco Central (BCC) estilo legacy.

    Formato legacy:
        🏛 *OFFICIAL RATE (BCC)*
        —————————————————
        *EUR:*   551.23   *CUP*  
        *USD:*   478.00   *CUP*  
        *CAD:*   348.17   *CUP*  

    Args:
        data: Dict con datos de la API (campo 'data.bcc')

    Returns:
        String formateado con el bloque completo
    """
    lines = []

    # Header
    lines.append("🏛 *OFFICIAL RATE (BCC)*")
    lines.append(SEPARATOR_THICK)

    bcc_data = data.get("bcc", {})

    if not bcc_data:
        logger.warning("⚠️ BCC data empty or missing")
        lines.append("⚠️ Not available")
        lines.append("")
        return "\n".join(lines)

    logger.debug("📊 BCC data: %d currencies", len(bcc_data))

    # Ordenar monedas: legacy order - EUR, USD, MLC, CAD, MXN, GBP, CHF, RUB, AUD, JPY
    priority = ["EUR", "USD", "MLC", "CAD", "MXN", "GBP", "CHF", "RUB", "AUD", "JPY"]
    sorted_currencies = sorted(
        bcc_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
    )

    for currency in sorted_currencies:
        currency_info = bcc_data[currency]

        # BCC puede venir como número directo o como dict
        if isinstance(currency_info, dict):
            rate = currency_info.get("rate", 0)
            change = currency_info.get("change")
            prev_rate = currency_info.get("prev_rate")
        else:
            rate = currency_info
            change = None
            prev_rate = None

        rate_str = format_rate_value(rate)
        
        # Indicador y cambio
        indicator = ""
        change_str = ""
        if change == "up" and prev_rate is not None:
            diff = rate - prev_rate
            indicator = "  " + INDICATOR_UP
            change_str = f" +{diff:,.2f}"
            logger.debug("📈 %s BCC indicator: %s %.2f", currency, INDICATOR_UP, diff)
        elif change == "down" and prev_rate is not None:
            diff = rate - prev_rate
            indicator = "  " + INDICATOR_DOWN
            change_str = f" {diff:,.2f}"
            logger.debug("📉 %s BCC indicator: %s %.2f", currency, INDICATOR_DOWN, diff)
        elif change in ("up", "down") and prev_rate is None:
            logger.debug("⚠️ %s BCC has change=%s but prev_rate is None", currency, change)

        # Formato legacy: " EUR:   551.23   CUP  🔺"
        line = f" *{currency}:*   {rate_str}   *CUP*{indicator}{change_str}"
        lines.append(line)

    # Otras monedas no estandar (si existen)
    for currency, currency_info in bcc_data.items():
        if currency not in priority:
            if isinstance(currency_info, dict):
                rate = currency_info.get("rate", 0)
            else:
                rate = currency_info
            rate_str = format_rate_value(rate)
            lines.append(f" *{currency}:*   {rate_str}  *CUP*")

    lines.append("")  # Línea vacía al final
    return "\n".join(lines)


def build_binance_block(data: Dict[str, Any]) -> str:
    """Construye el bloque opcional de Binance.

    Formato:
        ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

        🟡 *Binance P2P*
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        ₮ USDT  362.00 CUP  ―
        ₿ BTC   98500.00 USDT  🔺 +500

    Args:
        data: Dict con datos de la API (campo 'data.binance')

    Returns:
        String formateado con el bloque completo
    """
    lines = []

    # Separador thin
    lines.append(SEPARATOR_THIN)
    lines.append("")

    # Header
    lines.append("🟡 *Binance P2P*")
    lines.append(SEPARATOR_THICK)

    binance_data = data.get("binance", {})

    if not binance_data:
        logger.warning("⚠️ Binance data empty or missing")
        lines.append("_Datos no disponibles_")
        lines.append("")
        return "\n".join(lines)

    logger.debug("📊 Binance data: %d pairs", len(binance_data))

    # Ordenar: USDT, BTC, ETH, BNB, luego el resto
    priority = ["USDT", "BTC", "ETH", "BNB"]
    sorted_pairs = sorted(
        binance_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
    )

    for pair in sorted_currencies:
        pair_info = binance_data[pair]

        if isinstance(pair_info, dict):
            price = pair_info.get("price", 0)
            change = pair_info.get("change", None)
            change_value = pair_info.get("change_value", 0)
        else:
            price = pair_info
            change = None
            change_value = 0

        price_str = format_rate_value(price)
        indicator = get_change_indicator(change)

        # Determinar moneda de cotización
        quote_currency = "USDT" if "USDT" in pair.upper() else "CUP"

        if change_value != 0 and change not in (None, "neutral"):
            change_str = format_rate_value(abs(change_value))
            sign = "+" if change_value > 0 else ""
            line = f"{get_currency_flag(pair)} {pair}  {price_str} {quote_currency}  {indicator} {sign}{change_str}"
        else:
            line = f"{get_currency_flag(pair)} {pair}  {price_str} {quote_currency}  {indicator}"

        lines.append(line)

    lines.append("")  # Línea vacía al final
    return "\n".join(lines)


def build_footer(data: Dict[str, Any]) -> str:
    """Construye el footer del mensaje con timestamp y fuentes estilo legacy.

    Formato legacy:
        —————————————————
        📆 2026-03-23 09:00
        Fuentes de consulta:
        🔗 elToque.com
        🔗 www.cadeca.cu
        🔗 www.bc.gob.cu

    Args:
        data: Dict con datos de la API (campo 'updated_at' y 'sources')

    Returns:
        String formateado con el footer completo
    """
    lines = []

    # Separador thick
    lines.append(SEPARATOR_THICK)

    # Timestamp
    updated_at = data.get("updated_at")
    timestamp = parse_iso_datetime(updated_at)
    lines.append(f"📆 {timestamp}")

    # Fuentes disponibles - estilo legacy
    lines.append("Fuentes de consulta:")
    
    # Verificar qué fuentes tienen datos
    sources = []
    if data.get("eltoque"):
        sources.append("🔗 elToque.com")
    if data.get("cadeca"):
        sources.append("🔗 www.cadeca.cu")
    if data.get("bcc"):
        sources.append("🔗 www.bc.gob.cu")
    
    if sources:
        lines.extend(sources)
    else:
        # Fallback: mostrar todas las fuentes posibles
        lines.append("🔗 elToque.com")
        lines.append("🔗 www.cadeca.cu")
        lines.append("🔗 www.bc.gob.cu")

    return "\n".join(lines)


def build_full_message(data: Dict[str, Any]) -> str:
    """Construye el mensaje completo con todos los bloques estilo legacy.

    Combina los bloques de ElToque, CADECA, BCC y el footer en un solo mensaje.

    Args:
        data: Dict con datos de la API (estructura completa del response)

    Returns:
        String formateado con el mensaje completo listo para enviar
    """
    blocks = []

    # Bloque ElToque (siempre presente)
    eltoque_block = build_eltoque_block(data)
    if eltoque_block.strip():
        blocks.append(eltoque_block)

    # Separador ••• entre bloques
    blocks.append(SEPARATOR_THIN)

    # Bloque CADECA (si hay datos)
    cadeca_data = data.get("cadeca", {})
    if cadeca_data:
        logger.debug("📊 CADECA block included: %d currencies", len(cadeca_data))
        cadeca_block = build_cadeca_block(data)
        blocks.append(cadeca_block)
        blocks.append(SEPARATOR_THIN)
    else:
        logger.debug("📊 CADECA block skipped: no data")

    # Bloque BCC (si hay datos)
    bcc_data = data.get("bcc", {})
    if bcc_data:
        logger.debug("📊 BCC block included: %d currencies", len(bcc_data))
        bcc_block = build_bcc_block(data)
        blocks.append(bcc_block)
        blocks.append(SEPARATOR_THIN)
    else:
        logger.debug("📊 BCC block skipped: no data")

    # Footer
    footer = build_footer(data)
    blocks.append(footer)

    logger.debug(
        "📝 Built full message with %s",
        "DATE_TIME entities" if HAS_DATETIME_ENTITY else "Markdown fallback",
    )

    return "\n".join(blocks)


# =============================================================================
# BOT API 9.5 — DATE_TIME ENTITY SUPPORT
# =============================================================================


def build_full_message_with_datetime(
    data: Dict[str, Any],
    updated_at_timestamp: int,
) -> Tuple[str, List[MessageEntity]]:
    """Build full message with DATE_TIME entity for automatic timezone formatting.

    Bot API 9.5 (Mar 2026) introduced MessageEntity.DATE_TIME — Telegram
    automatically formats the date/time according to the user's timezone.

    Returns:
        Tuple of (text, entities) — use with parse_mode=None in edit_message_text

    Fallback: If DATE_TIME entity is not supported, returns (text, []) and
    the caller should use parse_mode="Markdown" as normal.
    """
    if not HAS_DATETIME_ENTITY:
        # Fallback: use standard Markdown formatting
        logger.debug("📝 DATE_TIME not supported, using Markdown fallback")
        text = build_full_message(data)
        return text, []

    logger.debug("📝 Building full message with DATE_TIME entities")

    # Build blocks manually (mirroring build_full_message but with DATE_TIME entity)
    blocks = []

    # ── ElToque block with datetime entity ──
    eltoque_lines = []
    eltoque_lines.append("📊 *MERCADO INFORMAL (El Toque)*")
    eltoque_lines.append(SEPARATOR_THICK)

    # Calculate timestamp text position
    header_prefix_len = sum(len(line) + 1 for line in ["📊 *MERCADO INFORMAL (El Toque)*", SEPARATOR_THICK])
    timestamp_marker = "📆 "
    ts_line_start = header_prefix_len
    ts_content_start = ts_line_start + len(timestamp_marker)

    eltoque_lines.append(f"📆 {updated_at_timestamp}")
    eltoque_lines.append("")

    eltoque_data = data.get("eltoque", {})
    if eltoque_data:
        priority = ["EUR", "USD", "MLC", "BTC", "TRX", "USDT"]
        sorted_currencies = sorted(
            eltoque_data.keys(),
            key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
        )
        for currency in sorted_currencies:
            currency_info = eltoque_data[currency]
            if isinstance(currency_info, dict):
                rate = currency_info.get("rate", 0)
                change = currency_info.get("change", None)
                prev_rate = currency_info.get("prev_rate")
            else:
                rate = currency_info
                change = None
                prev_rate = None

            rate_str = format_rate_value(rate)
            indicator = ""
            change_str = ""
            if change == "up" and prev_rate is not None:
                diff = rate - prev_rate
                indicator = " " + INDICATOR_UP
                change_str = f" +{diff:,.2f}"
            elif change == "down" and prev_rate is not None:
                diff = rate - prev_rate
                indicator = " " + INDICATOR_DOWN
                change_str = f" {diff:,.2f}"

            eltoque_lines.append(f" *{currency}:*   {rate_str}  CUP{indicator}{change_str}")
    else:
        eltoque_lines.append("Datos no disponibles")

    eltoque_lines.append("")
    blocks.append("\n".join(eltoque_lines))
    blocks.append(SEPARATOR_THIN)

    # ── CADECA block ──
    cadeca_data = data.get("cadeca", {})
    if cadeca_data:
        blocks.append(build_cadeca_block(data))
        blocks.append(SEPARATOR_THIN)

    # ── BCC block ──
    bcc_data = data.get("bcc", {})
    if bcc_data:
        blocks.append(build_bcc_block(data))
        blocks.append(SEPARATOR_THIN)

    # ── Footer (no duplicate timestamp) ──
    footer_lines = [SEPARATOR_THICK, "Fuentes de consulta:"]
    sources = []
    if data.get("eltoque"):
        sources.append("🔗 elToque.com")
    if data.get("cadeca"):
        sources.append("🔗 www.cadeca.cu")
    if data.get("bcc"):
        sources.append("🔗 www.bc.gob.cu")
    if sources:
        footer_lines.extend(sources)
    else:
        footer_lines.extend(["🔗 elToque.com", "🔗 www.cadeca.cu", "🔗 www.bc.gob.cu"])
    blocks.append("\n".join(footer_lines))

    full_text = "\n".join(blocks)

    # Calculate entity offset — timestamp is after "📆 " in the third line
    entity_offset = ts_content_start
    entity_length = len(str(updated_at_timestamp))

    entities = [
        MessageEntity(
            type=MessageEntity.DATE_TIME,
            offset=entity_offset,
            length=entity_length,
        )
    ]

    return full_text, entities


def build_history_message(
    currency: str,
    source: str,
    history_data: list,
) -> str:
    """Construye el mensaje de histórico de tasas.

    Formato:
        📈 *Histórico USD — ELTOQUE*
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        365.00 CUP  📅 2026-03-22 14:30
        360.00 CUP  📅 2026-03-21 14:30  🔺 +5.00
        358.00 CUP  📅 2026-03-20 14:30  🔺 +2.00

    Args:
        currency: Código de moneda (USD, EUR, etc.)
        source: Fuente (eltoque, cadeca, bcc, binance)
        history_data: Lista de dicts con sell_rate y fetched_at

    Returns:
        String formateado con el histórico
    """
    lines = []

    # Header
    source_label = source.upper() if source else "ELTOQUE"
    lines.append(f"📈 *Histórico {currency.upper()} — {source_label}*")
    lines.append(SEPARATOR_THICK)

    if not history_data:
        logger.debug("📜 No history data for %s/%s", currency, source)
        lines.append("_No hay datos históricos disponibles_")
        lines.append("")
        lines.append("Intenta con otro rango de días o fuente.")
        lines.append("")
        return "\n".join(lines)

    logger.debug("📜 History data for %s/%s: %d records", currency, source, len(history_data))

    # Procesar datos (más reciente primero)
    prev_rate = None
    for i, snapshot in enumerate(history_data[:15]):  # Máximo 15 entradas
        rate = snapshot.get("sell_rate") or snapshot.get("rate", 0)
        fetched_at = snapshot.get("fetched_at", "")

        # Formatear fecha
        date_str = parse_iso_datetime(fetched_at)

        # Calcular cambio vs anterior (si existe)
        change_indicator = ""
        if prev_rate is not None:
            diff = rate - prev_rate
            if diff > 0.001:
                change_indicator = f"  {INDICATOR_UP} +{diff:,.2f}"
            elif diff < -0.001:
                change_indicator = f"  {INDICATOR_DOWN} {diff:,.2f}"
            else:
                change_indicator = f"  {INDICATOR_NEUTRAL}"

        # Formatear línea
        rate_str = format_rate_value(rate)
        lines.append(f"{rate_str} CUP  📅 {date_str}{change_indicator}")

        prev_rate = rate

    lines.append("")

    # Footer con cantidad de datos
    if len(history_data) > 15:
        lines.append(f"_Mostrando 15 de {len(history_data)} registros_")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# FUNCIONES PARA COMANDOS INDIVIDUALES POR FUENTE
# =============================================================================


def build_eltoque_only_message(api_data: Dict[str, Any]) -> str:
    """Construye mensaje con solo ElToque para comando /toque."""
    lines = []

    lines.append("📊 *MERCADO INFORMAL (El Toque)*")
    lines.append(SEPARATOR_THICK)

    eltoque_data = api_data.get("eltoque", {})

    if not eltoque_data:
        logger.warning("⚠️ ElToque data empty for /toque command")
        lines.append("Datos no disponibles")
    else:
        logger.debug("📊 /toque ElToque data: %d currencies", len(eltoque_data))
        # Ordenar monedas: legacy order - EUR, USD, MLC, BTC, TRX, USDT
        priority = ["EUR", "USD", "MLC", "BTC", "TRX", "USDT"]
        sorted_currencies = sorted(
            eltoque_data.keys(),
            key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
        )

        for currency in sorted_currencies:
            currency_info = eltoque_data[currency]
            if isinstance(currency_info, dict):
                rate = currency_info.get("rate", 0)
                change = currency_info.get("change")
                prev_rate = currency_info.get("prev_rate")
            else:
                rate = currency_info
                change = None
                prev_rate = None

            rate_str = format_rate_value(rate) if rate else "---"

            # Calcular indicador y cambio (mismo formato que build_eltoque_block)
            indicator = ""
            change_str = ""
            if change == "up" and prev_rate is not None:
                diff = rate - prev_rate
                indicator = " " + INDICATOR_UP
                change_str = f" +{diff:,.2f}"
            elif change == "down" and prev_rate is not None:
                diff = rate - prev_rate
                indicator = " " + INDICATOR_DOWN
                change_str = f" {diff:,.2f}"

            # Formato legacy: " *EUR:*   580.00  CUP 🔺 +5.00"
            line = f" *{currency}:*   {rate_str}  CUP{indicator}{change_str}"
            lines.append(line)

    lines.append("")
    lines.append(SEPARATOR_THICK)

    # Footer
    updated_at = api_data.get("updated_at")
    if updated_at:
        date_str = parse_iso_datetime(updated_at)
        lines.append(f"📆 {date_str}")
    lines.append("🔗 elToque.com")

    return "\n".join(lines)


def build_bcc_only_message(api_data: Dict[str, Any]) -> str:
    """Construye mensaje con solo BCC para comando /bcc."""
    lines = []
    
    lines.append("🏛 *OFFICIAL RATE (BCC)*")
    lines.append(SEPARATOR_THICK)
    
    bcc_data = api_data.get("bcc", {})

    if not bcc_data:
        logger.warning("⚠️ BCC data empty for /bcc command")
        lines.append("⚠️ Not available")
    else:
        logger.debug("📊 /bcc BCC data: %d currencies", len(bcc_data))
        priority = ["EUR", "USD", "MLC", "CAD", "MXN", "GBP", "CHF", "RUB", "AUD", "JPY"]
        sorted_currencies = sorted(
            bcc_data.keys(),
            key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
        )
        
        for currency in sorted_currencies:
            currency_info = bcc_data[currency]
            if isinstance(currency_info, dict):
                rate = currency_info.get("rate", 0)
                change = currency_info.get("change")
                prev_rate = currency_info.get("prev_rate")
            else:
                rate = float(currency_info) if currency_info else 0
                change = None
                prev_rate = None
            
            rate_str = format_rate_value(rate) if rate else "---"
            
            indicator = ""
            change_str = ""
            if change == "up" and prev_rate is not None:
                diff = rate - prev_rate
                indicator = "  " + INDICATOR_UP
                change_str = f" +{diff:,.2f}"
            elif change == "down" and prev_rate is not None:
                diff = rate - prev_rate
                indicator = "  " + INDICATOR_DOWN
                change_str = f" {diff:,.2f}"
            
            line = f" *{currency}:*   {rate_str}   *CUP*{indicator}{change_str}"
            lines.append(line)
    
    lines.append("")
    lines.append(SEPARATOR_THICK)
    
    # Footer
    updated_at = api_data.get("updated_at")
    if updated_at:
        date_str = parse_iso_datetime(updated_at)
        lines.append(f"📆 {date_str}")
    lines.append("🔗 www.bc.gob.cu")
    
    return "\n".join(lines)


def build_cadeca_only_message(api_data: Dict[str, Any]) -> str:
    """Construye mensaje con solo CADECA para comando /cadeca."""
    lines = []
    
    lines.append("🏢 *CADECA (Exchange Houses)*")
    lines.append("↳ _Airports, Ports & Hotels_")
    lines.append(SEPARATOR_THICK)
    
    cadeca_data = api_data.get("cadeca", {})

    if not cadeca_data:
        logger.warning("⚠️ CADECA data empty for /cadeca command")
        lines.append("⚠️ Not available")
    else:
        logger.debug("📊 /cadeca CADECA data: %d currencies", len(cadeca_data))
        lines.append("_Currency_     _Buy_      _Sell_")
        
        priority = ["EUR", "USD", "MLC", "CAD", "MXN", "GBP", "CHF", "RUB", "AUD", "JPY"]
        sorted_currencies = sorted(
            cadeca_data.keys(),
            key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
        )
        
        for currency in sorted_currencies:
            currency_info = cadeca_data[currency]
            if isinstance(currency_info, dict):
                buy = currency_info.get("buy")
                sell = currency_info.get("sell")
                change = currency_info.get("change")
            else:
                buy = None
                sell = None
                change = None

            # Formatear compra y venta - mostrar --- solo si es None (no si es 0)
            if buy is not None:
                buy_str = f"{buy:6.2f}"
            else:
                buy_str = "  ---"
                
            if sell is not None:
                sell_str = f"{sell:6.2f}"
            else:
                sell_str = "  ---"

            indicator = ""
            if change == "up":
                indicator = " " + INDICATOR_UP
            elif change == "down":
                indicator = " " + INDICATOR_DOWN

            line = f" *{currency}*          {buy_str}       {sell_str}{indicator}"
            lines.append(line)
    
    lines.append("")
    lines.append(SEPARATOR_THICK)
    
    # Footer
    updated_at = api_data.get("updated_at")
    if updated_at:
        date_str = parse_iso_datetime(updated_at)
        lines.append(f"📆 {date_str}")
    lines.append("🔗 www.cadeca.cu")

    return "\n".join(lines)


# =============================================================================
# NUEVO FORMATO PARA COMANDO /toque
# =============================================================================


def build_toque_new_message(api_data: Dict[str, Any]) -> str:
    """Construye mensaje con nuevo formato para comando /toque.

    Formato:
        📊 MERCADO INFORMAL
        💹 Tasa en tiempo real
        ————————————————————

        » Valores actuales del mercado:  
        🇪🇺 EUR ⇾ 580.00  CUP
        🇺🇸 USD ⇾ 515.00  CUP 
        💳 MLC ⇾ 400.00  CUP  

        » Mercado Criptomonedas  
        🪙 BTC ⇾ 520.00 CUP
        ⚡ TRX ⇾ 185.00 CUP
        💰 USDT ⇾ 560.00  CUP    
   
        ————————————————————
        🔗 elToque.com
        ↳ 🕒 23/3/2026 20:32:44

    Args:
        api_data: Dict con datos de la API (campo 'data.eltoque')

    Returns:
        String formateado con el bloque completo
    """
    lines = []

    # Header
    lines.append("📊 MERCADO INFORMAL")
    lines.append("💹 Tasa en tiempo real")
    lines.append(SEPARATOR_THICK)
    lines.append("")

    eltoque_data = api_data.get("eltoque", {})

    if not eltoque_data:
        logger.warning("⚠️ ElToque data empty for /toque new format")
        lines.append("⚠️ Datos no disponibles")
        lines.append("")
        lines.append(SEPARATOR_THICK)
        updated_at = api_data.get("updated_at")
        if updated_at:
            date_str = parse_iso_datetime_extended(updated_at)
            lines.append(f"📆 {date_str}")
        lines.append("🔗 elToque.com")
        return "\n".join(lines)

    logger.debug("📊 /toque new format: %d currencies", len(eltoque_data))

    # Sección 1: Valores actuales del mercado (Fiat - EUR, USD, MLC)
    lines.append("» Valores actuales del mercado:")
    lines.append("")

    fiat_priority = ["EUR", "USD", "MLC"]
    fiat_flags = {"EUR": "🇪🇺", "USD": "🇺🇸", "MLC": "💳"}

    for currency in fiat_priority:
        if currency in eltoque_data:
            currency_info = eltoque_data[currency]
            if isinstance(currency_info, dict):
                rate = currency_info.get("rate", 0)
            else:
                rate = currency_info

            rate_str = format_rate_value(rate) if rate else "---"
            flag = fiat_flags.get(currency, "")
            lines.append(f"{flag} {currency} ⇾ {rate_str}  CUP")

    lines.append("")

    # Sección 2: Mercado Criptomonedas (BTC, TRX, USDT)
    lines.append("» Mercado Criptomonedas")
    lines.append("")

    crypto_priority = ["BTC", "TRX", "USDT"]
    crypto_icons = {"BTC": "🪙", "TRX": "⚡", "USDT": "💰"}

    for currency in crypto_priority:
        if currency in eltoque_data:
            currency_info = eltoque_data[currency]
            if isinstance(currency_info, dict):
                rate = currency_info.get("rate", 0)
            else:
                rate = currency_info

            rate_str = format_rate_value(rate) if rate else "---"
            icon = crypto_icons.get(currency, "")
            lines.append(f"{icon} {currency} ⇾ {rate_str} CUP")

    lines.append("")
    lines.append("")

    # Footer con timestamp
    updated_at = api_data.get("updated_at")
    if updated_at:
        date_str = parse_iso_datetime_extended(updated_at)
        lines.append(f"📆 {date_str}")

    lines.append("🔗 elToque.com")

    return "\n".join(lines)
