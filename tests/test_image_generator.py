"""Tests para el generador de imágenes de TASALO."""

import pytest
from io import BytesIO
from PIL import Image

from src.image_generator import (
    generate_image_sync,
    get_fonts,
    get_change_color,
    get_change_indicator,
    format_rate_value,
    COLOR_BG,
    COLOR_ACCENT,
    COLOR_UP,
    COLOR_DOWN,
    COLOR_NEUTRAL,
    IMAGE_WIDTH,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_api_data():
    """Datos de ejemplo para testing."""
    return {
        "eltoque": {
            "USD": {"rate": 365.00, "change": "up", "change_value": 5.00},
            "EUR": {"rate": 398.00, "change": "neutral", "change_value": 0},
            "MLC": {"rate": 210.00, "change": "down", "change_value": 5.00},
            "USDT": {"rate": 362.00, "change": "neutral", "change_value": 0},
        },
        "cadeca": {
            "USD": {"buy": 120.00, "sell": 125.00},
            "EUR": {"buy": 130.00, "sell": 136.00},
        },
        "bcc": {
            "USD": {"rate": 24.00},
            "EUR": {"rate": 26.50},
        },
        "updated_at": "2026-03-22T14:30:00Z",
        "sources": ["eltoque", "cadeca", "bcc"],
    }


@pytest.fixture
def minimal_api_data():
    """Datos mínimos para testing."""
    return {
        "eltoque": {
            "USD": {"rate": 360.00, "change": "neutral", "change_value": 0},
        },
        "updated_at": "2026-03-22T10:00:00Z",
        "sources": ["eltoque"],
    }


# =============================================================================
# TESTS DE FUNCIONES AUXILIARES
# =============================================================================

class TestChangeIndicators:
    """Tests para indicadores de cambio."""

    def test_get_change_color_up(self):
        """Color rojo para cambio positivo."""
        assert get_change_color("up") == COLOR_UP

    def test_get_change_color_down(self):
        """Color verde para cambio negativo."""
        assert get_change_color("down") == COLOR_DOWN

    def test_get_change_color_neutral(self):
        """Color gris para sin cambio."""
        assert get_change_color("neutral") == COLOR_NEUTRAL

    def test_get_change_color_none(self):
        """Color gris para None."""
        assert get_change_color(None) == COLOR_NEUTRAL

    def test_get_change_indicator_up(self):
        """Emoji 🔺 para cambio positivo."""
        assert get_change_indicator("up") == "🔺"

    def test_get_change_indicator_down(self):
        """Emoji 🔻 para cambio negativo."""
        assert get_change_indicator("down") == "🔻"

    def test_get_change_indicator_neutral(self):
        """Emoji ― para sin cambio."""
        assert get_change_indicator("neutral") == "―"


class TestFormatHelpers:
    """Tests para funciones de formateo."""

    def test_format_rate_value_whole_number(self):
        """Formateo de número entero."""
        assert format_rate_value(365) == "365.00"

    def test_format_rate_value_decimal(self):
        """Formateo con decimales."""
        assert format_rate_value(365.50) == "365.50"

    def test_format_rate_value_thousands(self):
        """Formateo con miles."""
        assert format_rate_value(1234.56) == "1,234.56"

    def test_format_rate_value_negative(self):
        """Formateo de negativos (para cambios)."""
        assert format_rate_value(-5.00) == "-5.00"


# =============================================================================
# TESTS DE FUENTES
# =============================================================================

class TestFonts:
    """Tests para gestión de fuentes."""

    def test_get_fonts_returns_all_fonts(self):
        """Obtener todas las fuentes."""
        font_title, font_section, font_rate, font_label, font_footer = get_fonts()

        assert font_title is not None
        assert font_section is not None
        assert font_rate is not None
        assert font_label is not None
        assert font_footer is not None

    def test_fonts_load_successfully(self):
        """Las fuentes se cargan correctamente."""
        font_title, font_section, font_rate, font_label, font_footer = get_fonts()

        # Verificar que las fuentes no son las de fallback (default)
        # Las fuentes cargadas tienen método getbbox funcional
        test_text = "Test"
        
        # Si las fuentes cargaron bien, getbbox debería funcionar
        title_bbox = font_title.getbbox(test_text)
        label_bbox = font_label.getbbox(test_text)
        
        # Verificar que los bbox tienen dimensiones razonables
        assert title_bbox[2] > 0  # width > 0
        assert title_bbox[3] > 0  # height > 0
        assert label_bbox[2] > 0
        assert label_bbox[3] > 0


# =============================================================================
# TESTS DE GENERACIÓN DE IMÁGENES
# =============================================================================

class TestImageGeneration:
    """Tests para generación de imágenes."""

    def test_generate_image_returns_bytesio(self, sample_api_data):
        """La imagen generada es un BytesIO."""
        result = generate_image_sync(sample_api_data)

        assert result is not None
        assert isinstance(result, BytesIO)

    def test_generate_image_valid_png(self, sample_api_data):
        """La imagen generada es un PNG válido."""
        result = generate_image_sync(sample_api_data)

        # Intentar abrir la imagen con PIL
        img = Image.open(result)
        assert img.format == "PNG"

    def test_generate_image_correct_width(self, sample_api_data):
        """La imagen tiene el ancho correcto."""
        result = generate_image_sync(sample_api_data)
        img = Image.open(result)

        assert img.width == IMAGE_WIDTH

    def test_generate_image_minimum_height(self, sample_api_data):
        """La imagen tiene altura mínima razonable."""
        result = generate_image_sync(sample_api_data)
        img = Image.open(result)

        # Altura mínima de 400px según implementación
        assert img.height >= 400

    def test_generate_image_with_minimal_data(self, minimal_api_data):
        """Generar imagen con datos mínimos."""
        result = generate_image_sync(minimal_api_data)

        assert result is not None
        img = Image.open(result)
        assert img.format == "PNG"

    def test_generate_image_has_accent_color(self, sample_api_data):
        """La imagen contiene el color de acento."""
        result = generate_image_sync(sample_api_data)
        img = Image.open(result)

        # Convertir a RGB si es necesario
        img = img.convert("RGB")

        # Buscar píxeles con el color de acento (#5b8aff)
        accent_rgb = (91, 138, 255)  # RGB de #5b8aff
        pixels = list(img.getdata())

        # Verificar que hay al menos algunos píxeles cercanos al color de acento
        found_accent = False
        for pixel in pixels:
            # Verificar si el pixel está cerca del color de acento (tolerancia 20)
            if (
                abs(pixel[0] - accent_rgb[0]) < 20 and
                abs(pixel[1] - accent_rgb[1]) < 20 and
                abs(pixel[2] - accent_rgb[2]) < 20
            ):
                found_accent = True
                break

        assert found_accent, "La imagen debería contener el color de acento #5b8aff"

    def test_generate_image_has_dark_background(self, sample_api_data):
        """La imagen tiene fondo oscuro."""
        result = generate_image_sync(sample_api_data)
        img = Image.open(result)
        img = img.convert("RGB")

        # Obtener algunos píxeles de las esquinas (deberían ser oscuros)
        pixels = [
            img.getpixel((10, 10)),
            img.getpixel((img.width - 10, 10)),
            img.getpixel((10, img.height - 10)),
            img.getpixel((img.width - 10, img.height - 10)),
        ]

        # Verificar que los píxeles son oscuros (suma RGB < 100)
        for pixel in pixels:
            assert sum(pixel) < 100, f"Pixel de esquina demasiado claro: {pixel}"


class TestImageContent:
    """Tests para contenido de la imagen."""

    def test_image_contains_eltoque_data(self, sample_api_data):
        """La imagen contiene datos de ElToque."""
        result = generate_image_sync(sample_api_data)
        img = Image.open(result)

        # La imagen debería ser más alta si tiene más datos
        # (esto es una verificación indirecta del contenido)
        assert img.height > 400  # Con todos los bloques, debería ser más alta

    def test_image_with_empty_data(self):
        """Generar imagen con datos vacíos."""
        empty_data = {
            "eltoque": {},
            "cadeca": {},
            "bcc": {},
            "updated_at": "2026-03-22T10:00:00Z",
            "sources": [],
        }

        result = generate_image_sync(empty_data)

        assert result is not None
        img = Image.open(result)
        assert img.format == "PNG"
        assert img.height >= 400  # Altura mínima


class TestErrorHandling:
    """Tests para manejo de errores."""

    def test_generate_image_with_none_data(self):
        """Manejo de datos None."""
        result = generate_image_sync(None)
        assert result is None

    def test_generate_image_with_invalid_data(self):
        """Manejo de datos inválidos."""
        invalid_data = {"invalid": "data"}

        # No debería lanzar excepción, debería retornar None o imagen básica
        result = generate_image_sync(invalid_data)

        # Puede retornar None o una imagen básica
        if result is not None:
            img = Image.open(result)
            assert img.format == "PNG"
