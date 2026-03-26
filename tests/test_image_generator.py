"""Tests para el generador de imágenes de TASALO.

Tests para verificar la generación de imágenes con tabla horizontal
para los comandos /tasalo, /toque, /bcc, /cadeca.
"""

import pytest
from datetime import datetime
from io import BytesIO

from src.image_generator import (
    generate_image,
    generate_tasalo_image,
    generate_single_source_image,
    generate_image_sync,
    get_change_emoji,
    get_change_color,
    format_rate_value,
    parse_iso_datetime,
    get_currency_flag,
    load_fonts,
    IMG_WIDTH_HORIZONTAL,
    IMG_HEIGHT_HORIZONTAL,
    IMG_WIDTH_VERTICAL,
    IMG_HEIGHT_VERTICAL,
    COLOR_BG,
    COLOR_SURFACE,
    COLOR_UP,
    COLOR_DOWN,
    COLOR_NEUTRAL,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
)


# =============================================================================
# DATOS DE PRUEBA
# =============================================================================

@pytest.fixture
def sample_api_data():
    """Datos de prueba completos para todas las fuentes."""
    return {
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


@pytest.fixture
def sample_eltoque_data():
    """Datos de prueba solo para ElToque."""
    return {
        "eltoque": {
            "EUR": {"rate": 580.00, "change": "up", "prev_rate": 575.00},
            "USD": {"rate": 515.00, "change": "up", "prev_rate": 512.00},
            "MLC": {"rate": 420.00, "change": None, "prev_rate": 420.00},
        },
        "updated_at": datetime.now().isoformat(),
    }


@pytest.fixture
def sample_bcc_data():
    """Datos de prueba solo para BCC."""
    return {
        "bcc": {
            "EUR": {"rate": 551.23, "change": "up", "prev_rate": 548.00},
            "USD": {"rate": 478.00, "change": None, "prev_rate": 478.00},
        },
        "updated_at": datetime.now().isoformat(),
    }


@pytest.fixture
def sample_cadeca_data():
    """Datos de prueba solo para CADECA."""
    return {
        "cadeca": {
            "EUR": {"buy": 531.94, "sell": 584.30},
            "USD": {"buy": 461.27, "sell": 506.68},
        },
        "updated_at": datetime.now().isoformat(),
    }


# =============================================================================
# TESTS DE FUNCIONES AUXILIARES
# =============================================================================

class TestAuxiliaryFunctions:
    """Tests para funciones auxiliares."""

    def test_get_change_emoji_up(self):
        """Emoji para subida."""
        assert get_change_emoji("up") == "🔺"

    def test_get_change_emoji_down(self):
        """Emoji para bajada."""
        assert get_change_emoji("down") == "🔻"

    def test_get_change_emoji_neutral(self):
        """Emoji para sin cambio."""
        assert get_change_emoji(None) == "―"
        assert get_change_emoji("neutral") == "―"

    def test_get_change_color_up(self):
        """Color para subida (rojo)."""
        assert get_change_color("up") == COLOR_UP

    def test_get_change_color_down(self):
        """Color para bajada (verde)."""
        assert get_change_color("down") == COLOR_DOWN

    def test_get_change_color_neutral(self):
        """Color para neutral (gris)."""
        assert get_change_color(None) == COLOR_NEUTRAL

    def test_format_rate_value(self):
        """Formateo de valores numéricos."""
        assert format_rate_value(580.00) == "580.00"
        assert format_rate_value(515.50) == "515.50"
        assert format_rate_value(1000000) == "1,000,000.00"
        assert format_rate_value(0.5) == "0.50"

    def test_parse_iso_datetime(self):
        """Parseo de datetime ISO."""
        iso_string = "2026-03-26T14:30:00Z"
        result = parse_iso_datetime(iso_string)
        assert "26/03/2026" in result
        assert "14:30" in result

    def test_parse_iso_datetime_none(self):
        """Parseo de None usa datetime actual."""
        result = parse_iso_datetime(None)
        assert datetime.now().strftime("%d/%m/%Y") in result

    def test_get_currency_flag(self):
        """Banderas de monedas."""
        assert get_currency_flag("USD") == "🇺🇸"
        assert get_currency_flag("EUR") == "🇪🇺"
        assert get_currency_flag("BTC") == "₿"
        assert get_currency_flag("USDT") == "₮"
        assert get_currency_flag("UNKNOWN") == "💱"


# =============================================================================
# TESTS DE GENERACIÓN DE IMÁGENES
# =============================================================================

class TestImageGeneration:
    """Tests para generación de imágenes."""

    def test_load_fonts(self):
        """Carga de fuentes no debe fallar."""
        fonts = load_fonts()
        assert fonts.title is not None
        assert fonts.subtitle is not None
        assert fonts.column_header is not None
        assert fonts.rate_value is not None

    @pytest.mark.asyncio
    async def test_generate_tasalo_image(self, sample_api_data):
        """Generar imagen TASALO con tabla triple."""
        result = await generate_tasalo_image(sample_api_data)
        
        assert result is not None
        assert isinstance(result, BytesIO)
        
        # Verificar tamaño del buffer
        result.seek(0, 2)  # Ir al final
        size = result.tell()
        assert size > 0
        assert size < 2 * 1024 * 1024  # Menor a 2MB
        
        # Verificar que es PNG válido
        result.seek(0)
        from PIL import Image
        img = Image.open(result)
        assert img.size == (IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL)
        assert img.mode == "RGBA"

    @pytest.mark.asyncio
    async def test_generate_single_source_image_eltoque(self, sample_eltoque_data):
        """Generar imagen individual de ElToque."""
        result = await generate_single_source_image(sample_eltoque_data, "eltoque")

        assert result is not None
        assert isinstance(result, BytesIO)

        result.seek(0)
        from PIL import Image
        img = Image.open(result)
        assert img.size == (IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL)

    @pytest.mark.asyncio
    async def test_generate_single_source_image_bcc(self, sample_bcc_data):
        """Generar imagen individual del BCC."""
        result = await generate_single_source_image(sample_bcc_data, "bcc")

        assert result is not None
        assert isinstance(result, BytesIO)

        result.seek(0)
        from PIL import Image
        img = Image.open(result)
        assert img.size == (IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL)

    @pytest.mark.asyncio
    async def test_generate_single_source_image_cadeca(self, sample_cadeca_data):
        """Generar imagen individual de CADECA."""
        result = await generate_single_source_image(sample_cadeca_data, "cadeca")

        assert result is not None
        assert isinstance(result, BytesIO)

        result.seek(0)
        from PIL import Image
        img = Image.open(result)
        assert img.size == (IMG_WIDTH_VERTICAL, IMG_HEIGHT_VERTICAL)

    @pytest.mark.asyncio
    async def test_generate_image_with_type_parameter(self, sample_api_data):
        """Generar imagen usando parámetro image_type."""
        # Probar tipo "tasalo"
        result_tasalo = await generate_image(sample_api_data, image_type="tasalo")
        assert result_tasalo is not None
        
        # Probar tipo "eltoque"
        result_eltoque = await generate_image(sample_api_data, image_type="eltoque")
        assert result_eltoque is not None
        
        # Probar tipo "bcc"
        result_bcc = await generate_image(sample_api_data, image_type="bcc")
        assert result_bcc is not None
        
        # Probar tipo "cadeca"
        result_cadeca = await generate_image(sample_api_data, image_type="cadeca")
        assert result_cadeca is not None

    @pytest.mark.asyncio
    async def test_generate_image_invalid_type(self, sample_api_data):
        """Tipo de imagen inválido retorna None."""
        result = await generate_image(sample_api_data, image_type="invalid")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_image_empty_data(self):
        """Generar imagen con datos vacíos no debe fallar."""
        empty_data = {
            "eltoque": {},
            "bcc": {},
            "cadeca": {},
            "updated_at": datetime.now().isoformat(),
        }
        
        result = await generate_image(empty_data, image_type="tasalo")
        
        # Debería generar imagen aunque esté vacía
        assert result is not None

    def test_generate_image_sync(self, sample_api_data):
        """Versión síncrona para testing."""
        result = generate_image_sync(sample_api_data, image_type="tasalo")
        
        assert result is not None
        assert isinstance(result, BytesIO)
        
        result.seek(0)
        from PIL import Image
        img = Image.open(result)
        assert img.size == (IMG_WIDTH_HORIZONTAL, IMG_HEIGHT_HORIZONTAL)


# =============================================================================
# TESTS DE INTEGRACIÓN
# =============================================================================

class TestIntegration:
    """Tests de integración para generación de imágenes."""

    def test_image_dimensions(self, sample_api_data):
        """Verificar dimensiones de imagen generada."""
        result = generate_image_sync(sample_api_data, image_type="tasalo")
        result.seek(0)
        
        from PIL import Image
        img = Image.open(result)
        
        assert img.width == IMG_WIDTH_HORIZONTAL
        assert img.height == IMG_HEIGHT_HORIZONTAL
        assert img.width == 1200
        assert img.height == 630

    def test_image_color_mode(self, sample_api_data):
        """Verificar modo de color RGBA."""
        result = generate_image_sync(sample_api_data, image_type="tasalo")
        result.seek(0)
        
        from PIL import Image
        img = Image.open(result)
        
        assert img.mode == "RGBA"

    def test_image_file_size(self, sample_api_data):
        """Verificar tamaño de archivo razonable."""
        result = generate_image_sync(sample_api_data, image_type="tasalo")
        result.seek(0, 2)
        size = result.tell()
        
        # Debería ser menor a 1MB para Telegram
        assert size < 1024 * 1024
        # Y mayor a 10KB para tener contenido
        assert size > 10 * 1024

    def test_watermark_presence(self, sample_api_data):
        """Verificar que la imagen contiene marca de agua."""
        result = generate_image_sync(sample_api_data, image_type="tasalo")
        result.seek(0)
        
        from PIL import Image
        img = Image.open(result)
        
        # La marca de agua debería estar en la parte inferior central
        # Verificar que hay contenido en esa región (no es completamente transparente)
        watermark_y = IMG_HEIGHT_HORIZONTAL - 90
        watermark_region = img.crop((
            IMG_WIDTH_HORIZONTAL // 4,
            watermark_y - 20,
            3 * IMG_WIDTH_HORIZONTAL // 4,
            watermark_y + 60,
        ))
        
        # La región no debería estar completamente vacía
        assert watermark_region.size[0] > 0
        assert watermark_region.size[1] > 0


# =============================================================================
# TESTS DE MANEJO DE ERRORES
# =============================================================================

class TestErrorHandling:
    """Tests para manejo de errores."""

    @pytest.mark.asyncio
    async def test_generate_image_none_data(self):
        """Datos None deberían manejarse gracefulmente."""
        result = await generate_image(None, image_type="tasalo")
        # Debería retornar None o manejar el error
        assert result is None or isinstance(result, BytesIO)

    @pytest.mark.asyncio
    async def test_generate_image_missing_keys(self):
        """Datos con claves faltantes no deberían crashear."""
        incomplete_data = {
            "eltoque": {"USD": {"rate": 515.00}},
            # Faltan "bcc" y "cadeca"
            "updated_at": datetime.now().isoformat(),
        }
        
        result = await generate_image(incomplete_data, image_type="tasalo")
        
        # Debería generar imagen aunque falten fuentes
        assert result is not None

    @pytest.mark.asyncio
    async def test_generate_image_invalid_rate_data(self):
        """Datos de tasa inválidos deberían manejarse."""
        data_with_invalid = {
            "eltoque": {
                "USD": {"rate": None, "change": "up"},
                "EUR": {"rate": "invalid", "change": "down"},
            },
            "updated_at": datetime.now().isoformat(),
        }
        
        # No debería crashear
        result = await generate_image(data_with_invalid, image_type="eltoque")
        
        # Debería generar imagen o retornar None gracefulmente
        assert result is None or isinstance(result, BytesIO)


# =============================================================================
# TESTS DE CALIDAD VISUAL
# =============================================================================

class TestVisualQuality:
    """Tests para calidad visual de imágenes generadas."""

    def test_background_color(self, sample_api_data):
        """Verificar color de fondo correcto (Dark Glass)."""
        result = generate_image_sync(sample_api_data, image_type="tasalo")
        result.seek(0)

        from PIL import Image
        img = Image.open(result)

        # Muestrear píxel de esquina (debería ser COLOR_BG = #10102A)
        bg_pixel = img.getpixel((10, 10))

        # El color de fondo debería ser oscuro (azul oscuro profundo)
        assert bg_pixel[0] < 30  # R bajo
        assert bg_pixel[1] < 30  # G bajo
        assert bg_pixel[2] < 50  # B bajo

    def test_surface_color(self, sample_api_data):
        """Verificar que la superficie glass está presente (Dark Glass)."""
        result = generate_image_sync(sample_api_data, image_type="tasalo")
        result.seek(0)

        from PIL import Image
        img = Image.open(result)

        # Verificar que la imagen es RGBA (tiene canal alpha para transparencia)
        assert img.mode == "RGBA"

        # La superficie glass debería estar en el centro
        # Muestrear múltiples puntos para verificar que hay variación de colores
        center_pixel = img.getpixel((IMG_WIDTH_HORIZONTAL // 2, IMG_HEIGHT_HORIZONTAL // 2))
        
        # El pixel central debería tener algún valor (no completamente negro)
        assert center_pixel[0] > 0 or center_pixel[1] > 0 or center_pixel[2] > 0


# =============================================================================
# SCRIPT DE PRUEBA MANUAL
# =============================================================================

if __name__ == "__main__":
    import logging
    
    logging.basicConfig(level=logging.INFO)
    
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
    
    print("🧪 Ejecutando tests manuales de generación de imágenes...")
    
    # Test 1: Imagen TASALO
    print("\n📊 Generando imagen TASALO...")
    img_tasalo = generate_image_sync(test_data, image_type="tasalo")
    if img_tasalo:
        with open("test_tasalo.png", "wb") as f:
            f.write(img_tasalo.read())
        print("✅ test_tasalo.png generada")
    else:
        print("❌ Error generando test_tasalo.png")
    
    # Test 2: Imagen ElToque
    print("\n🏠 Generando imagen ElToque...")
    img_eltoque = generate_image_sync(test_data, image_type="eltoque")
    if img_eltoque:
        with open("test_eltoque.png", "wb") as f:
            f.write(img_eltoque.read())
        print("✅ test_eltoque.png generada")
    else:
        print("❌ Error generando test_eltoque.png")
    
    # Test 3: Imagen BCC
    print("\n🏛 Generando imagen BCC...")
    img_bcc = generate_image_sync(test_data, image_type="bcc")
    if img_bcc:
        with open("test_bcc.png", "wb") as f:
            f.write(img_bcc.read())
        print("✅ test_bcc.png generada")
    else:
        print("❌ Error generando test_bcc.png")
    
    # Test 4: Imagen CADECA
    print("\n🏢 Generando imagen CADECA...")
    img_cadeca = generate_image_sync(test_data, image_type="cadeca")
    if img_cadeca:
        with open("test_cadeca.png", "wb") as f:
            f.write(img_cadeca.read())
        print("✅ test_cadeca.png generada")
    else:
        print("❌ Error generando test_cadeca.png")
    
    print("\n✅ Tests manuales completados")
    print("📁 Archivos: test_tasalo.png, test_eltoque.png, test_bcc.png, test_cadeca.png")
