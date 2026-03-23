"""Formateo de texto para mensajes del bot TASALO.

Módulo responsable de formatear las tasas de cambio con el diseño modernizado
de TASALO, usando separadores unicode, emojis de banderas e indicadores de cambio.
"""

from datetime import datetime
from typing import Dict, Any, Optional


# =============================================================================
# CONSTANTES DE FORMATO
# =============================================================================

# Separadores (legacy style)
SEPARATOR_THICK = "—" * 33  # Separador principal entre secciones
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
        lines.append("Datos no disponibles")
        lines.append("")
        return "\n".join(lines)

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
        elif change == "down" and prev_rate is not None:
            diff = rate - prev_rate
            indicator = " " + INDICATOR_DOWN
            change_str = f" {diff:,.2f}"

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

    if not cadeca_data:
        lines.append("⚠️ Not available")
        lines.append("")
        return "\n".join(lines)

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
            buy = currency_info.get("buy", 0)
            sell = currency_info.get("sell", 0)
            change = currency_info.get("change")
            prev_rate = currency_info.get("prev_rate")
        else:
            buy = 0
            sell = 0
            change = None
            prev_rate = None

        buy_str = f"{buy:6.2f}" if buy else "  ---"
        sell_str = f"{sell:6.2f}" if sell else "  ---"
        
        # Indicador solo si hay cambio significativo
        indicator = ""
        if change == "up":
            indicator = " " + INDICATOR_UP
        elif change == "down":
            indicator = " " + INDICATOR_DOWN

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
        lines.append("⚠️ Not available")
        lines.append("")
        return "\n".join(lines)

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
        elif change == "down" and prev_rate is not None:
            diff = rate - prev_rate
            indicator = "  " + INDICATOR_DOWN
            change_str = f" {diff:,.2f}"

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
        cadeca_block = build_cadeca_block(data)
        blocks.append(cadeca_block)
        blocks.append(SEPARATOR_THIN)

    # Bloque BCC (si hay datos)
    bcc_data = data.get("bcc", {})
    if bcc_data:
        bcc_block = build_bcc_block(data)
        blocks.append(bcc_block)
        blocks.append(SEPARATOR_THIN)

    # Footer
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


def build_eltoque_only_message(api_data: Dict[str, Any]) -> str:
    """Construye mensaje con solo ElToque para comando /toque."""
    lines = []
    
    lines.append("📊 *MERCADO INFORMAL (El Toque)*")
    lines.append(SEPARATOR_THICK)
    
    eltoque_data = api_data.get("eltoque", {})
    
    if not eltoque_data:
        lines.append("Datos no disponibles")
    else:
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
        lines.append("⚠️ Not available")
    else:
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
        lines.append("⚠️ Not available")
    else:
        lines.append("_Currency_     _Buy_      _Sell_")
        
        priority = ["EUR", "USD", "MLC", "CAD", "MXN", "GBP", "CHF", "RUB", "AUD", "JPY"]
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
            
            buy_str = f"{buy:6.2f}" if buy else "  ---"
            sell_str = f"{sell:6.2f}" if sell else "  ---"
            
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
