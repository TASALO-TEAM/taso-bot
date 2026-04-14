"""Utilidades para manejar la foto de perfil del bot.

Módulo para obtener y usar la foto de perfil del bot de Telegram
como fondo para las imágenes de tasas.
"""

import logging
import os
import io
import time
from typing import Optional
from telegram import Bot

logger = logging.getLogger(__name__)


async def fetch_bot_profile_photo(bot: Bot, cache_dir: str = "data") -> Optional[str]:
    """Obtener la foto de perfil del bot y guardarla localmente.

    Args:
        bot: Instancia del bot de Telegram
        cache_dir: Directorio para cachear la imagen

    Returns:
        Ruta al archivo guardado, o None si falla
    """
    operation_start = time.time()
    logger.info("📸 Fetching bot profile photo (cache_dir=%s)...", cache_dir)

    try:
        # Crear directorio de caché
        mkdir_start = time.time()
        os.makedirs(cache_dir, exist_ok=True)
        mkdir_ms = (time.time() - mkdir_start) * 1000
        cache_path = os.path.join(cache_dir, "bot_profile.jpg")
        logger.debug("📁 Cache directory ready: %s (%.0fms)", cache_dir, mkdir_ms)

        # Obtener información del bot
        bot_info_start = time.time()
        bot_info = await bot.get_me()
        bot_info_ms = (time.time() - bot_info_start) * 1000
        logger.debug("🤖 Bot info fetched: @%s (%.0fms)", bot_info.username, bot_info_ms)

        # Obtener fotos de perfil
        photos_start = time.time()
        photos = await bot.get_user_profile_photos(bot_info.id)
        photos_ms = (time.time() - photos_start) * 1000
        logger.debug("🖼️ Profile photos fetched: total_count=%d (%.0fms)", photos.total_count, photos_ms)

        if not photos or photos.total_count == 0:
            logger.warning("⚠️ Bot has no profile photo set (user_id=%s)", bot_info.id)
            return None

        # Obtener la foto de mayor resolución (última de la primera página)
        photo_file = photos.photos[0][-1]
        logger.debug("📐 Selected photo: file_id=%s, file_size=%s, dimensions=%dx%d",
                      photo_file.file_id,
                      photo_file.file_size or "unknown",
                      photo_file.width or 0,
                      photo_file.height or 0)

        # Descargar foto
        download_start = time.time()
        file = await bot.get_file(photo_file.file_id)
        file_bytes = await file.download_as_bytearray()
        download_ms = (time.time() - download_start) * 1000
        logger.debug("📥 Photo downloaded: %d bytes (%.0fms)", len(file_bytes), download_ms)

        # Guardar localmente
        write_start = time.time()
        buffer = io.BytesIO(file_bytes)
        with open(cache_path, "wb") as f:
            f.write(buffer.getvalue())
        file_size = os.path.getsize(cache_path)
        write_ms = (time.time() - write_start) * 1000
        logger.debug("💾 Photo saved to disk: %s (%d bytes, %.0fms)", cache_path, file_size, write_ms)

        total_ms = (time.time() - operation_start) * 1000
        logger.info("✅ Profile photo downloaded: %s (total %.0fms)", cache_path, total_ms)
        return cache_path

    except Exception as e:
        total_ms = (time.time() - operation_start) * 1000
        logger.error(
            "❌ Error downloading profile photo after %.0fms: %s (cache_dir=%s)",
            total_ms, e, cache_dir, exc_info=True
        )
        return None


def get_cached_profile_photo(cache_dir: str = "data") -> Optional[str]:
    """Obtener foto de perfil cacheada si existe.

    Args:
        cache_dir: Directorio donde se cachea la imagen

    Returns:
        Ruta al archivo si existe, None en caso contrario
    """
    cache_path = os.path.join(cache_dir, "bot_profile.jpg")
    logger.debug("🔍 Checking profile photo cache: %s", cache_path)

    if os.path.exists(cache_path):
        try:
            file_size = os.path.getsize(cache_path)
            modified = os.path.getmtime(cache_path)
            logger.info("📸 Profile photo cache HIT: %s (%d bytes, modified %s)",
                        cache_path, file_size, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(modified)))
        except OSError as e:
            logger.warning("⚠️ Could not stat cached photo %s: %s", cache_path, e)
            logger.info("📸 Profile photo cache HIT: %s", cache_path)
        return cache_path

    logger.info("📸 Profile photo cache MISS: %s does not exist", cache_path)
    return None


async def ensure_bot_profile_photo(bot: Bot, cache_dir: str = "data") -> Optional[str]:
    """Asegurar que existe una foto de perfil del bot.

    Intenta obtenerla de caché primero, si no existe la descarga.

    Args:
        bot: Instancia del bot de Telegram
        cache_dir: Directorio para cachear la imagen

    Returns:
        Ruta al archivo guardado, o None si falla
    """
    operation_start = time.time()
    logger.info("📸 Ensuring bot profile photo available...")

    # Intentar caché primero
    cache_check_start = time.time()
    cached = get_cached_profile_photo(cache_dir)
    cache_check_ms = (time.time() - cache_check_start) * 1000

    if cached:
        logger.debug("✅ Using cached profile photo: %s (cache check %.0fms)", cached, cache_check_ms)
        return cached

    logger.info("📥 Cache miss, downloading profile photo... (cache check %.0fms)", cache_check_ms)

    # Descargar si no está en caché
    result = await fetch_bot_profile_photo(bot, cache_dir)
    total_ms = (time.time() - operation_start) * 1000

    if result:
        logger.info("✅ Profile photo ensured: %s (total %.0fms)", result, total_ms)
    else:
        logger.error("❌ Failed to ensure profile photo after %.0fms", total_ms)

    return result


def create_template_with_profile(
    template_path: str,
    profile_photo_path: str,
    output_path: str,
    position: str = "center",
    size: tuple = (200, 200),
    opacity: float = 0.15,
) -> bool:
    """Crear plantilla con foto de perfil como marca de agua.

    Args:
        template_path: Ruta a la plantilla base
        profile_photo_path: Ruta a la foto de perfil
        output_path: Ruta para guardar la plantilla resultante
        position: Posición de la foto ("center", "topleft", "topright", "bottomleft", "bottomright")
        size: Tamaño de la foto (ancho, alto)
        opacity: Opacidad de la marca de agua (0.0 a 1.0)

    Returns:
        True si éxito, False si error
    """
    operation_start = time.time()
    logger.info(
        "🎨 Creating template with profile watermark: template=%s, profile=%s, output=%s",
        template_path, profile_photo_path, output_path
    )

    try:
        from PIL import Image, ImageEnhance

        # Validate inputs exist
        logger.debug("🔍 Validating input files exist...")
        if not os.path.exists(template_path):
            logger.error("❌ Template file not found: %s", template_path)
            return False
        if not os.path.exists(profile_photo_path):
            logger.error("❌ Profile photo not found: %s", profile_photo_path)
            return False

        template_size = os.path.getsize(template_path)
        profile_size = os.path.getsize(profile_photo_path)
        logger.debug("📁 Input files: template=%d bytes, profile=%d bytes", template_size, profile_size)

        # Abrir imágenes
        load_start = time.time()
        template = Image.open(template_path).convert("RGBA")
        profile = Image.open(profile_photo_path).convert("RGBA")
        load_ms = (time.time() - load_start) * 1000
        logger.debug("🖼️ Images loaded: template=%dx%d, profile=%dx%d (%.0fms)",
                      template.width, template.height, profile.width, profile.height, load_ms)

        # Redimensionar foto de perfil
        resize_start = time.time()
        profile = profile.resize(size, Image.Resampling.LANCZOS)
        resize_ms = (time.time() - resize_start) * 1000
        logger.debug("📐 Profile resized to %dx%d (%.0fms)", size[0], size[1], resize_ms)

        # Aplicar opacidad
        if opacity < 1.0:
            opacity_start = time.time()
            alpha = profile.split()[3]
            alpha = alpha.point(lambda x: int(x * opacity))
            profile.putalpha(alpha)
            opacity_ms = (time.time() - opacity_start) * 1000
            logger.debug("🔅 Opacity applied: %.2f (%.0fms)", opacity, opacity_ms)

        # Calcular posición
        W, H = template.size
        pw, ph = size

        if position == "center":
            px = (W - pw) // 2
            py = (H - ph) // 2
        elif position == "topleft":
            px, py = 20, 20
        elif position == "topright":
            px, py = W - pw - 20, 20
        elif position == "bottomleft":
            px, py = 20, H - ph - 20
        elif position == "bottomright":
            px, py = W - pw - 20, H - ph - 20
        else:
            px, py = (W - pw) // 2, (H - ph) // 2

        logger.debug("📍 Watermark position: %s at (%d, %d)", position, px, py)

        # Crear capa para marca de agua
        watermark_start = time.time()
        watermark = Image.new("RGBA", template.size, (0, 0, 0, 0))
        watermark.paste(profile, (px, py))
        watermark_ms = (time.time() - watermark_start) * 1000
        logger.debug("🎭 Watermark layer created (%.0fms)", watermark_ms)

        # Combinar con template
        composite_start = time.time()
        template = Image.alpha_composite(template, watermark)
        composite_ms = (time.time() - composite_start) * 1000
        logger.debug("🔀 Alpha composite complete (%.0fms)", composite_ms)

        # Guardar
        save_start = time.time()
        template.save(output_path, "PNG", quality=95)
        output_size = os.path.getsize(output_path)
        save_ms = (time.time() - save_start) * 1000
        logger.debug("💾 Template saved: %s (%d bytes, %.0fms)", output_path, output_size, save_ms)

        total_ms = (time.time() - operation_start) * 1000
        logger.info("✅ Template with watermark created: %s (total %.0fms)", output_path, total_ms)
        return True

    except ImportError as e:
        logger.error("❌ PIL/Pillow not available for template creation: %s", e, exc_info=True)
        return False
    except FileNotFoundError as e:
        logger.error("❌ File not found during template creation: %s", e, exc_info=True)
        return False
    except Exception as e:
        total_ms = (time.time() - operation_start) * 1000
        logger.error(
            "❌ Error creating template with watermark after %.0fms: %s (template=%s, profile=%s, output=%s)",
            total_ms, e, template_path, profile_photo_path, output_path, exc_info=True
        )
        return False
