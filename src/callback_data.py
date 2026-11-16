"""callback_data v2 (F6-T3, D-006): `ns:arg:arg`, un solo separador, <= 64 bytes.

El namespace es solo [a-z0-9]+ (sin "_"): asi un callback v2 nunca se confunde
con los formatos viejos, que siempre llevan "_" antes de cualquier ":" o "|"
(start_tasalo, alert_lvl|tok|1, status_cmd:1:24h). Los viejos siguen
funcionando por el resolutor de callback_router.
"""

import re

SEP = ":"
MAX_BYTES = 64  # limite de Telegram para callback_data
_NS = re.compile(r"[a-z0-9]+")


def build(ns: str, *args) -> str:
    """Arma un callback v2. ValueError si no es valido o pasa de 64 bytes."""
    if not _NS.fullmatch(ns):
        raise ValueError(f"namespace invalido: {ns!r}")
    partes = [str(a) for a in args]
    if any(SEP in p for p in partes):
        raise ValueError("un argumento no puede contener ':'")
    data = SEP.join((ns, *partes))
    if len(data.encode()) > MAX_BYTES:
        raise ValueError(f"callback_data de {len(data.encode())} bytes (maximo {MAX_BYTES})")
    return data


def parse_v2(data: str) -> tuple[str, tuple[str, ...]] | None:
    """(namespace, args) si `data` es v2; None si es el formato viejo."""
    ns, sep, resto = data.partition(SEP)
    if not _NS.fullmatch(ns):
        return None
    return ns, tuple(resto.split(SEP)) if sep else ()
