"""Proveedor de IA y modelo elegidos por un admin (F5-T7).

Estado minimo y persistente (JSON atomico en data/ai_config.json): proveedor
principal, proveedor de respaldo y modelo de NVIDIA. Sin dependencias de red.
"""

import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

PROVEEDORES = ("groq", "nvidia")
NOMBRES = {"groq": "Groq", "nvidia": "NVIDIA"}

# (id, etiqueta, nota). El primero es el predeterminado. Solo estos modelos son
# elegibles: salieron de probar el catalogo real con una consulta de resumen
# cripto (2026-11-18). Los demas del catalogo se descartaron por lentos o por
# gastar el presupuesto de tokens en razonamiento y devolver texto vacio.
MODELOS_NVIDIA = (
    ("nvidia/nemotron-3-ultra-550b-a55b", "Nemotron 3 Ultra", "rapido, recomendado"),
    ("minimaxai/minimax-m3.1-flash", "MiniMax M3.1 Flash", "correcto, mas lento"),
    ("google/gemma-4-31b-it", "Gemma 4 31B", "sin razonamiento, mas lento"),
)

_PATH = Path(__file__).resolve().parents[2] / "data" / "ai_config.json"
_lock = threading.Lock()
_cache: dict | None = None


def _defaults() -> dict:
    return {"primary": "groq", "backup": "nvidia", "nvidia_model": MODELOS_NVIDIA[0][0]}


def _valido(d) -> dict:
    """Mezcla `d` con los defaults descartando cualquier valor fuera de lo permitido."""
    out = _defaults()
    if not isinstance(d, dict):
        return out
    if d.get("primary") in PROVEEDORES:
        out["primary"] = d["primary"]
    if d.get("backup") in (*PROVEEDORES, "none"):
        out["backup"] = d["backup"]
    if d.get("nvidia_model") in {m[0] for m in MODELOS_NVIDIA}:
        out["nvidia_model"] = d["nvidia_model"]
    return out


def get() -> dict:
    global _cache
    with _lock:
        if _cache is None:
            try:
                _cache = _valido(json.loads(_PATH.read_text(encoding="utf-8")))
            except FileNotFoundError:
                _cache = _defaults()
            except Exception as e:  # archivo corrupto: se usan los defaults
                logger.warning("ai_config: archivo ilegible (%s); se usan los valores por defecto", type(e).__name__)
                _cache = _defaults()
        return dict(_cache)


def _guardar(cfg: dict) -> None:
    global _cache
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.replace(tmp, _PATH)
    _cache = cfg


def orden() -> list[str]:
    """Proveedores a intentar, en orden: principal y despues el respaldo si es otro."""
    cfg = get()
    res = [cfg["primary"]]
    if cfg["backup"] in PROVEEDORES and cfg["backup"] != cfg["primary"]:
        res.append(cfg["backup"])
    return res


def set_primary(prov: str) -> bool:
    if prov not in PROVEEDORES:
        return False
    cfg = get()
    cfg["primary"] = prov
    if cfg["backup"] == prov:
        cfg["backup"] = "none"
    with _lock:
        _guardar(cfg)
    return True


def set_backup(prov: str) -> bool:
    """`prov` en PROVEEDORES o 'none'. El respaldo no puede ser el principal."""
    cfg = get()
    if prov not in (*PROVEEDORES, "none") or prov == cfg["primary"]:
        return False
    cfg["backup"] = prov
    with _lock:
        _guardar(cfg)
    return True


def set_model(indice: int) -> bool:
    if not isinstance(indice, int) or not 0 <= indice < len(MODELOS_NVIDIA):
        return False
    cfg = get()
    cfg["nvidia_model"] = MODELOS_NVIDIA[indice][0]
    with _lock:
        _guardar(cfg)
    return True


def etiqueta_modelo(model_id: str) -> str:
    for mid, etiqueta, _ in MODELOS_NVIDIA:
        if mid == model_id:
            return etiqueta
    return model_id
