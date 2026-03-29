"""Daily image sender service using APScheduler."""

import httpx
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InputMediaPhoto, InputMediaDocument
from telegram.ext import ContextTypes

from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
API_URL = settings.TASALO_API_URL

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def send_daily_images_job(bot_context: ContextTypes.DEFAULT_TYPE):
    """
    Job diario que envía imágenes a usuarios con alertas activas.
    Se ejecuta a las 7:15 AM hora Cuba (UTC-4 = 11:15 UTC).
    """
    logger.info("📸 Starting daily image alert job...")
    
    try:
        # 1. Obtener todas las alertas activas desde API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/api/v1/images/alerts?enabled=true",
                timeout=10.0
            )
            data = response.json()
        
        if not data.get("ok"):
            logger.error(f"Failed to get alerts: {data.get('error')}")
            return
        
        alerts = data.get("data", [])
        logger.info(f"📋 Found {len(alerts)} active alerts")
        
        # 2. Para cada alerta, enviar imagen
        sent_count = 0
        error_count = 0
        
        for alert in alerts:
            user_id = alert["user_id"]
            format_type = alert["format_type"]
            
            try:
                # 3. Obtener última imagen
                async with httpx.AsyncClient() as client:
                    img_response = await client.get(
                        f"{API_URL}/api/v1/images/eltoque/latest",
                        timeout=10.0
                    )
                    img_data = img_response.json()
                
                if not img_data.get("ok"):
                    logger.error(f"Failed to get image for user {user_id}")
                    error_count += 1
                    continue
                
                image_path = img_data["data"]["image_path"]
                
                # 4. Construir caption
                caption = (
                    "🇨🇺 *Tasa Diaria El Toque*\n"
                    f"📅 {datetime.now().strftime('%d/%m/%Y')} · {datetime.now().strftime('%H:%M')}\n\n"
                    "Esta es la tasa diaria de El Toque."
                )
                
                # 5. Enviar imagen
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
                
                sent_count += 1
                logger.info(f"✅ Image sent to user {user_id}")
                
            except Exception as e:
                logger.error(f"❌ Error sending image to user {user_id}: {e}")
                error_count += 1
        
        logger.info(f"📊 Daily job completed: {sent_count} sent, {error_count} errors")
    
    except Exception as e:
        logger.error(f"❌ Daily image job failed: {e}")


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
