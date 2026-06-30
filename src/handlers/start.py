"""Handlers para el comando /start del bot TASALO.

Módulo responsable de manejar el comando /start con mensaje
de bienvenida y teclado inline con botones de acceso rápido.
"""

import logging
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from src.formatters import (
    build_eltoque_only_message,
    build_bcc_only_message,
    build_cadeca_only_message,
    build_toque_new_message,
)
from src.api_client import TasaloApiClient

logger = logging.getLogger(__name__)

# URL de la Mini App (producción)
MINIAPP_URL = "https://tasalo.duckdns.org/miniapp"


def build_start_keyboard() -> InlineKeyboardMarkup:
    """Construye el teclado inline con botones de acceso rápido + Web App.

    Distribución:
        [📊 Tasalo ] [📈 Toque  ]
        [🏛 BCC    ] [🏢 CADECA ]
        [💰 Precio Cripto /p]
        [📊 Análisis Técnico /ta]
        [🔔 Alertas de Precio /alert]
        [🌐 Abrir TASALO Web]

    Nota: el botón de ToqueImg fue retirado temporalmente del /start
    mientras esa función está en mantenimiento — el comando /toqueimg,
    su handler y callbacks siguen intactos y operativos vía comando.

    Returns:
        InlineKeyboardMarkup con los botones de acción
    """
    keyboard = [
        [
            InlineKeyboardButton(
                "📊 Tasalo",
                callback_data="start_tasalo",
                style="primary",  # Azul - acción principal
            ),
            InlineKeyboardButton("📈 Toque", callback_data="start_toque"),
        ],
        [
            InlineKeyboardButton("🏛 BCC", callback_data="start_bcc"),
            InlineKeyboardButton("🏢 CADECA", callback_data="start_cadeca"),
        ],
        [
            InlineKeyboardButton(
                "💰 Precio Cripto /p",
                callback_data="start_p_help",
                style="primary",  # Azul - feature destacada
            ),
        ],
        [
            InlineKeyboardButton("📊 Análisis Técnico /ta", callback_data="start_ta_help"),
        ],
        [
            InlineKeyboardButton("🔔 Alertas de Precio /alert", callback_data="start_alert_help"),
        ],
        [
            InlineKeyboardButton("🌐 Abrir TASALO Web", web_app=WebAppInfo(url=MINIAPP_URL)),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para el comando /start.

    Muestra mensaje de bienvenida con información del bot
    y botones inline para acceder rápidamente a las tasas.
    Incluye botón Web App para abrir la Mini App en Telegram.

    Args:
        update: Update de Telegram con el mensaje del usuario
        context: Contexto del bot
    """
    cmd_start = time.time()
    user = update.effective_user
    user_id = user.id
    username = user.username or "N/A"

    logger.info(
        "👋 /start command invoked by user %d (@%s)",
        user_id,
        username,
    )

    try:
        # Construir mensaje de bienvenida
        welcome_text = (
            f"👋 ¡Hola {user.mention_html()}!\n\n"
            f"Soy TASALO, un bot para consultar las tasas de cambio de Cuba.\n"
            f"Puedes consultar tanto el mercado informal de ElToque como el mercado Oficial BCC y CADECA.\n\n"
            f"Presiona el botón del tipo de tasas que desees consultar:"
        )

        # Construir teclado inline (ya incluye Web App en build_start_keyboard)
        keyboard = build_start_keyboard()

        msg_send_start = time.time()
        await update.message.reply_html(
            text=welcome_text,
            reply_markup=keyboard,
        )
        msg_send_ms = (time.time() - msg_send_start) * 1000

        duration_ms = (time.time() - cmd_start) * 1000
        logger.info(
            "✅ /start completed for user %d (@%s) [msg_send=%.0fms, total=%.0fms]",
            user_id,
            username,
            msg_send_ms,
            duration_ms,
        )

    except Exception as e:
        duration_ms = (time.time() - cmd_start) * 1000
        logger.error(
            "❌ /start failed for user %d (@%s) after %.0fms: %s",
            user_id,
            username,
            duration_ms,
            e,
            exc_info=True,
        )
        raise


async def start_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para los botones inline del /start.

    Maneja los callbacks:
    - start_tasalo: Muestra tasas combinadas (todas las fuentes)
    - start_toque: Muestra solo ElToque (nuevo formato)
    - start_bcc: Muestra solo BCC
    - start_cadeca: Muestra solo CADECA

    Args:
        update: Update de Telegram con el callback query
        context: Contexto del bot
    """
    cb_start = time.time()
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.username or "N/A"
    command = query.data.replace("start_", "")

    logger.info(
        "🔘 Start button '%s' pressed by user %d (@%s)",
        command,
        user_id,
        username,
    )

    try:
        # Answer callback immediately for responsiveness
        answer_start = time.time()
        await query.answer()
        answer_ms = (time.time() - answer_start) * 1000
        logger.debug("Callback answered for user %d (%.0fms)", user_id, answer_ms)

        # Botones de ayuda para comandos que requieren argumentos (/p, /ta,
        # /alert) — no consultan la API de tasas, solo muestran cómo usarlos.
        help_texts = {
            "p_help": (
                "💰 *Precio de Criptomonedas — /p*\n\n"
                "Consulta el precio en tiempo real de cualquier criptomoneda, "
                "con datos de CoinMarketCap y CoinGecko combinados.\n\n"
                "Uso: `/p <MONEDA>`\n"
                "Ejemplos:\n"
                "`/p BTC`\n"
                "`/p ETH`\n"
                "`/p SOL`"
            ),
            "ta_help": (
                "📊 *Análisis Técnico — /ta*\n\n"
                "Genera un análisis técnico completo con indicadores (RSI, MFI, "
                "CCI, ADX, MACD), niveles de soporte/resistencia y un análisis "
                "narrativo con IA.\n\n"
                "Uso: `/ta <SYMBOL> [PAR] [TIME]`\n"
                "Ejemplos:\n"
                "`/ta BTC`\n"
                "`/ta ETH USDT 4h`\n"
                "`/ta SOL USDT 1d`"
            ),
            "alert_help": (
                "🔔 *Alertas de Precio — /alert*\n\n"
                "Crea alertas para que el bot te avise automáticamente cuando "
                "una criptomoneda alcance el precio que definas.\n\n"
                "Usa `/alert` para ver el menú de gestión de tus alertas "
                "(crear, ver y eliminar)."
            ),
        }
        if command in help_texts:
            await query.message.reply_text(
                help_texts[command], parse_mode="Markdown"
            )
            duration_ms = (time.time() - cb_start) * 1000
            logger.info(
                "✅ Help text for '%s' sent to user %d (@%s) (%.0fms)",
                command, user_id, username, duration_ms,
            )
            return

        # Obtener cliente API
        api_client: TasaloApiClient = context.bot_data.get("api_client")
        if not api_client:
            logger.error("❌ api_client no está disponible en bot_data for user %d", user_id)
            await query.edit_message_text("❌ Error de configuración del bot.")
            return

        # Obtener datos de la API
        api_call_start = time.time()
        response = await api_client.get_latest()
        api_call_ms = (time.time() - api_call_start) * 1000

        logger.info(
            "📡 API get_latest for button '%s', user %d (%.0fms)",
            command,
            user_id,
            api_call_ms,
        )

        if not response or not response.get("ok"):
            logger.warning(
                "⚠️ API returned None or ok=False for button '%s', user %d",
                command,
                user_id,
            )
            await query.answer("⚠️ Error obteniendo datos", show_alert=True)
            return

        api_data = response.get("data", {})
        if not api_data:
            logger.warning(
                "⚠️ API data is empty for button '%s', user %d",
                command,
                user_id,
            )
            await query.answer("⚠️ Datos no disponibles", show_alert=True)
            return

        # Seleccionar formatter según comando
        build_funcs = {
            "tasalo": lambda data: _build_tasalo_start_message(data, api_data),
            "toque": build_toque_new_message,
            "bcc": build_bcc_only_message,
            "cadeca": build_cadeca_only_message,
        }

        build_func = build_funcs.get(command)
        if not build_func:
            logger.error(
                "❌ Build function not found for button '%s', user %d",
                command,
                user_id,
            )
            return

        # Construir mensaje
        msg_build_start = time.time()
        text = build_func(api_data)
        msg_build_ms = (time.time() - msg_build_start) * 1000

        # Construir teclado con botón refresh
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔄 Actualizar", callback_data=f"{command}_refresh")],
            ]
        )

        # Enviar como nuevo mensaje (no editar el existente)
        reply_start = time.time()
        await query.message.reply_text(
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        reply_ms = (time.time() - reply_start) * 1000

        duration_ms = (time.time() - cb_start) * 1000
        logger.info(
            "✅ Button '%s' response sent for user %d (@%s) "
            "[build=%.0fms, reply=%.0fms, total=%.0fms]",
            command,
            user_id,
            username,
            msg_build_ms,
            reply_ms,
            duration_ms,
        )

    except Exception as e:
        duration_ms = (time.time() - cb_start) * 1000
        logger.error(
            "❌ Error in start button callback '%s' for user %d (@%s) after %.0fms: %s",
            command,
            user_id,
            username,
            duration_ms,
            e,
            exc_info=True,
        )
        try:
            await query.answer("❌ Error obteniendo datos", show_alert=True)
        except Exception:
            logger.error(
                "❌ Failed to send error alert to user %d after callback exception",
                user_id,
                exc_info=True,
            )


def _build_tasalo_start_message(full_message_func, api_data: dict) -> str:
    """Construye mensaje para botón Tasalo (usa el formato completo).

    Args:
        full_message_func: Función build_full_message importada
        api_data: Datos de la API

    Returns:
        String formateado con el mensaje completo
    """
    # Importar aquí para evitar circular imports
    from src.formatters import build_full_message
    return build_full_message(api_data)


async def _handle_toqueimg_start(context: ContextTypes.DEFAULT_TYPE, query):
    """Maneja el botón ToqueImg del start - reutiliza el handler de toqueimg.

    Args:
        context: Contexto del bot
        query: Callback query de Telegram
    """
    handler_start = time.time()
    user_id = query.from_user.id
    username = query.from_user.username or "N/A"

    logger.info(
        "📸 ToqueImg handler invoked by user %d (@%s)",
        user_id,
        username,
    )

    try:
        from src.handlers.toqueimg import toqueimg_command

        # Responder al callback
        await query.answer("📸 Abriendo ToqueImg...")

        # Crear un mensaje temporal para pasar al handler
        # Usamos el mismo chat que el query
        temp_msg_start = time.time()
        temp_message = await query.message.reply_text("📸 Capturando imagen...")
        temp_msg_ms = (time.time() - temp_msg_start) * 1000

        logger.debug(
            "Temp message sent for ToqueImg, user %d (%.0fms)",
            user_id,
            temp_msg_ms,
        )

        # Crear update fake con la estructura correcta
        class FakeUpdate:
            def __init__(self, message, user):
                self.message = message
                self.effective_user = user
                self.effective_chat = message.chat

        fake_update = FakeUpdate(temp_message, query.from_user)

        # Llamar al handler de toqueimg
        handler_call_start = time.time()
        await toqueimg_command(fake_update, context)
        handler_call_ms = (time.time() - handler_call_start) * 1000

        duration_ms = (time.time() - handler_start) * 1000
        logger.info(
            "✅ ToqueImg handler completed for user %d (@%s) "
            "[temp_msg=%.0fms, handler=%.0fms, total=%.0fms]",
            user_id,
            username,
            temp_msg_ms,
            handler_call_ms,
            duration_ms,
        )

    except Exception as e:
        duration_ms = (time.time() - handler_start) * 1000
        logger.error(
            "❌ ToqueImg handler failed for user %d (@%s) after %.0fms: %s",
            user_id,
            username,
            duration_ms,
            e,
            exc_info=True,
        )
        try:
            await query.answer("❌ Error capturando imagen", show_alert=True)
        except Exception:
            logger.error(
                "❌ Failed to send error alert to user %d after ToqueImg exception",
                user_id,
                exc_info=True,
            )
