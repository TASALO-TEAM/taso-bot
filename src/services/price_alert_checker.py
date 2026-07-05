# src/services/price_alert_checker.py
"""Servicio que verifica alertas de precio de criptomonedas y notifica a los usuarios.

Corre cada 5 minutos via APScheduler.
Consulta los precios actuales de CoinMarketCap (igual que /p) y dispara
las alertas cuya condición se cumpla, marcándolas TRIGGERED en taso-api.
"""

import logging
import time
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram.ext import Application
from telegram.constants import ParseMode

from src.crypto_client import CryptoApiClient
from src.config import get_settings
from src.services.ads_manager import get_ad_block, safe_append

logger = logging.getLogger(__name__)
settings = get_settings()

# Intervalo de verificación en minutos
CHECK_INTERVAL_MINUTES = 5

# Instancia global del scheduler
_scheduler: Optional[AsyncIOScheduler] = None

# Cliente de cripto reutilizado (mismo que /p, singleton)
_crypto_client: Optional[CryptoApiClient] = None


def _get_crypto_client() -> CryptoApiClient:
    global _crypto_client
    if _crypto_client is None:
        _crypto_client = CryptoApiClient()
    return _crypto_client


def _format_price(price: float) -> str:
    """Formatea el precio con decimales apropiados."""
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:,.4f}"
    else:
        return f"${price:.8f}"


async def check_price_alerts_job(application: Application) -> None:
    """
    Job principal: verifica alertas de precio y notifica usuarios.

    Flujo:
    1. Obtener coins con alertas activas desde taso-api
    2. Consultar precio actual para cada coin (CoinMarketCap → CryptoCompare fallback)
    3. Obtener alertas activas de esas coins
    4. Para cada alerta que cumple condición: enviar mensaje + marcar TRIGGERED
    """
    job_start = time.time()
    api = application.bot_data.get("api_client")
    if not api:
        logger.error("❌ [AlertChecker] api_client no disponible en bot_data")
        return

    # 1. Coins con alertas activas
    try:
        active_coins = await api.get_active_alert_coins()
    except Exception as e:
        logger.error("❌ [AlertChecker] Error obteniendo coins activas: %s", e)
        return

    if not active_coins:
        logger.debug("💤 [AlertChecker] Sin alertas activas — nada que verificar")
        return

    logger.info("🔍 [AlertChecker] Verificando %d coin(s): %s", len(active_coins), active_coins)

    # 2. Obtener precios actuales
    crypto_client = _get_crypto_client()
    prices: dict[str, float] = {}

    for coin in active_coins:
        try:
            data = await crypto_client.get_crypto_data(coin)
            if data and data.get("price"):
                prices[coin] = data["price"]
                logger.debug("💰 [AlertChecker] %s = %s", coin, _format_price(data["price"]))
            else:
                logger.warning("⚠️ [AlertChecker] Sin precio para %s", coin)
        except Exception as e:
            logger.error("❌ [AlertChecker] Error obteniendo precio de %s: %s", coin, e)

    if not prices:
        logger.warning("⚠️ [AlertChecker] No se obtuvieron precios, abortando ciclo")
        return

    # 3. Obtener alertas activas para las coins con precio disponible
    coins_con_precio = list(prices.keys())
    triggered_count = 0

    for coin in coins_con_precio:
        current_price = prices[coin]

        try:
            # Obtener alertas activas del usuario para esta coin
            # Usamos el endpoint de coins activas ya consultado; ahora
            # necesitamos las alertas de cada user. Las obtenemos por coin
            # consultando el endpoint general con status=ACTIVE.
            # Nota: no hay endpoint /alerts?coin=X, pero get_active_alert_coins
            # nos dio la lista. Necesitamos iterar por user más adelante.
            # Por ahora consultamos todos los usuarios activos via el api.
            # La implementación más eficiente sería un endpoint GET /alerts/active
            # que retorne todas las alertas — lo resolvemos aquí con lo que tenemos:
            pass
        except Exception as e:
            logger.error("❌ [AlertChecker] Error procesando coin %s: %s", coin, e)

    # Obtener TODAS las alertas activas en una sola llamada
    # Usamos un endpoint no definido aún: GET /api/v1/alerts/active
    # Por ahora usamos get_active_alert_coins y luego consultamos por coin.
    # Implementación real: ver nota al pie del archivo.
    try:
        triggered_count = await _check_all_active_alerts(api, application, prices)
    except Exception as e:
        logger.error("❌ [AlertChecker] Error en _check_all_active_alerts: %s", e)

    duration_ms = (time.time() - job_start) * 1000
    logger.info(
        "✅ [AlertChecker] Ciclo completado: %d coin(s), %d alerta(s) disparada(s) (%.0fms)",
        len(active_coins), triggered_count, duration_ms,
    )


async def _check_all_active_alerts(api, application: Application, prices: dict) -> int:
    """
    Obtiene todas las alertas activas y evalúa condiciones contra los precios dados.

    Returns:
        Número de alertas disparadas en este ciclo.
    """
    # Llamamos al endpoint GET /api/v1/alerts/active (todas las alertas ACTIVE)
    # que añadimos al router. Si no existe aún, usamos el fallback de consultar
    # por user_id — pero eso requeriría conocer todos los user_ids.
    # Con el router como está, llamamos directamente al endpoint general.
    try:
        import httpx
        client = api._get_client()
        url = f"{api.api_url}/api/v1/alerts/active"
        resp = await client.get(url, headers=api._admin_headers)
        resp.raise_for_status()
        data = resp.json()
        alertas = data.get("data", []) if data.get("ok") else []
    except Exception as e:
        logger.error("❌ [AlertChecker] Error obteniendo alertas activas: %s", e)
        return 0

    triggered_count = 0
    bot = application.bot

    for alerta in alertas:
        coin = alerta.get("coin", "").upper()
        current_price = prices.get(coin)
        if current_price is None:
            continue

        target = alerta.get("target_price", 0)
        condition = alerta.get("condition", "")
        price_at_creation = alerta.get("price_at_creation")
        alert_id = alerta.get("id")
        user_id = alerta.get("user_id")

        # ── Lógica de cruce real ──────────────────────────────────────────────
        # Solo dispara si el precio CRUZÓ el objetivo desde el lado correcto.
        # Esto evita falsos positivos cuando el precio ya estaba por encima/debajo
        # del target en el momento de crear la alerta.
        #
        # ABOVE: el precio inicial estaba por debajo del target y ahora lo superó
        # BELOW: el precio inicial estaba por encima del target y ahora lo bajó
        #
        # Si price_at_creation es None (alertas antiguas), se usa la lógica simple.
        if price_at_creation is not None:
            if condition == "ABOVE":
                should_trigger = (
                    price_at_creation < target and current_price >= target
                )
            else:  # BELOW
                should_trigger = (
                    price_at_creation > target and current_price <= target
                )
        else:
            # Fallback para alertas creadas antes de esta mejora
            should_trigger = (
                (condition == "ABOVE" and current_price >= target) or
                (condition == "BELOW" and current_price <= target)
            )
        # ─────────────────────────────────────────────────────────────────────

        if not should_trigger:
            continue

        # Marcar TRIGGERED primero (evitar doble disparo en race condition)
        ok = await api.trigger_price_alert(alert_id)
        if not ok:
            logger.warning("⚠️ [AlertChecker] No se pudo marcar alert %d como TRIGGERED", alert_id)
            continue

        # Enviar notificación al usuario
        emoji = "📈" if condition == "ABOVE" else "📉"
        direction = "superó" if condition == "ABOVE" else "cayó por debajo de"
        text = (
            f"🔔 *Alerta de precio activada*\n\n"
            f"{emoji} *{coin}* {direction} {_format_price(target)}\n\n"
            f"💰 Precio actual: *{_format_price(current_price)}*\n\n"
            f"_Usa /alert para gestionar tus alertas._"
        )
        ad_block = await get_ad_block(api)
        text = safe_append(text, ad_block)
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
            logger.info(
                "📣 [AlertChecker] Notificación enviada: user=%d coin=%s %s %.6f (actual=%.6f)",
                user_id, coin, condition, target, current_price,
            )
            triggered_count += 1
        except Exception as e:
            logger.error(
                "❌ [AlertChecker] Error enviando notificación a user=%d alert=%d: %s",
                user_id, alert_id, e,
            )

    return triggered_count


def start_price_alert_checker(application: Application) -> None:
    """Inicia el scheduler del checker de alertas de precio."""
    global _scheduler

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        check_price_alerts_job,
        trigger=IntervalTrigger(minutes=CHECK_INTERVAL_MINUTES),
        args=[application],
        id="price_alert_checker",
        name="Price Alert Checker",
        max_instances=1,          # evitar solapamiento si el job tarda
        misfire_grace_time=60,    # tolera hasta 60s de retraso
    )
    _scheduler.start()
    logger.info(
        "✅ [AlertChecker] Scheduler iniciado — verificando cada %d min",
        CHECK_INTERVAL_MINUTES,
    )


def stop_price_alert_checker() -> None:
    """Detiene el scheduler del checker."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("🛑 [AlertChecker] Scheduler detenido")
