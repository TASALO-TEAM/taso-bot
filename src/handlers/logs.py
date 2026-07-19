"""Handler para el comando /log — logs de bot, api, web y gcg sin necesidad de SSH.

Uso:
    /log                            Resumen de los 4 servicios (bot, api, web, gcg)
    /log bot|api|web|gcg            Envía el log activo de ese servicio (documento)
    /log bot|api|web|gcg <fecha>    Envía el archivo archivado de esa fecha (YYYY-MM-DD)
    /log clear                      Borra los archivos archivados de los 4 servicios
    /log clear bot|api|web|gcg      Borra los archivados de un solo servicio

Los logs activos NUNCA se envían pegados en el texto del mensaje (por el
límite de caracteres de Telegram): siempre se mandan como documento adjunto.

Solo disponible para administradores configurados en ADMIN_CHAT_IDS.
"""

import logging
import time
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from src.handlers.admin import _is_admin
from src.services import log_manager

logger = logging.getLogger(__name__)

DATE_HINT = "Formato de fecha esperado: `YYYY-MM-DD` (ej. 2026-07-01)."
USAGE_HINT = (
    "Usa `/log`, `/log bot`, `/log api`, `/log web`, `/log gcg` o `/log clear`."
)


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal del comando /log (ver docstring del módulo)."""
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)

    logger.info(
        "📄 /log invoked by admin %d (@%s) args=%s", user_id, username, context.args
    )

    if not _is_admin(user_id):
        logger.warning("⚠️ Unauthorized /log attempt by user %d (@%s)", user_id, username)
        await update.message.reply_text(
            "🔑 *Acceso Denegado*\n\nEste comando es solo para administradores.",
            parse_mode="Markdown",
        )
        return

    args = context.args or []

    try:
        if not args:
            await _send_summary(update)
        elif args[0].lower() == "clear":
            await _handle_clear(update, args[1:])
        else:
            await _handle_service_request(update, args)

        duration_ms = (time.time() - cmd_start) * 1000
        logger.info("✅ /log completed for admin %d (%.0fms)", user_id, duration_ms)

    except Exception:
        logger.exception("❌ /log failed for admin %d (@%s)", user_id, username)
        try:
            await update.message.reply_text(
                "❌ *Error Inesperado*\n\n"
                "Ocurrió un error al procesar /log.\n"
                "Revisa los logs del bot para más detalles.",
                parse_mode="Markdown",
            )
        except Exception:
            logger.exception("❌ Failed to send error message for /log to admin %d", user_id)


async def _handle_clear(update: Update, extra_args: list):
    service = None
    if extra_args:
        service = log_manager.normalize_service(extra_args[0])
        if service is None:
            await update.message.reply_text(
                f"⚠️ Servicio desconocido: `{extra_args[0]}`.\n"
                "Usa: `bot`, `api`, `web` o `gcg`.",
                parse_mode="Markdown",
            )
            return
    await _clear(update, service)


async def _handle_service_request(update: Update, args: list):
    service = log_manager.normalize_service(args[0])
    if service is None:
        await update.message.reply_text(
            f"⚠️ Servicio desconocido: `{args[0]}`.\n\n{USAGE_HINT}",
            parse_mode="Markdown",
        )
        return
    date_str = args[1] if len(args) > 1 else None
    await _send_service_log(update, service, date_str)


async def _send_summary(update: Update):
    services = log_manager.list_all_services()
    lines = ["📄 *Estado de Logs — TASALO*\n"]

    for info in services.values():
        label = info.display_name

        if not info.exists:
            lines.append(f"🔴 *{label}*: no encontrado")
            lines.append(f"   _{info.error}_")
            lines.append("")
            continue

        if info.active_log_path:
            size = log_manager.format_size(info.active_size_bytes)
            last_mod = (
                info.last_modified.strftime("%Y-%m-%d %H:%M")
                if info.last_modified
                else "?"
            )
            lines.append(f"🟢 *{label}*: {size} · última actividad {last_mod}")
        else:
            lines.append(f"🟡 *{label}*: sin log activo por ahora")

        if info.archives:
            lines.append(f"   📦 {len(info.archives)} archivo(s) archivado(s)")

        lines.append("")

    lines.append("Usa `/log bot`, `/log api`, `/log web` o `/log gcg` para descargar el log activo.")
    lines.append("Usa `/log clear` para borrar los archivos archivados.")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _send_service_log(update: Update, service: str, date_str: Optional[str]):
    info = log_manager.get_service_log_info(service)

    if not info.exists:
        await update.message.reply_text(
            f"🔴 *{log_manager.SERVICE_DISPLAY_NAMES[service]}*\n\n{info.error}",
            parse_mode="Markdown",
        )
        return

    if date_str:
        await _send_archived_log(update, service, info, date_str)
        return

    if not info.active_log_path:
        hint = ""
        if info.archives:
            dates = ", ".join(f"`{a.date_str}`" for a in info.archives[:10])
            hint = f"\n\nSí hay archivos archivados: {dates}"
        await update.message.reply_text(
            f"🟡 *{info.display_name}* no tiene un log activo en este momento.{hint}",
            parse_mode="Markdown",
        )
        return

    caption_lines = [
        f"📄 *{info.display_name}* — {log_manager.format_size(info.active_size_bytes)}",
    ]
    if info.last_modified:
        caption_lines.append(
            f"Última actividad: {info.last_modified.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    if info.archives:
        dates = ", ".join(f"`{a.date_str}`" for a in info.archives[:10])
        caption_lines.append(f"\n📦 Archivados disponibles: {dates}")
        caption_lines.append(f"Pide uno con `/log {service} <fecha>`")

    with open(info.active_log_path, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=f"{info.display_name}.log",
            caption="\n".join(caption_lines),
            parse_mode="Markdown",
        )


async def _send_archived_log(update: Update, service: str, info, date_str: str):
    archived, available_dates = log_manager.find_archive_by_date(service, date_str)

    if not archived:
        if available_dates:
            hint = "\n\nFechas disponibles: " + ", ".join(
                f"`{d}`" for d in available_dates[:10]
            )
        else:
            hint = "\n\nNo hay ningún archivo archivado para este servicio todavía."
        await update.message.reply_text(
            f"⚠️ No se encontró un log de *{info.display_name}* con fecha "
            f"`{date_str}`.{hint}\n\n{DATE_HINT}",
            parse_mode="Markdown",
        )
        return

    caption = (
        f"📦 *{info.display_name}* — archivado {archived.date_str} "
        f"({log_manager.format_size(archived.size_bytes)})"
    )
    with open(archived.path, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=archived.filename,
            caption=caption,
            parse_mode="Markdown",
        )


async def _clear(update: Update, service: Optional[str]):
    results = log_manager.clear_archives(service)

    lines = ["🧹 *Limpieza de logs archivados*\n"]
    total_removed = 0
    total_bytes = 0

    for svc, result in results.items():
        label = log_manager.SERVICE_DISPLAY_NAMES[svc]
        if result["error"] and result["removed"] == 0:
            lines.append(f"🔴 *{label}*: {result['error']}")
            continue

        total_removed += result["removed"]
        total_bytes += result["bytes_freed"]
        freed = log_manager.format_size(result["bytes_freed"])
        lines.append(
            f"🟢 *{label}*: {result['removed']} archivo(s) eliminado(s), {freed} liberados"
        )

    lines.append(
        f"\n*Total:* {total_removed} archivo(s), "
        f"{log_manager.format_size(total_bytes)} liberados"
    )
    lines.append("\n_Los logs activos no se tocaron._")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
