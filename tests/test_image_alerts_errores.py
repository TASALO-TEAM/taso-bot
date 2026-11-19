"""F7 / H-056: las alertas de imagen no muestran al usuario el texto crudo de una excepcion."""

import asyncio
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.handlers import image_alerts

SECRETO = "http://10.0.0.5:8040/api/v1/images/alerts/1/disable detalle-interno"
FUENTE = Path(image_alerts.__file__).read_text(encoding="utf-8")


def _update():
    q = MagicMock()
    q.data = "alert_disable"
    q.answer = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    u.effective_user.id = 1
    return u


def _textos(mock_edit):
    return [str(c.args[1]) for c in mock_edit.call_args_list]


def _cliente(post):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=MagicMock(post=post))
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def test_error_http_no_muestra_detalle():
    post = AsyncMock(side_effect=httpx.ConnectError(SECRETO))
    with patch.object(image_alerts.httpx, "AsyncClient", return_value=_cliente(post)), \
            patch.object(image_alerts, "_safe_edit_message", new=AsyncMock()) as edit:
        asyncio.run(image_alerts.alert_disable_callback(_update(), MagicMock()))
    textos = _textos(edit)
    assert textos and all("detalle-interno" not in t and "10.0.0.5" not in t for t in textos)


def test_api_ok_false_no_muestra_detalle():
    resp = MagicMock()
    resp.json.return_value = {"ok": False, "error": SECRETO}
    post = AsyncMock(return_value=resp)
    with patch.object(image_alerts.httpx, "AsyncClient", return_value=_cliente(post)), \
            patch.object(image_alerts, "_safe_edit_message", new=AsyncMock()) as edit:
        asyncio.run(image_alerts.alert_disable_callback(_update(), MagicMock()))
    textos = _textos(edit)
    assert textos and all("detalle-interno" not in t and "API error" not in t for t in textos)


def test_timeout_de_lectura_no_deja_mensaje_vacio():
    post = AsyncMock(side_effect=httpx.ReadTimeout(""))
    with patch.object(image_alerts.httpx, "AsyncClient", return_value=_cliente(post)), \
            patch.object(image_alerts, "_safe_edit_message", new=AsyncMock()) as edit:
        asyncio.run(image_alerts.alert_disable_callback(_update(), MagicMock()))
    assert all(len(t.strip()) > 12 and not t.rstrip().endswith(":") for t in _textos(edit))


def test_ninguna_respuesta_interpola_la_excepcion():
    """Guardia estatica: ningun f-string de respuesta incluye str(e) ni str(http_err)."""
    assert not re.search(r'f"[^"\n]*\{str\((e|http_err)\)\}', FUENTE)
