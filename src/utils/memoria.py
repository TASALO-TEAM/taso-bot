"""Devuelve al sistema la memoria libre del heap de glibc.

Tras renderizar un mapa o un grafico (en hilos), Python deja el heap fragmentado y el
RSS no baja aunque los objetos ya esten liberados. En el VPS (2 GB, con swap en uso)
malloc_trim recupero ~15 MB de ~136 MB tras 20 renders. Solo Linux/glibc; en cualquier
otro sistema no hace nada.
"""
import ctypes
import sys

# shortcut: no se mide el tiempo de malloc_trim (ms con heap de ~100 MB); si algun dia
# bloquea el loop, moverlo a asyncio.to_thread.
_libc = None
_intentado = False


def liberar_memoria() -> bool:
    """True si pidio a glibc devolver memoria; False si no aplica o fallo (nunca lanza)."""
    global _libc, _intentado
    if not sys.platform.startswith("linux"):
        return False
    if not _intentado:
        _intentado = True
        try:
            _libc = ctypes.CDLL("libc.so.6")
        except OSError:
            _libc = None
    if _libc is None:
        return False
    try:
        _libc.malloc_trim(0)
    except Exception:
        return False
    return True
