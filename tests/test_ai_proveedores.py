"""F5-T7: proveedor de IA (Groq / NVIDIA) y modelo elegibles por un admin."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import src.core.ai_config as ai_config
import src.core.ai_logic as ai_logic


@pytest.fixture(autouse=True)
def _config_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_config, "_PATH", tmp_path / "ai_config.json")
    monkeypatch.setattr(ai_config, "_cache", None)


def _settings(nvidia="nvapi-test"):
    s = MagicMock()
    s.groq_api_key = "gsk_test"
    s.groq_api_keys = ["gsk_test"]
    s.nvidia_api_key = nvidia
    return s


OK = {"choices": [{"message": {"content": "hola"}}]}


# ── ai_config ────────────────────────────────────────────────────────────────

def test_defaults_groq_principal_nvidia_respaldo_modelo_recomendado():
    cfg = ai_config.get()
    assert cfg["primary"] == "groq"
    assert cfg["backup"] == "nvidia"
    assert cfg["nvidia_model"] == "nvidia/nemotron-3-ultra-550b-a55b"
    assert ai_config.orden() == ["groq", "nvidia"]


def test_cambios_persisten_en_disco(tmp_path):
    assert ai_config.set_primary("nvidia")
    assert ai_config.set_model(1)
    ai_config._cache = None  # simula reinicio
    cfg = ai_config.get()
    assert cfg["primary"] == "nvidia"
    assert cfg["nvidia_model"] == "minimaxai/minimax-m3.1-flash"
    assert json.loads((tmp_path / "ai_config.json").read_text())["primary"] == "nvidia"


def test_principal_igual_al_respaldo_desactiva_el_respaldo():
    assert ai_config.set_primary("nvidia")
    assert ai_config.get()["backup"] == "none"
    assert ai_config.orden() == ["nvidia"]


def test_respaldo_no_puede_ser_el_principal_ni_algo_invalido():
    assert not ai_config.set_backup("groq")
    assert not ai_config.set_backup("openai")
    assert ai_config.set_backup("none")
    assert ai_config.orden() == ["groq"]


def test_modelo_solo_de_la_lista_curada():
    assert not ai_config.set_model(99)
    assert not ai_config.set_model(-1)
    assert not ai_config.set_primary("openai")


def test_archivo_corrupto_o_con_valores_ajenos_cae_a_defaults(tmp_path):
    (tmp_path / "ai_config.json").write_text("{no es json")
    assert ai_config.get()["primary"] == "groq"
    ai_config._cache = None
    (tmp_path / "ai_config.json").write_text(json.dumps({"primary": "x", "nvidia_model": "otro/modelo"}))
    cfg = ai_config.get()
    assert cfg["primary"] == "groq" and cfg["nvidia_model"] == ai_config.MODELOS_NVIDIA[0][0]


# ── despachador ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_principal_groq_responde_y_no_toca_nvidia():
    nv = AsyncMock(return_value=OK)
    with patch("src.core.ai_logic.settings", _settings()), \
         patch("src.core.ai_logic._call_groq_async", AsyncMock(return_value=OK)), \
         patch("src.core.ai_logic._call_nvidia_async", nv):
        assert await ai_logic._call_ai_async({"messages": []}) == OK
    nv.assert_not_called()


@pytest.mark.asyncio
async def test_si_groq_falla_responde_el_respaldo_nvidia():
    nv = AsyncMock(return_value=OK)
    with patch("src.core.ai_logic.settings", _settings()), \
         patch("src.core.ai_logic._call_groq_async", AsyncMock(side_effect=RuntimeError("x"))), \
         patch("src.core.ai_logic._call_nvidia_async", nv):
        assert await ai_logic._call_ai_async({"messages": []}) == OK
    nv.assert_awaited_once()


@pytest.mark.asyncio
async def test_sin_clave_de_nvidia_no_se_intenta_y_se_relanza_el_error_original():
    nv = AsyncMock(return_value=OK)
    with patch("src.core.ai_logic.settings", _settings(nvidia="")), \
         patch("src.core.ai_logic._call_groq_async", AsyncMock(side_effect=ValueError("original"))), \
         patch("src.core.ai_logic._call_nvidia_async", nv):
        with pytest.raises(ValueError, match="original"):
            await ai_logic._call_ai_async({"messages": []})
    nv.assert_not_called()


@pytest.mark.asyncio
async def test_clave_que_no_es_texto_no_cuenta_como_configurada():
    """Los tests viejos usan MagicMock como settings: no debe disparar red a NVIDIA."""
    s = MagicMock()
    s.groq_api_key = "gsk"
    s.groq_api_keys = ["gsk"]
    nv = AsyncMock(return_value=OK)
    with patch("src.core.ai_logic.settings", s), \
         patch("src.core.ai_logic._call_groq_async", AsyncMock(side_effect=ValueError("x"))), \
         patch("src.core.ai_logic._call_nvidia_async", nv):
        with pytest.raises(ValueError):
            await ai_logic._call_ai_async({"messages": []})
    nv.assert_not_called()


@pytest.mark.asyncio
async def test_principal_nvidia_y_groq_de_respaldo():
    ai_config.set_primary("nvidia")
    ai_config.set_backup("groq")
    g = AsyncMock(return_value=OK)
    with patch("src.core.ai_logic.settings", _settings()), \
         patch("src.core.ai_logic._call_nvidia_async", AsyncMock(side_effect=RuntimeError("x"))), \
         patch("src.core.ai_logic._call_groq_async", g):
        assert await ai_logic._call_ai_async({"messages": []}) == OK
    g.assert_awaited_once()


@pytest.mark.asyncio
async def test_nvidia_adapta_el_payload_y_normaliza_contenido_nulo():
    visto = {}

    def handler(request: httpx.Request) -> httpx.Response:
        visto["url"] = str(request.url)
        visto["auth"] = request.headers["authorization"]
        visto["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

    ai_config.set_model(1)
    payload = {
        "model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": "x"}],
        "temperature": 0.6, "max_completion_tokens": 512, "reasoning_effort": "low",
    }
    with patch("src.core.ai_logic.settings", _settings()):
        data = await ai_logic._call_nvidia_async(payload, transport=httpx.MockTransport(handler))

    assert visto["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert visto["auth"] == "Bearer nvapi-test"
    b = visto["body"]
    assert b["model"] == "minimaxai/minimax-m3.1-flash"
    assert "reasoning_effort" not in b and "max_completion_tokens" not in b
    assert b["max_tokens"] >= 2048  # los modelos de razonamiento gastan tokens pensando
    assert data["choices"][0]["message"]["content"] == ""  # .strip() de los llamadores no falla


@pytest.mark.asyncio
async def test_nvidia_error_http_no_filtra_la_clave_en_el_log(caplog):
    t = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "bad"}))
    with patch("src.core.ai_logic.settings", _settings(nvidia="nvapi-SECRETA")):
        with pytest.raises(httpx.HTTPStatusError):
            await ai_logic._call_nvidia_async({"messages": []}, transport=t)
    assert "nvapi-SECRETA" not in caplog.text


def test_las_reglas_prohiben_inventar_niveles_de_precio():
    from src.core.ia_identidad import REGLAS

    assert "niveles de precio" in REGLAS


# ── /ia (solo admin) ─────────────────────────────────────────────────────────

def _upd(user_id, data=None):
    q = MagicMock()
    q.from_user.id = user_id
    q.edit_message_text = AsyncMock()
    q.message.reply_text = AsyncMock()
    u = MagicMock()
    u.callback_query = q if data else None
    u.effective_user.id = user_id
    u.message.reply_text = AsyncMock()
    return u, q


def _datas(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


@pytest.mark.asyncio
async def test_comando_ia_rechaza_a_no_admin():
    from src.ia_admin import ia_command

    u, _ = _upd(5)
    with patch("src.ia_admin.is_admin", return_value=False):
        await ia_command(u, MagicMock())
    assert "administradores" in u.message.reply_text.call_args[0][0]
    assert u.message.reply_text.call_args.kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_comando_ia_admin_muestra_estado_y_botones():
    from src.ia_admin import ia_command

    u, _ = _upd(1)
    with patch("src.ia_admin.is_admin", return_value=True), patch("src.ia_admin.settings", _settings()):
        await ia_command(u, MagicMock())
    texto = u.message.reply_text.call_args[0][0]
    markup = u.message.reply_text.call_args.kwargs["reply_markup"]
    assert "Principal" in texto and "Respaldo" in texto and "Nemotron 3 Ultra" in texto
    datas = _datas(markup)
    assert {"ia:p:groq", "ia:p:nvidia", "ia:b:groq", "ia:b:nvidia", "ia:b:none", "ia:m:0", "ia:m:1"} <= set(datas)
    assert "ia:m:2" not in datas
    assert all(len(d.encode()) <= 64 for d in datas)


@pytest.mark.asyncio
@pytest.mark.parametrize("data,esperado", [
    ("ia:p:nvidia", lambda c: c["primary"] == "nvidia"),
    ("ia:b:none", lambda c: c["backup"] == "none"),
    ("ia:m:1", lambda c: c["nvidia_model"] == "minimaxai/minimax-m3.1-flash"),
])
async def test_callback_cambia_la_config(data, esperado):
    from src.ia_admin import ia_callback

    u, q = _upd(1, data)
    with patch("src.ia_admin.is_admin", return_value=True), patch("src.ia_admin.settings", _settings()):
        await ia_callback(u, MagicMock(), data)
    assert esperado(ai_config.get())
    q.edit_message_text.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["ia:p:nvidia", "ia:m:1", "ia:b:none", "ia:p:openai", "ia:m:zz", "ia:m:99", "ia"])
async def test_callback_de_no_admin_o_invalido_no_cambia_nada(data):
    from src.ia_admin import ia_callback

    antes = ai_config.get()
    u, q = _upd(5, data)
    with patch("src.ia_admin.is_admin", return_value=False):
        await ia_callback(u, MagicMock(), data)
    assert ai_config.get() == antes

    u, q = _upd(1, data)
    with patch("src.ia_admin.is_admin", return_value=True), patch("src.ia_admin.settings", _settings()):
        await ia_callback(u, MagicMock(), data)
    if data in ("ia:p:openai", "ia:m:zz", "ia:m:99", "ia"):
        assert ai_config.get() == antes


def test_ia_registrado_como_comando_admin_con_su_namespace():
    from src.commands import COMANDOS

    c = next(c for c in COMANDOS if c.name == "ia")
    assert c.admin and c.callback is not None and c.rutas() == ("ia",)


def test_gemma_ya_no_es_elegible_y_una_config_vieja_vuelve_al_predeterminado(tmp_path):
    """google/gemma-4-31b-it salio del catalogo de NVIDIA (410 Gone, 2026-11-25)."""
    assert "google/gemma-4-31b-it" not in [m[0] for m in ai_config.MODELOS_NVIDIA]
    (tmp_path / "ai_config.json").write_text(json.dumps({"nvidia_model": "google/gemma-4-31b-it"}))
    ai_config._cache = None
    assert ai_config.get()["nvidia_model"] == ai_config.MODELOS_NVIDIA[0][0]
