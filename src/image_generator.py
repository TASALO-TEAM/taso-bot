"""Generador de imágenes con Pillow para el bot TASALO.

Módulo responsable de generar imágenes visualmente atractivas con las tasas
de cambio, usando el design system de TASALO (colores, tipografía, layout).
"""

import asyncio
import logging
import os
from io import BytesIO
from typing import Dict, Any, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTES DE DISEÑO (TASALO Design System)
# =============================================================================

# Colores
COLOR_BG = "#09091e"           # Fondo oscuro
COLOR_BG_GRADIENT = "#050510"  # Fondo más oscuro para gradiente
COLOR_ACCENT = "#5b8aff"       # Azul eléctrico principal
COLOR_TEXT = "#eeeef8"         # Texto primario
COLOR_TEXT2 = "#9090c0"        # Texto secundario
COLOR_UP = "#ff6b6b"           # Precio sube 🔺
COLOR_DOWN = "#4ade80"         # Precio baja 🔻
COLOR_NEUTRAL = "#9090c0"      # Sin cambio

# Dimensiones
IMAGE_WIDTH = 800
PADDING = 24
LINE_HEIGHT = 36
SECTION_SPACING = 16
CORNER_RADIUS = 12

# Fuentes (relativas al directorio del proyecto)
# Resolver path absoluto desde el directorio del archivo
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(BASE_DIR, "fonts")
FONT_MONO_PATH = os.path.join(FONT_DIR, "JetBrainsMono-Regular.ttf")
FONT_UI_PATH = os.path.join(FONT_DIR, "SpaceGrotesk-Regular.ttf")

# Tamaños de fuente
FONT_SIZE_TITLE = 28
FONT_SIZE_SECTION = 22
FONT_SIZE_RATE = 20
FONT_SIZE_LABEL = 16
FONT_SIZE_FOOTER = 14


# =============================================================================
# GESTIÓN DE FUENTES
# =============================================================================

def get_fonts() -> Tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    """Obtener las fuentes para renderizar la imagen.

    Returns:
        Tupla (font_title, font_section, font_rate, font_label)
    """
    try:
        font_title = ImageFont.truetype(FONT_UI_PATH, FONT_SIZE_TITLE)
        font_section = ImageFont.truetype(FONT_UI_PATH, FONT_SIZE_SECTION)
        font_rate = ImageFont.truetype(FONT_MONO_PATH, FONT_SIZE_RATE)
        font_label = ImageFont.truetype(FONT_UI_PATH, FONT_SIZE_LABEL)
        font_footer = ImageFont.truetype(FONT_UI_PATH, FONT_SIZE_FOOTER)
        return font_title, font_section, font_rate, font_label, font_footer
    except OSError as e:
        logger.warning(f"⚠️ No se pudieron cargar las fuentes: {e}. Usando fuentes por defecto.")
        # Fallback a fuentes por defecto
        font_title = ImageFont.load_default()
        font_section = ImageFont.load_default()
        font_rate = ImageFont.load_default()
        font_label = ImageFont.load_default()
        font_footer = ImageFont.load_default()
        return font_title, font_section, font_rate, font_label, font_footer


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def get_change_color(change: Optional[str]) -> str:
    """Obtener el color según el cambio.

    Args:
        change: Valor del cambio ("up", "down", "neutral") o None

    Returns:
        Código de color hexadecimal
    """
    if change == "up":
        return COLOR_UP
    elif change == "down":
        return COLOR_DOWN
    else:
        return COLOR_NEUTRAL


def get_change_indicator(change: Optional[str]) -> str:
    """Obtener el indicador visual según el cambio.

    Args:
        change: Valor del cambio ("up", "down", "neutral") o None

    Returns:
        String con el indicador (🔺, 🔻, ―)
    """
    if change == "up":
        return "🔺"
    elif change == "down":
        return "🔻"
    else:
        return "―"


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
    from datetime import datetime

    if not iso_string:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        iso_string = iso_string.replace("Z", "+00:00")
        if "+" in iso_string:
            iso_string = iso_string.split("+")[0]

        dt = datetime.fromisoformat(iso_string)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return datetime.now().strftime("%Y-%m-%d %H:%M")


# =============================================================================
# FUNCIONES DE DIBUJO POR BLOQUE
# =============================================================================

def draw_eltoque_block(
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    y: int,
    font_section: ImageFont.FreeTypeFont,
    font_rate: ImageFont.FreeTypeFont,
    font_label: ImageFont.FreeTypeFont,
) -> int:
    """Dibuja el bloque de Mercado Informal (El Toque).

    Args:
        draw: Objeto ImageDraw
        data: Datos de la API
        y: Posición Y inicial
        font_section: Fuente para títulos de sección
        font_rate: Fuente para tasas
        font_label: Fuente para labels

    Returns:
        Nueva posición Y después del bloque
    """
    x = PADDING

    # Header
    draw.text((x, y), "📊 MERCADO INFORMAL (El Toque)", fill=COLOR_TEXT, font=font_section)
    y += LINE_HEIGHT + 8

    # Línea de acento
    draw.line((x, y, IMAGE_WIDTH - PADDING, y), fill=COLOR_ACCENT, width=2)
    y += LINE_HEIGHT - 8

    eltoque_data = data.get("eltoque", {})

    if not eltoque_data:
        draw.text((x, y), "Datos no disponibles", fill=COLOR_TEXT2, font=font_label)
        return y + LINE_HEIGHT

    # Ordenar monedas: USD, EUR, MLC, USDT, BTC, ETH, BNB
    priority = ["USD", "EUR", "MLC", "USDT", "BTC", "ETH", "BNB"]
    sorted_currencies = sorted(
        eltoque_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x)
    )

    for currency in sorted_currencies:
        currency_info = eltoque_data[currency]

        if isinstance(currency_info, dict):
            rate = currency_info.get("rate", 0)
            change = currency_info.get("change", None)
            change_value = currency_info.get("change_value", 0)
        else:
            rate = currency_info
            change = None
            change_value = 0

        # Obtener emoji de bandera
        flags = {"USD": "🇺🇸", "EUR": "🇪🇺", "MLC": "🧾", "USDT": "₮", "BTC": "₿", "ETH": "Ξ", "BNB": "🟡"}
        flag = flags.get(currency.upper(), "")

        # Formatear tasa
        rate_str = format_rate_value(rate)
        indicator = get_change_indicator(change)
        color = get_change_color(change)

        # Dibujar línea
        if change_value != 0:
            change_str = format_rate_value(abs(change_value))
            sign = "+" if change_value > 0 else ""
            text = f"{flag} {currency:<6} {rate_str:>10} CUP  {indicator} {sign}{change_str}"
        else:
            text = f"{flag} {currency:<6} {rate_str:>10} CUP  {indicator}"

        draw.text((x, y), text, fill=COLOR_TEXT, font=font_rate)

        # Dibujar indicador de cambio con color
        if change_value != 0:
            # Calcular posición del indicador
            indicator_x = x + 380
            draw.text((indicator_x, y - 2), indicator, fill=color, font=font_rate)

        y += LINE_HEIGHT

    return y


def draw_cadeca_block(
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    y: int,
    font_section: ImageFont.FreeTypeFont,
    font_rate: ImageFont.FreeTypeFont,
    font_label: ImageFont.FreeTypeFont,
) -> int:
    """Dibuja el bloque de CADECA con formato de columnas.

    Args:
        draw: Objeto ImageDraw
        data: Datos de la API
        y: Posición Y inicial
        font_section: Fuente para títulos de sección
        font_rate: Fuente para tasas
        font_label: Fuente para labels

    Returns:
        Nueva posición Y después del bloque
    """
    x = PADDING

    # Separador
    y += SECTION_SPACING

    # Header
    draw.text((x, y), "🏢 CADECA", fill=COLOR_TEXT, font=font_section)
    y += LINE_HEIGHT + 8

    # Línea de acento
    draw.line((x, y, IMAGE_WIDTH - PADDING, y), fill=COLOR_ACCENT, width=2)
    y += LINE_HEIGHT - 8

    cadeca_data = data.get("cadeca", {})

    if not cadeca_data:
        draw.text((x, y), "Datos no disponibles", fill=COLOR_TEXT2, font=font_label)
        return y + LINE_HEIGHT

    # Header de columnas
    draw.text((x, y), f"{'Currency':<10} {'Buy':>12} {'Sell':>12}", fill=COLOR_TEXT2, font=font_label)
    y += LINE_HEIGHT

    # Ordenar monedas: USD, EUR, luego el resto
    priority = ["USD", "EUR"]
    sorted_currencies = sorted(
        cadeca_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x)
    )

    for currency in sorted_currencies:
        currency_info = cadeca_data[currency]

        if isinstance(currency_info, dict):
            buy = currency_info.get("buy", 0)
            sell = currency_info.get("sell", 0)
        else:
            buy = 0
            sell = 0

        buy_str = format_rate_value(buy) if buy else "---"
        sell_str = format_rate_value(sell) if sell else "---"

        draw.text((x, y), f"{currency:<10} {buy_str:>12} {sell_str:>12}", fill=COLOR_TEXT, font=font_rate)
        y += LINE_HEIGHT

    return y


def draw_bcc_block(
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    y: int,
    font_section: ImageFont.FreeTypeFont,
    font_rate: ImageFont.FreeTypeFont,
    font_label: ImageFont.FreeTypeFont,
) -> int:
    """Dibuja el bloque del Banco Central (BCC).

    Args:
        draw: Objeto ImageDraw
        data: Datos de la API
        y: Posición Y inicial
        font_section: Fuente para títulos de sección
        font_rate: Fuente para tasas
        font_label: Fuente para labels

    Returns:
        Nueva posición Y después del bloque
    """
    x = PADDING

    # Separador
    y += SECTION_SPACING

    # Header
    draw.text((x, y), "🏛 BANCO CENTRAL (BCC)", fill=COLOR_TEXT, font=font_section)
    y += LINE_HEIGHT + 8

    # Línea de acento
    draw.line((x, y, IMAGE_WIDTH - PADDING, y), fill=COLOR_ACCENT, width=2)
    y += LINE_HEIGHT - 8

    bcc_data = data.get("bcc", {})

    if not bcc_data:
        draw.text((x, y), "Datos no disponibles", fill=COLOR_TEXT2, font=font_label)
        return y + LINE_HEIGHT

    # Ordenar monedas: USD, EUR, luego el resto
    priority = ["USD", "EUR"]
    sorted_currencies = sorted(
        bcc_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x)
    )

    for currency in sorted_currencies:
        currency_info = bcc_data[currency]

        if isinstance(currency_info, dict):
            rate = currency_info.get("rate", 0)
        else:
            rate = currency_info

        rate_str = format_rate_value(rate)
        flags = {"USD": "🇺🇸", "EUR": "🇪🇺", "MLC": "🧾", "USDT": "₮"}
        flag = flags.get(currency.upper(), "")

        draw.text((x, y), f"{flag} {currency:<6} {rate_str:>10} CUP", fill=COLOR_TEXT, font=font_rate)
        y += LINE_HEIGHT

    return y


def draw_footer(
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    y: int,
    font_label: ImageFont.FreeTypeFont,
    font_footer: ImageFont.FreeTypeFont,
) -> int:
    """Dibuja el footer con timestamp y fuentes.

    Args:
        draw: Objeto ImageDraw
        data: Datos de la API
        y: Posición Y inicial
        font_label: Fuente para labels
        font_footer: Fuente para footer

    Returns:
        Nueva posición Y después del footer
    """
    x = PADDING

    # Separador
    y += SECTION_SPACING + 8

    # Línea de acento
    draw.line((x, y, IMAGE_WIDTH - PADDING, y), fill=COLOR_ACCENT, width=2)
    y += 12

    # Timestamp
    updated_at = data.get("updated_at")
    timestamp = parse_iso_datetime(updated_at)
    draw.text((x, y), f"📆 {timestamp}", fill=COLOR_TEXT2, font=font_footer)
    y += LINE_HEIGHT - 8

    # Fuentes
    sources = data.get("sources", [])
    if sources:
        source_labels = {"eltoque": "elToque.com", "cadeca": "cadeca.cu", "bcc": "bc.gob.cu", "binance": "binance.com"}
        labels = [source_labels.get(s.lower(), s) for s in sources]
        draw.text((x, y), f"🔗 {' · '.join(labels)}", fill=COLOR_TEXT2, font=font_footer)
    else:
        draw.text((x, y), "🔗 elToque.com · cadeca.cu · bc.gob.cu", fill=COLOR_TEXT2, font=font_footer)

    return y + LINE_HEIGHT


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

async def generate_image(data: Dict[str, Any]) -> Optional[BytesIO]:
    """Genera una imagen con las tasas de cambio.

    Args:
        data: Dict con datos de la API (campo 'data' del response)

    Returns:
        BytesIO con la imagen PNG, o None si hay error
    """
    try:
        # Obtener fuentes
        font_title, font_section, font_rate, font_label, font_footer = get_fonts()

        # Calcular altura estimada (dinámica según contenido)
        estimated_height = 200  # Header + footer
        if data.get("eltoque"):
            estimated_height += len(data["eltoque"]) * LINE_HEIGHT + 60
        if data.get("cadeca"):
            estimated_height += len(data["cadeca"]) * LINE_HEIGHT + 80
        if data.get("bcc"):
            estimated_height += len(data["bcc"]) * LINE_HEIGHT + 80

        # Crear imagen con fondo de gradiente
        img = Image.new("RGB", (IMAGE_WIDTH, estimated_height), COLOR_BG)
        draw = ImageDraw.Draw(img)

        # Dibujar gradiente (oscuro → más oscuro)
        for i in range(estimated_height):
            ratio = i / estimated_height
            r = int(int(COLOR_BG[1:3], 16) * (1 - ratio) + int(COLOR_BG_GRADIENT[1:3], 16) * ratio)
            g = int(int(COLOR_BG[3:5], 16) * (1 - ratio) + int(COLOR_BG_GRADIENT[3:5], 16) * ratio)
            b = int(int(COLOR_BG[5:7], 16) * (1 - ratio) + int(COLOR_BG_GRADIENT[5:7], 16) * ratio)
            draw.line((0, i, IMAGE_WIDTH, i), fill=(r, g, b))

        # Header
        y = PADDING
        draw.text((PADDING, y), "💱 TASALO", fill=COLOR_TEXT, font=font_title)

        # Timestamp en header (derecha)
        timestamp = parse_iso_datetime(data.get("updated_at"))
        timestamp_width = draw.textlength(timestamp, font=font_label)
        draw.text(
            (IMAGE_WIDTH - PADDING - timestamp_width, y + 8),
            timestamp,
            fill=COLOR_TEXT2,
            font=font_label,
        )

        y += LINE_HEIGHT + 16

        # Línea de acento en header
        draw.line((PADDING, y, IMAGE_WIDTH - PADDING, y), fill=COLOR_ACCENT, width=3)
        y += LINE_HEIGHT - 8

        # Dibujar bloques
        y = draw_eltoque_block(draw, data, y, font_section, font_rate, font_label)
        y = draw_cadeca_block(draw, data, y, font_section, font_rate, font_label)
        y = draw_bcc_block(draw, data, y, font_section, font_rate, font_label)
        y = draw_footer(draw, data, y, font_label, font_footer)

        # Recortar imagen a altura real
        actual_height = max(y + PADDING, 400)  # Altura mínima
        img = img.crop((0, 0, IMAGE_WIDTH, actual_height))

        # Guardar en BytesIO
        buffer = BytesIO()
        img.save(buffer, format="PNG", quality=95)
        buffer.seek(0)

        logger.info(f"✅ Imagen generada: {IMAGE_WIDTH}x{actual_height}px")
        return buffer

    except Exception as e:
        logger.error(f"❌ Error generando imagen: {e}", exc_info=True)
        return None


def generate_image_sync(data: Dict[str, Any]) -> Optional[BytesIO]:
    """Versión síncrona de generate_image para testing.

    Args:
        data: Dict con datos de la API

    Returns:
        BytesIO con la imagen PNG, o None si hay error
    """
    # Ejecutar en un event loop temporal
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(generate_image(data))


# =============================================================================
# SCRIPT DE DESCARGA DE FUENTES
# =============================================================================

async def download_fonts_async():
    """Descarga las fuentes de Google Fonts si no existen.

    Usa aiohttp para descargar las fuentes.
    """
    import aiohttp

    fonts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "fonts")
    os.makedirs(fonts_dir, exist_ok=True)

    fonts = {
        "JetBrainsMono-Regular.ttf": "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Regular.ttf",
        "SpaceGrotesk-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/spacegrotesk/SpaceGrotesk-Regular.ttf",
    }

    async with aiohttp.ClientSession() as session:
        for font_name, url in fonts.items():
            font_path = os.path.join(fonts_dir, font_name)

            if os.path.exists(font_path):
                logger.info(f"✅ Fuente ya existe: {font_name}")
                continue

            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(font_path, "wb") as f:
                            f.write(content)
                        logger.info(f"✅ Fuente descargada: {font_name}")
                    else:
                        logger.warning(f"⚠️ No se pudo descargar {font_name}: {response.status}")
            except Exception as e:
                logger.error(f"❌ Error descargando {font_name}: {e}")


def download_fonts():
    """Descarga las fuentes de Google Fonts si no existen.

    Función síncrona wrapper.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(download_fonts_async())


if __name__ == "__main__":
    # Script para descargar fuentes
    logging.basicConfig(level=logging.INFO)
    download_fonts()
