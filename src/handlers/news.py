# src/handlers/news.py
"""Handler para comando /news — feed directo de noticias cripto (NewsData.io).

A diferencia de /tspl (digest curado por Groq, 1x/día), /news es una
consulta directa sin pasar por IA: llama al endpoint /crypto de
NewsData.io y muestra los artículos tal cual, con cache corto para no
gastar de más los 200 créditos/día del plan gratis.

Subcomandos (por tema/moneda, ya que el plan gratis de NewsData.io no
tiene filtros de sentimiento como hot/important/bullish — ver
docs/plans/2026-07-23-tspl-news-newsdata.md):

    /news              → feed general "Crypto & Coin News", sin acotar
    /news btc          → coin=btc
    /news eth          → coin=eth
    /news sol          → coin=sol
    /news defi         → q="DeFi"
    /news regulacion   → q="regulación OR SEC OR ley"

Cualquier otro argumento se usa como query libre (ej. "/news halving"
→ q="halving") en vez de fallar.
"""

import asyncio
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.newsdata_client import get_newsdata_client
from src.stats_tracker import track_command_usage
from src.cache import cache

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 900  # 15 min — conserva créditos del plan gratis (200/día)

# Subcomandos que mapean a un "coin" específico del endpoint /crypto
_COIN_SUBCOMMANDS = {"btc", "eth", "sol", "xrp", "bnb", "ada", "doge", "trx", "ton", "link"}

# Subcomandos que mapean a una query de texto libre predefinida
_QUERY_SUBCOMMANDS = {
    "defi": "DeFi",
    "regulacion": "regulación OR SEC OR ley",
    "etf": "ETF",
    "mineria": "minería OR mining",
}


def _resolve_subcommand(arg: str | None) -> tuple[list[str] | None, str | None, str]:
    """Traduce el argumento de /news a (coin, query, etiqueta_para_mostrar).

    Si no hay argumento → feed general.
    Si matchea un símbolo conocido → filtra por coin.
    Si matchea una query predefinida → usa esa query.
    Si no matchea nada → se usa el argumento tal cual como query libre.
    """
    if not arg:
        return None, None, "general"

    arg_lower = arg.lower().strip()

    if arg_lower in _COIN_SUBCOMMANDS:
        return [arg_lower], None, arg_lower.upper()

    if arg_lower in _QUERY_SUBCOMMANDS:
        return None, _QUERY_SUBCOMMANDS[arg_lower], arg_lower

    # Query libre: lo que haya escrito el usuario, tal cual
    return None, arg, arg_lower


def _build_keyboard(subcommand_key: str) -> InlineKeyboardMarkup:
    btn_refresh = InlineKeyboardButton(
        "🔄 Actualizar",
        callback_data=f"news_refresh_{subcommand_key}"
    )
    return InlineKeyboardMarkup([[btn_refresh]])


def _format_articles(articles: list[dict], label: str) -> str:
    """Arma el mensaje final a partir de artículos ya normalizados."""
    lines = [f"📰 *Noticias — {label}*\n"]

    for art in articles:
        title = art.get("title") or "(sin título)"
        desc = art.get("description")
        source = art.get("source_name") or "Fuente desconocida"
        url = art.get("url")

        lines.append(f"*{title}*")
        if desc:
            # Recortar descripciones largas para no saturar el mensaje
            desc_corto = desc if len(desc) <= 220 else desc[:217] + "..."
            lines.append(desc_corto)
        detalle = f"_{source}_"
        if url:
            detalle += f" · [ver noticia]({url})"
        lines.append(detalle)
        lines.append("")  # línea en blanco entre artículos

    return "\n".join(lines).rstrip()


async def _get_or_build_news_body(coin: list[str] | None, query: str | None, cache_key: str) -> str | None:
    """Retorna el cuerpo del feed desde caché, o lo genera si expiró.

    Returns:
        El texto ya formateado, o None si NewsData.io no está configurado
        o la llamada falló (para que el caller decida el mensaje de error).
    """
    cached = cache.get(cache_key, ttl=CACHE_TTL_SECONDS)
    if cached:
        return cached

    client = get_newsdata_client()
    articles = await client.get_crypto_news(query=query, coin=coin, language="es", limit=8)

    if not articles:
        return None

    body = _format_articles(articles, cache_key.replace("news_", ""))
    cache.set(cache_key, body)
    return body


async def news_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback para botón 🔄 Actualizar de /news."""
    query = update.callback_query
    user_id = query.from_user.id
    subcommand_key = query.data.replace("news_refresh_", "", 1)
    logger.info("🔄 /news refresh callback (%s) by user %d", subcommand_key, user_id)
    await news_command(update, context, _forced_arg=subcommand_key if subcommand_key != "general" else None)


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE, _forced_arg: str | None = None) -> None:
    """Muestra noticias cripto directas de NewsData.io.

    Uso: /news [subcomando|query]
    """
    cmd_start = time.time()
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"

    arg = _forced_arg
    if arg is None and context.args:
        arg = " ".join(context.args)

    coin, query_text, label = _resolve_subcommand(arg)
    cache_key = f"news_{label}"

    logger.info("📰 /news command invoked by user %d (@%s) — filtro: %s", user_id, username, label)

    if update.message:
        await update.message.reply_chat_action("typing")
    elif update.callback_query:
        await update.callback_query.answer("🔄 Actualizando noticias...")

    try:
        cuerpo = await _get_or_build_news_body(coin, query_text, cache_key)
    except Exception as e:
        logger.error("❌ Error generando /news: %s", e, exc_info=True)
        cuerpo = None

    if cuerpo is None:
        error_msg = (
            "⚠️ No se pudieron obtener noticias en este momento "
            "(fuente no disponible o sin resultados para ese filtro)."
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        asyncio.create_task(track_command_usage(update, context, "/news", success=False))
        return

    keyboard = _build_keyboard(label)

    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                cuerpo,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        else:
            await update.message.reply_text(
                cuerpo,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
    except Exception as e:
        if "Message is not modified" in str(e):
            logger.debug("📝 /news: mensaje no modificado (ya actualizado)")
            if update.callback_query:
                await update.callback_query.answer("✅ Ya actualizado")
        else:
            # Fallback sin Markdown si algún título/descripción rompe el parseo
            logger.warning("⚠️ Fallo enviando /news con Markdown: %s", e)
            try:
                texto_plano = cuerpo.replace("*", "").replace("_", "")
                if update.callback_query:
                    await update.callback_query.edit_message_text(
                        texto_plano, reply_markup=keyboard, disable_web_page_preview=True
                    )
                else:
                    await update.message.reply_text(
                        texto_plano, reply_markup=keyboard, disable_web_page_preview=True
                    )
            except Exception as e2:
                logger.error("❌ Error enviando /news (fallback): %s", e2, exc_info=True)
                asyncio.create_task(track_command_usage(update, context, "/news", success=False))
                return

    total_duration_ms = (time.time() - cmd_start) * 1000
    logger.info("✅ /news completed for user %d (%.0fms)", user_id, total_duration_ms)

    asyncio.create_task(track_command_usage(update, context, "/news", success=True))
