"""Handlers para comandos de administración del bot TASALO.

Módulo responsable de manejar los comandos administrativos:
- /refresh: Fuerza refresco inmediato de tasas en el backend
- /status: Muestra estado del scheduler + estadísticas del bot

Ambos comandos están restringidos a usuarios en ADMIN_CHAT_IDS.
"""

import asyncio
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

    Muestra el estado actual del scheduler del backend + estadísticas del bot:
    - Estado del scheduler (running/stopped, última ejecución, errores)
    - Usuarios (total, nuevos 7d, activos 24h)
    - Uso de comandos (24h)
    - Top usuarios
    - Rendimiento de API

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
    status_msg = await update.message.reply_text("⏳ Obteniendo estado...")

    # Llamar a los endpoints de admin/status y admin/stats/summary en paralelo
    scheduler_result, stats_result = await asyncio.gather(
        api_client.admin_status(),
        api_client.get_stats_summary(),
        return_exceptions=True,
    )

    # Procesar resultado del scheduler
    if scheduler_result is None or isinstance(scheduler_result, Exception):
        logger.warning("⚠️ /status: API scheduler returned None")
        await status_msg.edit_text(
            "⚠️ *Error de Conexión*\n\n"
            "El backend no respondió.\n"
            "Verifica que taso-api esté corriendo.",
            parse_mode="Markdown",
        )
        return

    # Extraer datos del scheduler
    scheduler_data = scheduler_result.get("data", {})
    scheduler_info = scheduler_data.get("scheduler", {})

    is_running = scheduler_info.get("is_running", False)
    last_run_at = scheduler_info.get("last_run_at")
    last_success_at = scheduler_info.get("last_success_at")
    error_count = scheduler_info.get("error_count", 0)
    last_error = scheduler_info.get("last_error")

    # Formatear timestamps
    last_run_str = parse_iso_datetime(last_run_at) if last_run_at else "Nunca"
    last_success_str = parse_iso_datetime(last_success_at) if last_success_at else "Nunca"

    # Determinar estado visual
    status_icon = "🟢" if is_running else "🔴"
    status_text = "Corriendo" if is_running else "Detenido"

    # Construir sección del scheduler
    scheduler_lines = [
        f"{status_icon} *Estado del Scheduler*\n",
        f"*Estado:* {status_text}",
        f"*Última ejecución:* {last_run_str}",
        f"*Último éxito:* {last_success_str}",
        f"*Errores:* {error_count}",
    ]

    if last_error:
        scheduler_lines.append(f"\n⚠️ *Último error:*\n`{last_error[:200]}`")

    # Procesar estadísticas (si están disponibles)
    stats_lines = []
    if stats_result and isinstance(stats_result, dict) and stats_result.get("ok"):
        stats_data = stats_result.get("data", {})
        
        # Usuarios
        users = stats_data.get("users", {})
        stats_lines.append("\n📊 *Estadísticas del Bot*")
        stats_lines.append(f"\n👥 *Usuarios Totales:* {users.get('total', 0)}")
        stats_lines.append(f"   • Nuevos (7 días): {users.get('new_7d', 0)}")
        stats_lines.append(f"   • Activos (24h): {users.get('active_24h', 0)}")
        
        # Comandos 24h
        commands = stats_data.get("commands", {})
        commands_24h = commands.get("commands_24h", [])
        if commands_24h:
            stats_lines.append("\n📈 *Comandos (24h):*")
            for cmd in commands_24h[:5]:  # Top 5 comandos
                stats_lines.append(f"   {cmd['command']}: {cmd['count']} veces")
        
        # Top usuarios
        top_users_data = stats_data.get("top_users", {})
        top_users = top_users_data.get("top_users", [])
        if top_users:
            stats_lines.append("\n🏆 *Top Usuarios:*")
            for i, user in enumerate(top_users[:3], 1):  # Top 3
                username_display = user.get('username') or f"User {user['user_id']}"
                stats_lines.append(f"   {i}. {username_display} - {user['total_commands']} comandos")
        
        # Rendimiento
        perf = stats_data.get("performance", {})
        success_rate = perf.get('success_rate', 0)
        total_requests = perf.get('total_requests_24h', 0)
        stats_lines.append(f"\n⚡ *Rendimiento API:*")
        stats_lines.append(f"   • Éxito: {success_rate:.1f}%")
        stats_lines.append(f"   • Requests (24h): {total_requests}")
    else:
        stats_lines.append("\n⚠️ *Estadísticas no disponibles*")
        logger.warning("⚠️ No se pudieron obtener estadísticas del bot")

    # Unir todo
    status_lines = scheduler_lines + stats_lines
    status_lines.append(f"\n{SEPARATOR_THICK}")
    status_lines.append(f"📆 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    status_text = "\n".join(status_lines)

    await status_msg.edit_text(status_text, parse_mode="Markdown")
    logger.info("✅ Status obtenido correctamente")
