"""Handlers para comandos de administración del bot TASALO.

Módulo responsable de manejar los comandos administrativos:
- /refresh: Fuerza refresco inmediato de tasas en el backend
- /status: Panel ejecutivo con botones (scheduler, usuarios, API pública,
  cambios recientes) — ver docs/plans/2026-07-08-status-command-v2.md

Ambos comandos están restringidos a usuarios en ADMIN_CHAT_IDS.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.api_client import TasaloApiClient
from src.build_info import BOT_BUILD_INFO, BOT_VERSION, format_uptime
from src.cache import cache
from src.formatters import SEPARATOR_THICK, parse_iso_datetime
from src.utils.permissions import is_admin as _is_admin

logger = logging.getLogger(__name__)

# Cache corto del bundle de /status (admin_status + stats + api_usage 24h) —
# es un panel de control, no un dato de mercado, así que el TTL es bajo:
# solo evita golpear la DB si dos admins abren /status casi a la vez o si
# el mismo admin navega entre secciones en pocos segundos.
STATUS_BUNDLE_CACHE_KEY = "admin_status_bundle"
STATUS_BUNDLE_CACHE_TTL = 30  # segundos

_WINDOW_LABELS = {"24h": "24 horas", "7d": "7 días", "30d": "30 días"}
_CLIENT_LABELS = {
    "bot": "🤖 Bot",
    "app": "📱 App",
    "ext": "🧩 Extensión",
    "extmf": "🧩 Ext MF",
    "web": "🌐 Web",
    "unknown": "❓ Sin identificar",
}


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


# ─────────────────────────────────────────────────────────────────────────
# /status — panel ejecutivo con botones
# Ver docs/plans/2026-07-08-status-command-v2.md (Fase 3)
# ─────────────────────────────────────────────────────────────────────────


async def _get_status_bundle(api_client: TasaloApiClient) -> dict:
    """Obtiene (o sirve desde caché corta) admin_status + stats + api_usage(24h).

    Se cachea el bundle ya ensamblado 30s — evita golpear la DB si dos
    admins abren /status casi a la vez, o si el mismo admin navega entre
    secciones del panel en pocos segundos.
    """
    cached = cache.get(STATUS_BUNDLE_CACHE_KEY, ttl=STATUS_BUNDLE_CACHE_TTL)
    if cached:
        return cached

    admin_status_res, stats_res, api_usage_res = await asyncio.gather(
        api_client.admin_status(),
        api_client.get_stats_summary(),
        api_client.get_api_usage_stats("24h"),
        return_exceptions=True,
    )

    bundle = {
        "admin_status": admin_status_res if not isinstance(admin_status_res, Exception) else None,
        "stats": stats_res if not isinstance(stats_res, Exception) else None,
        "api_usage": api_usage_res if not isinstance(api_usage_res, Exception) else None,
        "fetched_at": datetime.now(timezone.utc),
    }
    cache.set(STATUS_BUNDLE_CACHE_KEY, bundle)
    return bundle


def _compute_health(admin_status: Optional[dict]) -> tuple[str, str]:
    """Determina el ícono/estado general a partir de admin_status.

    🔴 si el scheduler no está corriendo, 🟡 si algún job tiene errores
    recientes (1-5), 🔴 si tiene más de 5, 🟢 si todo limpio.
    """
    if not admin_status or not admin_status.get("is_scheduler_running"):
        return "🔴", "Scheduler detenido"

    jobs = admin_status.get("jobs", [])
    max_errors = max((j.get("error_count", 0) or 0 for j in jobs), default=0)
    if max_errors == 0:
        return "🟢", "Todo operativo"
    if max_errors <= 5:
        return "🟡", "Atención — hay errores recientes"
    return "🔴", "Errores persistentes en scheduler"


def _render_summary_text(bundle: dict) -> str:
    """Resumen ejecutivo corto — mensaje inicial de /status."""
    admin_status = bundle.get("admin_status")
    stats = bundle.get("stats")
    api_usage = bundle.get("api_usage")

    icon, health_word = _compute_health(admin_status)

    jobs = admin_status.get("jobs", []) if admin_status else []
    jobs_ok = sum(1 for j in jobs if (j.get("error_count", 0) or 0) == 0)
    jobs_total = len(jobs)

    users = stats.get("users", {}) if stats and stats.get("ok") else {}
    total_users = users.get("total")
    active_recent = users.get("active_recent")

    if api_usage and api_usage.get("ok"):
        total_requests = api_usage.get("total_requests", 0)
        total_errors = api_usage.get("total_errors", 0)
        success_pct = max(0.0, 100.0 - api_usage.get("error_rate", 0.0))
        api_line = f"🌐 API pública: {total_requests} req/24h · {success_pct:.1f}% éxito"
    else:
        total_errors = "N/D"
        api_line = "🌐 API pública: sin datos (24h)"

    lines = [
        "📊 *TASALO — Estado del sistema*",
        f"{icon} {health_word} · bot `{BOT_BUILD_INFO['commit']}`",
        "",
        f"⚙️ Scheduler: {jobs_ok}/{jobs_total} jobs OK" if jobs_total else "⚙️ Scheduler: sin datos",
        f"👥 {total_users if total_users is not None else 'N/D'} usuarios"
        f" · {active_recent if active_recent is not None else 'N/D'} activos ahora",
        api_line,
        f"❌ {total_errors} errores (24h)",
        "",
        SEPARATOR_THICK,
    ]

    fetched_at = bundle.get("fetched_at")
    ts = fetched_at.strftime("%Y-%m-%d %H:%M:%S UTC") if fetched_at else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"📆 {ts}")

    return "\n".join(lines)


def _render_commands_view(bundle: dict, window: str) -> str:
    """Vista detallada de uso de comandos (botón 📈 Comandos)."""
    stats = bundle.get("stats")
    if not stats or not stats.get("ok"):
        return "📈 *Comandos*\n\n⚠️ Estadísticas no disponibles."

    commands = stats.get("commands", {})
    items = commands.get(f"commands_{window}", [])
    window_label = _WINDOW_LABELS.get(window, window)

    lines = [f"📈 *Comandos — últimas {window_label}*", ""]
    if not items:
        lines.append("Sin actividad registrada en este período.")
    else:
        for i, cmd in enumerate(items[:10], 1):
            lines.append(f"{i}. {cmd['command']}: {cmd['count']} veces")
    return "\n".join(lines)


def _render_users_view(bundle: dict) -> str:
    """Vista detallada de usuarios (botón 👥 Usuarios)."""
    stats = bundle.get("stats")
    if not stats or not stats.get("ok"):
        return "👥 *Usuarios*\n\n⚠️ Estadísticas no disponibles."

    users = stats.get("users", {})
    top_users = stats.get("top_users", {}).get("top_users", [])

    lines = [
        "👥 *Usuarios*",
        "",
        f"*Total:* {users.get('total', 0)}",
        f"*Nuevos (7 días):* {users.get('new_7d', 0)}",
        f"*Activos (24h):* {users.get('active_24h', 0)}",
        f"*Activos ahora (15 min):* {users.get('active_recent', 0)}",
    ]

    if top_users:
        lines.append("")
        lines.append("🏆 *Top usuarios:*")
        for i, u in enumerate(top_users[:5], 1):
            username_display = u.get("username") or f"User {u['user_id']}"
            lines.append(f"{i}. {username_display} — {u['total_commands']} comandos")

    return "\n".join(lines)


def _render_api_view(api_usage: Optional[dict], window: str) -> str:
    """Vista detallada de uso de la API pública (botón 🌐 API pública)."""
    window_label = _WINDOW_LABELS.get(window, window)
    if not api_usage or not api_usage.get("ok"):
        return f"🌐 *API pública — últimas {window_label}*\n\n⚠️ Sin datos disponibles."

    lines = [
        f"🌐 *API pública — últimas {window_label}*",
        "",
        f"*Requests totales:* {api_usage.get('total_requests', 0)}",
        f"*Errores:* {api_usage.get('total_errors', 0)} ({api_usage.get('error_rate', 0.0):.1f}%)",
        f"*Latencia promedio:* {api_usage.get('avg_duration_ms', 0.0):.0f}ms",
    ]

    by_client = api_usage.get("by_client", [])
    if by_client:
        lines.append("")
        lines.append("*Por cliente:*")
        for c in by_client[:6]:
            label = _CLIENT_LABELS.get(c["client_id"], c["client_id"])
            lines.append(f"  {label}: {c['requests']} req ({c['errors']} err)")

    by_endpoint = api_usage.get("by_endpoint", [])
    if by_endpoint:
        lines.append("")
        lines.append("*Top endpoints:*")
        for e in by_endpoint[:5]:
            lines.append(f"  `{e['path']}`: {e['requests']} req")

    return "\n".join(lines)


def _render_schedulers_view(bundle: dict) -> str:
    """Vista detallada de todos los jobs del scheduler (botón ⚙️ Schedulers)."""
    admin_status = bundle.get("admin_status")
    if not admin_status:
        return "⚙️ *Schedulers*\n\n⚠️ Sin datos disponibles."

    is_running = admin_status.get("is_scheduler_running", False)
    jobs = admin_status.get("jobs", [])

    lines = [
        "⚙️ *Schedulers*",
        "",
        f"*Estado global:* {'🟢 Corriendo' if is_running else '🔴 Detenido'}",
        "",
    ]

    if not jobs:
        lines.append("Sin jobs registrados.")

    for job in jobs:
        error_count = job.get("error_count", 0) or 0
        icon = "🟢" if error_count == 0 else ("🟡" if error_count <= 5 else "🔴")
        next_run = parse_iso_datetime(job["next_run_at"]) if job.get("next_run_at") else "N/D"

        lines.append(f"{icon} *{job.get('name') or job['id']}*")
        lines.append(f"   Próxima ejecución: {next_run}")
        if job.get("last_run_at"):
            last_run = parse_iso_datetime(job["last_run_at"])
            lines.append(f"   Última ejecución: {last_run} · errores: {error_count}")
            if job.get("last_error"):
                lines.append(f"   ⚠️ `{job['last_error'][:150]}`")
        lines.append("")

    return "\n".join(lines).rstrip()


def _read_changelog_bullets(relative_path: str, max_items: int = 5) -> list[str]:
    """Lee los primeros bullets bajo el encabezado de versión más reciente
    de un CHANGELOG.md (formato Keep-a-Changelog: '## [x.y.z] ...' seguido
    de líneas '- ...'). Devuelve [] si el archivo no existe o no matchea
    el formato — no es crítico para el resto del panel.
    """
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # src/handlers -> src -> taso-bot
        base_dir = os.path.dirname(base_dir)
        full_path = os.path.normpath(os.path.join(base_dir, relative_path))
        if not os.path.exists(full_path):
            return []
        with open(full_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        bullets = []
        seen_header = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                if seen_header:
                    break
                seen_header = True
                continue
            if seen_header and stripped.startswith("- "):
                bullets.append(stripped[2:].strip())
                if len(bullets) >= max_items:
                    break
        return bullets
    except Exception as e:
        logger.debug("⚠️ No se pudo leer changelog en %s: %s", relative_path, e)
        return []


async def _render_changes_view(api_client: TasaloApiClient) -> str:
    """Vista de build info + changelog reciente (botón 📝 Cambios recientes)."""
    health = await api_client.get_health()
    uptime = format_uptime()

    lines = [
        "📝 *Cambios recientes*",
        "",
        f"🤖 *taso-bot* `{BOT_BUILD_INFO['commit']}` ({BOT_BUILD_INFO['commit_date']})",
        f"   v{BOT_VERSION} · uptime {uptime}",
    ]

    if health:
        api_commit = health.get("git_commit", "unknown")
        api_date = health.get("git_commit_date", "unknown")
        api_version = health.get("version", "?")
        lines.append(f"🔌 *taso-api* `{api_commit}` ({api_date})")
        lines.append(f"   v{api_version}")
    else:
        lines.append("🔌 *taso-api*: no se pudo obtener /health")

    bullets = _read_changelog_bullets("../taso-api/CHANGELOG.md")
    if bullets:
        lines.append("")
        lines.append("*Últimos cambios registrados (taso-api):*")
        for b in bullets:
            lines.append(f"  • {b}")

    return "\n".join(lines)


# ── Teclados ──


def _build_status_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    """Teclado del resumen ejecutivo — accesos a cada sección."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 Comandos", callback_data=f"status_cmd:{admin_id}:24h"),
            InlineKeyboardButton("👥 Usuarios", callback_data=f"status_usr:{admin_id}"),
        ],
        [
            InlineKeyboardButton("🌐 API pública", callback_data=f"status_api:{admin_id}:24h"),
            InlineKeyboardButton("⚙️ Schedulers", callback_data=f"status_sch:{admin_id}"),
        ],
        [
            InlineKeyboardButton("📝 Cambios recientes", callback_data=f"status_log:{admin_id}"),
            InlineKeyboardButton("🔄 Refrescar", callback_data=f"status_refresh:{admin_id}"),
        ],
    ])


def _build_period_row(admin_id: int, prefix: str, current_window: str) -> list[InlineKeyboardButton]:
    """Fila de selector de período (24h/7d/30d) para Comandos y API pública."""
    row = []
    for label, w in (("24h", "24h"), ("7d", "7d"), ("30d", "30d")):
        text = f"• {label} •" if w == current_window else label
        row.append(InlineKeyboardButton(text, callback_data=f"{prefix}:{admin_id}:{w}"))
    return row


def _build_back_keyboard(
    admin_id: int, extra_row: Optional[list[InlineKeyboardButton]] = None
) -> InlineKeyboardMarkup:
    """Teclado de las vistas de detalle: fila opcional + botón Volver."""
    rows = []
    if extra_row:
        rows.append(extra_row)
    rows.append([InlineKeyboardButton("🔙 Volver", callback_data=f"status_back:{admin_id}")])
    return InlineKeyboardMarkup(rows)


async def _safe_edit(query, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    """edit_message_text tolerante a 'Message is not modified' (click repetido
    sobre la misma sección — no es un error real, solo contenido idéntico).
    """
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        if "Message is not modified" in str(e):
            logger.debug("📝 /status: mensaje no modificado (contenido igual)")
        else:
            raise


def _parse_status_callback(callback_data: str) -> tuple[str, int, Optional[str]]:
    """Parsea 'status_<action>:<admin_id>[:<window>]' → (action, admin_id, window)."""
    body = callback_data[len("status_"):]
    parts = body.split(":")
    action = parts[0]
    admin_id = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    window = parts[2] if len(parts) > 2 and parts[2] else None
    return action, admin_id, window


# ── Entry points ──


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /status — panel ejecutivo con botones.

    Muestra un resumen corto (salud general, scheduler, usuarios, API
    pública) con botones inline para profundizar en cada sección sin
    saturar el mensaje. Ver docs/plans/2026-07-08-status-command-v2.md.

    Solo disponible para administradores configurados en ADMIN_CHAT_IDS.
    """
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)

    logger.info("📊 /status command invoked by admin %d (@%s)", user_id, username)

    if not _is_admin(user_id):
        logger.warning("⚠️ Unauthorized /status attempt by user %d (@%s)", user_id, username)
        await update.message.reply_text(
            "🔑 *Acceso Denegado*\n\nEste comando es solo para administradores.",
            parse_mode="Markdown",
        )
        return

    logger.info("✅ Admin %d (@%s) authorized for /status", user_id, username)

    api_client: TasaloApiClient = context.bot_data.get("api_client")

    if not api_client:
        logger.error("❌ api_client not available in bot_data (admin %d)", user_id)
        await update.message.reply_text(
            "⚠️ *Error de Configuración*\n\nEl bot no está configurado correctamente.",
            parse_mode="Markdown",
        )
        return

    if not api_client.admin_key:
        logger.error("❌ admin_key not configured (admin %d)", user_id)
        await update.message.reply_text(
            "⚠️ *Error de Configuración*\n\nLa clave de administración no está configurada.",
            parse_mode="Markdown",
        )
        return

    status_msg = await update.message.reply_text("⏳ Obteniendo estado...")

    try:
        bundle = await _get_status_bundle(api_client)
    except Exception:
        duration_ms = (time.time() - cmd_start) * 1000
        logger.exception("❌ /status failed fetching bundle for admin %d (%.0fms)", user_id, duration_ms)
        await status_msg.edit_text(
            "⚠️ *Error de Conexión*\n\nEl backend no respondió.\nVerifica que taso-api esté corriendo.",
            parse_mode="Markdown",
        )
        return

    text = _render_summary_text(bundle)
    keyboard = _build_status_keyboard(user_id)

    await status_msg.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

    duration_ms = (time.time() - cmd_start) * 1000
    logger.info("✅ /status panel rendered for admin %d (%.0fms)", user_id, duration_ms)


async def status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatcher de los botones inline del panel /status.

    callback_data: 'status_<action>:<admin_id>[:<window>]'. El <admin_id>
    en el callback_data ata el panel a quien lo abrió (mismo patrón que
    tkt_bug:<uid> en handlers/tkt.py) para que otro admin no pueda operar
    los botones de una sesión ajena si dos abren /status a la vez.

    NOTA: callback_router ya llamó query.answer() antes de despachar acá
    (ver callback_router.callback_router) — no se debe volver a llamar
    query.answer(show_alert=True), Telegram solo permite una respuesta por
    callback query. Los errores/avisos se comunican editando el mensaje.
    """
    handler_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id
    callback_data = query.data

    try:
        action, owner_id, window = _parse_status_callback(callback_data)
    except (ValueError, IndexError):
        logger.warning("⚠️ status_callback: callback_data mal formado: %s", callback_data)
        return

    if not _is_admin(user_id):
        logger.warning("⚠️ status_callback: usuario no admin %d intentó '%s'", user_id, callback_data)
        try:
            await query.edit_message_text(
                "🔑 *Acceso Denegado*\n\nEste panel es solo para administradores.",
                parse_mode="Markdown",
            )
        except Exception:
            pass
        return

    if owner_id and owner_id != user_id:
        try:
            await query.edit_message_text(
                "⚠️ Este panel pertenece a otro administrador.\nUsa /status para abrir el tuyo.",
                parse_mode="Markdown",
            )
        except Exception:
            pass
        return

    api_client: TasaloApiClient = context.bot_data.get("api_client")
    if not api_client or not api_client.admin_key:
        try:
            await query.edit_message_text(
                "⚠️ *Error de Configuración*\n\nEl bot no está configurado correctamente.",
                parse_mode="Markdown",
            )
        except Exception:
            pass
        return

    try:
        if action in ("summary", "back"):
            bundle = await _get_status_bundle(api_client)
            await _safe_edit(query, _render_summary_text(bundle), _build_status_keyboard(user_id))

        elif action == "refresh":
            cache.invalidate(STATUS_BUNDLE_CACHE_KEY)
            bundle = await _get_status_bundle(api_client)
            await _safe_edit(query, _render_summary_text(bundle), _build_status_keyboard(user_id))

        elif action == "cmd":
            window = window or "24h"
            bundle = await _get_status_bundle(api_client)
            text = _render_commands_view(bundle, window)
            keyboard = _build_back_keyboard(user_id, _build_period_row(user_id, "status_cmd", window))
            await _safe_edit(query, text, keyboard)

        elif action == "usr":
            bundle = await _get_status_bundle(api_client)
            await _safe_edit(query, _render_users_view(bundle), _build_back_keyboard(user_id))

        elif action == "api":
            window = window or "24h"
            api_usage = await api_client.get_api_usage_stats(window)
            text = _render_api_view(api_usage, window)
            keyboard = _build_back_keyboard(user_id, _build_period_row(user_id, "status_api", window))
            await _safe_edit(query, text, keyboard)

        elif action == "sch":
            bundle = await _get_status_bundle(api_client)
            await _safe_edit(query, _render_schedulers_view(bundle), _build_back_keyboard(user_id))

        elif action == "log":
            text = await _render_changes_view(api_client)
            await _safe_edit(query, text, _build_back_keyboard(user_id))

        else:
            logger.warning("⚠️ status_callback: acción desconocida '%s' (data: %s)", action, callback_data)
            return

        duration_ms = (time.time() - handler_start) * 1000
        logger.info(
            "✅ status_callback '%s' completed for admin %d (%.0fms)",
            callback_data, user_id, duration_ms,
        )

    except Exception:
        duration_ms = (time.time() - handler_start) * 1000
        logger.exception(
            "❌ status_callback failed for admin %d callback '%s' (%.0fms)",
            user_id, callback_data, duration_ms,
        )
        try:
            await query.edit_message_text(
                "❌ *Error Inesperado*\n\nOcurrió un error procesando la acción.\nUsa /status para reabrir el panel.",
                parse_mode="Markdown",
            )
        except Exception:
            pass
