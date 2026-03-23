"""Utilidades para manejar la foto de perfil del bot.

Módulo para obtener y usar la foto de perfil del bot de Telegram
como fondo para las imágenes de tasas.
"""

import logging
import os
import io
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
    try:
        # Crear directorio de caché
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, "bot_profile.jpg")
        
        # Obtener información del bot
        bot_info = await bot.get_me()
        
        # Obtener fotos de perfil
        photos = await bot.get_user_profile_photos(bot_info.id)
        
        if not photos or photos.total_count == 0:
            logger.warning("⚠️ El bot no tiene foto de perfil")
            return None
        
        # Obtener la foto de mayor resolución (última de la primera página)
        photo_file = photos.photos[0][-1]
        
        # Descargar foto
        file = await bot.get_file(photo_file.file_id)
        
        # Guardar localmente
        buffer = io.BytesIO()
        await file.download_to_custom(buffer)
        buffer.seek(0)
        
        with open(cache_path, "wb") as f:
            f.write(buffer.read())
        
        logger.info(f"✅ Foto de perfil descargada: {cache_path}")
        return cache_path
        
    except Exception as e:
        logger.error(f"❌ Error descargando foto de perfil: {e}", exc_info=True)
        return None


def get_cached_profile_photo(cache_dir: str = "data") -> Optional[str]:
    """Obtener foto de perfil cacheada si existe.
    
    Args:
        cache_dir: Directorio donde se cachea la imagen
        
    Returns:
        Ruta al archivo si existe, None en caso contrario
    """
    cache_path = os.path.join(cache_dir, "bot_profile.jpg")
    
    if os.path.exists(cache_path):
        logger.debug(f"✅ Foto de perfil cacheada encontrada: {cache_path}")
        return cache_path
    
    logger.debug("ℹ️ No hay foto de perfil cacheada")
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
    # Intentar caché primero
    cached = get_cached_profile_photo(cache_dir)
    if cached:
        return cached
    
    # Descargar si no está en caché
    return await fetch_bot_profile_photo(bot, cache_dir)


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
    try:
        from PIL import Image, ImageEnhance
        
        # Abrir imágenes
        template = Image.open(template_path).convert("RGBA")
        profile = Image.open(profile_photo_path).convert("RGBA")
        
        # Redimensionar foto de perfil
        profile = profile.resize(size, Image.Resampling.LANCZOS)
        
        # Aplicar opacidad
        if opacity < 1.0:
            alpha = profile.split()[3]
            alpha = alpha.point(lambda x: int(x * opacity))
            profile.putalpha(alpha)
        
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
        
        # Crear capa para marca de agua
        watermark = Image.new("RGBA", template.size, (0, 0, 0, 0))
        watermark.paste(profile, (px, py))
        
        # Combinar con template
        template = Image.alpha_composite(template, watermark)
        
        # Guardar
        template.save(output_path, "PNG", quality=95)
        
        logger.info(f"✅ Plantilla con marca de agua creada: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error creando plantilla con marca de agua: {e}", exc_info=True)
        return False
