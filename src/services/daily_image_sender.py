"""Daily image sender service using APScheduler."""

import httpx
import logging
import time
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InputMediaPhoto, InputMediaDocument
from telegram.ext import ContextTypes

from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
API_URL = settings.tasalo_api_url

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def send_daily_images_job(bot_context: ContextTypes.DEFAULT_TYPE):
    """
    Job diario que envía imágenes a usuarios con alertas activas.
    Se ejecuta a las 7:15 AM hora Cuba (UTC-4 = 11:15 UTC).
    """
    job_start = time.time()
    logger.info("📸 Daily image dispatch job started at %s", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))

    try:
        # 1. Obtener todas las alertas activas desde API
        alerts_fetch_start = time.time()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_URL}/api/v1/images/alerts?enabled=true",
                    timeout=10.0
                )
                data = response.json()
            alerts_fetch_ms = (time.time() - alerts_fetch_start) * 1000
            logger.info("📋 Alerts API response received (%.0fms)", alerts_fetch_ms)
        except httpx.TimeoutException:
            logger.error("❌ Timeout fetching active alerts (10s limit)", exc_info=True)
            return
        except Exception:
            logger.error("❌ Failed to fetch active alerts from API", exc_info=True)
            return

        if not data.get("ok"):
            logger.error("❌ API returned error: %s", data.get("error"))
            return

        alerts = data.get("data", [])
        logger.info("📋 Found %d active alerts to process", len(alerts))

        # 2. Para cada alerta, enviar imagen
        sent_count = 0
        fail_count = 0

        for alert in alerts:
            user_id = alert["user_id"]
            alert_id = alert.get("id", "unknown")
            format_type = alert["format_type"]

            logger.info("📤 Sending image to user %d (alert_id=%s, format=%s)", user_id, alert_id, format_type)
            send_start = time.time()

            try:
                # 3. Obtener última imagen
                img_fetch_start = time.time()
                try:
                    async with httpx.AsyncClient() as client:
                        img_response = await client.get(
                            f"{API_URL}/api/v1/images/eltoque/latest",
                            timeout=10.0
                        )
                        img_data = img_response.json()
                    img_fetch_ms = (time.time() - img_fetch_start) * 1000
                    logger.debug("🖼️ Image API response for user %d (%.0fms)", user_id, img_fetch_ms)
                except httpx.TimeoutException:
                    logger.error("❌ Timeout fetching image for user %d (10s limit)", user_id, exc_info=True)
                    fail_count += 1
                    continue
                except Exception:
                    logger.error("❌ Failed to fetch image for user %d", user_id, exc_info=True)
                    fail_count += 1
                    continue

                if not img_data.get("ok"):
                    logger.error("❌ Image API returned error for user %d: %s", user_id, img_data.get("error"))
                    fail_count += 1
                    continue

                image_path = img_data["data"]["image_path"]
                logger.debug("📁 Image path for user %d: %s", user_id, image_path)

                # 4. Construir caption
                caption = (
                    "🇨🇺 *Tasa Diaria El Toque*\n"
                    f"📅 {datetime.now().strftime('%d/%m/%Y')} · {datetime.now().strftime('%H:%M')}\n\n"
                    "Esta es la tasa diaria de El Toque."
                )

                # 5. Enviar imagen
                send_msg_start = time.time()
                try:
                    with open(image_path, "rb") as f:
                        if format_type == "photo":
                            await bot_context.bot.send_photo(
                                chat_id=user_id,
                                photo=f,
                                caption=caption,
                                parse_mode="Markdown"
                            )
                        else:  # document
                            await bot_context.bot.send_document(
                                chat_id=user_id,
                                document=f,
                                caption=caption,
                                parse_mode="Markdown"
                            )
                    send_msg_ms = (time.time() - send_msg_start) * 1000
                    logger.debug("📨 Telegram send completed for user %d (%.0fms)", user_id, send_msg_ms)
                except Exception:
                    logger.error("❌ Telegram send failed for user %d (alert_id=%s)", user_id, alert_id, exc_info=True)
                    fail_count += 1
                    continue

                sent_count += 1
                send_duration_ms = (time.time() - send_start) * 1000
                logger.info("✅ Image sent to user %d (%.0fms)", user_id, send_duration_ms)

            except Exception:
                logger.error("❌ Unexpected error processing alert for user %d (alert_id=%s)", user_id, alert_id, exc_info=True)
                fail_count += 1

        # Job completion summary
        total_duration_ms = (time.time() - job_start) * 1000
        logger.info(
            "✅ Daily image dispatch completed: %d sent, %d failed (%.0fms total)",
            sent_count, fail_count, total_duration_ms
        )

    except Exception:
        total_duration_ms = (time.time() - job_start) * 1000
        logger.error("❌ Daily image dispatch job failed after %.0fms", total_duration_ms, exc_info=True)


def start_daily_dispatcher(bot_context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Iniciar el dispatcher diario.

    Args:
        bot_context: Bot context for sending messages
    """
    # 7:15 AM hora Cuba = 11:15 UTC (Cuba es UTC-4)
    scheduler.add_job(
        send_daily_images_job,
        trigger=CronTrigger(hour=11, minute=15, timezone="UTC"),
        id="daily_image_alert",
        name="Daily Image Alert - 7:15 AM Cuba",
        args=[bot_context],
        replace_existing=True
    )

    scheduler.start()
    logger.info("✅ Daily image dispatcher started (7:15 AM Cuba / 11:15 UTC)")


def stop_daily_dispatcher() -> None:
    """Detener el dispatcher."""
    scheduler.shutdown()
    logger.info("⏹️ Daily image dispatcher stopped")
