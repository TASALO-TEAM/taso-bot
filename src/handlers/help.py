# src/handlers/help.py
"""Handler para el comando /help — ayuda del bot en dos niveles.

    /help            → resumen corto por categorías (pensado para una
                        pantalla de teléfono, sin scroll eterno)
    /help <tema>      → ficha detallada de un comando específico

Comandos de administración (/ads, /refresh, /status, /health, /log) solo
aparecen en el resumen y responden a /help <tema> si is_admin(user_id) es
True (ver src/utils/permissions.py). Si un usuario normal pide ayuda sobre
un tema admin, se responde igual que si el tema no existiera — no se
revela que el comando existe (mismo criterio que /ads).

No se inyecta bloque de anuncios (get_ad_block) en /help: es un comando de
utilidad/onboarding, no de valor de mercado.

Ver docs/plans/2026-07-07-comando-help.md para el diseño completo.
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.stats_tracker import track_command_usage
from src.utils.permissions import is_admin

logger = logging.getLogger(__name__)

# Resumen corto — lo que se muestra en /help sin argumentos.
# Se arma como f-string simple, NO como loop sobre HELP_TOPICS, para
# controlar el orden y el texto exacto.
SUMMARY_TEXT = """📚 *TASALO BOT - Ayuda*

Bienvenido 👋 Estos son los principales comandos del bot.

💱 *Tasas de cambio*
/tasalo — Todas las tasas
/toque — Tasas de El Toque
/bcc — Tasas del BCC
/cadeca — Tasas de CADECA
/fuel — Combustible
/toqueimg — Imagen diaria de El Toque

🪙 *Criptomonedas*
/p <cripto> — Precio detallado
/spl — Panorama del mercado
_Ejemplos: /p btc · /p eth · /p hive_

📈 *Trading*
/ta <par> — Análisis técnico
/graf <par> — Gráfico con indicadores
/mk — Resumen del mercado
_Ejemplos: /ta btcusdt · /graf ethusdt_

🔔 *Alertas*
/alert — Mis alertas
/alert BTC 120000 — Crear alerta

📅 *Año*
/y — Estado del año y frase del día

ℹ️ *Utilidades*
/start — Menú principal
/tkt — Contactar a los administradores

💡 _Toca los botones de cualquier mensaje para IA, análisis técnico, gráficos o alertas._
💡 _Usa `/help <comando>` para ver el detalle de uno en particular (ej. `/help p`)._"""

# Bloque admin — se concatena SOLO si is_admin(user_id) es True
SUMMARY_ADMIN_EXTRA = """

🔑 *Administración*
/refresh /status /health /log /ads /ms — usa `/help admin`, `/help ads` o `/help ms` para el detalle.
/tkt list · /tkt active · /tkt show <id> — gestión de tickets, ver `/help admin`."""


# Fichas detalladas — clave = tema (lo que va después de "/help ")
HELP_TOPICS: dict[str, str] = {
    "tasalo": """📊 */tasalo — Todas las tasas de cambio*

Uso: `/tasalo`

Muestra en un solo mensaje las tasas de El Toque, BCC y CADECA juntas, para comparar de un vistazo.

Botones:
🔄 Actualizar · 🗺 Provincias · 📈 Históricos""",

    "toque": """📈 */toque — Tasas de El Toque*

Uso: `/toque`

Tasa del mercado informal (USD, EUR, MLC) según El Toque, con flecha de tendencia (🔺🔻) respecto a la consulta anterior.

Botón: 🔄 Actualizar""",

    "bcc": """🏛 */bcc — Tasas del Banco Central de Cuba*

Uso: `/bcc`

Tasa oficial de cambio publicada por el BCC (USD, EUR).

Botón: 🔄 Actualizar""",

    "cadeca": """🏢 */cadeca — Tasas de CADECA*

Uso: `/cadeca`

Tasas oficiales de compra y venta de CADECA (USD, EUR).

Botón: 🔄 Actualizar""",

    "fuel": """⛽ */fuel — Precio del combustible*

Uso: `/fuel`

Precio del combustible en el mercado informal, tomado del mismo feed de El Toque.

_Se actualiza junto con el resto de las tasas, cada 5 minutos aprox._""",

    "toqueimg": """🖼 */toqueimg — Imagen diaria de El Toque*

Uso: `/toqueimg`

Envía la imagen del post diario de tasas que publica El Toque, capturada automáticamente. Si todavía no hay una versión fresca, se envía la última disponible.

Botón: 🔄 Actualizar""",

    "p": """🪙 */p — Precio de criptomonedas*

Uso: `/p <moneda>`
Ejemplos: `/p btc` · `/p eth` · `/p hive`

Información mostrada:
• Precio actual, variación 24h, máximo/mínimo
• Capitalización y volumen
• Bloque extendido (ATH/ATL, supply) si hay datos de CoinGecko

Botones:
🔄 Actualizar · 📊 Análisis técnico (4H) · 🌍 Panorama IA · 🔔 Crear alerta""",

    "ta": """📊 */ta — Análisis técnico*

Uso: `/ta <par>`
Ejemplos: `/ta btcusdt` · `/ta ethusdt`

Indicadores técnicos (RSI, medias móviles, soportes/resistencias) más un resumen en lenguaje simple generado por IA.

Botones:
⏱ Cambiar temporalidad · 🔔 Crear alerta desde un nivel""",

    "graf": """📉 */graf — Gráfico con indicadores*

Uso: `/graf <par>`
Ejemplos: `/graf btcusdt` · `/graf ethusdt`

Gráfico de velas (OHLCV) con indicadores técnicos superpuestos.

Botones:
⏱ 4H / 12H / 1D / 1W · 🔔 Crear alerta desde un nivel""",

    "mk": """📊 */mk — Resumen del mercado*

Uso: `/mk`

Vista rápida del mercado cripto: variación de las principales monedas y tendencia general.

_Para un panorama más completo con narrativa de IA, usá `/spl`._""",

    "spl": """🌍 */spl — Spotlight del mercado*

Uso: `/spl`

Panorama general del mercado cripto: Fear & Greed Index, Altcoin Season Index, dominancia, top gainers/losers, tendencias, más una narrativa generada por IA.

Botón: 🔄 Actualizar Spotlight

_El panorama es el mismo para todos los usuarios y se actualiza cada 15 minutos._""",

    "alert": """🔔 */alert — Alertas de precio*

Uso:
`/alert` — ver tus alertas activas
`/alert <MONEDA> <PRECIO>` — crear una alerta directamente
Ejemplo: `/alert BTC 120000`

También podés crear alertas desde los botones de `/p`, `/ta` y `/graf`, sobre un nivel específico (soporte, resistencia, pivot).

Botones: ➕ Crear · 🗑 Eliminar · ⬅️ Volver""",

    "y": """📅 */y — Estado del año*

Uso: `/y`

Muestra cuánto va del año en curso (barra de progreso) y una frase del día.

_Los administradores pueden agregar, editar o eliminar frases con subcomandos adicionales._""",

    "start": """ℹ️ */start — Menú principal*

Uso: `/start`

Muestra el mensaje de bienvenida con botones de acceso directo a Tasalo, Toque, BCC, CADECA, precio cripto y alertas.""",

    "tkt": """🎫 */tkt — Contactar a los administradores*

Uso: `/tkt`

Abre un menú para reportar un bug o pedir que te promocionen/publiquen un anuncio. Elegís una opción, contás en un mensaje qué pasa, y un admin te contacta directamente. Te avisamos cuando tu ticket se toma y cuando se resuelve (o se aprueba/rechaza si es un anuncio).""",

    # Solo visibles/respondidas si is_admin:
    "ads": """📢 */ads — Gestión de anuncios* (admin)

Uso:
`/ads` — lista todos los anuncios
`/ads add <texto>` — crea un anuncio
`/ads del <id>` — elimina un anuncio
`/ads on <id>` / `/ads off <id>` — activa/desactiva
`/ads sponsor <id>` / `/ads unsponsor <id>` — marca/desmarca Patrocinado
`/ads weight <id> <n>` — ajusta el peso (1-100)
`/ads edit <id> <texto>` — edita el texto""",

    "ms": """📢 */ms — Difundir mensaje a todos los usuarios* (admin)

Uso:
`/ms <texto>` — difunde ese texto a todos los usuarios registrados
Reply a un mensaje con foto (con o sin caption) + `/ms` — difunde esa foto

Siempre muestra una vista previa con botones de confirmación antes de enviar nada — nada se manda hasta que tocás ✅ Confirmar.

Pensado para avisos rápidos: un comando que cambió, un bug arreglado, mantenimiento, etc.""",

    "admin": """🔑 *Comandos de administración*

`/refresh` — fuerza un refresh manual de las tasas
`/status` — estado del scheduler y última actualización
`/health` — verifica la conexión del bot con el backend
`/log` — logs de bot/api/web/gcg sin necesitar SSH (`/log` para ver subcomandos)

🎫 *Gestión de tickets (/tkt)*
`/tkt list` — últimos 20 tickets, cualquier estado
`/tkt active` — tickets abiertos o en progreso (pendientes de atender)
`/tkt show <id>` — detalle de un ticket puntual, con los botones de Tomar/Resolver o Aprobar/Rechazar según corresponda""",
}

# Alias → tema real. Permite /help alertas, /help cripto, /help ayuda, etc.
TOPIC_ALIASES: dict[str, str] = {
    "alertas": "alert",
    "alerta": "alert",
    "año": "y",
    "anio": "y",
    "cripto": "p",
    "criptomonedas": "p",
    "anuncios": "ads",
    "broadcast": "ms",
    "aviso": "ms",
    "notificar": "ms",
    "ticket": "tkt",
    "tickets": "admin",  # /help tickets -> detalle unificado de gestion en "admin"
    "soporte": "tkt",
    "contacto": "tkt",
    "logs": "admin",
    "log": "admin",
    "status": "admin",
    "refresh": "admin",
    "health": "admin",
    # Extras: comandos que la gente suele escribir en lenguaje natural
    "menu": "start",
    "inicio": "start",
    "grafico": "graf",
    "chart": "graf",
    "tecnico": "ta",
    "analisis": "ta",
    "spotlight": "spl",
    "panorama": "spl",
    "mercado": "mk",
    "combustible": "fuel",
    "gasolina": "fuel",
    "imagen": "toqueimg",
    "eltoque": "toque",
}

ADMIN_ONLY_TOPICS = {"ads", "admin", "ms"}


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler principal de /help.

    Sin argumentos muestra el resumen por categorías (+ bloque admin si
    corresponde). Con un argumento busca la ficha detallada de ese tema,
    resolviendo alias y respetando la visibilidad admin.
    """
    user_id = update.effective_user.id
    args = context.args or []

    asyncio.create_task(track_command_usage(update, context, "/help"))

    if not args:
        text = SUMMARY_TEXT
        if is_admin(user_id):
            text += SUMMARY_ADMIN_EXTRA
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    topic_raw = args[0].lower().lstrip("/")
    topic = TOPIC_ALIASES.get(topic_raw, topic_raw)

    if topic in ADMIN_ONLY_TOPICS and not is_admin(user_id):
        # Mismo criterio de "no revelar lo que no puede usar" que /ads
        topic = None

    body = HELP_TOPICS.get(topic)
    if not body:
        await update.message.reply_text(
            f"❓ No encontré ayuda para `{args[0]}`.\n"
            "Usa `/help` para ver todos los comandos disponibles.",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text(body, parse_mode="Markdown")
