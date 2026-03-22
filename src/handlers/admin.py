"""Handlers para comandos de administración del bot TASALO.

Módulo responsable de manejar los comandos administrativos:
- /refresh: Fuerza refresco inmediato de tasas en el backend
- /status: Muestra estado del scheduler del backend

Ambos comandos están restringidos a usuarios en ADMIN_CHAT_IDS.
"""

import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from src.config import settings
from src.api_client import TasaloApiClient
from src.formatters import SEPARATOR_THICK, parse_iso_datetime

logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    """Verifica si un user_id está en la lista de administradores.

    Args:
        user_id: ID del usuario a verificar

    Returns:
        True si el usuario es admin, False en caso contrario
    """
    admin_ids = settings.get_admin_chat_ids_list()
    return user_id in admin_ids


async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /refresh.

    Fuerza un refresco inmediato de las tasas en el backend llamando
    al endpoint POST /api/v1/admin/refresh.

    Solo disponible para administradores configurados en ADMIN_CHAT_IDS.

    Args:
        update: Update de Telegram con el comando
        context: Contexto del bot (incluye api_client)
    """
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)

    logger.info(f"🔄 /refresh command invoked by user {user_id} (@{username})")

    # Verificar permisos de administrador
    if not _is_admin(user_id):
        logger.warning(f"⚠️ User {user_id} no autorizado para /refresh")
        await update.message.reply_text(
            "🔑 *Acceso Denegado*\n\n"
            "Este comando es solo para administradores.",
            parse_mode="Markdown",
        )
        return

    logger.info(f"✅ User {user_id} autorizado para /refresh")

    # Obtener cliente API
    api_client: TasaloApiClient = context.bot_data.get("api_client")

    if not api_client:
        logger.error("❌ api_client no está disponible en bot_data")
        await update.message.reply_text(
            "⚠️ *Error de Configuración*\n\n"
            "El bot no está configurado correctamente.\n"
            "Contacta al administrador.",
            parse_mode="Markdown",
        )
        return

    # Verificar si está configurada la API key
    if not api_client.admin_key:
        logger.error("❌ admin_key no configurada")
        await update.message.reply_text(
            "⚠️ *Error de Configuración*\n\n"
            "La clave de administración no está configurada.\n"
            "Contacta al administrador.",
            parse_mode="Markdown",
        )
        return

    # Mensaje de estado inicial
    status_msg = await update.message.reply_text("🔄 Refrescando tasas...")

    # Llamar al endpoint admin/refresh
    result = await api_client.admin_refresh()

    if result is None:
        logger.warning("⚠️ /refresh: API returned None")
        await status_msg.edit_text(
            "⚠️ *Error de Conexión*\n\n"
            "El backend no respondió.\n"
            "Verifica que taso-api esté corriendo.",
            parse_mode="Markdown",
        )
        return

    # Extraer datos del resultado
    refresh_data = result.get("data", {})
    sources_refreshed = refresh_data.get("sources", [])
    timestamp = refresh_data.get("timestamp") or result.get("updated_at")

    # Construir mensaje de éxito
    sources_list = "\n".join([f"  • {src}" for src in sources_refreshed]) if sources_refreshed else "  • Todas las fuentes"

    success_text = (
        "✅ *Refresco Completado*\n\n"
        f"{sources_list}\n\n"
        f"🕐 {timestamp or datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        "Las tasas han sido actualizadas."
    )

    await status_msg.edit_text(success_text, parse_mode="Markdown")
    logger.info("✅ Refresh ejecutado correctamente")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /status.

    Muestra el estado actual del scheduler del backend, incluyendo:
    - Último refresco exitoso
    - Próximo refresco programado
    - Conteo de errores recientes
    - Estado general (running/stopped)

    Solo disponible para administradores configurados en ADMIN_CHAT_IDS.

    Args:
        update: Update de Telegram con el comando
        context: Contexto del bot (incluye api_client)
    """
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)

    logger.info(f"📊 /status command invoked by user {user_id} (@{username})")

    # Verificar permisos de administrador
    if not _is_admin(user_id):
        logger.warning(f"⚠️ User {user_id} no autorizado para /status")
        await update.message.reply_text(
            "🔑 *Acceso Denegado*\n\n"
            "Este comando es solo para administradores.",
            parse_mode="Markdown",
        )
        return

    logger.info(f"✅ User {user_id} autorizado para /status")

    # Obtener cliente API
    api_client: TasaloApiClient = context.bot_data.get("api_client")

    if not api_client:
        logger.error("❌ api_client no está disponible en bot_data")
        await update.message.reply_text(
            "⚠️ *Error de Configuración*\n\n"
            "El bot no está configurado correctamente.",
            parse_mode="Markdown",
        )
        return

    # Verificar si está configurada la API key
    if not api_client.admin_key:
        logger.error("❌ admin_key no configurada")
        await update.message.reply_text(
            "⚠️ *Error de Configuración*\n\n"
            "La clave de administración no está configurada.",
            parse_mode="Markdown",
        )
        return

    # Mensaje de estado inicial
    status_msg = await update.message.reply_text("⏳ Obteniendo estado del scheduler...")

    # Llamar al endpoint admin/status
    result = await api_client.admin_status()

    if result is None:
        logger.warning("⚠️ /status: API returned None")
        await status_msg.edit_text(
            "⚠️ *Error de Conexión*\n\n"
            "El backend no respondió.\n"
            "Verifica que taso-api esté corriendo.",
            parse_mode="Markdown",
        )
        return

    # Extraer datos del scheduler
    scheduler_data = result.get("data", {})
    scheduler_info = scheduler_data.get("scheduler", {})

    # Extraer campos con valores por defecto
    is_running = scheduler_info.get("is_running", False)
    last_run_at = scheduler_info.get("last_run_at")
    last_success_at = scheduler_info.get("last_success_at")
    next_run_at = scheduler_info.get("next_run_at")
    error_count = scheduler_info.get("error_count", 0)
    last_error = scheduler_info.get("last_error")

    # Formatear timestamps
    last_run_str = parse_iso_datetime(last_run_at) if last_run_at else "Nunca"
    last_success_str = parse_iso_datetime(last_success_at) if last_success_at else "Nunca"
    next_run_str = parse_iso_datetime(next_run_at) if next_run_at else "N/A"

    # Determinar estado visual
    status_icon = "🟢" if is_running else "🔴"
    status_text = "Corriendo" if is_running else "Detenido"

    # Construir mensaje de estado
    status_lines = [
        f"{status_icon} *Estado del Scheduler*\n",
        f"*Estado:* {status_text}",
        f"*Última ejecución:* {last_run_str}",
        f"*Último éxito:* {last_success_str}",
        f"*Próxima ejecución:* {next_run_str}",
        f"*Errores:* {error_count}",
    ]

    if last_error:
        status_lines.append(f"\n⚠️ *Último error:*\n`{last_error[:200]}`")

    status_lines.append(f"\n{SEPARATOR_THICK}")
    status_lines.append(f"📆 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    status_text = "\n".join(status_lines)

    await status_msg.edit_text(status_text, parse_mode="Markdown")
    logger.info("✅ Status obtenido correctamente")
