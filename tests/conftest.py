"""Entorno minimo para correr la suite en un clon limpio, sin .env ni red.

TELEGRAM_BOT_TOKEN es el unico campo obligatorio de Settings. Una variable de
entorno tiene prioridad sobre .env, asi que los tests nunca usan el token real.
"""

import os

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TOKEN-FALSO-SOLO-TESTS")
# Clave de admin vacia: con un .env real, el empuje del digest de /tspl haria un PUT contra la
# API de verdad y pisaria el digest de produccion con datos de prueba.
os.environ.setdefault("TASALO_ADMIN_KEY", "")


@pytest.fixture(autouse=True)
def _restaurar_entorno():
    # test_config.py hace os.environ.pop(...) en sus finally sin devolver el
    # valor previo; sin esto, los tests siguientes (y los subprocesos) pierden
    # el token (H-031).
    antes = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(antes)
