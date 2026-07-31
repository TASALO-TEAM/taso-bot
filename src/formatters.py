# src/formatters.py
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
from zoneinfo import ZoneInfo

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

    for pair in sorted_pairs:
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
            # NOTE: get_currency_flag() no está definida en el código base.
            # Se mantiene comoplaceholder para futura implementación.
            flag = ""  # get_currency_flag(pair)
            line = f"{flag} {pair}  {price_str} {quote_currency}  {indicator} {sign}{change_str}"
        else:
            # NOTE: get_currency_flag() no está definida en el código base.
            flag = ""  # get_currency_flag(pair)
            line = f"{flag} {pair}  {price_str} {quote_currency}  {indicator}"

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


def build_fuel_only_message(api_data: Dict[str, Any]) -> str:
    """Construye mensaje con precios de combustible para comando /fuel."""
    lines = []

    lines.append("COMBUSTIBLE (MERCADO INFORMAL)")
    lines.append(SEPARATOR_THICK)

    fuel_data = api_data.get("rates", api_data.get("fuel", {}))

    if not fuel_data:
        logger.warning("⚠️ Fuel data empty for /fuel command")
        lines.append("Datos no disponibles")
    else:
        logger.debug("⛽ /fuel fuel data: %d items", len(fuel_data))

        priority = ["B-94", "B-90", "B-83", "Petroleo", "Gas_LP"]
        display_names = {
            "B-94": "B-94",
            "B-90": "B-90",
            "B-83": "B-83",
            "Petroleo": "Petroleo (Diésel)",
            "Gas_LP": "Gas LP",
        }
        sorted_items = sorted(
            fuel_data.keys(),
            key=lambda x: (priority.index(x) if x in priority else 99, x),
        )

        for key in sorted_items:
            item = fuel_data[key]
            if not isinstance(item, dict):
                continue

            rate = item.get("rate")
            buy = item.get("buy")
            sell = item.get("sell")
            change = item.get("change")
            prev_rate = item.get("prev_rate")
            subtype = item.get("subtype")
            unit = item.get("unit")

            label = f"{display_names.get(key, key)}" + (f" ({subtype})" if subtype else "")

            if buy is not None and sell is not None and buy != sell:
                price_str = f"{buy:,.0f} – {sell:,.0f}"
            elif rate is not None:
                price_str = f"{rate:,.0f}"
            else:
                price_str = "---"

            unit_str = f" {unit}" if unit else ""

            indicator = ""
            change_str = ""

            # Preferir change_pct/change_direction del scraper (más preciso)
            change_pct = item.get("change_pct")
            change_direction = item.get("change_direction", "neutral")

            if change_pct is not None and change_direction in ("up", "down"):
                indicator = "  " + (INDICATOR_UP if change_direction == "up" else INDICATOR_DOWN)
                sign = "+" if change_direction == "up" else ""
                change_str = f" {sign}{change_pct:.1f}%"
            elif change == "up" and prev_rate is not None and rate is not None:
                diff = rate - prev_rate
                indicator = "  " + INDICATOR_UP
                change_str = f" +{diff:,.0f}"
            elif change == "down" and prev_rate is not None and rate is not None:
                diff = rate - prev_rate
                indicator = "  " + INDICATOR_DOWN
                change_str = f" {diff:,.0f}"

            line = f" *{label}:*  {price_str}{unit_str}{indicator}{change_str}"
            lines.append(line)

    lines.append("")
    lines.append(SEPARATOR_THICK)

    updated_at = api_data.get("updated_at")
    if updated_at:
        date_str = parse_iso_datetime(updated_at)
        lines.append(f"📆 {date_str}")
    lines.append("🔗 eltoque.com")

    return "\n".join(lines)


# Zona horaria de Cuba para el timestamp de /qp — mismo patrón que
# CUBA_TZ en toqueimg.py / daily_image_sender.py / tspl_digest_scheduler.py
_QP_CUBA_TZ = ZoneInfo("America/Havana")

# Etiqueta -> emoji mostrado en /qp (orden = orden de aparición)
QVAPAY_EMOJIS: Dict[str, str] = {
    "CUP": "💰",
    "MLC": "💵",
    "TROPIPAY": "💶",
    "ETECSA": "📱",
    "ZELLE": "🏦",
    "CLASICA": "💷",
    "BOLSATM": "💸",
    "BANDECPREPAGO": "🏦",
    "SBERBANK": "🏦",
}


def build_qvapay_message(rates: Dict[str, Optional[float]]) -> str:
    """Construye el mensaje de /qp — tasas promedio P2P de QvaPay x USD.

    Args:
        rates: Dict {etiqueta: promedio_o_None}, tal como lo devuelve
            QvaPayClient.get_p2p_rates(). None (sin operaciones recientes
            o error de esa moneda puntual) se OMITE del mensaje en vez de
            mostrarse como "$0.00" — una moneda sin datos no aporta nada
            al usuario y "$0.00" se lee como una tasa real (confuso).

    Formato (estilo legacy, igual que /bcc, /cadeca, /toque):
        💱 *QVAPAY P2P — Promedio x USD*
        ————————————————————
        💰 *CUP:*   $977.73
        ...

        ————————————————————
        📆 29/7/2026, 14:50:24
        🔗 qvapay.com
    """
    lines = ["💱 *QVAPAY P2P — Promedio x USD*", SEPARATOR_THICK]

    hay_datos = False
    for label, value in rates.items():
        if value is None:
            logger.debug("QvaPay %s: omitida en /qp (sin datos disponibles)", label)
            continue
        hay_datos = True
        emoji = QVAPAY_EMOJIS.get(label, "💱")
        lines.append(f"{emoji} *{label}:*   ${value:,.2f}")

    if not hay_datos:
        lines.append("⚠️ Datos no disponibles")

    ahora = datetime.now(_QP_CUBA_TZ)
    lines.append("")
    lines.append(SEPARATOR_THICK)
    lines.append(f"📆 {ahora.day}/{ahora.month}/{ahora.year}, {ahora.hour:02d}:{ahora.minute:02d}:{ahora.second:02d}")
    lines.append("🔗 qvapay.com")

    return "\n".join(lines)


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


# =============================================================================
# CRIPTOMONEDAS — COMANDO /spl (Spotlight de Mercado)
# =============================================================================

TV_RECOMMENDATION_LABELS = {
    "STRONG_BUY": "🚀 Compra fuerte",
    "BUY": "🐂 Compra",
    "NEUTRAL": "⚖️ Neutral",
    "SELL": "📉 Venta",
    "STRONG_SELL": "🐻 Venta fuerte",
}


def _fmt_pct_change(value: Optional[float]) -> str:
    """Formatea un % de cambio con flecha, estilo CMC (▲1.67% / ▼0.31%)."""
    if value is None:
        return ""
    arrow = "🔺" if value >= 0 else "🔻"
    return f" {arrow}{abs(value):.2f}%"


def build_market_spotlight_data_block(snapshot: Dict[str, Any]) -> str:
    """Construye el bloque de datos duros del Spotlight de mercado (/spl).

    Reproduce, con los datos disponibles en el plan Basic de CMC + el
    sesgo técnico de TradingView, el mismo tipo de bloque numérico que
    aparece en el newsletter real "CMC Spotlight": Fear & Greed, Altcoin
    Season Index, Market Cap/Volumen/Dominancia globales con su variación
    24h, gainers/losers y monedas en tendencia.

    Args:
        snapshot: Dict devuelto por CryptoApiClient.get_market_snapshot()

    Returns:
        Bloque de texto formateado (Markdown v1), listo para anteponer al
        comentario narrativo generado por IA.
    """
    lines: list[str] = []

    fear_greed = snapshot.get("fear_greed")
    altcoin_season = snapshot.get("altcoin_season")
    if fear_greed and fear_greed.get("value") is not None:
        lines.append(f"😨 *Fear & Greed:* {fear_greed['value']} ({fear_greed.get('classification', 'N/A')})")
    if altcoin_season and altcoin_season.get("value") is not None:
        lines.append(f"🌗 *Altcoin Season Index:* {altcoin_season['value']}/100 ({altcoin_season.get('label', 'N/A')})")

    global_metrics = snapshot.get("global_metrics")
    if global_metrics:
        mcap = global_metrics.get("total_market_cap")
        vol = global_metrics.get("total_volume_24h")
        btc_dom = global_metrics.get("btc_dominance")
        eth_dom = global_metrics.get("eth_dominance")
        if mcap:
            lines.append(f"🌍 *Market Cap Global:* {format_supply(mcap)} USD{_fmt_pct_change(global_metrics.get('market_cap_change_24h'))}")
        if vol:
            lines.append(f"📊 *Volumen 24h:* {format_supply(vol)} USD{_fmt_pct_change(global_metrics.get('volume_change_24h'))}")
        if btc_dom is not None:
            dom_line = f"₿ *Dominancia BTC:* {btc_dom:.1f}%{_fmt_pct_change(global_metrics.get('btc_dominance_change_24h'))}"
            if eth_dom is not None:
                dom_line += f"  |  Ξ *ETH:* {eth_dom:.1f}%"
            lines.append(dom_line)

    btc_technical = snapshot.get("btc_technical")
    if btc_technical and btc_technical.get("recommendation"):
        rec_label = TV_RECOMMENDATION_LABELS.get(btc_technical["recommendation"], btc_technical["recommendation"])
        lines.append(
            f"📈 *Sesgo Técnico BTC (TradingView, 1D):* {rec_label} "
            f"({btc_technical.get('buy_score', 0)} 🆚 {btc_technical.get('sell_score', 0)})"
        )

    top_movers = snapshot.get("top_movers") or {}
    gainers = top_movers.get("gainers") or []
    losers = top_movers.get("losers") or []
    if gainers or losers:
        lines.append("")
    if gainers:
        lines.append("🔺 *Mayores subidas 24h:*")
        for coin in gainers:
            lines.append(f"   • {coin.get('name')} ({coin.get('symbol')}): +{coin.get('percent_change_24h', 0):.2f}%")
    if losers:
        lines.append("🔻 *Mayores bajadas 24h:*")
        for coin in losers:
            lines.append(f"   • {coin.get('name')} ({coin.get('symbol')}): {coin.get('percent_change_24h', 0):.2f}%")

    trending = snapshot.get("trending") or []
    if trending:
        lines.append("")
        nombres = ", ".join(f"{c.get('name')} ({c.get('symbol')})" for c in trending)
        lines.append(f"🔥 *Tendencia:* {nombres}")

    if not lines:
        lines.append("⚠️ Datos de mercado no disponibles en este momento.")

    return "\n".join(lines)


def build_tspl_market_bullets(snapshot: Dict[str, Any]) -> str:
    """Construye el bloque "Resumen del mercado" en formato de bullets
    para /tspl (a diferencia de build_market_spotlight_data_block, usado
    por /spl, que arma bloques de texto separados en vez de una lista).

    Reutiliza el mismo snapshot de CryptoApiClient.get_market_snapshot()
    que ya usa /spl — no agrega ninguna llamada nueva a la API.

    Args:
        snapshot: Dict devuelto por CryptoApiClient.get_market_snapshot()

    Returns:
        Bloque de texto con bullets (Markdown v1), listo para insertarse
        en la plantilla de /tspl.
    """
    lines: list[str] = []

    global_metrics = snapshot.get("global_metrics")
    if global_metrics:
        mcap = global_metrics.get("total_market_cap")
        vol = global_metrics.get("total_volume_24h")
        btc_dom = global_metrics.get("btc_dominance")
        if mcap:
            lines.append(f"• 💰 *Capitalización:* {format_supply(mcap)} USD{_fmt_pct_change(global_metrics.get('market_cap_change_24h'))}")
        if vol:
            lines.append(f"• 📉 *Volumen 24h:* {format_supply(vol)} USD{_fmt_pct_change(global_metrics.get('volume_change_24h'))}")
        if btc_dom is not None:
            lines.append(f"• ₿ *Dominancia BTC:* {btc_dom:.2f}%{_fmt_pct_change(global_metrics.get('btc_dominance_change_24h'))}")

    fear_greed = snapshot.get("fear_greed")
    if fear_greed and fear_greed.get("value") is not None:
        lines.append(f"• 😨 *Fear & Greed:* {fear_greed['value']} ({fear_greed.get('classification', 'N/A')})")

    altcoin_season = snapshot.get("altcoin_season")
    if altcoin_season and altcoin_season.get("value") is not None:
        lines.append(f"• 🔄 *Altcoin Season Index:* {altcoin_season['value']}/100")

    if not lines:
        lines.append("• ⚠️ Datos de mercado no disponibles en este momento.")

    return "\n".join(lines)


# =============================================================================
# CRIPTOMONEDAS — COMANDO /p
# =============================================================================


def format_change_crypto(change: Optional[float]) -> str:
    """Formatea cambio porcentual con emoji indicador.

    Emojis:
    - > +0.5% → 😄
    - -0.5% a +0.5% → 😕
    - -5% a -0.5% → 😔
    - ≤ -5% → 😢

    Args:
        change: Cambio porcentual (puede ser None)

    Returns:
        String con formato "+X.XX% 😄" o "0.00%"
    """
    if change is None:
        return "0.00%"

    sign = "+" if change > 0 else ""
    icon = (
        "😄" if change > 0.5
        else "😕" if change > -0.5
        else "😔" if change > -5.0
        else "😢"
    )
    return f"{sign}{change:.2f}%  {icon}"


def build_crypto_message(data: Dict[str, Any]) -> str:
    """Construye el mensaje completo de criptomoneda para comando /p.

    Muestra siempre toda la información disponible en un único mensaje
    (ya no hay botón "Ver más"): precio base, high/low 24h, precios
    cruzados, cambios %, market cap/volumen, y — si hay datos de
    CoinGecko — el bloque adicional de ATH/ATL, supply y categoría.

    Args:
        data: Diccionario con datos de criptomoneda. Puede incluir la clave
              opcional "enrichment" (dict de CoinGeckoClient.get_enrichment_data)
              que se renderiza automáticamente al final del mensaje.

    Returns:
        Mensaje formateado listo para enviar (Markdown).
    """
    lines = []

    symbol = data.get("symbol", "N/A")
    price = data.get("price", 0)
    high_24h = data.get("high_24h", 0)
    low_24h = data.get("low_24h", 0)
    price_eth = data.get("price_eth", 0)
    price_btc = data.get("price_btc", 0)
    pct_1h = data.get("percent_change_1h")
    pct_24h = data.get("percent_change_24h", 0)
    pct_7d = data.get("percent_change_7d")
    rank = data.get("market_cap_rank", 0)
    mcap = data.get("market_cap", 0)
    volume = data.get("volume_24h", 0)
    source = data.get("primary_source", "")
    enrichment = data.get("enrichment")

    # Header — símbolo
    lines.append(f"*{symbol}*")
    lines.append(SEPARATOR_THICK)

    # Precio principal
    lines.append(f"💰 *Precio:* ${price:,.4f}")

    # High/Low (mostrar N/A si son 0)
    if high_24h > 0:
        lines.append(f"📈 *High 24h:* ${high_24h:,.4f}")
        lines.append(f"📉 *Low 24h:* ${low_24h:,.4f}")
    else:
        lines.append("📈 *High 24h:* N/A")
        lines.append("📉 *Low 24h:* N/A")

    lines.append(SEPARATOR_THICK)

    # Precios en ETH y BTC
    lines.append(f"Ξ: {price_eth:.8f}")
    lines.append(f"₿: {price_btc:.8f}")

    # Cambios porcentuales
    lines.append(f"1h  {format_change_crypto(pct_1h)}")
    lines.append(f"24h {format_change_crypto(pct_24h)}")
    lines.append(f"7d  {format_change_crypto(pct_7d)}")

    # Market cap y volumen
    lines.append(f"Cap: #{rank} | ${mcap:,.0f}")
    lines.append(f"Vol: ${volume:,.0f}")

    # Bloque extendido de CoinGecko (ATH/ATL, supply, categoría) — ahora
    # siempre visible cuando hay datos disponibles, sin botón "Ver más"
    if enrichment and not enrichment.get("not_found"):
        lines.append(build_crypto_extended_block(enrichment))

    # Indicador de fuente (solo cuando NO es CoinMarketCap, que es lo normal)
    if source == "cryptocompare":
        lines.append("_🔄 Fuente: CryptoCompare (fallback)_")
    elif source == "coingecko":
        lines.append("_🔄 Fuente: CoinGecko_")

    return "\n".join(lines)


def format_supply(value: Optional[float]) -> str:
    """Formatea un valor de supply en notación compacta (K/M/B/T).

    Args:
        value: Cantidad de tokens (puede ser None)

    Returns:
        String formateado, ej: "19.80M" o "N/A" si value es None
    """
    if value is None:
        return "N/A"

    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:,.2f}T"
    elif abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.2f}B"
    elif abs_value >= 1_000_000:
        return f"{value / 1_000_000:,.2f}M"
    elif abs_value >= 1_000:
        return f"{value / 1_000:,.2f}K"
    return f"{value:,.2f}"


def format_ath_date(iso_string: Optional[str]) -> str:
    """Formatea la fecha de ATH/ATL de CoinGecko a "DD/MM/YYYY".

    Args:
        iso_string: Fecha en formato ISO 8601 (ej: "2021-11-10T14:24:11.849Z")

    Returns:
        String formateado como "DD/MM/YYYY" o "N/A" si no se puede parsear
    """
    if not iso_string:
        return "N/A"
    try:
        cleaned = iso_string.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.strftime("%d/%m/%Y")
    except (ValueError, AttributeError):
        return "N/A"


def build_crypto_extended_block(enrichment: Dict[str, Any]) -> str:
    """Construye el bloque extendido de enriquecimiento (CoinGecko) para /p.

    Se muestra al pulsar el botón "📋 Ver más" en el mensaje de /p, debajo
    del bloque base ya generado por build_crypto_message(). Solo incluye
    datos que CoinMarketCap/CryptoCompare NO proveen: ATH/ATL, supply y
    categoría del proyecto. Nunca repite precio, % de cambio ni market cap
    ya mostrados en el bloque base.

    Formato:
        ─────────────────────
        📋 *Info adicional (CoinGecko)*
        🏆 *ATH:* $73,750.07 (10/03/2024)
        ↳ -18.45% desde el máximo
        🔻 *ATL:* $67.81 (06/07/2013)
        🪙 *Supply circulante:* 19.80M
        🔒 *Supply máximo:* 21.00M
        🏷️ *Categoría:* Smart Contract Platform
        😊 *Sentiment:* 78.3% positivo

    Args:
        enrichment: Dict devuelto por CoinGeckoClient.get_enrichment_data()

    Returns:
        String formateado con el bloque adicional (Markdown).
    """
    lines = []

    lines.append(SEPARATOR_THICK)
    lines.append("📋 *Info adicional (CoinGecko)*")

    ath = enrichment.get("ath")
    ath_change_pct = enrichment.get("ath_change_pct")
    ath_date = enrichment.get("ath_date")
    if ath:
        lines.append(f"🏆 *ATH:* ${ath:,.4f} ({format_ath_date(ath_date)})")
        if ath_change_pct is not None:
            lines.append(f"   ↳ {ath_change_pct:.2f}% desde el máximo")

    atl = enrichment.get("atl")
    atl_date = enrichment.get("atl_date")
    if atl is not None:
        lines.append(f"🔻 *ATL:* ${atl:,.4f} ({format_ath_date(atl_date)})")

    circulating = enrichment.get("circulating_supply")
    max_supply = enrichment.get("max_supply")
    total_supply = enrichment.get("total_supply")

    if circulating:
        lines.append(f"🪙 *Supply circulante:* {format_supply(circulating)}")

    # Mostrar total solo si difiere significativamente del circulante
    # (evitar mostrar el mismo número dos veces, ej: BTC donde son casi iguales)
    if total_supply and circulating:
        diff_ratio = abs(total_supply - circulating) / max(total_supply, circulating)
        if diff_ratio > 0.001:  # Más del 0.1% de diferencia
            lines.append(f"📦 *Supply total:* {format_supply(total_supply)}")
    elif total_supply and not circulating:
        lines.append(f"📦 *Supply total:* {format_supply(total_supply)}")

    if max_supply:
        lines.append(f"🔒 *Supply máximo:* {format_supply(max_supply)}")

    category = enrichment.get("category")
    if category:
        lines.append(f"🏷️ *Categoría:* {category}")

    sentiment = enrichment.get("sentiment_up_pct")
    if sentiment is not None:
        lines.append(f"😊 *Sentiment:* {sentiment:.1f}% positivo")

    cg_rank = enrichment.get("market_cap_rank")
    if cg_rank:
        lines.append(f"📊 *Rank CoinGecko:* #{cg_rank}")

    if len(lines) == 2:
        # No había ningún dato útil más allá del header — evitar bloque vacío
        lines.append("Sin datos adicionales disponibles.")

    return "\n".join(lines)
