"""Devolver al SO la memoria libre del heap tras tareas pesadas (VPS de 2 GB)."""
from unittest.mock import MagicMock, patch

from src.utils import memoria


def _reset():
    memoria._libc = None
    memoria._intentado = False


def test_fuera_de_linux_no_hace_nada():
    _reset()
    with patch.object(memoria.sys, "platform", "win32"), patch.object(memoria.ctypes, "CDLL") as cdll:
        assert memoria.liberar_memoria() is False
    cdll.assert_not_called()


def test_en_linux_llama_malloc_trim_una_vez_por_llamada():
    _reset()
    libc = MagicMock()
    with patch.object(memoria.sys, "platform", "linux"), patch.object(memoria.ctypes, "CDLL", return_value=libc) as cdll:
        assert memoria.liberar_memoria() is True
        assert memoria.liberar_memoria() is True
    libc.malloc_trim.assert_called_with(0)
    assert libc.malloc_trim.call_count == 2
    assert cdll.call_count == 1  # la libreria se carga una sola vez


def test_si_no_hay_libc_devuelve_false_sin_lanzar_y_no_reintenta():
    _reset()
    with patch.object(memoria.sys, "platform", "linux"), patch.object(memoria.ctypes, "CDLL", side_effect=OSError("musl")) as cdll:
        assert memoria.liberar_memoria() is False
        assert memoria.liberar_memoria() is False
    assert cdll.call_count == 1


def test_si_malloc_trim_falla_no_lanza():
    _reset()
    libc = MagicMock()
    libc.malloc_trim.side_effect = AttributeError("sin malloc_trim")
    with patch.object(memoria.sys, "platform", "linux"), patch.object(memoria.ctypes, "CDLL", return_value=libc):
        assert memoria.liberar_memoria() is False
