"""Gestor de anuncios del lado del bot (taso-bot).

Consume el catálogo público de taso-api (GET /api/v1/ads/active), lo cachea
en memoria (reutilizando el SimpleCache compartido de src/cache.py, el mismo
mecanismo que ya usa /spl) y arma el bloque de texto a inyectar en los
mensajes aprobados en docs/plans/2026-07-04-sistema-anuncios.md.

Usado por los 10 puntos de inyección aprobados: /tasalo, /toque, /bcc, /cadeca,
/fuel (+ sus respectivos refresh), /p, /y, /ta, /graf (caption), /mk y /qp,
además de la notificación de price_alert_checker.py.

(El stub legacy `src/utils/ads_manager.py` que usaban ta.py/trading.py fue
eliminado — ya no queda ninguna referencia a él en el proyecto.)
"""

import logging
import random
from typing import Any, Dict, List, Optional

from src.cache import cache
from src.config import settings
from src.formatters import SEPARATOR_THICK

logger = logging.getLogger(__name__)

_CACHE_KEY = "ads:pool"
_CACHE_TTL_SECONDS = 600  # 10 minutos, igual criterio que el cache de /spl

# Último anuncio mostrado (proceso completo, no por usuario) para evitar
# repetir el mismo dos veces seguidas cuando hay ≥2 anuncios activos.
_last_shown_id: Optional[int] = None


def _escape_ad_text(text: str) -> str:
    """Sanea el texto de un anuncio para que nunca rompa un mensaje Markdown.

    Reemplaza los caracteres especiales de Markdown por equivalentes
    visualmente neutros (mismo criterio que usaba el _clean_markdown del
    bot legacy), en vez de intentar escaparlos: más simple y a prueba de
    errores para un campo de texto libre escrito por un admin.
    """
    if not text:
        return ""
    return (
        text.replace("_", " ")
        .replace("*", " ")
        .replace("`", "'")
        .replace("[", "(")
        .replace("]", ")")
    )


async def _get_ad_pool(api_client) -> List[Dict[str, Any]]:
    """Obtiene la lista de anuncios activos, usando el cache compartido."""
    pool = cache.get(_CACHE_KEY, ttl=_CACHE_TTL_SECONDS)
    if pool is not None:
        return pool

    pool = await api_client.get_active_ads()
    cache.set(_CACHE_KEY, pool)
    return pool


def _pick_ad(pool: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Elige un anuncio ponderado por 'weight', evitando repetir el último."""
    global _last_shown_id
    if not pool:
        return None

    candidates = pool
    if len(pool) > 1 and _last_shown_id is not None:
        filtered = [ad for ad in pool if ad.get("id") != _last_shown_id]
        if filtered:
            candidates = filtered

    weights = [max(1, ad.get("weight", 1)) for ad in candidates]
    chosen = random.choices(candidates, weights=weights, k=1)[0]
    _last_shown_id = chosen.get("id")
    return chosen


def format_ad_block(ad: Dict[str, Any], markdown: bool = True) -> str:
    """Formatea el bloque de anuncio, con la etiqueta correcta según is_sponsored.

    Reusa el separador estándar de formatters.py para no introducir un
    estilo visual distinto al del resto del mensaje.

    Args:
        ad: dict del anuncio ({id, text, is_sponsored, ...})
        markdown: si False, omite las negritas (`*...*`) porque el mensaje
            anfitrión se envía con parse_mode=None (ej. /tasalo con
            entidades DATE_TIME de Bot API 9.5) y los asteriscos se
            mostrarían literalmente en vez de resaltar el texto.
    """
    text = _escape_ad_text(ad.get("text", ""))
    if not text:
        return ""
    label = "Patrocinado" if ad.get("is_sponsored") else "Aviso"
    label_fmt = f"*{label}:*" if markdown else f"{label}:"
    return f"\n{SEPARATOR_THICK}\n📢 {label_fmt} {text}"


def invalidate_ad_cache() -> None:
    """Invalida el cache del pool de anuncios.

    Se llama tras cualquier cambio admin (add/edit/on/off/del/sponsor/weight)
    para que el próximo mensaje ya refleje el cambio, sin esperar el TTL
    de 10 minutos.
    """
    cache.invalidate(_CACHE_KEY)


async def get_ad_block(api_client, markdown: bool = True) -> str:
    """Punto de entrada principal: devuelve el bloque de anuncio listo para
    concatenar al final de un mensaje, o "" si no hay nada que mostrar.

    Nunca lanza excepción: cualquier fallo (red, caché, API caída) resulta
    en "" para que el mensaje anfitrión (precio, tasa, alerta) se envíe
    igual, sin el anuncio. Esa garantía es más importante que mostrar el ad.

    Args:
        api_client: instancia de TasaloApiClient
        markdown: pasar False si el mensaje anfitrión se envía con
            parse_mode=None (ver format_ad_block)
    """
    if not settings.ads_enabled:
        return ""
    try:
        pool = await _get_ad_pool(api_client)
        ad = _pick_ad(pool)
        if not ad:
            return ""
        return format_ad_block(ad, markdown=markdown)
    except Exception as e:
        logger.error("❌ Error obteniendo bloque de anuncio: %s", e)
        return ""


def safe_append(base_text: str, ad_block: str, hard_limit: int = 4096) -> str:
    """Pega el bloque de anuncio al mensaje solo si no excede el límite de
    Telegram. Si el mensaje base ya viene largo, el anuncio se omite sin
    lanzar error — el contenido real nunca se corta ni se rompe por un ad.

    Args:
        base_text: mensaje final ya armado (precio, tasa, alerta...)
        ad_block: bloque devuelto por get_ad_block() (puede ser "")
        hard_limit: límite de caracteres de Telegram (4096 para texto)

    Returns:
        base_text + ad_block si cabe, o base_text intacto si no.
    """
    if not ad_block:
        return base_text
    if len(base_text) + len(ad_block) > hard_limit:
        logger.debug("Anuncio omitido: mensaje base ya cerca del límite de Telegram")
        return base_text
    return base_text + ad_block
