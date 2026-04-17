"""Daily image sender service using APScheduler."""

import asyncio
import httpx
import logging
import time
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InputMediaPhoto, InputMediaDocument
from telegram.ext import Application

from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
API_URL = settings.tasalo_api_url

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def send_daily_images_job(application: Application):
    """
    Job diario que envía imágenes a usuarios con alertas activas.
    Se ejecuta a las 8:15 AM hora Cuba (UTC-4 = 12:15 UTC).
    """
    job_start = time.time()
    today_date = datetime.utcnow().date()
    logger.info("📸 Daily image dispatch job started at %s UTC", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

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
            logger.error("❌ Timeout fetching active alerts (10s limit)")
            return
        except Exception:
            logger.error("❌ Failed to fetch active alerts from API", exc_info=True)
            return

        if not data.get("ok"):
            logger.error("❌ API returned error: %s", data.get("error"))
            return

        alerts = data.get("data", [])
        logger.info("📋 Found %d active alerts to process", len(alerts))

        if not alerts:
            logger.info("ℹ️ No active alerts found, skipping")
            return

        # 2. Obtener imagen actual con retry y validación de fecha
        img_data = None
        for attempt in range(3):
            logger.info("🔍 Intentando obtener imagen del día (intento %d/3)", attempt + 1)
            try:
                async with httpx.AsyncClient() as client:
                    img_response = await client.get(
                        f"{API_URL}/api/v1/images/eltoque/latest",
                        timeout=10.0
                    )
                    img_data = img_response.json()
            except httpx.TimeoutException:
                logger.warning("⏱️ Timeout al obtener imagen (intento %d/3)", attempt + 1)
                if attempt < 2:
                    logger.info("⏳ Esperando 5 minutos antes del próximo intento...")
                    await asyncio.sleep(300)
                continue
            except Exception:
                logger.warning("⚠️ Error obteniendo imagen (intento %d/3)", attempt + 1, exc_info=True)
                if attempt < 2:
                    logger.info("⏳ Esperando 5 minutos antes del próximo intento...")
                    await asyncio.sleep(300)
                continue

            if not img_data.get("ok"):
                logger.warning("⚠️ API devolvió error en intento %d: %s", attempt + 1, img_data.get("error"))
                if attempt < 2:
                    logger.info("⏳ Esperando 5 minutos antes del próximo intento...")
                    await asyncio.sleep(300)
                continue

            # Verificar que la imagen sea del día actual
            image_date_str = img_data["data"]["date"]
            image_date = datetime.strptime(image_date_str, "%Y-%m-%d").date()
            
            if image_date == today_date:
                logger.info("✅ Imagen del día %s obtenida correctamente", today_date.strftime("%d/%m/%Y"))
                break
            else:
                logger.warning("⚠️ Imagen recibida es del día anterior (%s), no es la actual", image_date_str)
                if attempt < 2:
                    logger.info("⏳ Esperando 5 minutos antes del próximo intento...")
                    await asyncio.sleep(300)
                else:
                    logger.warning("⚠️ Máximo de intentos alcanzado, se usará imagen del día anterior como último recurso")

        if not img_data or not img_data.get("ok"):
            logger.error("❌ No se pudo obtener la imagen después de 3 intentos, abortando job")
            return

        image_path = img_data["data"]["image_path"]
        logger.debug("📁 Image path: %s", image_path)

        # 3. Para cada alerta, enviar imagen
        sent_count = 0
        fail_count = 0

        for alert in alerts:
            user_id = alert["user_id"]
            alert_id = alert.get("id", "unknown")
            format_type = alert["format_type"]

            logger.info("📤 Processing alert %s for user %d (format=%s)", alert_id, user_id, format_type)
            send_start = time.time()

            try:

                # 4. Construir caption
                caption = (
                    "🇨🇺 *Tasa Diaria El Toque*\n"
                    f"📅 {datetime.now().strftime('%d/%m/%Y')} · {datetime.now().strftime('%H:%M')}\n\n"
                    "Esta es la tasa diaria de El Toque."
                )

                # 5. Enviar imagen usando application.bot
                send_msg_start = time.time()
                try:
                    with open(image_path, "rb") as f:
                        if format_type == "photo":
                            await application.bot.send_photo(
                                chat_id=user_id,
                                photo=f,
                                caption=caption,
                                parse_mode="Markdown"
                            )
                        else:  # document
                            await application.bot.send_document(
                                chat_id=user_id,
                                document=f,
                                caption=caption,
                                parse_mode="Markdown"
                            )
                    send_msg_ms = (time.time() - send_msg_start) * 1000
                    logger.info("📨 Image sent to user %d via Telegram (%.0fms)", user_id, send_msg_ms)
                except httpx.TimeoutException:
                    logger.error("❌ Timeout sending image to user %d (10s limit)", user_id)
                    fail_count += 1
                    continue
                except Exception:
                    logger.error("❌ Telegram send failed for user %d (alert_id=%s)", user_id, alert_id, exc_info=True)
                    fail_count += 1
                    continue

                sent_count += 1
                send_duration_ms = (time.time() - send_start) * 1000
                logger.info("✅ Image sent to user %d (alert_id=%s, total=%.0fms)", user_id, alert_id, send_duration_ms)

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


def start_daily_dispatcher(application: Application) -> None:
    """
    Iniciar el dispatcher diario.

    Args:
        application: La aplicación de Telegram (para acceder al bot)
    """
    # 8:15 AM hora Cuba = 12:15 UTC (Cuba es UTC-4)
    scheduler.add_job(
        send_daily_images_job,
        trigger=CronTrigger(hour=12, minute=15, timezone="UTC"),
        id="daily_image_alert",
        name="Daily Image Alert - 8:15 AM Cuba",
        args=[application],
        replace_existing=True
    )

    scheduler.start()
    logger.info("✅ Daily image dispatcher started (8:15 AM Cuba / 12:15 UTC)")


def stop_daily_dispatcher() -> None:
    """Detener el dispatcher."""
    scheduler.shutdown()
    logger.info("⏹️ Daily image dispatcher stopped")
