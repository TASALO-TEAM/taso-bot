"""Daily image sender service - FIXED VERSION.

Correctly uses user's alert_time and prevents duplicate sends.
Handles Cuba timezone (UTC-4/UTC-5) and ensures image is captured after source update.
"""

import asyncio
import httpx
import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InputMediaPhoto, InputMediaDocument
from telegram.ext import Application
from typing import Set

from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
API_URL = settings.tasalo_api_url

# Cuba timezone - handles both UTC-4 (summer) and UTC-5 (standard)
CUBA_TZ = ZoneInfo("America/Havana")

# Time constants (in Cuba time)
IMAGE_CAPTURE_TIME = "07:30"  # Capture image at 7:30 AM Cuba (after source updates at 7:00)
MIN_SEND_TIME = "07:30"       # Earliest time to send images (7:30 AM Cuba)

# Global scheduler instance
scheduler = AsyncIOScheduler()

# Track sent alerts to prevent duplicates (reset daily)
_sent_today: Set[str] = set()
_last_reset_date = datetime.now(CUBA_TZ).date()


def _get_sent_key(user_id: int, date_str: str) -> str:
    """Generate unique key for tracking sent alerts."""
    return f"{user_id}:{date_str}"


def _reset_if_new_day():
    """Reset sent tracking if we're on a new day (Cuba timezone)."""
    global _sent_today, _last_reset_date
    today = datetime.now(CUBA_TZ).date()
    if today != _last_reset_date:
        _sent_today.clear()
        _last_reset_date = today
        logger.info("🔄 Daily sent tracking reset for %s", today)


async def send_daily_images_job(application: Application):
    """
    Job that sends images to users with alerts matching current time slot.
    
    Runs every 5 minutes, but only sends to users whose alert_time
    matches the current time (within 5-minute window) AND it's after
    the image capture time (7:30 AM Cuba).
    
    Prevents duplicate sends within the same day.
    """
    _reset_if_new_day()
    
    job_start = time.time()
    now_cuba = datetime.now(CUBA_TZ)
    today_date = now_cuba.date()
    current_time = now_cuba.strftime("%H:%M")
    
    logger.info("📸 Daily image dispatch job started at %s Cuba time", 
                 now_cuba.strftime("%Y-%m-%d %H:%M:%S"))
    
    # Check if it's already past the capture time (7:30 AM Cuba)
    current_hour, current_min = now_cuba.hour, now_cuba.minute
    capture_hour, capture_min = map(int, IMAGE_CAPTURE_TIME.split(":"))
    current_minutes = current_hour * 60 + current_min
    capture_minutes = capture_hour * 60 + capture_min
    
    if current_minutes < capture_minutes:
        logger.info("⏳ Not yet %s Cuba time, skipping dispatch (current: %s)", 
                     IMAGE_CAPTURE_TIME, current_time)
        return
    
    logger.info("✅ Past %s Cuba time, proceeding with dispatch", IMAGE_CAPTURE_TIME)
    
    # 1. Get all enabled alerts
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/api/v1/images/alerts?enabled=true",
                timeout=10.0
            )
            data = response.json()
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
    
    # 2. Filter alerts matching current Cuba time (within 5-minute window)
    matching_alerts = []
    for alert in alerts:
        alert_time = alert.get("alert_time", "07:15")
        try:
            alert_hour, alert_min = map(int, alert_time.split(":"))
            # Compare using Cuba time
            current_hour = now_cuba.hour
            current_min = now_cuba.minute
            
            # Allow 5-minute window
            time_diff = abs((current_hour * 60 + current_min) - (alert_hour * 60 + alert_min))
            if time_diff <= 5:  # Within 5 minutes
                matching_alerts.append(alert)
        except (ValueError, AttributeError) as e:
            logger.warning("⚠️ Invalid alert_time format: %s (alert: %s)", alert_time, alert.get("id"))
            continue
    
    logger.info("📋 Found %d total alerts, %d match time=%s (Cuba)", 
                 len(alerts), len(matching_alerts), current_time)
    
    if not matching_alerts:
        logger.info("ℹ️ No alerts matching current Cuba time slot, skipping")
        return
    
    # 3. Capture image from API (after 7:30 AM Cuba to ensure source is updated)
    logger.info("📸 Capturing image from API...")
    img_data = None
    for attempt in range(3):
        logger.info("🔍 Getting image (attempt %d/3)", attempt + 1)
        try:
            async with httpx.AsyncClient() as client:
                img_response = await client.get(
                    f"{API_URL}/api/v1/images/eltoque/capture",
                    timeout=30.0
                )
                img_data = img_response.json()
        except httpx.TimeoutException:
            logger.warning("⏱️ Timeout getting image (attempt %d/3)", attempt + 1)
            if attempt < 2:
                await asyncio.sleep(60)
            continue
        except Exception:
            logger.warning("⚠️ Error getting image (attempt %d/3)", attempt + 1, exc_info=True)
            if attempt < 2:
                await asyncio.sleep(60)
            continue
        
        if not img_data.get("ok"):
            logger.warning("⚠️ API error on attempt %d: %s", attempt + 1, img_data.get("error"))
            if attempt < 2:
                await asyncio.sleep(60)
            continue
        
        # Verify image is from today (Cuba time)
        captured_at_str = img_data["data"]["captured_at"]
        captured_at = datetime.fromisoformat(captured_at_str.replace('Z', '+00:00'))
        captured_at_cuba = captured_at.astimezone(CUBA_TZ)
        image_date = captured_at_cuba.date()
        
        if image_date == today_date:
            logger.info("✅ Image from today %s obtained", today_date.strftime("%d/%m/%Y"))
            break
        else:
            logger.warning("⚠️ Image is from previous day (%s), waiting for today's image", 
                          image_date.strftime("%Y-%m-%d"))
            if attempt < 2:
                await asyncio.sleep(60)
            else:
                # Last attempt - use what we have but log warning
                logger.warning("⚠️ Using image from %s as fallback", image_date.strftime("%Y-%m-%d"))
    
    if not img_data or not img_data.get("ok"):
        logger.error("❌ Failed to get image after 3 attempts, aborting job")
        return
    
    image_path = img_data["data"]["image_path"]
    logger.debug("📁 Image path: %s", image_path)
    
    # 4. Send to matching users (with deduplication)
    sent_count = 0
    fail_count = 0
    
    for alert in matching_alerts:
        user_id = alert["user_id"]
        alert_id = alert.get("id", "unknown")
        format_type = alert["format_type"]
        
        # Deduplication check
        sent_key = _get_sent_key(user_id, str(today_date))
        if sent_key in _sent_today:
            logger.info("ℹ️ User %d already received image today, skipping", user_id)
            continue
        
        logger.info("📤 Processing alert %s for user %d (format=%s)", alert_id, user_id, format_type)
        send_start = time.time()
        
        try:
            # Build caption with Cuba time
            caption = (
                "🇨🇺 *Tasa Diaria El Toque*\n"
                f"📅 {today_date.strftime('%d/%m/%Y')} · {now_cuba.strftime('%H:%M')} (Cuba)\n\n"
                "Esta es la tasa diaria de El Toque."
            )
            
            # Send image using application.bot
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
            
            send_duration_ms = (time.time() - send_start) * 1000
            logger.info("📨 Image sent to user %d via Telegram (%.0fms)", user_id, send_duration_ms)
            
        except httpx.TimeoutException:
            logger.error("❌ Timeout sending image to user %d (10s limit)", user_id)
            fail_count += 1
            continue
        except Exception:
            logger.error("❌ Telegram send failed for user %d (alert_id=%s)", user_id, alert_id, exc_info=True)
            fail_count += 1
            continue
        
        # Mark as sent
        _sent_today.add(sent_key)
        sent_count += 1
        send_duration_ms = (time.time() - send_start) * 1000
        logger.info("✅ Image sent to user %d (alert_id=%s, total=%.0fms)", 
                     user_id, alert_id, send_duration_ms)
    
    # Job completion summary
    total_duration_ms = (time.time() - job_start) * 1000
    logger.info(
        "✅ Daily image dispatch completed: %d sent, %d failed (%.0fms total)",
        sent_count, fail_count, total_duration_ms
    )


def start_daily_dispatcher(application: Application) -> None:
    """
    Start the daily image dispatcher.
    
    Runs every 5 minutes to check for users whose alert_time matches current time.
    Only sends to users who haven't received the image today.
    
    Args:
        application: The Telegram application (to access the bot)
    """
    # Run every 5 minutes to check for alerts matching current time
    scheduler.add_job(
        send_daily_images_job,
        trigger=CronTrigger(minute="*/5", timezone="UTC"),
        id="daily_image_alert",
        name="Daily Image Alert Dispatcher (every 5 min, time-aware)",
        args=[application],
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("✅ Daily image dispatcher started (every 5 min, time-aware)")


def stop_daily_dispatcher() -> None:
    """Stop the dispatcher."""
    scheduler.shutdown()
    logger.info("⏹️ Daily image dispatcher stopped")
