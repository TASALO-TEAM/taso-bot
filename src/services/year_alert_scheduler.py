"""APScheduler-based year-progress alert dispatcher for taso-bot.

This scheduler polls the taso-api year subscriptions and dispatches
Telegram messages to each subscribed user at their configured hour.
"""

import asyncio
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import get_settings
from src.api_client import TasaloApiClient

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: AsyncIOScheduler | None = None


def create_year_scheduler(application) -> AsyncIOScheduler:
    """Create and return the year alert scheduler.

    Args:
        application: python-telegram-bot Application instance
                     (used to access bot via application.bot)

    Returns:
        Configured AsyncIOScheduler
    """
    global _scheduler
    scheduler = AsyncIOScheduler()
    _scheduler = scheduler
    app_ref = application
    settings = get_settings()

    async def year_alert_job():
        """Check subscriptions and send alerts to users whose hour matches now (UTC)."""
        api_client = TasaloApiClient(
            api_url=settings.tasalo_api_url,
            timeout=settings.api_timeout_seconds,
        )

        now = datetime.now(timezone.utc)
        current_hour = now.hour

        try:
            # Fetch all subscriptions (admin endpoint)
            subs_data = await api_client.admin_list_year_subscriptions()
            if not subs_data or not subs_data.get("ok"):
                return

            subs = subs_data.get("data", [])
            if not subs:
                return

            # Filter: hour matches current UTC hour
            matched = [s for s in subs if s.get("hour") == current_hour]
            if not matched:
                return

            # Fetch progress + quote once
            state_data = await api_client.get_year_state()
            if not state_data:
                return

            progress = state_data.get("progress", {})
            quote = state_data.get("quote", {})
            percent = progress.get("percent", 0.0)
            year = progress.get("year", now.year)
            bar = "▓" * int(20 * percent // 100) + "░" * (20 - int(20 * percent // 100))
            status_mood = (
                "🍀 Recién estamos empezando..." if percent < 2 else
                "🌱 Arrancando motores..." if percent < 10 else
                "🏃‍♂️ Aún hay tiempo de cumplir propósitos." if percent < 50 else
                "🔥 ¡Se nos va el año!" if percent < 80 else
                "🏁 Recta final, ¡agárrate!"
            )
            quote_text = quote.get("quote", "⏳ El tiempo vuela, pero tú eres el piloto.")
            days_left = progress.get("days_left", 0)
            date_str = progress.get("date_str", now.strftime("%d/%m/%Y"))

            msg = (
                f"🗓 *ESTADO DEL AÑO {year}*\n"
                f"•••\n"
                f"📆 *Fecha:* {date_str}\n"
                f"⏳ *Progreso:* `{percent:.2f}%`\n"
                f"📊 `{bar}`\n\n"
                f"🔚 Faltan *{days_left} días* para {year + 1}.\n"
                f"💭 _{status_mood}_\n"
                f"•••\n"
                f"💡 *Frase Del Día:*\n"
                f'"{quote_text}"'
            )

            for sub in matched:
                uid = sub.get("user_id")
                if not uid:
                    continue
                try:
                    await app_ref.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
                    logger.info("📨 Year alert sent to user %s", uid)
                except Exception as e:
                    logger.error("❌ Failed to send year alert to %s: %s", uid, e)

        except Exception:
            logger.exception("❌ Year alert job failed")

    # Run at :00 every UTC hour
    trigger = CronTrigger(minute="0", timezone="UTC")

    scheduler.add_job(
        year_alert_job,
        trigger=trigger,
        id="year_daily_alert",
        name="Year daily progress alert",
        replace_existing=True,
        misfire_grace_time=300,
    )

    print("✅ [Scheduler] Year daily alert job added (runs at :00 UTC every hour)")
    return scheduler


def start_year_scheduler(application) -> AsyncIOScheduler:
    """Create, configure, and start the year alert scheduler."""
    scheduler = create_year_scheduler(application)
    scheduler.start()
    print("✅ [Scheduler] Year alert scheduler started")
    return scheduler


def stop_year_scheduler() -> None:
    """Stop the year alert scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        print("🛑 [Scheduler] Year alert scheduler stopped")
        _scheduler = None
