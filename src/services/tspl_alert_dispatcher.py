"""APScheduler-based /tspl subscription dispatcher for taso-bot.

Corre cada hora en punto (UTC) y despacha el TASALO Spotlight completo a
todos los usuarios suscritos a esa hora — hasta 2 horarios por usuario
(ver docs/plans/2026-07-24-tspl-suscripcion-horarios.md).

Mismo patrón que year_alert_scheduler.py, pero:
- Filtra por igualdad de hora contra una lista con potencialmente 2 filas
  por usuario (no 1), así que un mismo user_id puede aparecer 2 veces en
  la lista total y matchear en 2 horas distintas del día.
- El mensaje se arma UNA sola vez por hora despachada (mismo digest +
  snapshot de mercado para todos los que matchean esa hora), reusando
  los helpers de src.handlers.tspl en vez de duplicar la lógica.
"""

import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import get_settings
from src.api_client import TasaloApiClient

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def create_tspl_alert_dispatcher(application) -> AsyncIOScheduler:
    """Crea y retorna el dispatcher de suscripciones de /tspl.

    Args:
        application: instancia de Application de python-telegram-bot
            (se usa application.bot para enviar los mensajes).

    Returns:
        AsyncIOScheduler configurado (sin arrancar).
    """
    global _scheduler
    scheduler = AsyncIOScheduler()
    _scheduler = scheduler
    app_ref = application
    settings = get_settings()

    async def tspl_alert_job():
        """Revisa suscripciones y despacha /tspl a quien matchee la hora actual (UTC)."""
        # Import diferido para evitar import circular (tspl.py importa
        # servicios que a su vez podrían tocar este módulo en el futuro).
        from src.handlers.tspl import (
            _get_or_build_digest,
            _get_or_build_market_snapshot,
            _build_message,
        )

        api_client = TasaloApiClient(
            api_url=settings.tasalo_api_url,
            admin_key=settings.tasalo_admin_key,
            timeout=settings.api_timeout_seconds,
        )

        current_hour = datetime.now(timezone.utc).hour

        try:
            subs = await api_client.admin_list_tspl_subscriptions()
            if not subs:
                return

            matched = [s for s in subs if s.get("hour") == current_hour]
            if not matched:
                return

            digest = await _get_or_build_digest()
            snapshot = await _get_or_build_market_snapshot()
            mensaje = _build_message(digest, snapshot)

            for sub in matched:
                uid = sub.get("user_id")
                if not uid:
                    continue
                try:
                    await app_ref.bot.send_message(
                        chat_id=uid, text=mensaje, parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                    logger.info("📨 /tspl alert sent to user %s (hour=%d)", uid, current_hour)
                except Exception as e:
                    logger.error("❌ Failed to send /tspl alert to %s: %s", uid, e)

        except Exception:
            logger.exception("❌ /tspl alert job failed")

    trigger = CronTrigger(minute="0", timezone="UTC")

    scheduler.add_job(
        tspl_alert_job,
        trigger=trigger,
        id="tspl_hourly_dispatch",
        name="TASALO Spotlight subscription dispatch",
        replace_existing=True,
        misfire_grace_time=300,
    )

    logger.info("✅ [Scheduler] /tspl subscription dispatcher added (runs at :00 UTC every hour)")
    return scheduler


def start_tspl_alert_dispatcher(application) -> AsyncIOScheduler:
    """Crea, configura y arranca el dispatcher de suscripciones de /tspl."""
    scheduler = create_tspl_alert_dispatcher(application)
    scheduler.start()
    logger.info("✅ [Scheduler] /tspl subscription dispatcher started")
    return scheduler


def stop_tspl_alert_dispatcher() -> None:
    """Detiene el dispatcher de suscripciones de /tspl."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("🛑 [Scheduler] /tspl subscription dispatcher stopped")
        _scheduler = None
