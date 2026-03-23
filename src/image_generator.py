"""Generador de imágenes con plantilla para el bot TASALO.

Módulo responsable de generar imágenes visualmente atractivas con las tasas
de cambio, usando una plantilla base (template.png) similar a bbalert.

Inspirado en la implementación de /home/ersus/bot/dev/utils/image_generator.py
"""

import asyncio
import logging
import os
import io
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from src.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTES DE DISEÑO (TASALO Design System)
# =============================================================================

# Colores (usando el esquema de bbalert - tinta oscura sobre plantilla clara)
COLOR_TINTA = "#0B1E38"        # Color principal para texto (azul oscuro)
COLOR_TINTA_CLARO = "#1a3a5c"  # Versión más clara para texto secundario
COLOR_BLANCO = "#FFFFFF"       # Blanco para títulos
COLOR_GRIS = "#A0B0D0"         # Gris azulado para subtítulos

# Dimensiones de la plantilla
TEMPLATE_WIDTH = 1200
TEMPLATE_HEIGHT = 800

# Fuentes - tamaños relativos al alto de la imagen (como bbalert)
FONT_SCALE_TITLE = 0.048       # Para título principal
FONT_SCALE_SECTION = 0.032     # Para nombres de sección
FONT_SCALE_RATE = 0.032        # Para valores de tasas
FONT_SCALE_LABEL = 0.024       # Para labels secundarios
FONT_SCALE_FOOTER = 0.020      # Para footer


# =============================================================================
# GESTIÓN DE FUENTES
# =============================================================================

def get_font_path() -> str:
    """Obtener la ruta a una fuente disponible en el sistema.
    
    Returns:
        Ruta a la fuente o None si no se encuentra
    """
    # Priorizar fuentes del sistema
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf",  # Windows
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    
    # También buscar en el directorio fonts/ del proyecto
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fonts_dir = os.path.join(base_dir, "fonts")
    project_fonts = [
        os.path.join(fonts_dir, "SpaceGrotesk-Regular.ttf"),
        os.path.join(fonts_dir, "SpaceGrotesk-Bold.ttf"),
        os.path.join(fonts_dir, "JetBrainsMono-Regular.ttf"),
    ]
    font_paths.extend(project_fonts)
    
    for path in font_paths:
        if os.path.exists(path):
            return path
    
    return None


def load_fonts() -> Tuple[Optional[ImageFont.FreeTypeFont], ...]:
    """Cargar todas las fuentes necesarias.
    
    Returns:
        Tupla (font_title, font_section, font_rate, font_label, font_footer)
    """
    font_path = get_font_path()
    
    if not font_path:
        logger.warning("⚠️ No se encontraron fuentes TrueType, usando fuente por defecto")
        default_font = ImageFont.load_default()
        return (default_font,) * 5
    
    try:
        # Calcular tamaños basados en la altura de la plantilla
        font_title = ImageFont.truetype(font_path, int(TEMPLATE_HEIGHT * FONT_SCALE_TITLE))
        font_section = ImageFont.truetype(font_path, int(TEMPLATE_HEIGHT * FONT_SCALE_SECTION))
        font_rate = ImageFont.truetype(font_path, int(TEMPLATE_HEIGHT * FONT_SCALE_RATE))
        font_label = ImageFont.truetype(font_path, int(TEMPLATE_HEIGHT * FONT_SCALE_LABEL))
        font_footer = ImageFont.truetype(font_path, int(TEMPLATE_HEIGHT * FONT_SCALE_FOOTER))
        
        return font_title, font_section, font_rate, font_label, font_footer
    except OSError as e:
        logger.warning(f"⚠️ Error cargando fuentes: {e}. Usando fuente por defecto.")
        default_font = ImageFont.load_default()
        return (default_font,) * 5


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
        return "#DC2626"  # Rojo para subida
    elif change == "down":
        return "#16A34A"  # Verde para bajada
    else:
        return COLOR_TINTA_CLARO


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
        String formateado como "YYYY-MM-DD HH:MM"
    """
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
        "MLC": "🧾",
        "USDT": "₮",
        "BTC": "₿",
        "ETH": "Ξ",
        "BNB": "🟡",
        "TRX": "🔷",
    }
    return flags.get(currency.upper(), "💱")


# =============================================================================
# FUNCIONES DE DIBUJO POR BLOQUE
# =============================================================================

def draw_eltoque_section(
    draw: ImageDraw.ImageDraw,
    eltoque_data: Dict[str, Any],
    start_y: float,
    row_height: float,
    font_section: ImageFont.FreeTypeFont,
    font_rate: ImageFont.FreeTypeFont,
    W: int,
    H: int,
) -> float:
    """Dibujar sección de Mercado Informal (El Toque).
    
    Args:
        draw: Objeto ImageDraw
        eltoque_data: Datos de El Toque
        start_y: Posición Y inicial
        row_height: Altura entre filas
        font_section: Fuente para nombres
        font_rate: Fuente para valores
        W: Ancho de imagen
        H: Alto de imagen
        
    Returns:
        Nueva posición Y
    """
    y = start_y
    
    # Título de sección
    draw.text((W * 0.15, y), "📊 MERCADO INFORMAL", fill=COLOR_TINTA, font=font_section)
    y += row_height * 0.9
    
    # Línea separadora
    draw.line((W * 0.15, y, W * 0.85, y), fill=COLOR_TINTA_CLARO, width=2)
    y += row_height * 0.6
    
    # Ordenar monedas por prioridad
    priority = ["USD", "EUR", "MLC", "USDT", "BTC", "ETH", "BNB", "TRX"]
    sorted_currencies = sorted(
        eltoque_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x)
    )
    
    for currency in sorted_currencies[:8]:  # Máximo 8 monedas
        currency_info = eltoque_data[currency]
        
        if isinstance(currency_info, dict):
            rate = currency_info.get("rate", 0)
            change = currency_info.get("change", None)
        else:
            rate = currency_info
            change = None
        
        flag = get_currency_flag(currency)
        rate_str = format_rate_value(rate)
        
        # Dibujar moneda con bandera (izquierda)
        currency_text = f"{flag} {currency}"
        draw.text((W * 0.15, y), currency_text, fill=COLOR_TINTA, font=font_rate)
        
        # Dibujar valor (derecha)
        value_text = f"{rate_str} CUP"
        draw.text((W * 0.78, y), value_text, fill=COLOR_TINTA, anchor="rm", font=font_rate)
        
        # Dibujar indicador de cambio (centro-derecha)
        indicator = get_change_emoji(change)
        if indicator != "―":
            change_color = get_change_color(change)
            draw.text((W * 0.82, y), indicator, fill=change_color, font=font_rate)
        
        y += row_height
    
    return y


def draw_cadeca_section(
    draw: ImageDraw.ImageDraw,
    cadeca_data: Dict[str, Any],
    start_y: float,
    row_height: float,
    font_section: ImageFont.FreeTypeFont,
    font_rate: ImageFont.FreeTypeFont,
    font_label: ImageFont.FreeTypeFont,
    W: int,
    H: int,
) -> float:
    """Dibujar sección de CADECA.
    
    Args:
        draw: Objeto ImageDraw
        cadeca_data: Datos de CADECA
        start_y: Posición Y inicial
        row_height: Altura entre filas
        font_section: Fuente para títulos
        font_rate: Fuente para valores
        font_label: Fuente para labels
        W: Ancho de imagen
        H: Alto de imagen
        
    Returns:
        Nueva posición Y
    """
    y = start_y
    
    # Título
    draw.text((W * 0.15, y), "🏢 CADECA", fill=COLOR_TINTA, font=font_section)
    y += row_height * 0.9
    
    # Línea separadora
    draw.line((W * 0.15, y, W * 0.85, y), fill=COLOR_TINTA_CLARO, width=2)
    y += row_height * 0.6
    
    # Headers de columnas
    draw.text((W * 0.15, y), "Moneda", fill=COLOR_TINTA_CLARO, font=font_label)
    draw.text((W * 0.50, y), "Compra", fill=COLOR_TINTA_CLARO, font=font_label, anchor="rm")
    draw.text((W * 0.65, y), "Venta", fill=COLOR_TINTA_CLARO, font=font_label, anchor="rm")
    y += row_height * 0.9
    
    # Ordenar monedas
    priority = ["USD", "EUR"]
    sorted_currencies = sorted(
        cadeca_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x)
    )
    
    for currency in sorted_currencies[:6]:  # Máximo 6 monedas
        currency_info = cadeca_data[currency]
        
        if isinstance(currency_info, dict):
            buy = currency_info.get("buy", 0)
            sell = currency_info.get("sell", 0)
        else:
            buy = 0
            sell = 0
        
        buy_str = format_rate_value(buy) if buy else "—"
        sell_str = format_rate_value(sell) if sell else "—"
        
        draw.text((W * 0.15, y), currency, fill=COLOR_TINTA, font=font_rate)
        draw.text((W * 0.50, y), buy_str, fill=COLOR_TINTA, anchor="rm", font=font_rate)
        draw.text((W * 0.65, y), sell_str, fill=COLOR_TINTA, anchor="rm", font=font_rate)
        
        y += row_height
    
    return y


def draw_bcc_section(
    draw: ImageDraw.ImageDraw,
    bcc_data: Dict[str, Any],
    start_y: float,
    row_height: float,
    font_section: ImageFont.FreeTypeFont,
    font_rate: ImageFont.FreeTypeFont,
    W: int,
    H: int,
) -> float:
    """Dibujar sección del Banco Central (BCC).
    
    Args:
        draw: Objeto ImageDraw
        bcc_data: Datos del BCC
        start_y: Posición Y inicial
        row_height: Altura entre filas
        font_section: Fuente para títulos
        font_rate: Fuente para valores
        W: Ancho de imagen
        H: Alto de imagen
        
    Returns:
        Nueva posición Y
    """
    y = start_y
    
    # Título
    draw.text((W * 0.15, y), "🏛 BANCO CENTRAL (BCC)", fill=COLOR_TINTA, font=font_section)
    y += row_height * 0.9
    
    # Línea separadora
    draw.line((W * 0.15, y, W * 0.85, y), fill=COLOR_TINTA_CLARO, width=2)
    y += row_height * 0.6
    
    # Ordenar monedas
    priority = ["USD", "EUR"]
    sorted_currencies = sorted(
        bcc_data.keys(),
        key=lambda x: (priority.index(x.upper()) if x.upper() in priority else 99, x)
    )
    
    for currency in sorted_currencies[:6]:  # Máximo 6 monedas
        currency_info = bcc_data[currency]
        
        if isinstance(currency_info, dict):
            rate = currency_info.get("rate", 0)
        else:
            rate = currency_info
        
        flag = get_currency_flag(currency)
        rate_str = format_rate_value(rate)
        
        draw.text((W * 0.15, y), f"{flag} {currency}", fill=COLOR_TINTA, font=font_rate)
        draw.text((W * 0.78, y), f"{rate_str} CUP", fill=COLOR_TINTA, anchor="rm", font=font_rate)
        
        y += row_height
    
    return y


def draw_footer(
    draw: ImageDraw.ImageDraw,
    timestamp: str,
    footer_y: float,
    font_footer: ImageFont.FreeTypeFont,
    W: int,
    H: int,
) -> None:
    """Dibujar footer con timestamp y fuentes.
    
    Args:
        draw: Objeto ImageDraw
        timestamp: Fecha y hora formateada
        footer_y: Posición Y del footer
        font_footer: Fuente para footer
        W: Ancho de imagen
        H: Alto de imagen
    """
    footer_text = f"Actualizado: {timestamp} · Fuente: elToque.com · CADECA · BCC"
    draw.text((W / 2, footer_y), footer_text, fill=COLOR_TINTA_CLARO, anchor="mt", font=font_footer)


# =============================================================================
# FUNCIÓN PRINCIPAL DE GENERACIÓN
# =============================================================================

async def generate_image(data: Dict[str, Any]) -> Optional[io.BytesIO]:
    """Generar imagen con las tasas de cambio usando plantilla.
    
    Implementación basada en bbalert:
    - Carga template.png como fondo (o template_watermark.png si existe)
    - Superpone las tasas en posiciones relativas
    - Genera JPEG optimizado para Telegram
    
    Args:
        data: Diccionario con datos de la API (campo 'data' del response)
        
    Returns:
        BytesIO con la imagen PNG, o None si hay error
    """
    try:
        # 1. Cargar plantilla (priorizar template_watermark.png si existe)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        
        # Priorizar plantilla con marca de agua
        template_path = os.path.join(data_dir, "template_watermark.png")
        if not os.path.exists(template_path):
            template_path = settings.template_full_path
        
        if not os.path.exists(template_path):
            logger.error(f"❌ No se encuentra la plantilla en: {template_path}")
            return None
        
        img = Image.open(template_path).convert("RGBA")
        W, H = img.size
        draw = ImageDraw.Draw(img)
        
        # 2. Cargar fuentes
        font_title, font_section, font_rate, font_label, font_footer = load_fonts()
        
        # 3. Extraer datos
        eltoque_data = data.get("eltoque", {})
        cadeca_data = data.get("cadeca", {})
        bcc_data = data.get("bcc", {})
        updated_at = data.get("updated_at")
        timestamp = parse_iso_datetime(updated_at)
        
        # 4. Calcular posiciones
        # El contenido comienza después del header (~48% de la altura)
        start_y = H * 0.48
        
        # Espacio disponible para contenido (~30% de la altura)
        espacio_disponible = H * 0.30
        
        # Calcular número total de filas estimadas
        total_rows = 0
        if eltoque_data:
            total_rows += min(len(eltoque_data), 8)
        if cadeca_data:
            total_rows += min(len(cadeca_data), 6) + 3  # +3 para headers
        if bcc_data:
            total_rows += min(len(bcc_data), 6) + 2  # +2 para header
        
        # Altura dinámica por fila
        if total_rows > 0:
            row_height = espacio_disponible / (total_rows + 1)
        else:
            row_height = H * 0.04  # Valor por defecto
        
        # 5. Dibujar secciones
        y = start_y
        
        if eltoque_data:
            y = draw_eltoque_section(
                draw, eltoque_data, y, row_height,
                font_section, font_rate, W, H
            )
            y += row_height * 0.5  # Espacio entre secciones
        
        if cadeca_data:
            y = draw_cadeca_section(
                draw, cadeca_data, y, row_height,
                font_section, font_rate, font_label, W, H
            )
            y += row_height * 0.5
        
        if bcc_data:
            y = draw_bcc_section(
                draw, bcc_data, y, row_height,
                font_section, font_rate, W, H
            )
        
        # 6. Dibujar footer
        footer_y = H * 0.77
        draw_footer(draw, timestamp, footer_y, font_footer, W, H)
        
        # 7. Guardar como JPEG optimizado
        buffer = io.BytesIO()
        img_rgb = img.convert('RGB')  # Eliminar canal alpha para JPEG
        img_rgb.save(
            buffer,
            format='JPEG',
            quality=85,
            optimize=True,
            progressive=True,
        )
        buffer.seek(0)
        
        logger.info(f"✅ Imagen generada: {W}x{H}px (JPEG optimizado)")
        return buffer
        
    except Exception as e:
        logger.error(f"❌ Error generando imagen: {e}", exc_info=True)
        return None


def generate_image_sync(data: Dict[str, Any]) -> Optional[io.BytesIO]:
    """Versión síncrona para testing.
    
    Args:
        data: Datos de la API
        
    Returns:
        BytesIO con la imagen
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(generate_image(data))


# =============================================================================
# SCRIPT DE PRUEBA
# =============================================================================

if __name__ == "__main__":
    # Datos de prueba
    test_data = {
        "eltoque": {
            "USD": {"rate": 385.50, "change": "up", "change_value": 2.50},
            "EUR": {"rate": 415.20, "change": "down", "change_value": -1.80},
            "MLC": {"rate": 390.00, "change": None, "change_value": 0},
            "USDT": {"rate": 388.00, "change": "up", "change_value": 1.20},
            "BTC": {"rate": 28500000, "change": "up", "change_value": 500000},
        },
        "cadeca": {
            "USD": {"buy": 122.00, "sell": 128.00},
            "EUR": {"buy": 132.50, "sell": 138.50},
        },
        "bcc": {
            "USD": {"rate": 122.00},
            "EUR": {"rate": 132.50},
        },
        "updated_at": datetime.now().isoformat(),
    }
    
    logging.basicConfig(level=logging.INFO)
    
    print("🧪 Generando imagen de prueba...")
    result = generate_image_sync(test_data)
    
    if result:
        output_path = "test_output.jpg"
        with open(output_path, "wb") as f:
            f.write(result.read())
        print(f"✅ Imagen guardada en: {output_path}")
    else:
        print("❌ Error generando imagen")
