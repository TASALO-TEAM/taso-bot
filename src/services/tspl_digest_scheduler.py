"""APScheduler job que genera 1x/dia el digest de noticias curado por Groq
para el comando /tspl.

Sigue el mismo patron que year_alert_scheduler.py: un AsyncIOScheduler
propio, arrancado/detenido desde main.py (post_init/post_shutdown).

A diferencia del scheduler de /y, este job no envia mensajes a usuarios:
solo genera el digest y lo deja en cache (src/cache.py, key "tspl_digest")
para que /tspl lo lea sin tener que llamar a Groq en cada invocacion.
"""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.newsdata_client import get_newsdata_client
from src.core.ai_logic import get_groq_tspl_digest
from src.handlers.p import get_crypto_client
from src.cache import cache

logger = logging.getLogger(__name__)

TSPL_DIGEST_CACHE_KEY = "tspl_digest"
_MIN_ARTICLES = 4
CUBA_TZ = ZoneInfo("America/Havana")

_scheduler: AsyncIOScheduler | None = None


def _momento_dia_cuba() -> str:
    """Bucket del momento del dia en hora de Cuba, para que el "lede" no
    tenga que adivinarlo (evita que Groq escriba "esta noche" cuando en
    Cuba son las 7 de la mañana, por ejemplo)."""
    hora = datetime.now(CUBA_TZ).hour
    if 5 <= hora < 12:
        return "esta mañana"
    if 12 <= hora < 19:
        return "esta tarde"
    return "esta noche"


async def _fetch_tspl_market_context() -> dict | None:
    """Junta Fear & Greed + precio de BTC en paralelo para anclar la
    apertura del "lede" a cifras reales en vez de dejar que Groq las
    invente. Reusa el mismo cliente singleton que /p
    (src.handlers.p.get_crypto_client) — no agrega ninguna llamada nueva
    a ninguna API que el bot no use ya.

    Si una de las dos consultas falla, se sigue con lo que si respondio
    (el prompt sabe omitir lo que falte); si ambas fallan retorna None.
    """
    client = get_crypto_client()
    fng_result, btc_result = await asyncio.gather(
        client.get_fear_greed(),
        client.get_crypto_data("BTC"),
        return_exceptions=True,
    )

    fear_greed = None if isinstance(fng_result, Exception) else fng_result
    btc_data = None if isinstance(btc_result, Exception) else btc_result

    if not fear_greed and not btc_data:
        logger.warning("⚠️ Digest /tspl: no se pudo obtener Fear & Greed ni precio BTC")
        return None

    return {
        "fng_value": (fear_greed or {}).get("value"),
        "fng_classification": (fear_greed or {}).get("classification"),
        "btc_price": (btc_data or {}).get("price"),
        "btc_change_24h": (btc_data or {}).get("percent_change_24h"),
        "momento_dia": _momento_dia_cuba(),
    }


def _dedup_by_title(articles: list[dict]) -> list[dict]:
    """Dedup simple por titulo normalizado (lowercase, sin espacios extra).

    No hace falta un criterio mas sofisticado (difflib, etc.) porque
    NewsData.io ya trae un campo "duplicate" propio en el crudo, pero el
    normalizador de newsdata_client.py no lo expone (no se necesita en
    /news) — este dedup es solo una red de seguridad extra antes de
    gastar tokens de Groq con articulos repetidos.
    """
    seen = set()
    result = []
    for art in articles:
        title = (art.get("title") or "").strip().lower()
        if title and title not in seen:
            seen.add(title)
            result.append(art)
    return result


async def generate_and_cache_tspl_digest() -> dict | None:
    """Obtiene noticias frescas de NewsData.io y genera el digest curado
    con Groq, guardandolo en cache para que /tspl lo lea directo.

    Usada tanto por el job diario (_generate_tspl_digest_job) como por
    src/handlers/tspl.py cuando el cache esta vacio/expirado y hace falta
    generarlo bajo demanda (primer uso tras un restart del bot, o si el
    usuario pregunta antes de que corra el cron de las 11:00 UTC).

    Returns:
        El digest generado (mismo dict que devuelve get_groq_tspl_digest),
        o None si no se pudo generar (sin articulos o Groq fallo). En ese
        caso el cache anterior (si existe) se deja intacto.
    """
    client = get_newsdata_client()

    try:
        articles = await client.get_crypto_news(language="es", limit=8)

        if not articles or len(articles) < _MIN_ARTICLES:
            logger.info(
                "📰 Digest /tspl: cobertura en español insuficiente (%d articulos), reintentando en inglés",
                len(articles or []),
            )
            articles_en = await client.get_crypto_news(language="en", limit=8)
            if articles_en:
                articles = _dedup_by_title((articles or []) + articles_en)

        if not articles:
            logger.warning("⚠️ Digest /tspl: sin articulos disponibles, no se genera digest hoy")
            return None

        articles = _dedup_by_title(articles)

        market_data = await _fetch_tspl_market_context()

        digest = await get_groq_tspl_digest(articles, market_data)
        if digest is None:
            logger.warning("⚠️ Digest /tspl: Groq no devolvio un digest valido, se conserva el cache anterior (si existe)")
            return None

        cache.set(TSPL_DIGEST_CACHE_KEY, digest)
        logger.info("✅ Digest /tspl generado y cacheado (%d items)", len(digest.get("items", [])))
        return digest

    except Exception:
        logger.exception("❌ Error generando el digest diario de /tspl")
        return None


async def _generate_tspl_digest_job() -> None:
    """Wrapper del job de APScheduler — ignora el valor de retorno, ya que
    generate_and_cache_tspl_digest() ya deja el resultado en cache."""
    await generate_and_cache_tspl_digest()


def create_tspl_digest_scheduler(application) -> AsyncIOScheduler:
    """Crea y retorna el scheduler del digest de /tspl.

    Args:
        application: instancia de Application de python-telegram-bot
            (no se usa directamente en el job, se recibe por consistencia
            con el resto de schedulers del proyecto).

    Returns:
        AsyncIOScheduler configurado (sin arrancar).
    """
    global _scheduler
    scheduler = AsyncIOScheduler()
    _scheduler = scheduler

    # 11:00 UTC ~= 7:00 AM Cuba (UTC-4/-5 segun horario de verano en EE.UU.,
    # Cuba no cambia de horario desde 2024) — mismo horario que el
    # dispatcher de imagenes diarias (start_daily_dispatcher).
    trigger = CronTrigger(hour="11", minute="0", timezone="UTC")

    scheduler.add_job(
        _generate_tspl_digest_job,
        trigger=trigger,
        id="tspl_daily_digest",
        name="TASALO Spotlight daily news digest",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    logger.info("✅ [Scheduler] /tspl daily digest job added (runs at 11:00 UTC)")
    return scheduler


def start_tspl_digest_scheduler(application) -> AsyncIOScheduler:
    """Crea, configura y arranca el scheduler del digest de /tspl."""
    scheduler = create_tspl_digest_scheduler(application)
    scheduler.start()
    logger.info("✅ [Scheduler] /tspl digest scheduler started")
    return scheduler


def stop_tspl_digest_scheduler() -> None:
    """Detiene el scheduler del digest de /tspl."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("🛑 [Scheduler] /tspl digest scheduler stopped")
        _scheduler = None
