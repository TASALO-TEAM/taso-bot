"""Formateo de texto para mensajes del bot TASALO.

Módulo responsable de formatear las tasas de cambio con el diseño modernizado
de TASALO, usando separadores unicode, emojis de banderas e indicadores de cambio.
"""

from datetime import datetime
from typing import Dict, Any, Optional


# =============================================================================
# CONSTANTES DE FORMATO
# =============================================================================

# Separadores
SEPARATOR_THICK = "━" * 22  # Separador principal entre secciones
SEPARATOR_THIN = "┈" * 22  # Separador secundario

# Indicadores de cambio
INDICATOR_UP = "🔺"  # Precio sube
INDICATOR_DOWN = "🔻"  # Precio baja
INDICATOR_NEUTRAL = "―"  # Sin cambio o datos no disponibles

# Emojis de banderas por moneda
CURRENCY_FLAGS = {
    "USD": "🇺🇸",
    "EUR": "🇪🇺",
    "MLC": "🧾",
    "USDT": "₮",
    "BTC": "₿",
    "ETH": "Ξ",
    "BNB": "🟡",
}

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


def get_currency_flag(currency_code: str) -> str:
    """Retorna el emoji de bandera para una moneda.

    Args:
        currency_code: Código de moneda (USD, EUR, etc.)

    Returns:
        Emoji de bandera o string vacío si no hay matching
    """
    return CURRENCY_FLAGS.get(currency_code.upper(), "")


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


# =============================================================================
# CONSTRUCTORES DE BLOQUES
# =============================================================================


def build_eltoque_block(data: Dict[str, Any]) -> str:
    """Construye el bloque de Mercado Informal (El Toque).

    Formato:
        📊 *Mercado Informal (El Toque)*
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        🇺🇸 USD  365.00 CUP  🔺 +5.00
        🇪🇺 EUR  398.00 CUP  ―

    Args:
        data: Dict con datos de la API (campo 'data.eltoque')

    Returns:
        String formateado con el bloque completo
    """
    lines = []

    # Header
    lines.append("📊 *Mercado Informal (El Toque)*")
    lines.append(SEPARATOR_THICK)

    eltoque_data = data.get("eltoque", {})

    if not eltoque_data:
        lines.append("_Datos no disponibles_")
        lines.append("")
        return "\n".join(lines)

    # Ordenar monedas: USD, EUR, MLC, USDT, BTC, ETH, BNB, luego el resto
    priority = ["USD", "EUR", "MLC", "USDT", "BTC", "ETH", "BNB"]
    sorted_currencies = sorted(
        eltoque_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
    )

    for currency in sorted_currencies:
        currency_info = eltoque_data[currency]
        flag = get_currency_flag(currency)

        # Extraer tasa y cambio
        if isinstance(currency_info, dict):
            rate = currency_info.get("rate", 0)
            change = currency_info.get("change", None)
            change_value = currency_info.get("change_value", 0)
        else:
            rate = currency_info
            change = None
            change_value = 0

        # Formatear línea
        rate_str = format_rate_value(rate)
        indicator = get_change_indicator(change)

        # Construir línea con o sin valor de cambio
        if change_value > 0:
            # Cambio positivo: mostrar con signo +
            change_str = format_rate_value(change_value)
            line = f"{flag} {currency}  {rate_str} CUP  {indicator} +{change_str}"
        elif change_value < 0:
            # Cambio negativo: mostrar con signo -
            change_str = format_rate_value(abs(change_value))
            line = f"{flag} {currency}  {rate_str} CUP  {indicator} -{change_str}"
        else:
            line = f"{flag} {currency}  {rate_str} CUP  {indicator}"

        lines.append(line)

    lines.append("")  # Línea vacía al final
    return "\n".join(lines)


def build_cadeca_block(data: Dict[str, Any]) -> str:
    """Construye el bloque de CADECA con formato compacto estilo legacy.

    Formato:
        🏢 *CADECA*
        ━━━━━━━━━━━━━━━━━━━━━━
        *USD*    120.00  /  125.00 🔺
        *EUR*    130.00  /  135.00 ―

    Args:
        data: Dict con datos de la API (campo 'data.cadeca')

    Returns:
        String formateado con el bloque completo
    """
    lines = []

    # Separador thin
    lines.append(SEPARATOR_THIN)
    lines.append("")

    # Header
    lines.append("🏢 *CADECA*")
    lines.append(SEPARATOR_THICK)

    cadeca_data = data.get("cadeca", {})

    if not cadeca_data:
        lines.append("_Datos no disponibles_")
        lines.append("")
        return "\n".join(lines)

    # Ordenar monedas: USD, EUR, luego el resto alfabético
    priority = ["USD", "EUR"]
    sorted_currencies = sorted(
        cadeca_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
    )

    for currency in sorted_currencies:
        currency_info = cadeca_data[currency]

        if isinstance(currency_info, dict):
            buy = currency_info.get("buy", 0)
            sell = currency_info.get("sell", 0)
            change = currency_info.get("change")
        else:
            buy = 0
            sell = 0
            change = None

        buy_str = format_rate_value(buy) if buy else "---"
        sell_str = format_rate_value(sell) if sell else "---"
        indicator = get_change_indicator(change)

        lines.append(f" *{currency}*    {buy_str}  /  {sell_str} {indicator}")

    lines.append("")  # Linea vacia al final
    return "\n".join(lines)

    # Header de columnas
    lines.append(f"{'Currency':<12} {'Buy':>8} {'Sell':>8}")

    # Ordenar monedas: USD, EUR, luego el resto alfabético
    priority = ["USD", "EUR"]
    sorted_currencies = sorted(
        cadeca_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
    )

    for currency in sorted_currencies:
        currency_info = cadeca_data[currency]

        if isinstance(currency_info, dict):
            buy = currency_info.get("buy", 0)
            sell = currency_info.get("sell", 0)
        else:
            # Formato alternativo
            buy = currency_info.get("buy", 0) if isinstance(currency_info, dict) else 0
            sell = (
                currency_info.get("sell", 0) if isinstance(currency_info, dict) else 0
            )

        buy_str = format_rate_value(buy) if buy else "---"
        sell_str = format_rate_value(sell) if sell else "---"

        lines.append(f"{currency:<12} {buy_str:>8} {sell_str:>8}")

    lines.append("")  # Línea vacía al final
    return "\n".join(lines)


def build_bcc_block(data: Dict[str, Any]) -> str:
    """Construye el bloque del Banco Central (BCC).

    Formato:
        ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

        🏛 *Banco Central (BCC)*
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        USD   24.00 CUP
        EUR   26.50 CUP

    Args:
        data: Dict con datos de la API (campo 'data.bcc')

    Returns:
        String formateado con el bloque completo
    """
    lines = []

    # Separador thin
    lines.append(SEPARATOR_THIN)
    lines.append("")

    # Header
    lines.append("🏛 *Banco Central (BCC)*")
    lines.append(SEPARATOR_THICK)

    bcc_data = data.get("bcc", {})

    if not bcc_data:
        lines.append("_Datos no disponibles_")
        lines.append("")
        return "\n".join(lines)

    # Ordenar monedas: USD, EUR, luego el resto
    priority = ["USD", "EUR"]
    sorted_currencies = sorted(
        bcc_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x),
    )

    for currency in sorted_currencies:
        currency_info = bcc_data[currency]

        # BCC puede venir como número directo o como dict
        if isinstance(currency_info, dict):
            rate = currency_info.get("rate", 0)
        else:
            rate = currency_info

        rate_str = format_rate_value(rate)
        flag = get_currency_flag(currency)

        lines.append(f"{flag} {currency}   {rate_str} CUP")

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
        lines.append("_Datos no disponibles_")
        lines.append("")
        return "\n".join(lines)

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
    """Construye el footer del mensaje con timestamp y fuentes.

    Formato:
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        📆 2026-03-22 14:30
        🔗 elToque.com · cadeca.cu · bc.gob.cu

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

    # Fuentes disponibles
    sources = data.get("sources", [])
    if sources:
        source_labels = [SOURCES_LABELS.get(s.lower(), s) for s in sources]
        lines.append(f"🔗 {' · '.join(source_labels)}")
    else:
        # Fallback: mostrar todas las fuentes posibles
        lines.append("🔗 elToque.com · cadeca.cu · bc.gob.cu")

    return "\n".join(lines)


def build_full_message(data: Dict[str, Any]) -> str:
    """Construye el mensaje completo con todos los bloques.

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

    # Bloque CADECA (si hay datos)
    cadeca_data = data.get("cadeca", {})
    if cadeca_data:
        cadeca_block = build_cadeca_block(data)
        blocks.append(cadeca_block)

    # Bloque BCC (si hay datos)
    bcc_data = data.get("bcc", {})
    if bcc_data:
        bcc_block = build_bcc_block(data)
        blocks.append(bcc_block)

    # Footer (siempre presente)
    footer = build_footer(data)
    blocks.append(footer)

    return "\n".join(blocks)


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
        lines.append("_No hay datos históricos disponibles_")
        lines.append("")
        lines.append("Intenta con otro rango de días o fuente.")
        lines.append("")
        return "\n".join(lines)

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


def _build_source_footer(source: str, api_data: Dict[str, Any]) -> str:
    """Construye footer simple para comandos individuales."""
    lines = []
    lines.append(SEPARATOR_THICK)

    updated_at = api_data.get("updated_at")
    if updated_at:
        date_str = parse_iso_datetime(updated_at)
        if date_str:
            lines.append(f"📆 {date_str}")

    source_url = SOURCES_LABELS.get(source, source)
    lines.append(f"🔗 {source_url}")
    return "\n".join(lines)


def build_eltoque_only_message(api_data: Dict[str, Any]) -> str:
    """Construye mensaje con solo ElToque para comando /toque."""
    eltoque_block = build_eltoque_block(api_data)
    footer = _build_source_footer("eltoque", api_data)
    return f"{eltoque_block}\n{footer}"


def build_bcc_only_message(api_data: Dict[str, Any]) -> str:
    """Construye mensaje con solo BCC para comando /bcc."""
    lines = []
    lines.append("🏛 *Banco Central (BCC)*")
    lines.append(SEPARATOR_THICK)

    bcc_data = api_data.get("bcc", {})
    if not bcc_data:
        lines.append("_Datos no disponibles_")
    else:
        priority = ["USD", "EUR", "MLC"]
        sorted_currencies = sorted(
            bcc_data.keys(),
            key=lambda x: (
                priority.index(x.upper()) if x.upper() in priority else 99,
                x,
            ),
        )
        for currency in sorted_currencies:
            currency_info = bcc_data[currency]
            if isinstance(currency_info, dict):
                rate = currency_info.get("rate", 0)
                change = currency_info.get("change")
            else:
                rate = float(currency_info) if currency_info else 0
                change = None
            flag = get_currency_flag(currency)
            indicator = get_change_indicator(change)
            rate_str = format_rate_value(rate) if rate else "---"
            lines.append(f"{flag} {currency}   {rate_str} CUP  {indicator}")

    footer = _build_source_footer("bcc", api_data)
    return f"{'\n'.join(lines)}\n{footer}"


def build_cadeca_only_message(api_data: Dict[str, Any]) -> str:
    """Construye mensaje con solo CADECA para comando /cadeca."""
    cadeca_block = build_cadeca_block(api_data)
    footer = _build_source_footer("cadeca", api_data)
    return f"{cadeca_block}\n{footer}"
