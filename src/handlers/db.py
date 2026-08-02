"""Handler para el comando /db — gestión de la base de datos de taso-api.

Uso:
    /db                 Resumen: backups existentes
    /db backup          Crea un backup manual y lo envía como documento
    /db list             Lista los backups existentes
    /db prune-rates      Poda on-demand de tasas históricas (>1 año)

Restore NO existe como subcomando aquí — es la única operación
deliberadamente excluida de Telegram, por seguridad. Vive solo en la CLI
del VPS (`python -m src.cli.db restore` en taso-api). Ver
docs/plans/2026-08-01-comando-db-gestion-retencion-tasas.md.

Solo disponible para administradores configurados en ADMIN_CHAT_IDS,
mismo patrón que /log.
"""

import io
import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from src.api_client import TasaloApiClient
from src.utils.permissions import is_admin as _is_admin

logger = logging.getLogger(__name__)

USAGE_HINT = "Usa `/db`, `/db backup`, `/db list` o `/db prune-rates`."
RESTORE_HINT = (
    "🔒 La restauración no está disponible por Telegram, por seguridad.\n"
    "Solo puede hacerse por CLI directamente en el VPS:\n"
    "`python -m src.cli.db restore <archivo> --confirm=RESTORE`"
)


def _fmt_size(n: int) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


async def db_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal del comando /db (ver docstring del módulo)."""
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)

    logger.info("💾 /db invoked by admin %d (@%s) args=%s", user_id, username, context.args)

    if not _is_admin(user_id):
        logger.warning("⚠️ Unauthorized /db attempt by user %d (@%s)", user_id, username)
        await update.message.reply_text(
            "🔑 *Acceso Denegado*\n\nEste comando es solo para administradores.",
            parse_mode="Markdown",
        )
        return

    api_client: TasaloApiClient = context.bot_data.get("api_client")
    if not api_client or not api_client.admin_key:
        logger.error("❌ api_client no disponible o sin admin_key (admin %d)", user_id)
        await update.message.reply_text(
            "⚠️ *Error de Configuración*\n\nEl bot no está configurado correctamente.",
            parse_mode="Markdown",
        )
        return

    args = context.args or []

    try:
        if not args:
            await _send_summary(update, api_client)
        elif args[0].lower() == "backup":
            await _handle_backup(update, api_client)
        elif args[0].lower() == "list":
            await _handle_list(update, api_client)
        elif args[0].lower() == "prune-rates":
            await _handle_prune_rates(update, api_client)
        elif args[0].lower() == "restore":
            await update.message.reply_text(RESTORE_HINT, parse_mode="Markdown")
        else:
            await update.message.reply_text(
                f"⚠️ Subcomando desconocido: `{args[0]}`.\n\n{USAGE_HINT}",
                parse_mode="Markdown",
            )

        duration_ms = (time.time() - cmd_start) * 1000
        logger.info("✅ /db completed for admin %d (%.0fms)", user_id, duration_ms)

    except Exception:
        logger.exception("❌ /db failed for admin %d (@%s)", user_id, username)
        try:
            await update.message.reply_text(
                "❌ *Error Inesperado*\n\n"
                "Ocurrió un error al procesar /db.\n"
                "Revisa los logs del bot para más detalles.",
                parse_mode="Markdown",
            )
        except Exception:
            logger.exception("❌ Failed to send error message for /db to admin %d", user_id)


async def _send_summary(update: Update, api_client: TasaloApiClient):
    backups = await api_client.admin_db_list_backups()

    lines = ["💾 *Base de datos — TASALO*\n"]
    if not backups:
        lines.append("No hay backups todavía.")
    else:
        lines.append(f"*Backups existentes:* {len(backups)}")
        for b in backups:
            created = b.get("created_at", "")[:19].replace("T", " ")
            lines.append(f"  📦 {b['filename']} — {_fmt_size(b['size_bytes'])} ({created})")

    lines.append("")
    lines.append(USAGE_HINT)

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _handle_backup(update: Update, api_client: TasaloApiClient):
    status_msg = await update.message.reply_text("⏳ Creando backup...")

    result = await api_client.admin_db_backup()
    if not result:
        await status_msg.edit_text(
            "❌ *Error*\n\nNo se pudo crear el backup. Revisa los logs de taso-api.",
            parse_mode="Markdown",
        )
        return

    info = result.get("data", {})
    remaining = result.get("backups_remaining", "?")
    filename = info.get("filename")

    await status_msg.edit_text(
        f"✅ Backup creado: `{filename}` ({_fmt_size(info.get('size_bytes', 0))})\n"
        f"Descargando para enviarlo...",
        parse_mode="Markdown",
    )

    content = await api_client.admin_db_download_backup(filename)
    if not content:
        await update.message.reply_text(
            f"⚠️ El backup `{filename}` se creó, pero no se pudo descargar para enviarlo por Telegram.\n"
            f"Backups restantes tras retención: {remaining}",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_document(
        document=io.BytesIO(content),
        filename=filename,
        caption=(
            f"💾 Backup manual · {_fmt_size(info.get('size_bytes', 0))} · {info.get('engine')}\n"
            f"sha256: `{info.get('checksum_sha256', '')[:16]}...`\n"
            f"Backups restantes tras retención: {remaining}"
        ),
        parse_mode="Markdown",
    )


async def _handle_list(update: Update, api_client: TasaloApiClient):
    backups = await api_client.admin_db_list_backups()
    if not backups:
        await update.message.reply_text("No hay backups todavía.")
        return

    lines = ["📦 *Backups existentes*\n"]
    for b in backups:
        created = b.get("created_at", "")[:19].replace("T", " ")
        lines.append(
            f"{created}  `{b['filename']}`  {_fmt_size(b['size_bytes'])}  ({b.get('engine')})"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _handle_prune_rates(update: Update, api_client: TasaloApiClient):
    status_msg = await update.message.reply_text("⏳ Podando tasas históricas...")

    result = await api_client.admin_db_prune_rates()
    if not result:
        await status_msg.edit_text(
            "❌ *Error*\n\nNo se pudo ejecutar la poda. Revisa los logs de taso-api.",
            parse_mode="Markdown",
        )
        return

    await status_msg.edit_text(
        "🧹 *Poda completada*\n\n"
        f"*rate_snapshots* borrados: {result.get('rate_snapshots_deleted', 0)}\n"
        f"*history_snapshots* borrados: {result.get('history_snapshots_deleted', 0)}\n"
        f"Retención: > {result.get('days', 365)} días",
        parse_mode="Markdown",
    )
