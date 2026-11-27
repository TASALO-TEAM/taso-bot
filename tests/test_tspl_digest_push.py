# tests/test_tspl_digest_push.py
"""Empuje del digest de /tspl a taso-api, para que taso-gcg lo publique.

- TasaloApiClient.admin_put_tspl_digest(): un PUT con X-API-Key; devuelve True/False y nunca lanza.
- _push_digest_to_api(): arma el texto de Telegram y el markdown del blog con los mismos
  constructores que /tspl y /tspl blog, y los empuja. Nunca lanza.
- generate_and_cache_tspl_digest(): empuja despues de cachear.
"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import src.services.tspl_digest_scheduler as scheduler
from src.api_client import TasaloApiClient

URL = "http://api.test/api/v1/tspl/digest/latest"
GENERATED_AT = "2026-11-27T11:00:05+00:00"


def _cliente(handler) -> TasaloApiClient:
    """Cliente real con un transporte falso: se comprueba la peticion HTTP exacta, sin red."""
    cliente = TasaloApiClient(api_url="http://api.test", admin_key="clave-test", timeout=5)
    cliente._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return cliente


# -- admin_put_tspl_digest ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_digest_envia_put_con_clave_y_cuerpo():
    vistas = []

    def handler(request):
        vistas.append(request)
        return httpx.Response(200, json={"ok": True})

    cliente = _cliente(handler)
    ok = await cliente.admin_put_tspl_digest("texto telegram", "# blog", GENERATED_AT)
    await cliente.close()

    assert ok is True
    (peticion,) = vistas
    assert peticion.method == "PUT"
    assert str(peticion.url) == URL
    assert peticion.headers["X-API-Key"] == "clave-test"
    assert json.loads(peticion.content) == {
        "telegram_text": "texto telegram",
        "blog_markdown": "# blog",
        "generated_at": GENERATED_AT,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", [401, 422, 500])
async def test_put_digest_devuelve_false_si_la_api_responde_error(estado):
    cliente = _cliente(lambda request: httpx.Response(estado, json={"detail": "x"}))
    assert await cliente.admin_put_tspl_digest("t", None, GENERATED_AT) is False
    await cliente.close()


@pytest.mark.asyncio
async def test_put_digest_devuelve_false_si_no_hay_red():
    def handler(request):
        raise httpx.ConnectError("sin red")

    cliente = _cliente(handler)
    assert await cliente.admin_put_tspl_digest("t", None, GENERATED_AT) is False
    await cliente.close()


# -- _push_digest_to_api --------------------------------------------------------------------


def _handler_falso(snapshot={"btc": 1}, put_ok=True):
    """Sustituye lo que _push_digest_to_api importa de src.handlers.tspl."""
    return SimpleNamespace(
        _get_or_build_market_snapshot=AsyncMock(return_value=snapshot),
        _build_message=MagicMock(return_value="TEXTO-TG"),
        _build_blog_content=MagicMock(return_value="TEXTO-BLOG"),
        _tspl_api=SimpleNamespace(admin_put_tspl_digest=AsyncMock(return_value=put_ok)),
    )


def _con_handler(handler, clave="clave-test"):
    return (
        patch("src.services.tspl_digest_scheduler.get_settings", return_value=SimpleNamespace(tasalo_admin_key=clave)),
        # Atributos del modulo real: parchear sys.modules no vale si otro test ya lo importo.
        patch.multiple(
            "src.handlers.tspl",
            _get_or_build_market_snapshot=handler._get_or_build_market_snapshot,
            _build_message=handler._build_message,
            _build_blog_content=handler._build_blog_content,
            _tspl_api=handler._tspl_api,
        ),
    )


@pytest.mark.asyncio
async def test_push_envia_texto_telegram_blog_y_hora_de_generacion():
    handler = _handler_falso()
    digest = {"items": [], "lede": "hola"}
    ajustes, modulos = _con_handler(handler)
    with ajustes, modulos:
        await scheduler._push_digest_to_api(digest)

    handler._build_message.assert_called_once_with(digest, {"btc": 1})
    handler._build_blog_content.assert_called_once_with(digest, {"btc": 1})
    kwargs = handler._tspl_api.admin_put_tspl_digest.await_args.kwargs
    assert kwargs["telegram_text"] == "TEXTO-TG"
    assert kwargs["blog_markdown"] == "TEXTO-BLOG"
    assert datetime.fromisoformat(kwargs["generated_at"]).tzinfo is not None


@pytest.mark.asyncio
async def test_push_sin_clave_de_admin_no_hace_nada():
    handler = _handler_falso()
    ajustes, modulos = _con_handler(handler, clave="")
    with ajustes, modulos:
        await scheduler._push_digest_to_api({"items": []})

    handler._get_or_build_market_snapshot.assert_not_awaited()
    handler._tspl_api.admin_put_tspl_digest.assert_not_awaited()


@pytest.mark.asyncio
async def test_push_sin_snapshot_de_mercado_no_publica_un_post_a_medias():
    handler = _handler_falso(snapshot=None)
    ajustes, modulos = _con_handler(handler)
    with ajustes, modulos:
        await scheduler._push_digest_to_api({"items": []})

    handler._tspl_api.admin_put_tspl_digest.assert_not_awaited()


@pytest.mark.asyncio
async def test_push_no_lanza_si_la_api_responde_error():
    handler = _handler_falso(put_ok=False)
    ajustes, modulos = _con_handler(handler)
    with ajustes, modulos:
        await scheduler._push_digest_to_api({"items": []})  # no debe lanzar


@pytest.mark.asyncio
async def test_push_no_lanza_si_algo_revienta():
    handler = _handler_falso()
    handler._get_or_build_market_snapshot = AsyncMock(side_effect=RuntimeError("mercado caido"))
    ajustes, modulos = _con_handler(handler)
    with ajustes, modulos:
        await scheduler._push_digest_to_api({"items": []})  # no debe lanzar


# -- generate_and_cache_tspl_digest empuja despues de cachear -------------------------------


@pytest.mark.asyncio
async def test_generate_empuja_el_digest_despues_de_cachearlo():
    digest = {"items": [{"titulo": "t"}]}
    news_client = MagicMock()
    news_client.get_crypto_news = AsyncMock(
        return_value=[{"title": f"Noticia {i}", "description": "d", "source_name": "S"} for i in range(5)]
    )
    orden = []

    with (
        patch("src.services.tspl_digest_scheduler.get_newsdata_client", return_value=news_client),
        patch("src.services.tspl_digest_scheduler._fetch_tspl_market_context", AsyncMock(return_value={})),
        patch("src.services.tspl_digest_scheduler.get_groq_tspl_digest", AsyncMock(return_value=digest)),
        patch("src.services.tspl_digest_scheduler.cache") as mock_cache,
        patch(
            "src.services.tspl_digest_scheduler._push_digest_to_api",
            AsyncMock(side_effect=lambda d: orden.append("push")),
        ) as mock_push,
    ):
        mock_cache.set.side_effect = lambda *a, **k: orden.append("cache")
        resultado = await scheduler.generate_and_cache_tspl_digest()

    assert resultado is digest
    mock_push.assert_awaited_once_with(digest)
    assert orden == ["cache", "push"]


@pytest.mark.asyncio
async def test_generate_sin_digest_no_empuja():
    news_client = MagicMock()
    news_client.get_crypto_news = AsyncMock(return_value=[])

    with (
        patch("src.services.tspl_digest_scheduler.get_newsdata_client", return_value=news_client),
        patch("src.services.tspl_digest_scheduler._push_digest_to_api", AsyncMock()) as mock_push,
    ):
        assert await scheduler.generate_and_cache_tspl_digest() is None

    mock_push.assert_not_awaited()
