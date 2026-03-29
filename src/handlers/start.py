"""Handlers para el comando /start del bot TASALO.

Módulo responsable de manejar el comando /start con mensaje
de bienvenida y teclado inline con botones de acceso rápido.
"""

import logging

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
    """Construye el teclado inline con 5 botones para comandos + Web App.

    Distribución:
        [📊 Tasalo] [📈 Toque]
        [🏛 BCC    ] [🏢 CADECA]
        [📸 ToqueImg]
        [🌐 Abrir TASALO Web]

    Returns:
        InlineKeyboardMarkup con los botones de acción
    """
    keyboard = [
        [
            InlineKeyboardButton("📊 Tasalo", callback_data="start_tasalo"),
            InlineKeyboardButton("📈 Toque", callback_data="start_toque"),
        ],
        [
            InlineKeyboardButton("🏛 BCC", callback_data="start_bcc"),
            InlineKeyboardButton("🏢 CADECA", callback_data="start_cadeca"),
        ],
        [
            InlineKeyboardButton("📸 ToqueImg", callback_data="start_toqueimg"),
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
    user = update.effective_user

    # Construir mensaje de bienvenida
    welcome_text = (
        f"👋 ¡Hola {user.mention_html()}!\n\n"
        f"Soy TASALO, un bot para consultar las tasas de cambio de Cuba.\n"
        f"Puedes consultar tanto el mercado informal de ElToque como el mercado Oficial BCC y CADECA.\n\n"
        f"Presiona el botón del tipo de tasas que desees consultar:"
    )

    # Construir teclado inline (ya incluye Web App en build_start_keyboard)
    keyboard = build_start_keyboard()

    await update.message.reply_html(
        text=welcome_text,
        reply_markup=keyboard,
    )

    logger.info(f"✅ /start command executed for user {user.id}")


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
    query = update.callback_query
    await query.answer()

    # Extraer comando del callback_data
    command = query.data.replace("start_", "")
    logger.info(f"🔘 Start button '{command}' pressed by user {query.from_user.id}")

    # Obtener cliente API
    api_client: TasaloApiClient = context.bot_data.get("api_client")
    if not api_client:
        logger.error("❌ api_client no está disponible en bot_data")
        await query.edit_message_text("❌ Error de configuración del bot.")
        return

    try:
        # Obtener datos de la API
        response = await api_client.get_latest()

        if not response or not response.get("ok"):
            logger.warning(f"⚠️ API respondió None o ok=False para {command}")
            await query.answer("⚠️ Error obteniendo datos", show_alert=True)
            return

        api_data = response.get("data", {})
        if not api_data:
            logger.warning(f"⚠️ API data está vacío para {command}")
            await query.answer("⚠️ Datos no disponibles", show_alert=True)
            return

        # Seleccionar formatter según comando
        build_funcs = {
            "tasalo": lambda data: _build_tasalo_start_message(data, api_data),
            "toque": build_toque_new_message,
            "bcc": build_bcc_only_message,
            "cadeca": build_cadeca_only_message,
            "toqueimg": _handle_toqueimg_start,
        }

        build_func = build_funcs.get(command)
        if not build_func:
            logger.error(f"❌ Build function no encontrada para {command}")
            return

        # Manejar toqueimg diferente (envía imagen, no texto)
        if command == "toqueimg":
            await build_func(context, query)
            return

        # Construir mensaje
        text = build_func(api_data)

        # Construir teclado con botón refresh
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔄 Actualizar", callback_data=f"{command}_refresh")],
            ]
        )

        # Enviar como nuevo mensaje (no editar el existente)
        await query.message.reply_text(
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

        logger.info(f"✅ Start button '{command}' response sent")

    except Exception as e:
        logger.error(f"❌ Error en start button callback {command}: {e}", exc_info=True)
        await query.answer("❌ Error obteniendo datos", show_alert=True)


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
    from src.handlers.toqueimg import toqueimg_command
    
    # Crear un update falso para reutilizar el handler de toqueimg
    # Simplemente redirigimos al usuario al comando /toqueimg
    await query.answer("📸 Abriendo ToqueImg...")
    
    # Enviar mensaje indicando que use /toqueimg
    await query.message.reply_text(
        "📸 Para ver la imagen de la tasa diaria, usa el comando:\n\n"
        "/toqueimg\n\n"
        "O espera un momento que te la envío ahora..."
    )
    
    # Llamar al handler de toqueimg directamente
    # Necesitamos crear un update con un mensaje válido
    fake_update = type('FakeUpdate', (), {
        'message': type('FakeMessage', (), {
            'reply_text': lambda self, text: query.message.reply_text(text)
        })(),
        'effective_user': query.from_user
    })()
    
    # Mejor enfoque: simplemente ejecutar la lógica de toqueimg
    from src.handlers.toqueimg import toqueimg_command
    await toqueimg_command(
        type('FakeUpdate', (), {
            'message': query.message,
            'effective_user': query.from_user
        })(),
        context
    )
