# src/core/config.py
# Minimal configuration stub for BBAlert trading command integration.
# Reads environment variables where appropriate.

import os
from typing import List

# Telegram Bot token is already in taso-bot's src/config.py; we only need BBAlert-specific vars.

# Admin chat IDs (list of ints) — optional for our commands; BBAlert checks for admin access in some places.
ADMIN_CHAT_IDS: List[int] = []
_admin_str = os.getenv("ADMIN_CHAT_IDS", "")
if _admin_str:
    try:
        ADMIN_CHAT_IDS = [int(x.strip()) for x in _admin_str.split(",") if x.strip()]
    except Exception:
        ADMIN_CHAT_IDS = []

# GROQ API Key for AI analysis (optional; if missing, AI button will show error gracefully)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# CoinMarketCap API keys (only needed if we were using BBAlert's api_client; we are using taso-bot's crypto_client)
CMC_API_KEY_CONTROL = os.getenv("CMC_API_KEY_CONTROL", "")
CMC_API_KEY_ALERTA = os.getenv("CMC_API_KEY_ALERTA", "")

# Data directory (BBAlert expects a ./data folder). Not used heavily but kept for compatibility.
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

# Ads path (ads.json) — used by get_random_ad_text stub will be empty anyway
ADS_PATH = os.path.join(DATA_DIR, 'ads.json')
