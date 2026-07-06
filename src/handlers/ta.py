# src/handlers/ta.py
# Handler para comando /ta — copia literal de BBAlert mejorada
# Provee análisis técnico profesional con indicadores y mensajes en español.

import asyncio
import logging
import requests
import json
import pytz
import pandas as pd
import pandas_ta as ta
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from tradingview_ta import TA_Handler, Interval, Exchange

from src.core.ai_logic import get_groq_crypto_analysis
from src.core.config import ADMIN_CHAT_IDS
from src.utils.file_manager import add_log_line
from src.utils.subscription_manager import check_feature_access, registrar_uso_comando
from src.services.ads_manager import get_ad_block, safe_append
from src.handlers.alert import cache_alert_levels
# I18n removed – using Spanish strings directly
from src.core.btc_advanced_analysis import BTCAdvancedAnalyzer

logger = logging.getLogger(__name__)


# === NUEVO COMANDO /ta MEJORADO ===

def get_binance_klines(symbol, interval, limit=500):
    endpoints = [
        "https://api.binance.com/api/v3/klines",
        "https://api.binance.us/api/v3/klines"
    ]
    for url in endpoints:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        try:
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            if not data or not isinstance(data, list): continue

            df = pd.DataFrame(data, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "trades",
                "taker_base", "taker_quote", "ignore"
            ])
            cols = ["open", "high", "low", "close", "volume"]
            df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')

            df['time'] = pd.to_datetime(df['open_time'], unit='ms')
            df.set_index('time', inplace=True)

            return df
        except Exception:
            continue
    return None

def calculate_table_indicators(df):
    def safe_ind(name, series):
        try:
            df[name] = series if series is not None else 0.0
        except (KeyError, TypeError):
            df[name] = 0.0

    safe_ind('RSI', df.ta.rsi(length=14))
    safe_ind('MFI', df.ta.mfi(length=14))
    safe_ind('CCI', df.ta.cci(length=20))
    safe_ind('ADX', df.ta.adx(length=14)['ADX_14'])
    safe_ind('WILLR', df.ta.willr(length=14))
    safe_ind('OBV', df.ta.obv())

    return df.iloc[-3:]

def get_tradingview_analysis_enhanced(symbol_pair, interval_str):
    interval_map = {
        "1m": Interval.INTERVAL_1_MINUTE, "5m": Interval.INTERVAL_5_MINUTES,
        "15m": Interval.INTERVAL_15_MINUTES, "1h": Interval.INTERVAL_1_HOUR,
        "4h": Interval.INTERVAL_4_HOURS, "1d": Interval.INTERVAL_1_DAY,
        "1w": Interval.INTERVAL_1_WEEK, "1M": Interval.INTERVAL_1_MONTH
    }
    tv_interval = interval_map.get(interval_str, Interval.INTERVAL_1_HOUR)

    try:
        handler = TA_Handler(symbol=symbol_pair, screener="crypto", exchange="BINANCE", interval=tv_interval)
        analysis = handler.get_analysis()
    except Exception:
        try:
            handler = TA_Handler(symbol=symbol_pair, screener="crypto", exchange="GATEIO", interval=tv_interval)
            analysis = handler.get_analysis()
        except Exception:
            return None

    if not analysis: return None

    ind = analysis.indicators
    summ = analysis.summary

    return {
        'source': 'TradingView',
        'close': ind.get('close', 0),
        'volume': ind.get('volume', 0),
        'RSI': ind.get('RSI', 0),
        'MFI': ind.get('MFI', 0) or 0,
        'CCI': ind.get('CCI20', 0),
        'ADX': ind.get('ADX', 0),
        'WR': ind.get('W.R', 0),
        'OBV': ind.get('OBV', 0) or ind.get('volume', 0),

        'Pivot': ind.get('Pivot.M.Classic.Middle', 0),
        'R1': ind.get('Pivot.M.Classic.R1', 0), 'R2': ind.get('Pivot.M.Classic.R2', 0), 'R3': ind.get('Pivot.M.Classic.R3', 0),
        'S1': ind.get('Pivot.M.Classic.S1', 0), 'S2': ind.get('Pivot.M.Classic.S2', 0), 'S3': ind.get('Pivot.M.Classic.S3', 0),

        'RECOMMENDATION': summ.get('RECOMMENDATION', 'NEUTRAL'),
        'BUY_SCORE': summ.get('BUY', 0),
        'SELL_SCORE': summ.get('SELL', 0),
        'NEUTRAL_SCORE': summ.get('NEUTRAL', 0),

        'MACD_hist': ind.get('MACD.hist', 0),
        'SMA_50': ind.get('SMA50', 0),
        'EMA_200': ind.get('EMA200', 0),
        'ATR': ind.get('ATR', 0)
    }

async def ta_command(update: Update, context: ContextTypes.DEFAULT_TYPE, override_source=None, override_args=None, skip_binance_check=False, force_new_message=False):
    user_id = update.effective_user.id
    is_callback = (update.callback_query is not None) and not force_new_message
    message = update.effective_message
    if force_new_message and update.callback_query:
        message = update.callback_query.message

    if not is_callback:
        registrar_uso_comando(user_id, 'ta')

    if override_args:
        symbol_base, pair, timeframe = override_args
        full_symbol = f"{symbol_base}{pair}"
        target_source = override_source
    else:
        if not context.args:
            await message.reply_text(
                "⚠️ *Formato incorrecto*\n\nUso: `/ta <SYMBOL> [PAR] [TIME] [TV]`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        raw_args = [arg.upper() for arg in context.args]
        target_source = "TV" if "TV" in raw_args else "BINANCE"
        if "TV" in raw_args: raw_args.remove("TV")

        symbol_base = raw_args[0]
        pair = "USDT"
        timeframe = "1h"

        if len(raw_args) > 1:
            for arg in raw_args[1:]:
                if arg[-1].lower() in ['m', 'h', 'd', 'w']:
                    timeframe = arg.lower()
                else:
                    pair = arg
        full_symbol = f"{symbol_base}{pair}"

    if is_callback:
        if target_source == "BINANCE" and not skip_binance_check:
            loop = asyncio.get_running_loop()
            check_df = await loop.run_in_executor(None, get_binance_klines, full_symbol, timeframe, 50)
            if check_df is None or check_df.empty:
                await update.callback_query.answer("❌ No disponible en Binance Local", show_alert=True)
                return
    else:
        if not is_callback:
            msg_wait = await message.reply_text(
                f"⏳ _Analizando {full_symbol} ({timeframe})..._",
                parse_mode=ParseMode.MARKDOWN
            )

    loop = asyncio.get_running_loop()
    final_data = {}
    data_source_display = ""
    reasons_list = []
    signal_emoji, signal_text = "⚖️", "NEUTRAL"
    score_buy, score_sell = 0, 0
    df_result = None

    if target_source == "BINANCE":
        df_result = await loop.run_in_executor(None, get_binance_klines, full_symbol, timeframe)

        if df_result is not None:
            data_source_display = "Binance (Local PRO)"

            last_3 = await loop.run_in_executor(None, calculate_table_indicators, df_result.copy())

            analyzer = BTCAdvancedAnalyzer(df_result)
            sig, emo, (sb, ss), reasons = analyzer.get_momentum_signal()
            curr_vals = analyzer.get_current_values()

            signal_emoji, signal_text = emo, sig
            score_buy, score_sell = sb, ss
            reasons_list = reasons

            curr = last_3.iloc[-1]
            prev = last_3.iloc[-2]
            pprev = last_3.iloc[-3]

            last_10 = df_result.tail(10)
            h, l, c = last_10['high'].max(), last_10['low'].min(), df_result['close'].iloc[-1]
            pivot_val = (h + l + c) / 3
            rango_val = h - l

            final_data = {
                'close': curr['close'], 'volume': curr['volume'], 'ATR': curr_vals.get('ATR', 0),
                'RSI_list': [curr.get('RSI', 0), prev.get('RSI', 0), pprev.get('RSI', 0)],
                'MFI_list': [curr.get('MFI', 0), prev.get('MFI', 0), pprev.get('MFI', 0)],
                'CCI_list': [curr.get('CCI', 0), prev.get('CCI', 0), pprev.get('CCI', 0)],
                'ADX_list': [curr.get('ADX', 0), prev.get('ADX', 0), pprev.get('ADX', 0)],
                'WR_list':  [curr.get('WILLR', 0), prev.get('WILLR', 0), pprev.get('WILLR', 0)],
                'OBV_list': [curr.get('OBV', 0), prev.get('OBV', 0), pprev.get('OBV', 0)],
                'MACD_hist': curr_vals.get('MACD_HIST', 0),
                'SMA_50': curr_vals.get('EMA_50', 0),

                'Pivot': pivot_val,
                'Rango': rango_val
            }

            p = final_data['Pivot']
            r = final_data['Rango']

            final_data.update({
                'R1': p + (r * 0.382),
                'R2': p + (r * 0.618),
                'R3': p + (r * 1.272),
                'S1': p - (r * 0.382),
                'S2': p - (r * 0.618),
                'S3': p - (r * 1.272)
            })

    used_tv = False
    if df_result is None:
        used_tv = True
        tv_data = await loop.run_in_executor(None, get_tradingview_analysis_enhanced, full_symbol, timeframe)

        if tv_data:
            data_source_display = "TradingView API"
            final_data = tv_data

            rec = final_data.get('RECOMMENDATION', '')
            if "STRONG_BUY" in rec: signal_emoji, signal_text = "🚀", "COMPRA FUERTE"
            elif "BUY" in rec: signal_emoji, signal_text = "🐂", "COMPRA"
            elif "STRONG_SELL" in rec: signal_emoji, signal_text = "🐻", "VENTA FUERTE"
            elif "SELL" in rec: signal_emoji, signal_text = "📉", "VENTA"

            score_buy = final_data.get('BUY_SCORE', 0)
            score_sell = final_data.get('SELL_SCORE', 0)

            for k in ['RSI', 'MFI', 'CCI', 'ADX', 'WR', 'OBV']:
                val = final_data.get(k, 0) or 0
                final_data[f'{k}_list'] = [val, 0, 0]
        else:
            err_txt = f"❌ No se encontraron datos para {full_symbol} ni en Binance ni en TV."
            if is_callback:
                await update.callback_query.answer("❌ Datos no encontrados", show_alert=True)
            else:
                await msg_wait.edit_text(err_txt, parse_mode=ParseMode.MARKDOWN)
            return

    def fmt_cell(val, width=7):
        if val is None or pd.isna(val) or val == 0: return "   --  ".center(width)
        try:
            f = float(val)
            if abs(f) > 10000: return f"{f/1000:.1f}k".rjust(width)
            elif abs(f) > 999: return f"{f:.0f}".rjust(width)
            else: return f"{f:.2f}".rjust(width)
        except (ValueError, TypeError): return "   --  ".center(width)

    table_msg = "```text\nIND     ACTUAL   PREVIO     ANT.\n──────  ───────  ───────  ───────\n"
    rows = [("RSI", 'RSI_list'), ("MFI", 'MFI_list'), ("CCI", 'CCI_list'), ("WR%", 'WR_list'), ("ADX", 'ADX_list'), ("OBV", 'OBV_list')]
    for l, k in rows:
        v = final_data.get(k, [0,0,0])
        table_msg += f"{l:<6} {fmt_cell(v[0])}  {fmt_cell(v[1])}  {fmt_cell(v[2])}\n"
    table_msg += "```"

    price = final_data.get('close', 0)

    sr = {}
    kijun_val = 0
    fib_val = 0
    zone = "⚖️ NEUTRAL (TV)"
    kijun_icon = "➖"
    kijun_label = "N/A"
    fib_label = "N/A"

    if 'analyzer' in locals():
        sr = analyzer.get_support_resistance_dynamic()

        kijun_val = sr.get('KIJUN', 0)
        if price > kijun_val:
            kijun_label = "Soporte Dinámico"
            kijun_icon = "🛡️"
        else:
            kijun_label = "Resistencia Dinámica"
            kijun_icon = "🚧"

        fib_val = sr.get('FIB_618', 0)
        if price > fib_val:
            fib_label = "Zona de Rebote (Bullish)"
        else:
            fib_label = "Techo de Tendencia (Bearish)"

        zone = sr.get('status_zone', "⚖️ NEUTRAL")

    price = final_data.get('close', 0)
    macd_s = "Bullish 🟢" if final_data.get('MACD_hist', 0) > 0 else "Bearish 🔴"
    trend_s = "Alcista" if price > final_data.get('SMA_50', 0) else "Bajista"

    msg = (
        f"📊 *Análisis Técnico: {full_symbol}*\n"
        f"—————————————————\n"
        f"⏱ *{timeframe}* | 📡 *{data_source_display}*\n\n"
        f"{signal_emoji} *SEÑAL:* `{signal_text}`\n"
        f"⚖️ *Score:* {score_buy} Compra 🆚 {score_sell} Venta\n\n"
        f"💰 *Precio:* `${price:,.4f}`\n"
        f"📉 *ATR:* `{final_data.get('ATR', 0) or 0:.4f}`\n"
        f"•\n{table_msg}•\n"
        f"🧐 *Diagnóstico de Momentum*\n"
        f"🌊 *Tendencia:* {trend_s}\n"
        f"❌ *MACD:* {macd_s}\n"
        f"*Confluencia y Estado:*\n"
        f"📍 *Zona:* `{zone}`\n"
        f"☁️ *Ichimoku:* `${kijun_val:,.0f}`\n"
        f"   ↳ _{kijun_icon} {kijun_label}_\n"
        f"🟡 *FIB 0.618:* `${fib_val:,.0f}`\n"
        f"   ↳ _📐 {fib_label}_\n\n"
    )
    if reasons_list: msg += f"💡 *Nota:* _{reasons_list[0]}_\n"

    msg += (
        f"\n🛡 *Niveles (Pivotes)*\n"
        f"R3: `${final_data.get('R3', 0):,.4f}`\n"
        f"R2: `${final_data.get('R2', 0):,.4f}`\n"
        f"R1: `${final_data.get('R1', 0):,.4f}`\n"
        f"🎯 *Pivot: ${final_data.get('Pivot', 0):,.4f}*\n"
        f"S1: `${final_data.get('S1', 0):,.4f}`\n"
        f"S2: `${final_data.get('S2', 0):,.4f}`\n"
        f"S3: `${final_data.get('S3', 0):,.4f}`\n"
    )
    msg += "\n_v2.1 Experimental_"

    # Inyectar bloque de anuncio (safe_append omite el ad si el mensaje ya
    # viene largo, así que /ta nunca se corta por esto).
    api_client_for_ad = context.bot_data.get("api_client")
    if api_client_for_ad:
        ad_block = await get_ad_block(api_client_for_ad)
        msg = safe_append(msg, ad_block)

    kb = []
    current_source = "TV" if used_tv else "BINANCE"

    if used_tv:
        btn_data = f"ta_switch|BINANCE|{symbol_base}|{pair}|{timeframe}"
        kb.append([InlineKeyboardButton("🦁 Ver Local (Binance)", callback_data=btn_data)])
    else:
        btn_data = f"ta_switch|TV|{symbol_base}|{pair}|{timeframe}"
        kb.append([InlineKeyboardButton("📊 Ver en TradingView", callback_data=btn_data)])

    kb.append([
        InlineKeyboardButton("📊 Ver Gráfico", callback_data=f"graf_from_ta|{symbol_base}|{pair}|{timeframe}")
    ])

    kb.append([
        InlineKeyboardButton("🤖 Análisis IA Profesional", callback_data=f"ai_analyze|{current_source}|{symbol_base}|{pair}|{timeframe}")
    ])

    levels_for_alert = {
        lvl: (final_data.get(lvl, 0) or 0) for lvl in ("Pivot", "R1", "R2", "R3", "S1", "S2", "S3")
    }
    alert_token = cache_alert_levels(
        context, symbol_base, pair, timeframe, levels_for_alert,
        kind="ta", render_source=current_source,
    )
    kb.append([
        InlineKeyboardButton("🔔 Crear alerta", callback_data=f"alert_menu|{alert_token}")
    ])

    reply_markup = InlineKeyboardMarkup(kb)

    if is_callback:
        try:
            await update.callback_query.edit_message_text(text=msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        except Exception:
            pass
    else:
        await msg_wait.edit_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


async def ai_analysis_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '🤖 Análisis IA Profesional' button from /ta command."""
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer("🧠 Analizando datos con IA...")

    try:
        parts = query.data.split("|")
        if len(parts) < 5:
            await query.answer("❌ Datos de callback inválidos", show_alert=True)
            return

        _, source, symbol, pair, timeframe = parts[:5]
        full_symbol = f"{symbol}{pair}"

        await query.message.reply_chat_action("typing")

        # Extract original technical report from the message
        original_report_text = query.message.caption if query.message.caption else query.message.text
        if not original_report_text:
            await query.message.reply_text(
                "❌ No se pudo leer el reporte técnico en pantalla.\n"
                "Por favor, genera un nuevo análisis con /ta.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        source_context = (
            "FUENTE: TradingView (Consenso de indicadores y medias móviles)."
            if source == "TV"
            else "FUENTE: Binance Local (Cálculo matemático directo del Bot)."
        )
        final_text_for_ai = f"{source_context}\n\n{original_report_text}"

        # Call Groq API (async with retry)
        logger.info("🔍 Requesting Groq analysis for %s %s from user %d", full_symbol, timeframe, user_id)
        ai_response = await get_groq_crypto_analysis(
            symbol=full_symbol,
            timeframe=timeframe,
            technical_report_text=final_text_for_ai,
            source=source,
        )

        # Send AI analysis as a reply
        header = (
            f"🤖 *Panorama IA* (_Experimental_)\n"
            f"{'📡' if source == 'TV' else '📊'} *{source}* | Moneda: *{full_symbol}* ({timeframe})\n"
            f"—————————————————\n"
        )

        await query.message.reply_text(
            header + ai_response,
            parse_mode=ParseMode.MARKDOWN,
            reply_to_message_id=query.message.message_id,
        )

        logger.info("✅ AI analysis delivered to user %d for %s %s", user_id, full_symbol, timeframe)

    except Exception as e:
        logger.exception("Unexpected error in ai_analysis_callback for user %d: %s", user_id, e)
        try:
            await query.message.reply_text(
                "❌ Error inesperado al generar análisis IA.\n"
                "Por favor, intenta de nuevo en unos minutos.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass  # Give up gracefully


async def graf_from_ta_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📊 Generando gráfico...")

    try:
        parts = query.data.split("|")
        if len(parts) < 4:
            await query.answer("❌ Datos inválidos", show_alert=True)
            return

        _, base, pair, timeframe = parts[0], parts[1], parts[2], parts[3]
        context.args = [base, pair, timeframe]

        from src.handlers.trading import _do_graf
        await _do_graf(update, context, base=base.upper(), quote=pair.upper(), timeframe=timeframe.lower(), is_callback=True)
    except Exception as e:
        print(f"Error en graf_from_ta_callback: {e}")
        await query.answer("❌ Error al generar el gráfico", show_alert=True)


async def ta_switch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    data = query.data.split("|")
    if len(data) < 5:
        await query.answer("❌ Datos corruptos", show_alert=True)
        return

    target = data[1]
    symbol = data[2]
    pair = data[3]
    timeframe = data[4]

    await ta_command(update, context, override_source=target, override_args=[symbol, pair, timeframe])
