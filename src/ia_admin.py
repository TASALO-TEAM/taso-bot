"""/ia (solo administradores, F5-T7): proveedor principal, respaldo y modelo de NVIDIA.

Registrado por el contrato de extension (F6-T2): namespace `ia`, callbacks `ia:<p|b|m>:<valor>`.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from src.config import settings
from src.core import ai_config
from src.utils.permissions import is_admin

logger = logging.getLogger(__name__)

SOLO_ADMIN = "Este comando es solo para administradores."


def _marca(activo: bool, texto: str) -> str:
    return f"✅ {texto}" if activo else texto


def _panel() -> tuple[str, InlineKeyboardMarkup]:
    cfg = ai_config.get()
    nombres = ai_config.NOMBRES
    modelo = next((m for m in ai_config.MODELOS_NVIDIA if m[0] == cfg["nvidia_model"]), None)
    modelo_txt = f"{modelo[1]} ({modelo[2]})" if modelo else cfg["nvidia_model"]
    clave = getattr(settings, "nvidia_api_key", "")
    clave_ok = isinstance(clave, str) and bool(clave.strip())
    respaldo = nombres.get(cfg["backup"], "Ninguno")

    texto = (
        "🧠 TASALO IA — proveedores\n\n"
        f"Principal: {nombres[cfg['primary']]}\n"
        f"Respaldo: {respaldo}\n"
        f"Modelo de NVIDIA: {modelo_txt}\n"
        f"Clave de NVIDIA: {'configurada' if clave_ok else 'no configurada'}\n\n"
        "El respaldo solo responde si el principal falla. "
        "A los proveedores solo se envían datos de mercado y titulares públicos, "
        "no mensajes de usuarios."
    )

    filas = [
        [InlineKeyboardButton(_marca(cfg["primary"] == p, f"Principal: {nombres[p]}"), callback_data=f"ia:p:{p}")
         for p in ai_config.PROVEEDORES],
        [InlineKeyboardButton(_marca(cfg["backup"] == p, f"Respaldo: {nombres[p]}"), callback_data=f"ia:b:{p}")
         for p in ai_config.PROVEEDORES],
        [InlineKeyboardButton(_marca(cfg["backup"] == "none", "Sin respaldo"), callback_data="ia:b:none")],
    ]
    for i, (mid, etiqueta, nota) in enumerate(ai_config.MODELOS_NVIDIA):
        filas.append([InlineKeyboardButton(
            _marca(cfg["nvidia_model"] == mid, f"{etiqueta} · {nota}"), callback_data=f"ia:m:{i}")])
    return texto, InlineKeyboardMarkup(filas)


async def ia_command(update, context) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(SOLO_ADMIN)
        return
    texto, markup = _panel()
    await update.message.reply_text(texto, reply_markup=markup)


async def ia_callback(update, context, data: str) -> None:
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.message.reply_text(SOLO_ADMIN)
        return

    partes = data.split(":")
    if len(partes) == 3:
        _, accion, valor = partes
        if accion == "p":
            ai_config.set_primary(valor)
        elif accion == "b":
            ai_config.set_backup(valor)
        elif accion == "m" and valor.isascii() and valor.isdigit():
            ai_config.set_model(int(valor))

    texto, markup = _panel()
    try:
        await query.edit_message_text(texto, reply_markup=markup)
    except BadRequest:
        pass  # "Message is not modified": el valor ya era ese
