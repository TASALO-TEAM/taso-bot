"""Generador de imágenes Dark Glass v2 para el bot TASALO.

Módulo responsable de generar imágenes visualmente atractivas con las tasas
de cambio, usando diseño Dark Glass (modo oscuro) consistente con taso-app.

Diseño Dark Glass v2:
- Modo oscuro con glassmorphism (blur + bordes sutiles)
- Tabla horizontal 1200×630px para /tasalo
- Tarjetas verticales 800×1000px para comandos individuales
- Marca de agua @tasalobot discreta (5% opacity)
- Colores mejorados: rojo coral (subida), turquesa (bajada)
- Gradiente oscuro de fondo (#10102A → #1A1A3E)

Inspirado en: plans/2026-03-26-taso-bot-dark-glass-image-v2.md
"""

import asyncio
import logging
import os
import io
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, NamedTuple

from PIL import Image, ImageDraw, ImageFont

from src.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# TASALO DARK GLASS DESIGN SYSTEM v2
# =============================================================================

# Dimensiones
IMG_WIDTH_HORIZONTAL = 1200  # Para /tasalo
IMG_HEIGHT_HORIZONTAL = 630   # Ratio 1.91:1
IMG_WIDTH_VERTICAL = 800      # Para comandos individuales
IMG_HEIGHT_VERTICAL = 1000    # Ratio 4:5
PADDING = 40
COLUMN_GAP = 20

# Colores (Dark Glass)
COLOR_BG = "#10102A"                    # Fondo principal (azul oscuro profundo)
COLOR_BG_GRADIENT_START = "#10102A"     # Gradiente inicio
COLOR_BG_GRADIENT_MID = "#1A1A3E"       # Gradiente medio
COLOR_BG_GRADIENT_END = "#0F0F2D"       # Gradiente fin

# Superficie Glass (RGBA para transparencia)
COLOR_SURFACE = (255, 255, 255, 13)     # 5% opacity (13/255)
COLOR_SURFACE_BORDER = (255, 255, 255, 31)  # 12% opacity (31/255)

# Texto
COLOR_TEXT_PRIMARY = "#FFFFFF"          # Blanco (alto contraste: 18.5:1)
COLOR_TEXT_SECONDARY = "#A0B0D0"        # Gris azulado (6.8:1)

# Acentos
COLOR_ACCENT = "#5B8AFF"                # Azul brillante (8.2:1)
COLOR_ACCENT_GRADIENT_END = "#9B7BFF"   # Violeta

# Indicadores (colores mejorados)
COLOR_UP = "#FF6B6B"                    # Rojo coral (subida)
COLOR_DOWN = "#4ECDC4"                  # Turquesa (bajada)
COLOR_NEUTRAL = "#6C7A89"               # Gris azulado (neutral)

# Marca de agua (5% opacity, visible pero no intrusiva)
COLOR_WATERMARK = (255, 255, 255, 13)   # 5% opacity

# Shadow
COLOR_SHADOW = (0, 0, 0, 102)           # 40% opacity

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
CARD_WIDTH = IMG_WIDTH_VERTICAL - (PADDING * 2)
CARD_X_START = PADDING
CARD_X_END = IMG_WIDTH_VERTICAL - PADDING

# Tamaños de fuente (escalados por alto de imagen) - AUMENTADOS para mejor legibilidad
FONT_SCALE = {
    "title": 0.042,         # 42px para 1000px (antes 36px)
    "subtitle": 0.024,      # 24px (antes 20px)
    "column_header": 0.028, # 28px (antes 24px)
    "column_subheader": 0.020, # 20px (antes 16px)
    "currency": 0.028,      # 28px (antes 24px)
    "rate_value": 0.032,    # 32px BOLD (antes 28px)
    "footer": 0.018,        # 18px (antes 16px)
    "watermark": 0.040,     # 40px (antes 56px - muy grande)
}

# Altura de fila
ROW_HEIGHT = 48
HEADER_HEIGHT = 80


# =============================================================================
# GESTIÓN DE FUENTES
# =============================================================================

class Fonts(NamedTuple):
    """Colección de fuentes cargadas."""
    title: ImageFont.FreeTypeFont
    subtitle: ImageFont.FreeTypeFont
    column_header: ImageFont.FreeTypeFont
    column_subheader: ImageFont.FreeTypeFont
    currency: ImageFont.FreeTypeFont
    rate_value: ImageFont.FreeTypeFont
    footer: ImageFont.FreeTypeFont
    watermark: ImageFont.FreeTypeFont


def get_font_path() -> Optional[str]:
    """Obtener la ruta a una fuente disponible en el sistema.

    Prioriza Space Grotesk y JetBrains Mono, fallback a DejaVu Sans.

    Returns:
        Ruta a la fuente o None si no se encuentra
    """
    # Fuentes preferidas (Space Grotesk, JetBrains Mono)
    preferred_fonts = [
        "/usr/share/fonts/truetype/space-grotesk/SpaceGrotesk-Bold.ttf",
        "/usr/share/fonts/truetype/space-grotesk/SpaceGrotesk-SemiBold.ttf",
        "/usr/share/fonts/truetype/space-grotesk/SpaceGrotesk-Regular.ttf",
        "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf",
        "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Medium.ttf",
        "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf",
    ]
    
    # Fallback a fuentes del sistema
    fallback_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf",  # Windows
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    
    # Buscar en directorio fonts/ del proyecto
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fonts_dir = os.path.join(base_dir, "fonts")
    project_fonts = [
        os.path.join(fonts_dir, "SpaceGrotesk-Bold.ttf"),
        os.path.join(fonts_dir, "SpaceGrotesk-Regular.ttf"),
        os.path.join(fonts_dir, "JetBrainsMono-Bold.ttf"),
        os.path.join(fonts_dir, "JetBrainsMono-Regular.ttf"),
    ]
    
    # Buscar en orden: preferidas → proyecto → fallback
    all_fonts = preferred_fonts + project_fonts + fallback_fonts
    
    for path in all_fonts:
        if os.path.exists(path):
            return path
    
    return None


def load_fonts() -> Fonts:
    """Cargar todas las fuentes necesarias.

    Returns:
        Fonts namedtuple con todas las fuentes cargadas
    """
    font_path = get_font_path()

    if not font_path:
        logger.warning("⚠️ No se encontraron fuentes TrueType, usando fuente por defecto")
        default_font = ImageFont.load_default()
        return Fonts(
            title=default_font,
            subtitle=default_font,
            column_header=default_font,
            column_subheader=default_font,
            currency=default_font,
            rate_value=default_font,
            footer=default_font,
            watermark=default_font,
        )

    try:
        # Calcular tamaños basados en IMG_HEIGHT_VERTICAL (1000px)
        return Fonts(
            title=ImageFont.truetype(font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["title"])),
            subtitle=ImageFont.truetype(font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["subtitle"])),
            column_header=ImageFont.truetype(font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_header"])),
            column_subheader=ImageFont.truetype(font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_subheader"])),
            currency=ImageFont.truetype(font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["currency"])),
            rate_value=ImageFont.truetype(font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["rate_value"])),
            footer=ImageFont.truetype(font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["footer"])),
            watermark=ImageFont.truetype(font_path, int(IMG_HEIGHT_VERTICAL * FONT_SCALE["watermark"])),
        )
    except OSError as e:
        logger.warning(f"⚠️ Error cargando fuentes: {e}. Usando fuente por defecto.")
        default_font = ImageFont.load_default()
        return Fonts(
            title=default_font,
            subtitle=default_font,
            column_header=default_font,
            column_subheader=default_font,
            currency=default_font,
            rate_value=default_font,
            footer=default_font,
            watermark=default_font,
        )


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def get_change_emoji(change: Optional[str]) -> str:
    """Obtener emoji según la dirección del cambio.

    Args:
        change: "up", "down", o None

    Returns:
        Emoji correspondiente (🔺, 🔻, ―)
    """
    if change == "up":
        return "🔺"
    elif change == "down":
        return "🔻"
    else:
        return "―"


def get_change_color(change: Optional[str]) -> str:
    """Obtener color según la dirección del cambio.

    Args:
        change: "up", "down", o None

    Returns:
        Color hexadecimal
    """
    if change == "up":
        return COLOR_UP
    elif change == "down":
        return COLOR_DOWN
    else:
        return COLOR_NEUTRAL


def format_rate_value(rate: float) -> str:
    """Formatear valor de tasa con 2 decimales.

    Args:
        rate: Valor numérico

    Returns:
        String formateado
    """
    return f"{rate:,.2f}"


def parse_iso_datetime(iso_string: Optional[str]) -> str:
    """Parsear datetime ISO a formato legible.

    Args:
        iso_string: datetime en formato ISO 8601

    Returns:
        String formateado como "DD/MM/YYYY HH:MM"
    """
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


def get_currency_flag(currency: str) -> str:
    """Obtener emoji de bandera para una moneda.

    Args:
        currency: Código de moneda (USD, EUR, etc.)

    Returns:
        Emoji de bandera o símbolo
    """
    flags = {
        "USD": "🇺🇸",
        "EUR": "🇪🇺",
        "MLC": "💳",
        "USDT": "₮",
        "BTC": "₿",
        "ETH": "Ξ",
        "BNB": "🟡",
        "TRX": "🔷",
        "CAD": "🇨🇦",
        "MXN": "🇲🇽",
        "GBP": "🇬🇧",
        "CHF": "🇨🇭",
        "RUB": "🇷🇺",
        "AUD": "🇦🇺",
        "JPY": "🇯🇵",
    }
    return flags.get(currency.upper(), "💱")


def draw_gradient_background(
    draw: ImageDraw.ImageDraw,
    W: int,
    H: int,
) -> None:
    """Dibujar fondo con gradiente oscuro (Dark Glass).
    
    Crea un gradiente vertical suave de 3 bandas:
    - Superior: #10102A
    - Media: #1A1A3E
    - Inferior: #0F0F2D
    
    Args:
        draw: Objeto ImageDraw
        W: Ancho de imagen
        H: Alto de imagen
    """
    # Gradiente vertical simple (3 bandas)
    h1 = H // 3
    h2 = H * 2 // 3
    
    # Dibujar bandas de gradiente
    draw.rectangle((0, 0, W, h1), fill=COLOR_BG_GRADIENT_START)
    draw.rectangle((0, h1, W, h2), fill=COLOR_BG_GRADIENT_MID)
    draw.rectangle((0, h2, W, H), fill=COLOR_BG_GRADIENT_END)


def draw_rounded_rectangle(
    draw: ImageDraw.ImageDraw,
    rect: Tuple[int, int, int, int],
    radius: int,
    fill: Tuple[int, int, int, int] | str | None = None,
    outline: Tuple[int, int, int, int] | str | None = None,
    width: int = 1,
) -> None:
    """Dibujar rectángulo con bordes redondeados (compatible con Pillow <10.2).

    Args:
        draw: Objeto ImageDraw
        rect: Tupla (x1, y1, x2, y2)
        radius: Radio de los bordes redondeados
        fill: Color de relleno (RGBA o None)
        outline: Color de borde (RGBA o None)
        width: Ancho del borde
    """
    try:
        # Intentar usar método nativo (Pillow >=10.2)
        if fill is not None and outline is not None:
            draw.rounded_rectangle(rect, radius=radius, fill=fill, outline=outline, width=width)
        elif fill is not None:
            draw.rounded_rectangle(rect, radius=radius, fill=fill)
        elif outline is not None:
            draw.rounded_rectangle(rect, radius=radius, outline=outline, width=width)
    except AttributeError:
        # Fallback para versiones antiguas
        x1, y1, x2, y2 = rect
        if fill is not None:
            draw.rectangle(rect, fill=fill)
        if outline is not None:
            draw.rectangle(rect, outline=outline, width=width)


# =============================================================================
# FUNCIONES DE DIBUJO POR SECCIÓN
# =============================================================================

def draw_header(
    draw: ImageDraw.ImageDraw,
    W: int,
    H: int,
    fonts: Fonts,
) -> int:
    """Dibujar header con título y subtítulo.

    Args:
        draw: Objeto ImageDraw
        W: Ancho de imagen
        H: Alto de imagen
        fonts: Fuentes cargadas

    Returns:
        Posición Y para el contenido principal
    """
    y = PADDING
    
    # Título principal
    draw.text(
        (PADDING, y),
        "📊 TASALO — Tasas de Cambio",
        fill=COLOR_TEXT_PRIMARY,
        font=fonts.title,
    )
    y += int(H * FONT_SCALE["title"]) + 10
    
    # Subtítulo con fecha
    date_str = datetime.now().strftime("%d/%m/%Y · Cuba")
    draw.text(
        (PADDING, y),
        date_str,
        fill=COLOR_TEXT_SECONDARY,
        font=fonts.subtitle,
    )
    
    return y + 40  # Retornar Y para contenido principal


def draw_eltoque_column(
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    x_start: int,
    x_end: int,
    y_start: int,
    fonts: Fonts,
) -> int:
    """Dibujar columna de ElToque con tasas.

    Args:
        draw: Objeto ImageDraw
        data: Datos de ElToque
        x_start: Posición X inicial
        x_end: Posición X final
        y_start: Posición Y inicial
        fonts: Fuentes cargadas

    Returns:
        Nueva posición Y
    """
    y = y_start
    
    # Header de columna
    draw.text(
        (x_start, y),
        "🏠 informal",
        fill=COLOR_ACCENT,
        font=fonts.column_header,
    )
    y += int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_header"])
    
    draw.text(
        (x_start, y),
        "ElToque",
        fill=COLOR_TEXT_SECONDARY,
        font=fonts.column_subheader,
    )
    y += int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_subheader"]) + 10
    
    # Línea separadora
    draw.line((x_start, y, x_end, y), fill=COLOR_SURFACE_BORDER, width=2)
    y += 15
    
    # Ordenar monedas por prioridad
    priority = ["EUR", "USD", "MLC", "USDT", "BTC", "TRX", "BNB", "ETH"]
    sorted_currencies = sorted(
        data.keys() if isinstance(data, dict) else [],
        key=lambda x: priority.index(x.upper()) if x.upper() in priority else 99,
    )
    
    # Dibujar filas (máximo 8)
    for currency in sorted_currencies[:8]:
        if not isinstance(data, dict):
            break
            
        currency_info = data.get(currency, {})
        
        if isinstance(currency_info, dict):
            rate = currency_info.get("rate", 0)
            change = currency_info.get("change")
        else:
            rate = currency_info
            change = None
        
        # Emoji de bandera
        flag = get_currency_flag(currency)
        
        # Dibujar moneda (izquierda)
        draw.text(
            (x_start, y),
            f"{flag} {currency}",
            fill=COLOR_TEXT_PRIMARY,
            font=fonts.currency,
        )
        
        # Dibujar valor (derecha)
        rate_str = format_rate_value(rate) if rate else "---"
        indicator = get_change_emoji(change)
        indicator_color = get_change_color(change)
        
        # Valor alineado a derecha
        draw.text(
            (x_end - 10, y),
            rate_str,
            fill=COLOR_TEXT_PRIMARY,
            anchor="rm",
            font=fonts.rate_value,
        )
        
        # Indicador (después del valor)
        draw.text(
            (x_end + 15, y),
            indicator,
            fill=indicator_color,
            font=fonts.rate_value,
        )
        
        y += ROW_HEIGHT
    
    return y


def draw_bcc_column(
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    x_start: int,
    x_end: int,
    y_start: int,
    fonts: Fonts,
) -> int:
    """Dibujar columna del BCC con tasas.

    Args:
        draw: Objeto ImageDraw
        data: Datos del BCC
        x_start: Posición X inicial
        x_end: Posición X final
        y_start: Posición Y inicial
        fonts: Fuentes cargadas

    Returns:
        Nueva posición Y
    """
    y = y_start
    
    # Header de columna
    draw.text(
        (x_start, y),
        "🏛 BCC",
        fill=COLOR_ACCENT,
        font=fonts.column_header,
    )
    y += int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_header"])
    
    draw.text(
        (x_start, y),
        "Oficial",
        fill=COLOR_TEXT_SECONDARY,
        font=fonts.column_subheader,
    )
    y += int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_subheader"]) + 10
    
    # Línea separadora
    draw.line((x_start, y, x_end, y), fill=COLOR_SURFACE_BORDER, width=2)
    y += 15
    
    # Ordenar monedas por prioridad
    priority = ["EUR", "USD", "MLC", "CAD", "MXN", "GBP", "CHF", "RUB", "AUD", "JPY"]
    sorted_currencies = sorted(
        data.keys() if isinstance(data, dict) else [],
        key=lambda x: priority.index(x.upper()) if x.upper() in priority else 99,
    )
    
    # Dibujar filas (máximo 8)
    for currency in sorted_currencies[:8]:
        if not isinstance(data, dict):
            break
            
        currency_info = data.get(currency, {})
        
        if isinstance(currency_info, dict):
            rate = currency_info.get("rate", 0)
            change = currency_info.get("change")
        else:
            rate = currency_info
            change = None
        
        # Emoji de bandera
        flag = get_currency_flag(currency)
        
        # Dibujar moneda (izquierda)
        draw.text(
            (x_start, y),
            f"{flag} {currency}",
            fill=COLOR_TEXT_PRIMARY,
            font=fonts.currency,
        )
        
        # Dibujar valor (derecha)
        rate_str = format_rate_value(rate) if rate else "---"
        indicator = get_change_emoji(change)
        indicator_color = get_change_color(change)
        
        # Valor alineado a derecha
        draw.text(
            (x_end - 10, y),
            rate_str,
            fill=COLOR_TEXT_PRIMARY,
            anchor="rm",
            font=fonts.rate_value,
        )
        
        # Indicador (después del valor)
        draw.text(
            (x_end + 15, y),
            indicator,
            fill=indicator_color,
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

    Args:
        draw: Objeto ImageDraw
        data: Datos de CADECA
        x_start: Posición X inicial
        x_end: Posición X final
        y_start: Posición Y inicial
        fonts: Fuentes cargadas

    Returns:
        Nueva posición Y
    """
    y = y_start
    
    # Header de columna
    draw.text(
        (x_start, y),
        "🏢 CADECA",
        fill=COLOR_ACCENT,
        font=fonts.column_header,
    )
    y += int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_header"])
    
    draw.text(
        (x_start, y),
        "Exchange",
        fill=COLOR_TEXT_SECONDARY,
        font=fonts.column_subheader,
    )
    y += int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_subheader"]) + 10
    
    # Línea separadora
    draw.line((x_start, y, x_end, y), fill=COLOR_SURFACE_BORDER, width=2)
    y += 15
    
    # Headers de columnas (Buy / Sell)
    col_width = (x_end - x_start) // 3
    draw.text(
        (x_start, y),
        "Moneda",
        fill=COLOR_TEXT_SECONDARY,
        font=fonts.column_subheader,
    )
    draw.text(
        (x_start + col_width, y),
        "Compra",
        fill=COLOR_TEXT_SECONDARY,
        font=fonts.column_subheader,
        anchor="rm",
    )
    draw.text(
        (x_end - 10, y),
        "Venta",
        fill=COLOR_TEXT_SECONDARY,
        font=fonts.column_subheader,
        anchor="rm",
    )
    y += int(IMG_HEIGHT_VERTICAL * FONT_SCALE["column_subheader"]) + 10
    
    # Línea separadora
    draw.line((x_start, y, x_end, y), fill=COLOR_SURFACE_BORDER, width=1)
    y += 10
    
    # Ordenar monedas por prioridad
    priority = ["EUR", "USD", "MLC", "CAD", "MXN", "GBP", "CHF", "RUB", "AUD", "JPY"]
    sorted_currencies = sorted(
        data.keys() if isinstance(data, dict) else [],
        key=lambda x: priority.index(x.upper()) if x.upper() in priority else 99,
    )
    
    # Dibujar filas (máximo 6 para CADECA)
    for currency in sorted_currencies[:6]:
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
            (x_start, y),
            currency,
            fill=COLOR_TEXT_PRIMARY,
            font=fonts.currency,
        )
        
        # Dibujar compra (centro)
        if buy is not None:
            buy_str = format_rate_value(buy)
            draw.text(
                (x_start + col_width, y),
                buy_str,
                fill=COLOR_TEXT_PRIMARY,
                anchor="rm",
                font=fonts.rate_value,
            )
        else:
            draw.text(
                (x_start + col_width, y),
                "---",
                fill=COLOR_TEXT_SECONDARY,
                anchor="rm",
                font=fonts.rate_value,
            )
        
        # Dibujar venta (derecha)
        if sell is not None:
            sell_str = format_rate_value(sell)
            draw.text(
                (x_end - 10, y),
                sell_str,
                fill=COLOR_TEXT_PRIMARY,
                anchor="rm",
                font=fonts.rate_value,
            )
        else:
            draw.text(
                (x_end - 10, y),
                "---",
                fill=COLOR_TEXT_SECONDARY,
                anchor="rm",
                font=fonts.rate_value,
            )
        
        y += ROW_HEIGHT
    
    return y


def draw_single_source_column(
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    source: str,
    x_start: int,
    x_end: int,
    y_start: int,
    fonts: Fonts,
) -> int:
    """Dibujar columna individual para una fuente específica.

    Args:
        draw: Objeto ImageDraw
        data: Datos de la fuente
        source: Identificador de fuente ("eltoque", "bcc", "cadeca")
        x_start: Posición X inicial
        x_end: Posición X final
        y_start: Posición Y inicial
        fonts: Fuentes cargadas

    Returns:
        Nueva posición Y
    """
    # Configurar según fuente
    if source == "eltoque":
        icon = "🏠"
        title = "informal"
        subtitle = "ElToque"
        return draw_eltoque_column(draw, data, x_start, x_end, y_start, fonts)
    elif source == "bcc":
        icon = "🏛"
        title = "BCC"
        subtitle = "Oficial"
        return draw_bcc_column(draw, data, x_start, x_end, y_start, fonts)
    elif source == "cadeca":
        icon = "🏢"
        title = "CADECA"
        subtitle = "Exchange"
        return draw_cadeca_column(draw, data, x_start, x_end, y_start, fonts)
    else:
        return y_start


def draw_single_source_card(
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    source: str,
    W: int,
    H: int,
    fonts: Fonts,
) -> None:
    """Dibujar tarjeta vertical para fuente individual (Dark Glass).
    
    Args:
        draw: Objeto ImageDraw
        data: Datos de la fuente
        source: Identificador de fuente ("eltoque", "bcc", "cadeca")
        W: Ancho de imagen
        H: Alto de imagen
        fonts: Fuentes cargadas
    """
    # Títulos por fuente
    source_titles = {
        "eltoque": ("🏠 MERCADO INFORMAL", "ElToque"),
        "bcc": ("🏛 BANCO CENTRAL", "BCC"),
        "cadeca": ("🏢 CADECA", "Exchange"),
    }
    
    title, subtitle = source_titles.get(source, ("📊 TASALO", "TASALO"))
    
    # Dibujar header personalizado
    y = PADDING
    
    # Título principal
    draw.text((PADDING, y), title, fill=COLOR_TEXT_PRIMARY, font=fonts.title)
    y += int(H * FONT_SCALE["title"]) + 10
    
    # Subtítulo con fecha
    date_str = datetime.now().strftime("%d/%m/%Y · Cuba")
    subtitle_text = f"{subtitle} · {date_str}"
    draw.text((PADDING, y), subtitle_text, fill=COLOR_TEXT_SECONDARY, font=fonts.subtitle)
    
    y_content = y + int(H * FONT_SCALE["subtitle"]) + 40
    y_content = max(y_content, 120)
    
    # Dibujar superficie glass (tarjeta centrada)
    card_rect = (
        CARD_X_START,
        y_content,
        CARD_X_END,
        H - 120,  # Antes del footer
    )
    
    # Fondo glass con border
    draw_rounded_rectangle(draw, card_rect, radius=16, fill=COLOR_SURFACE)
    draw_rounded_rectangle(draw, card_rect, radius=16, outline=COLOR_SURFACE_BORDER, width=1)
    
    # Contenido de la tarjeta
    inner_y = y_content + 20
    inner_x_start = CARD_X_START + 20
    inner_x_end = CARD_X_END - 20
    
    # Dibujar columna según fuente
    if source == "eltoque":
        draw_eltoque_column(draw, data.get("eltoque", {}), inner_x_start, inner_x_end, inner_y, fonts)
    elif source == "bcc":
        draw_bcc_column(draw, data.get("bcc", {}), inner_x_start, inner_x_end, inner_y, fonts)
    elif source == "cadeca":
        draw_cadeca_column(draw, data.get("cadeca", {}), inner_x_start, inner_x_end, inner_y, fonts)


def draw_watermark(
    draw: ImageDraw.ImageDraw,
    W: int,
    H: int,
    fonts: Fonts,
) -> None:
    """Dibujar marca de agua @tasalobot en esquina superior derecha.

    Args:
        draw: Objeto ImageDraw
        W: Ancho de imagen
        H: Alto de imagen
        fonts: Fuentes cargadas
    """
    watermark_text = "@tasalobot"

    # Calcular posición (esquina superior derecha)
    bbox = draw.textbbox((0, 0), watermark_text, font=fonts.watermark)
    text_width = bbox[2] - bbox[0]

    x = W - PADDING - text_width  # PADDING desde la derecha
    y = PADDING // 2  # 20px desde el top

    # Dibujar con transparencia aumentada (15% para mejor visibilidad)
    watermark_color = (255, 255, 255, 38)  # 15% opacity (38/255)
    draw.text(
        (x, y),
        watermark_text,
        fill=watermark_color,
        font=fonts.watermark,
    )


def draw_footer(
    draw: ImageDraw.ImageDraw,
    W: int,
    H: int,
    data: Dict[str, Any],
    fonts: Fonts,
) -> None:
    """Dibujar footer con timestamp y fuentes.

    Args:
        draw: Objeto ImageDraw
        W: Ancho de imagen
        H: Alto de imagen
        data: Datos de la API
        fonts: Fuentes cargadas
    """
    y = H - 50
    
    # Timestamp
    updated_at = data.get("updated_at")
    timestamp = parse_iso_datetime(updated_at)
    
    # Fuentes disponibles
    sources = []
    if data.get("eltoque"):
        sources.append("elToque")
    if data.get("bcc"):
        sources.append("BCC")
    if data.get("cadeca"):
        sources.append("CADECA")
    
    sources_str = " · ".join(sources) if sources else "TASALO"
    
    # Texto del footer
    footer_text = f"Actualizado: {timestamp} · {sources_str}"
    
    # Centrar horizontalmente
    bbox = draw.textbbox((0, 0), footer_text, font=fonts.footer)
    text_width = bbox[2] - bbox[0]
    x = (W - text_width) // 2
    
    draw.text(
        (x, y),
        footer_text,
        fill=COLOR_TEXT_SECONDARY,
        font=fonts.footer,
    )


# =============================================================================
# FUNCIONES PRINCIPALES DE GENERACIÓN
# =============================================================================

async def generate_tasalo_image(data: Dict[str, Any]) -> Optional[io.BytesIO]:
    """Generar imagen horizontal con tabla triple (ElToque | BCC | CADECA).

    Args:
        data: Datos de la API (campo 'data' del response)

    Returns:
        BytesIO con PNG optimizado, o None si hay error
    """
    try:
        # 1. Crear imagen horizontal
        img = Image.new("RGBA", (IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL), COLOR_BG)
        draw = ImageDraw.Draw(img)

        # 2. Cargar fuentes
        fonts = load_fonts()

        # 3. Dibujar fondo gradiente
        draw_gradient_background(draw, IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL)

        # 4. Dibujar superficie glass principal
        surface_rect = (
            PADDING - 10,
            100,
            IMG_WIDTH_HORIZONTAL - PADDING + 10,
            IMG_HEIGHT_HORIZONTAL - 70,
        )
        draw_rounded_rectangle(draw, surface_rect, radius=16, fill=COLOR_SURFACE)
        draw_rounded_rectangle(draw, surface_rect, radius=16, outline=COLOR_SURFACE_BORDER, width=1)

        # 5. Dibujar header
        y_content = draw_header(draw, IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL, fonts)
        y_content = max(y_content, 120)

        # 6. Extraer datos por fuente
        eltoque_data = data.get("eltoque", {})
        bcc_data = data.get("bcc", {})
        cadeca_data = data.get("cadeca", {})

        # 7. Dibujar columnas
        draw_eltoque_column(
            draw,
            eltoque_data,
            COLUMN_POSITIONS["eltoque"]["start"],
            COLUMN_POSITIONS["eltoque"]["end"],
            y_content,
            fonts,
        )

        draw_bcc_column(
            draw,
            bcc_data,
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

        # 8. Dibujar marca de agua
        draw_watermark(draw, IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL, fonts)

        # 9. Dibujar footer
        draw_footer(draw, IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL, data, fonts)

        # 10. Guardar como PNG optimizado
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True, compress_level=6)
        buffer.seek(0)

        logger.info(f"✅ Imagen TASALO generada: {IMG_WIDTH_HORIZONTAL}x{IMG_HEIGHT_HORIZONTAL}px")
        return buffer

    except Exception as e:
        logger.error(f"❌ Error generando imagen TASALO: {e}", exc_info=True)
        return None


async def generate_single_source_image(
    data: Dict[str, Any],
    source: str,
) -> Optional[io.BytesIO]:
    """Generar imagen vertical individual para una fuente específica.

    Args:
        data: Datos de la API (campo 'data' del response)
        source: Identificador de fuente ("eltoque", "bcc", "cadeca")

    Returns:
        BytesIO con PNG optimizado, o None si hay error
    """
    try:
        # 1. Crear imagen vertical
        img = Image.new("RGBA", (IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL), COLOR_BG)
        draw = ImageDraw.Draw(img)

        # 2. Cargar fuentes
        fonts = load_fonts()

        # 3. Dibujar fondo gradiente
        draw_gradient_background(draw, IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL)

        # 4. Dibujar tarjeta vertical centrada
        draw_single_source_card(draw, data, source, IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL, fonts)

        # 5. Dibujar marca de agua
        draw_watermark(draw, IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL, fonts)

        # 6. Dibujar footer
        draw_footer(draw, IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL, data, fonts)

        # 7. Guardar como PNG optimizado
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True, compress_level=6)
        buffer.seek(0)

        logger.info(f"✅ Imagen {source.upper()} generada: {IMG_WIDTH_VERTICAL}x{IMG_HEIGHT_VERTICAL}px")
        return buffer

    except Exception as e:
        logger.error(f"❌ Error generando imagen {source.upper()}: {e}", exc_info=True)
        return None


async def generate_image(
    data: Dict[str, Any],
    image_type: str = "tasalo",
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


def generate_image_sync(data: Dict[str, Any], image_type: str = "tasalo") -> Optional[io.BytesIO]:
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
    # Datos de prueba
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
    print("📁 Archivos generados: test_tasalo.png, test_eltoque.png, test_bcc.png, test_cadeca.png")
