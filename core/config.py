# core/config.py
# Minimal configuration for BBAlert-derived commands.

import os
from typing import List

ADMIN_CHAT_IDS: List[int] = []
_admin_str = os.getenv("ADMIN_CHAT_IDS", "")
if _admin_str:
    try:
        ADMIN_CHAT_IDS = [int(x.strip()) for x in _admin_str.split(",") if x.strip()]
    except Exception:
        ADMIN_CHAT_IDS = []

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
CMC_API_KEY_CONTROL = os.getenv("CMC_API_KEY_CONTROL", "")
CMC_API_KEY_ALERTA = os.getenv("CMC_API_KEY_ALERTA", "")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
ADS_PATH = os.path.join(DATA_DIR, 'ads.json')
