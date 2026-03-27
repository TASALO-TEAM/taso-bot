"""Generador de imágenes v3 para el bot TASALO.

Módulo responsable de generar imágenes visualmente atractivas con las tasas
de cambio, usando diseño minimalista y limpio sobre plantilla personalizada.

Diseño v3:
- Contenido simplificado: solo moneda + precio + indicador
- Espaciado aumentado: 60px padding, 40px gap, 56px row height
- Encabezados claros: "Tasa El Toque", "Tasa BCC", "Tasa CADECA"
- Footer minimalista: solo "@tasalobot"
- Color de texto: #EDFFF1 (blanco-azulado)
- Sin emojis - solo texto limpio
- Usa plantilla img.jpg como fondo (data/img.jpg)
- Manejo de errores robusto con fallback graceful

Inspirado en: plans/2026-03-26-taso-bot-image-redesign-v3.md
"""

import asyncio
import logging
import os
import io
from datetime import datetime
from typing import Dict, Any, Optional, NamedTuple

from PIL import Image, ImageDraw, ImageFont

from src.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURACIÓN DE PLANTILLA
# =============================================================================

# Ruta a la plantilla
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(BASE_DIR, "data", "img.jpg")


# =============================================================================
# TASALO DESIGN SYSTEM v3
# =============================================================================

# Dimensiones
IMG_WIDTH_HORIZONTAL = 1200  # Para /tasalo
IMG_HEIGHT_HORIZONTAL = 630  # Ratio 1.91:1
IMG_WIDTH_VERTICAL = 800  # Para comandos individuales
IMG_HEIGHT_VERTICAL = 1000  # Ratio 4:5
PADDING = 60  # Aumentado de 40px → 60px
COLUMN_GAP = 40  # Aumentado de 20px → 40px

# Texto
COLOR_TEXT_PRIMARY = "#EDFFF1"  # Blanco-azulado (pedido por usuario)
COLOR_TEXT_SECONDARY = "#8A9BA8"  # Gris azulado más oscuro

# Acentos
COLOR_ACCENT = "#5B8AFF"  # Azul brillante

# Indicadores
COLOR_UP = "#FF6B6B"  # Rojo coral (subida)
COLOR_DOWN = "#4ECDC4"  # Turquesa (bajada)
COLOR_NEUTRAL = "#6C7A89"  # Gris azulado (neutral)

# Layout de columnas (horizontal)
COLUMN_WIDTH_HORIZONTAL = (IMG_WIDTH_HORIZONTAL - (PADDING * 2) - (COLUMN_GAP * 2)) // 3

COLUMN_POSITIONS = {
    "eltoque": {
        "start": PADDING,
        "end": PADDING + COLUMN_WIDTH_HORIZONTAL,
    },
    "bcc": {
        "start": PADDING + COLUMN_WIDTH_HORIZONTAL + COLUMN_GAP,
        "end": PADDING + (COLUMN_WIDTH_HORIZONTAL * 2) + COLUMN_GAP,
    },
    "cadeca": {
        "start": PADDING + (COLUMN_WIDTH_HORIZONTAL * 2) + (COLUMN_GAP * 2),
        "end": IMG_WIDTH_HORIZONTAL - PADDING,
    },
}

# Layout vertical (single source)
CARD_X_START = PADDING
CARD_X_END = IMG_WIDTH_VERTICAL - PADDING

# Tamaños de fuente (escalados por alto de imagen)
FONT_SCALE = {
    "title": 0.036,  # 36px para 1000px
    "subtitle": 0.020,  # 20px
    "column_header": 0.032,  # 32px Bold (encabezado de fuente)
    "currency": 0.028,  # 28px
    "rate_value": 0.032,  # 32px Bold
    "footer": 0.024,  # 24px (@tasalobot)
}

# Altura de fila - AUMENTADA
ROW_HEIGHT = 56  # Aumentado de 48px → 56px

# Encabezados por fuente (solo título principal, sin subtítulos redundantes)
SOURCE_TITLES = {
    "eltoque": "Tasa El Toque",
    "bcc": "Tasa BCC",
    "cadeca": "Tasa CADECA",
}


# =============================================================================
# GESTIÓN DE FUENTES
# =============================================================================


class Fonts(NamedTuple):
    """Colección de fuentes cargadas."""

    title: ImageFont.FreeTypeFont
    subtitle: ImageFont.FreeTypeFont
    column_header: ImageFont.FreeTypeFont
    currency: ImageFont.FreeTypeFont
    rate_value: ImageFont.FreeTypeFont
    footer: ImageFont.FreeTypeFont


def get_font_path() -> Optional[str]:
    """Obtener la ruta a una fuente disponible en el sistema."""
    preferred_fonts = [
        "/usr/share/fonts/truetype/space-grotesk/SpaceGrotesk-Bold.ttf",
        "/usr/share/fonts/truetype/space-grotesk/SpaceGrotesk-SemiBold.ttf",
        "/usr/share/fonts/truetype/space-grotesk/SpaceGrotesk-Regular.ttf",
        "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf",
        "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Medium.ttf",
        "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf",
    ]

    fallback_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fonts_dir = os.path.join(base_dir, "fonts")
    project_fonts = [
        os.path.join(fonts_dir, "SpaceGrotesk-Bold.ttf"),
        os.path.join(fonts_dir, "SpaceGrotesk-Regular.ttf"),
        os.path.join(fonts_dir, "JetBrainsMono-Bold.ttf"),
        os.path.join(fonts_dir, "JetBrainsMono-Regular.ttf"),
    ]

    all_fonts = preferred_fonts + project_fonts + fallback_fonts

    for path in all_fonts:
        if os.path.exists(path):
            return path

    return None


def load_fonts() -> Fonts:
    """Cargar todas las fuentes necesarias."""
    font_path = get_font_path()

    if not font_path:
        logger.warning(
            "⚠️ No se encontraron fuentes TrueType, usando fuente por defecto"
        )
        default_font = ImageFont.load_default()
        return Fonts(
            title=default_font,
            subtitle=default_font,
            column_header=default_font,
            currency=default_font,
            rate_value=default_font,
            footer=default_font,
        )

    try:
        return Fonts(
            title=ImageFont.truetype(
                font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["title"])
            ),
            subtitle=ImageFont.truetype(
                font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["subtitle"])
            ),
            column_header=ImageFont.truetype(
                font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_header"])
            ),
            currency=ImageFont.truetype(
                font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["currency"])
            ),
            rate_value=ImageFont.truetype(
                font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["rate_value"])
            ),
            footer=ImageFont.truetype(
                font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["footer"])
            ),
        )
    except OSError as e:
        logger.warning(f"⚠️ Error cargando fuentes: {e}. Usando fuente por defecto.")
        default_font = ImageFont.load_default()
        return Fonts(
            title=default_font,
            subtitle=default_font,
            column_header=default_font,
            currency=default_font,
            rate_value=default_font,
            footer=default_font,
        )


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================


def get_change_indicator(change: Optional[str]) -> str:
    """Obtener indicador de cambio según la dirección."""
    if change == "up":
        return "+"
    elif change == "down":
        return "-"
    else:
        return "="


def get_change_color(change: Optional[str]) -> str:
    """Obtener color según la dirección del cambio."""
    if change == "up":
        return COLOR_UP
    elif change == "down":
        return COLOR_DOWN
    else:
        return COLOR_NEUTRAL


def format_rate_value(rate: float) -> str:
    """Formatear valor de tasa con 2 decimales."""
    return f"{rate:,.2f}"


def parse_iso_datetime(iso_string: Optional[str]) -> str:
    """Parsear datetime ISO a formato legible."""
    if not iso_string:
        return datetime.now().strftime("%d/%m/%Y %H:%M")

    try:
        iso_string = iso_string.replace("Z", "+00:00")
        if "+" in iso_string:
            iso_string = iso_string.split("+")[0]
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, AttributeError):
        return datetime.now().strftime("%d/%m/%Y %H:%M")


# =============================================================================
# FUNCIONES DE DIBUJO
# =============================================================================


def load_template(image_type: str = "tasalo") -> Optional[Image.Image]:
    """Cargar plantilla desde archivo.

    Args:
        image_type: Tipo de imagen ("tasalo" u otro)

    Returns:
        Imagen PIL o None si falla
    """
    try:
        if not os.path.exists(TEMPLATE_PATH):
            logger.warning(f"⚠️ Plantilla no encontrada: {TEMPLATE_PATH}")
            return None

        img = Image.open(TEMPLATE_PATH)

        # Redimensionar según tipo
        if image_type == "tasalo":
            target_size = (IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL)
        else:
            target_size = (IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL)

        # Convertir a RGBA si es necesario
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        # Redimensionar manteniendo aspect ratio
        img = img.resize(target_size, Image.Resampling.LANCZOS)

        logger.info(f"✅ Plantilla cargada: {target_size[0]}x{target_size[1]}px")
        return img

    except Exception as e:
        logger.error(f"❌ Error cargando plantilla: {e}", exc_info=True)
        return None


def draw_gradient_background(draw: ImageDraw.ImageDraw, W: int, H: int) -> None:
    """Dibujar fondo con gradiente oscuro (fallback si no hay plantilla)."""
    h1 = H // 3
    h2 = H * 2 // 3

    draw.rectangle((0, 0, W, h1), fill="#0D0D1A")
    draw.rectangle((0, h1, W, h2), fill="#15152A")
    draw.rectangle((0, h2, W, H), fill="#0A0A15")


def draw_header(draw: ImageDraw.ImageDraw, W: int, H: int, fonts: Fonts) -> int:
    """Dibujar header con título centrado."""
    y = PADDING

    # Título principal centrado
    title = "TASALO — Tasas de Cambio"
    bbox = draw.textbbox((0, 0), title, font=fonts.title)
    text_width = bbox[2] - bbox[0]
    x = (W - text_width) // 2

    draw.text((x, y), title, fill=COLOR_TEXT_PRIMARY, font=fonts.title)
    y += int(H * FONT_SCALE["title"]) + 10

    # Subtítulo con fecha centrado
    date_str = datetime.now().strftime("%d/%m/%Y · Cuba")
    bbox = draw.textbbox((0, 0), date_str, font=fonts.subtitle)
    text_width = bbox[2] - bbox[0]
    x = (W - text_width) // 2

    draw.text((x, y), date_str, fill=COLOR_TEXT_SECONDARY, font=fonts.subtitle)

    return y + 50


def draw_currency_column(
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    source: str,
    x_start: int,
    x_end: int,
    y_start: int,
    fonts: Fonts,
) -> int:
    """Dibujar columna de tasas para una fuente específica (ElToque/BCC).

    Layout:
        Tasa El Toque · 26/03/2026 · Cuba
        ——————————————————————————————
        Moneda              Tasa
        ——————————————————————————————
        EUR              580.00 🔺
        USD              515.00 🔺
        ...
    """
    y = y_start

    # Línea separadora después del título
    draw.line((x_start, y, x_end, y), fill=COLOR_ACCENT, width=2)
    y += 15

    # Headers de columnas: "Moneda" (izquierda) y "Tasa" (derecha)
    draw.text(
        (x_start + 20, y), "Moneda", fill=COLOR_TEXT_SECONDARY, font=fonts.column_header
    )
    draw.text(
        (x_end - 20, y),
        "Tasa",
        fill=COLOR_TEXT_SECONDARY,
        font=fonts.column_header,
        anchor="rm",
    )
    y += int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_header"]) + 10

    # Línea separadora después de headers
    draw.line((x_start, y, x_end, y), fill=COLOR_ACCENT, width=1)
    y += 15

    # Ordenar monedas por prioridad
    priority = [
        "EUR",
        "USD",
        "MLC",
        "USDT",
        "BTC",
        "TRX",
        "BNB",
        "ETH",
        "CAD",
        "MXN",
        "GBP",
        "CHF",
        "RUB",
        "AUD",
        "JPY",
    ]
    sorted_currencies = sorted(
        data.keys() if isinstance(data, dict) else [],
        key=lambda x: priority.index(x.upper()) if x.upper() in priority else 99,
    )

    # Posiciones
    currency_x = x_start + 20
    value_x = x_end - 20

    # Dibujar filas (máximo 8)
    for currency in sorted_currencies[:8]:
        if not isinstance(data, dict):
            break

        currency_info = data.get(currency, {})

        if isinstance(currency_info, dict):
            rate = currency_info.get("rate")
            change = currency_info.get("change")
        else:
            rate = currency_info
            change = None

        # Dibujar código de moneda (izquierda)
        draw.text(
            (currency_x, y),
            currency.upper(),
            fill=COLOR_TEXT_PRIMARY,
            font=fonts.currency,
        )

        # Dibujar valor + indicador (derecha)
        if rate is not None:
            rate_str = format_rate_value(rate)
            indicator = get_change_indicator(change)
            indicator_color = get_change_color(change)

            value_full = f"{rate_str} {indicator}"
            value_bbox = draw.textbbox((0, 0), value_full, font=fonts.rate_value)
            value_width = value_bbox[2] - value_bbox[0]
            value_pos_x = value_x - value_width

            draw.text(
                (value_pos_x, y),
                value_full,
                fill=indicator_color,
                font=fonts.rate_value,
            )
        else:
            draw.text(
                (value_x, y),
                "---",
                fill=COLOR_TEXT_SECONDARY,
                anchor="rm",
                font=fonts.rate_value,
            )

        y += ROW_HEIGHT

    return y


def draw_cadeca_column(
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    x_start: int,
    x_end: int,
    y_start: int,
    fonts: Fonts,
) -> int:
    """Dibujar columna de CADECA con tasas (buy/sell).

    Layout mejorado con 3 columnas bien espaciadas:
        Tasa CADECA · 26/03/2026 · Cuba
        ——————————————————————————————
        Moneda        Compra       Venta
        ——————————————————————————————
        EUR          544.49       566.71
        USD          470.40       489.60
        ...
    """
    y = y_start

    # Línea separadora después del título
    draw.line((x_start, y, x_end, y), fill=COLOR_ACCENT, width=2)
    y += 15

    # Headers de columnas - mejor espaciados
    # Columna 1: Moneda (izquierda) - 30% del ancho
    # Columna 2: Compra (centro) - 35% del ancho
    # Columna 3: Venta (derecha) - 35% del ancho
    total_width = x_end - x_start
    col1_width = int(total_width * 0.30)  # Moneda
    col2_width = int(total_width * 0.35)  # Compra
    col3_width = int(total_width * 0.35)  # Venta

    # Posiciones X para cada columna (usando layout proporcional 30/35/35%)
    # Moneda: 30% del ancho, starts left
    # Compra: 35% del ancho, starts after Moneda
    # Venta: 35% del ancho, starts after Compra
    moneda_x = x_start + 15
    compra_x = x_start + col1_width + 15
    venta_x = x_start + col1_width + col2_width + 15

    # Dibujar headers
    draw.text(
        (moneda_x, y), "Moneda", fill=COLOR_TEXT_SECONDARY, font=fonts.column_header
    )
    draw.text(
        (compra_x, y),
        "Compra",
        fill=COLOR_TEXT_SECONDARY,
        font=fonts.column_header,
        anchor="rm",
    )
    draw.text(
        (venta_x, y),
        "Venta",
        fill=COLOR_TEXT_SECONDARY,
        font=fonts.column_header,
        anchor="rm",
    )
    y += int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_header"]) + 10

    # Línea separadora después de headers
    draw.line((x_start, y, x_end, y), fill=COLOR_ACCENT, width=1)
    y += 15

    # Ordenar monedas por prioridad
    priority = ["EUR", "USD", "MLC", "CAD", "MXN", "GBP", "CHF", "RUB", "AUD", "JPY"]
    sorted_currencies = sorted(
        data.keys() if isinstance(data, dict) else [],
        key=lambda x: priority.index(x.upper()) if x.upper() in priority else 99,
    )

    # Dibujar filas (máximo 8 para CADECA)
    for currency in sorted_currencies[:8]:
        if not isinstance(data, dict):
            break

        currency_info = data.get(currency, {})

        if isinstance(currency_info, dict):
            buy = currency_info.get("buy")
            sell = currency_info.get("sell")
        else:
            buy = None
            sell = None

        # Dibujar moneda (izquierda)
        draw.text(
            (moneda_x, y),
            currency.upper(),
            fill=COLOR_TEXT_PRIMARY,
            font=fonts.currency,
        )

        # Dibujar compra (centro)
        if buy is not None:
            buy_str = format_rate_value(buy)
            draw.text(
                (compra_x, y),
                buy_str,
                fill=COLOR_TEXT_PRIMARY,
                anchor="rm",
                font=fonts.rate_value,
            )
        else:
            draw.text(
                (compra_x, y),
                "---",
                fill=COLOR_TEXT_SECONDARY,
                anchor="rm",
                font=fonts.rate_value,
            )

        # Dibujar venta (derecha)
        if sell is not None:
            sell_str = format_rate_value(sell)
            draw.text(
                (venta_x, y),
                sell_str,
                fill=COLOR_TEXT_PRIMARY,
                anchor="rm",
                font=fonts.rate_value,
            )
        else:
            draw.text(
                (venta_x, y),
                "---",
                fill=COLOR_TEXT_SECONDARY,
                anchor="rm",
                font=fonts.rate_value,
            )

        y += ROW_HEIGHT

    return y


def draw_single_source_card(
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    source: str,
    W: int,
    H: int,
    fonts: Fonts,
) -> None:
    """Dibujar tarjeta vertical para fuente individual.

    Título simplificado: "Tasa El Toque · 26/03/2026 · Cuba"
    Sin subtítulos redundantes ("ElToque", "Oficial", "Exchange").
    """
    # Título simplificado: solo "Tasa <Fuente> · fecha · Cuba"
    source_title = SOURCE_TITLES.get(source, source.upper())
    date_str = datetime.now().strftime("%d/%m/%Y · Cuba")
    title_text = f"{source_title} · {date_str}"

    # Dibujar header personalizado
    y = PADDING

    # Título centrado
    title_bbox = draw.textbbox((0, 0), title_text, font=fonts.title)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (W - title_width) // 2

    draw.text((title_x, y), title_text, fill=COLOR_TEXT_PRIMARY, font=fonts.title)
    y += int(H * FONT_SCALE["title"]) + 20

    # Contenido
    inner_y = y + 20
    inner_x_start = CARD_X_START + 20
    inner_x_end = CARD_X_END - 20

    # Dibujar columna según fuente
    if source == "eltoque":
        draw_currency_column(
            draw,
            data.get("eltoque", {}),
            "eltoque",
            inner_x_start,
            inner_x_end,
            inner_y,
            fonts,
        )
    elif source == "bcc":
        draw_currency_column(
            draw, data.get("bcc", {}), "bcc", inner_x_start, inner_x_end, inner_y, fonts
        )
    elif source == "cadeca":
        draw_cadeca_column(
            draw, data.get("cadeca", {}), inner_x_start, inner_x_end, inner_y, fonts
        )


def draw_footer(draw: ImageDraw.ImageDraw, W: int, H: int, fonts: Fonts) -> None:
    """Dibujar footer minimalista centrado."""
    footer_text = "@tasalobot"

    bbox = draw.textbbox((0, 0), footer_text, font=fonts.footer)
    text_width = bbox[2] - bbox[0]
    x = (W - text_width) // 2
    y = H - 50

    draw.text((x, y), footer_text, fill=COLOR_TEXT_SECONDARY, font=fonts.footer)


# =============================================================================
# FUNCIONES PRINCIPALES DE GENERACIÓN
# =============================================================================


async def generate_tasalo_image(data: Dict[str, Any]) -> Optional[io.BytesIO]:
    """Generar imagen horizontal con tabla triple (ElToque | BCC | CADECA).

    Usa la plantilla img.jpg si está disponible, sino usa fondo gradiente.
    """
    try:
        # 1. Cargar plantilla o crear fallback
        template = load_template("tasalo")

        if template:
            # Usar plantilla
            img = template.convert("RGBA")
        else:
            # Fallback: crear imagen con fondo gradiente
            img = Image.new(
                "RGBA", (IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL), (13, 13, 26, 255)
            )

        draw = ImageDraw.Draw(img)

        # 2. Cargar fuentes
        fonts = load_fonts()

        # 3. Si no hay plantilla, dibujar fondo gradiente
        if not template:
            draw_gradient_background(draw, IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL)

        # 4. Dibujar header
        y_content = draw_header(
            draw, IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL, fonts
        )
        y_content = max(y_content, 120)

        # 5. Extraer datos por fuente
        eltoque_data = data.get("eltoque", {})
        bcc_data = data.get("bcc", {})
        cadeca_data = data.get("cadeca", {})

        # 6. Dibujar columnas
        draw_currency_column(
            draw,
            eltoque_data,
            "eltoque",
            COLUMN_POSITIONS["eltoque"]["start"],
            COLUMN_POSITIONS["eltoque"]["end"],
            y_content,
            fonts,
        )

        draw_currency_column(
            draw,
            bcc_data,
            "bcc",
            COLUMN_POSITIONS["bcc"]["start"],
            COLUMN_POSITIONS["bcc"]["end"],
            y_content,
            fonts,
        )

        draw_cadeca_column(
            draw,
            cadeca_data,
            COLUMN_POSITIONS["cadeca"]["start"],
            COLUMN_POSITIONS["cadeca"]["end"],
            y_content,
            fonts,
        )

        # 7. Dibujar footer
        draw_footer(draw, IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL, fonts)

        # 8. Guardar como PNG optimizado
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True, compress_level=6)
        buffer.seek(0)

        logger.info(
            f"✅ Imagen TASALO generada: {IMG_WIDTH_HORIZONTAL}x{IMG_HEIGHT_HORIZONTAL}px"
        )
        return buffer

    except Exception as e:
        logger.error(f"❌ Error generando imagen TASALO: {e}", exc_info=True)
        return None


async def generate_single_source_image(
    data: Dict[str, Any], source: str
) -> Optional[io.BytesIO]:
    """Generar imagen vertical individual para una fuente específica.

    Usa la plantilla img.jpg si está disponible, sino usa fondo gradiente.
    """
    try:
        # 1. Cargar plantilla o crear fallback
        template = load_template(source)

        if template:
            # Usar plantilla
            img = template.convert("RGBA")
        else:
            # Fallback: crear imagen con fondo gradiente
            img = Image.new(
                "RGBA", (IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL), (13, 13, 26, 255)
            )

        draw = ImageDraw.Draw(img)

        # 2. Cargar fuentes
        fonts = load_fonts()

        # 3. Si no hay plantilla, dibujar fondo gradiente
        if not template:
            draw_gradient_background(draw, IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL)

        # 4. Dibujar tarjeta vertical
        draw_single_source_card(
            draw, data, source, IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL, fonts
        )

        # 5. Dibujar footer
        draw_footer(draw, IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL, fonts)

        # 6. Guardar como PNG optimizado
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True, compress_level=6)
        buffer.seek(0)

        logger.info(
            f"✅ Imagen {source.upper()} generada: {IMG_WIDTH_VERTICAL}x{IMG_HEIGHT_VERTICAL}px"
        )
        return buffer

    except Exception as e:
        logger.error(f"❌ Error generando imagen {source.upper()}: {e}", exc_info=True)
        return None


async def generate_image(
    data: Dict[str, Any], image_type: str = "tasalo"
) -> Optional[io.BytesIO]:
    """Generar imagen con tasas de cambio.

    Args:
        data: Datos de la API (campo 'data' del response)
        image_type: Tipo de imagen ("tasalo", "eltoque", "bcc", "cadeca")

    Returns:
        BytesIO con PNG optimizado, o None si hay error
    """
    if image_type == "tasalo":
        return await generate_tasalo_image(data)
    elif image_type in ("eltoque", "bcc", "cadeca"):
        return await generate_single_source_image(data, image_type)
    else:
        logger.error(f"❌ Tipo de imagen desconocido: {image_type}")
        return None


def generate_image_sync(
    data: Dict[str, Any], image_type: str = "tasalo"
) -> Optional[io.BytesIO]:
    """Versión síncrona para testing.

    Args:
        data: Datos de la API
        image_type: Tipo de imagen

    Returns:
        BytesIO con la imagen
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(generate_image(data, image_type))


# =============================================================================
# SCRIPT DE PRUEBA
# =============================================================================

if __name__ == "__main__":
    test_data = {
        "eltoque": {
            "EUR": {"rate": 580.00, "change": "up", "prev_rate": 575.00},
            "USD": {"rate": 515.00, "change": "up", "prev_rate": 512.00},
            "MLC": {"rate": 420.00, "change": None, "prev_rate": 420.00},
            "BTC": {"rate": 52000000, "change": "up", "prev_rate": 51500000},
            "TRX": {"rate": 185.00, "change": "down", "prev_rate": 190.00},
            "USDT": {"rate": 560.00, "change": "up", "prev_rate": 558.00},
        },
        "bcc": {
            "EUR": {"rate": 551.23, "change": "up", "prev_rate": 548.00},
            "USD": {"rate": 478.00, "change": None, "prev_rate": 478.00},
            "CAD": {"rate": 348.17, "change": "down", "prev_rate": 352.00},
        },
        "cadeca": {
            "EUR": {"buy": 531.94, "sell": 584.30},
            "USD": {"buy": 461.27, "sell": 506.68},
        },
        "updated_at": datetime.now().isoformat(),
    }

    logging.basicConfig(level=logging.INFO)

    print("🎨 Generando imágenes de prueba...")

    # Probar imagen triple TASALO
    print("\n📊 Generando imagen TASALO (tabla triple)...")
    img_tasalo = generate_image_sync(test_data, image_type="tasalo")
    if img_tasalo:
        with open("test_tasalo.png", "wb") as f:
            f.write(img_tasalo.read())
        print("✅ test_tasalo.png generada")
    else:
        print("❌ Error generando test_tasalo.png")

    # Probar imagen individual ElToque
    print("\n🏠 Generando imagen ElToque...")
    img_eltoque = generate_image_sync(test_data, image_type="eltoque")
    if img_eltoque:
        with open("test_eltoque.png", "wb") as f:
            f.write(img_eltoque.read())
        print("✅ test_eltoque.png generada")
    else:
        print("❌ Error generando test_eltoque.png")

    # Probar imagen individual BCC
    print("\n🏛 Generando imagen BCC...")
    img_bcc = generate_image_sync(test_data, image_type="bcc")
    if img_bcc:
        with open("test_bcc.png", "wb") as f:
            f.write(img_bcc.read())
        print("✅ test_bcc.png generada")
    else:
        print("❌ Error generando test_bcc.png")

    # Probar imagen individual CADECA
    print("\n🏢 Generando imagen CADECA...")
    img_cadeca = generate_image_sync(test_data, image_type="cadeca")
    if img_cadeca:
        with open("test_cadeca.png", "wb") as f:
            f.write(img_cadeca.read())
        print("✅ test_cadeca.png generada")
    else:
        print("❌ Error generando test_cadeca.png")

    print("\n🎨 Pruebas completadas")
    print(
        "📁 Archivos generados: test_tasalo.png, test_eltoque.png, test_bcc.png, test_cadeca.png"
    )
