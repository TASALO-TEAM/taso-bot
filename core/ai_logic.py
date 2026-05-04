# core/ai_logic.py
# Copia de BBAlert — análisis con Groq LLM

import requests
import json
import math
from core.config import GROQ_API_KEY

def clean_data(data):
    cleaned = {}
    for k, v in data.items():
        if isinstance(v, (float, int)):
            if math.isnan(v) or math.isinf(v):
                cleaned[k] = "N/A"
            else:
                cleaned[k] = round(v, 4)
        else:
            cleaned[k] = v
    return cleaned

def escape_markdown(text):
    if not text:
        return ""
    return text.replace("*", "").replace("_", "").replace("`", "").replace("[", "(").replace("]", ")")

def get_groq_crypto_analysis(symbol, timeframe, technical_report_text):
    if not GROQ_API_KEY:
        return "⚠️ Error: Falta configurar la GROQ_API_KEY."

    prompt = (
        f"Eres un Analista Experto en Inversiones Institucionales, Trading y criptomonedas."
        f"Analiza este reporte técnico de {symbol} ({timeframe}) y escribe un Informe Completo en base a los datos del reporte.\n\n"
        f"--- REPORTE TÉCNICO ---\n"
        f"{technical_report_text}\n"
        f"--- FIN REPORTE ---\n\n"
    )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "Eres un asistente que analiza reportes técnicos de criptomonedas y produce narrativas claras, profesionales, en español."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return "⚠️ No se recibió respuesta de la IA."
        content = choices[0].get("message", {}).get("content", "").strip()
        if not content:
            return "⚠️ La IA devolvió contenido vacío."
        return content
    except requests.exceptions.HTTPError as e:
        return f"⚠️ Error HTTP de la IA: {e}"
    except Exception as e:
        return f"⚠️ Error procesando análisis IA: {e}"
