"""Handlers para comandos de administración del bot TASALO.

Módulo responsable de manejar los comandos administrativos:
- /refresh: Fuerza refresco inmediato de tasas en el backend
- /status: Muestra estado del scheduler + estadísticas del bot

Ambos comandos están restringidos a usuarios en ADMIN_CHAT_IDS.
"""

import asyncio
import logging
import time
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
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)

    logger.info("🔄 /refresh command invoked by admin %d (@%s)", user_id, username)

    try:
        # Verificar permisos de administrador
        if not _is_admin(user_id):
            logger.warning(
                "⚠️ Unauthorized /refresh attempt by user %d (@%s)",
                user_id,
                username,
            )
            await update.message.reply_text(
                "🔑 *Acceso Denegado*\n\n"
                "Este comando es solo para administradores.",
                parse_mode="Markdown",
            )
            return

        logger.info("✅ Admin %d (@%s) authorized for /refresh", user_id, username)

        # Obtener cliente API
        api_client: TasaloApiClient = context.bot_data.get("api_client")

        if not api_client:
            logger.error("❌ api_client not available in bot_data (admin %d)", user_id)
            await update.message.reply_text(
                "⚠️ *Error de Configuración*\n\n"
                "El bot no está configurado correctamente.\n"
                "Contacta al administrador.",
                parse_mode="Markdown",
            )
            return

        # Verificar si está configurada la API key
        if not api_client.admin_key:
            logger.error("❌ admin_key not configured (admin %d)", user_id)
            await update.message.reply_text(
                "⚠️ *Error de Configuración*\n\n"
                "La clave de administración no está configurada.\n"
                "Contacta al administrador.",
                parse_mode="Markdown",
            )
            return

        # Mensaje de estado inicial
        status_msg = await update.message.reply_text("🔄 Refrescando tasas...")

        # Llamar al endpoint admin/refresh with timing
        api_start = time.time()
        logger.info("📡 Calling POST /api/v1/admin/refresh for admin %d", user_id)

        result = await api_client.admin_refresh()

        api_duration_ms = (time.time() - api_start) * 1000
        logger.info(
            "📡 admin/refresh API call completed for admin %d (%.0fms) — result=%s",
            user_id,
            api_duration_ms,
            "ok" if result else "None",
        )

        if result is None:
            logger.warning(
                "⚠️ /refresh: API returned None for admin %d (%.0fms)",
                user_id,
                api_duration_ms,
            )
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
        sources_list = (
            "\n".join([f"  • {src}" for src in sources_refreshed])
            if sources_refreshed
            else "  • Todas las fuentes"
        )

        success_text = (
            "✅ *Refresco Completado*\n\n"
            f"{sources_list}\n\n"
            f"🕐 {timestamp or datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            "Las tasas han sido actualizadas."
        )

        await status_msg.edit_text(success_text, parse_mode="Markdown")

        duration_ms = (time.time() - cmd_start) * 1000
        logger.info(
            "✅ /refresh completed for admin %d (%.0fms) — sources: %d",
            user_id,
            duration_ms,
            len(sources_refreshed),
        )

    except Exception:
        duration_ms = (time.time() - cmd_start) * 1000
        logger.exception(
            "❌ /refresh failed for admin %d (@%s) after %.0fms",
            user_id,
            username,
            duration_ms,
            exc_info=True,
        )
        try:
            await update.message.reply_text(
                "❌ *Error Inesperado*\n\n"
                "Ocurrió un error al ejecutar el refresco.\n"
                "Revisa los logs del bot para más detalles.",
                parse_mode="Markdown",
            )
        except Exception:
            logger.exception("❌ Failed to send error message for /refresh to admin %d", user_id)


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
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)

    logger.info("📊 /status command invoked by admin %d (@%s)", user_id, username)

    try:
        # Verificar permisos de administrador
        if not _is_admin(user_id):
            logger.warning(
                "⚠️ Unauthorized /status attempt by user %d (@%s)",
                user_id,
                username,
            )
            await update.message.reply_text(
                "🔑 *Acceso Denegado*\n\n"
                "Este comando es solo para administradores.",
                parse_mode="Markdown",
            )
            return

        logger.info("✅ Admin %d (@%s) authorized for /status", user_id, username)

        # Obtener cliente API
        api_client: TasaloApiClient = context.bot_data.get("api_client")

        if not api_client:
            logger.error("❌ api_client not available in bot_data (admin %d)", user_id)
            await update.message.reply_text(
                "⚠️ *Error de Configuración*\n\n"
                "El bot no está configurado correctamente.",
                parse_mode="Markdown",
            )
            return

        # Verificar si está configurada la API key
        if not api_client.admin_key:
            logger.error("❌ admin_key not configured (admin %d)", user_id)
            await update.message.reply_text(
                "⚠️ *Error de Configuración*\n\n"
                "La clave de administración no está configurada.",
                parse_mode="Markdown",
            )
            return

        # Mensaje de estado inicial
        status_msg = await update.message.reply_text("⏳ Obteniendo estado...")

        # Llamar a los endpoints de admin/status y admin/stats/summary en paralelo with timing
        api_start = time.time()
        logger.info(
            "📡 Calling GET /api/v1/admin/status + /api/v1/admin/stats/summary for admin %d",
            user_id,
        )

        scheduler_result, stats_result = await asyncio.gather(
            api_client.admin_status(),
            api_client.get_stats_summary(),
            return_exceptions=True,
        )

        api_duration_ms = (time.time() - api_start) * 1000
        scheduler_ok = scheduler_result is not None and not isinstance(scheduler_result, Exception)
        stats_ok = stats_result is not None and not isinstance(stats_result, Exception)
        logger.info(
            "📡 Admin status API calls completed for admin %d (%.0fms) — scheduler=%s, stats=%s",
            user_id,
            api_duration_ms,
            "ok" if scheduler_ok else "failed",
            "ok" if stats_ok else "failed",
        )

        # Procesar resultado del scheduler
        if not scheduler_ok:
            logger.warning(
                "⚠️ /status: API scheduler returned None/Exception for admin %d (%.0fms)",
                user_id,
                api_duration_ms,
            )
            await status_msg.edit_text(
                "⚠️ *Error de Conexión*\n\n"
                "El backend no respondió.\n"
                "Verifica que taso-api esté corriendo.",
                parse_mode="Markdown",
            )
            return

        # Extraer datos del scheduler
        # NOTA: AdminStatusResponse (taso-api) devuelve {ok, scheduler, updated_at}
        # SIN envoltorio "data" -> se lee directo de la raiz del JSON.
        scheduler_info = scheduler_result.get("scheduler", {})

        is_running = scheduler_info.get("is_running", False)
        last_run_at = scheduler_info.get("last_run_at")
        last_success_at = scheduler_info.get("last_success_at")
        error_count = scheduler_info.get("error_count", 0)
        last_error = scheduler_info.get("last_error")

        # Formatear timestamps
        last_run_str = parse_iso_datetime(last_run_at) if last_run_at else "Nunca"
        last_success_str = (
            parse_iso_datetime(last_success_at) if last_success_at else "Nunca"
        )

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

        # Procesar estadisticas (si estan disponibles)
        # NOTA: BotStatsSummary (taso-api) devuelve {ok, users, commands,
        # top_users, performance, updated_at} SIN envoltorio "data" -> se lee
        # directo de la raiz del JSON (mismo bug que scheduler_info arriba).
        stats_lines = []
        if stats_result and isinstance(stats_result, dict) and stats_result.get("ok"):
            stats_data = stats_result

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
                    username_display = user.get("username") or f"User {user['user_id']}"
                    stats_lines.append(
                        f"   {i}. {username_display} - {user['total_commands']} comandos"
                    )

            # Rendimiento
            perf = stats_data.get("performance", {})
            success_rate = perf.get("success_rate", 0)
            total_requests = perf.get("total_requests_24h", 0)
            stats_lines.append(f"\n⚡ *Rendimiento API:*")
            stats_lines.append(f"   • Éxito: {success_rate:.1f}%")
            stats_lines.append(f"   • Requests (24h): {total_requests}")
        else:
            stats_lines.append("\n⚠️ *Estadísticas no disponibles*")
            logger.warning(
                "⚠️ Could not retrieve bot stats for admin %d",
                user_id,
            )

        # Unir todo
        status_lines = scheduler_lines + stats_lines
        status_lines.append(f"\n{SEPARATOR_THICK}")
        status_lines.append(f"📆 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        status_text = "\n".join(status_lines)

        await status_msg.edit_text(status_text, parse_mode="Markdown")

        duration_ms = (time.time() - cmd_start) * 1000
        logger.info(
            "✅ /status completed for admin %d (%.0fms) — scheduler_running=%s, has_stats=%s",
            user_id,
            duration_ms,
            is_running,
            "yes" if stats_result and isinstance(stats_result, dict) else "no",
        )

    except Exception:
        duration_ms = (time.time() - cmd_start) * 1000
        logger.exception(
            "❌ /status failed for admin %d (@%s) after %.0fms",
            user_id,
            username,
            duration_ms,
            exc_info=True,
        )
        try:
            await update.message.reply_text(
                "❌ *Error Inesperado*\n\n"
                "Ocurrió un error al obtener el estado.\n"
                "Revisa los logs del bot para más detalles.",
                parse_mode="Markdown",
            )
        except Exception:
            logger.exception("❌ Failed to send error message for /status to admin %d", user_id)
