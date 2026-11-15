# tests/test_tspl_digest_markdown.py
"""H-058: el digest de /tspl lo redacta un LLM a partir de noticias de
terceros. Sus textos entran al mensaje de Telegram (Markdown v1), asi que un
'_' o '*' suelto (p. ej. un @usuario_x de una noticia) no puede romper el
envio a todos los suscriptores."""

from unittest.mock import patch

from src.handlers.tspl import _build_message, _build_news_section


def _msg(digest):
    with patch("src.handlers.tspl.build_tspl_market_bullets", return_value="- BTC 1"), \
         patch("src.handlers.tspl._fecha_hoy", return_value="14 nov"):
        return _build_message(digest, {})


DIGEST = {
    "lede": "El BTC sube y @michael_saylor lo celebra.",
    "teaser": "Primera noticia con ETF_spot. Vamos a empezar.",
    "items": [
        {"emoji": "N", "titulo": "ETF_spot aprobado",
         "parrafo": "Segun @Whale_Alert hubo 5*10 movimientos."},
    ],
    "radar": "Vigilar el nivel BTC_USD.",
}


def test_guion_bajo_del_digest_se_escapa_en_todos_los_campos():
    msg = _msg(DIGEST)
    for crudo in ("@michael_saylor", "ETF_spot", "@Whale_Alert", "BTC_USD"):
        assert crudo not in msg
        assert crudo.replace("_", "\\_") in msg


def test_asterisco_del_digest_se_escapa():
    msg = _msg(DIGEST)
    assert "5*10" not in msg
    assert "5\\*10" in msg


def test_formato_propio_del_mensaje_se_conserva():
    msg = _msg(DIGEST)
    assert "*TASALO Spotlight — 14 nov*" in msg
    assert "*ETF\\_spot aprobado*" in msg


def test_texto_normal_no_cambia():
    digest = {
        "lede": "El mercado cierra en verde.",
        "teaser": "Una noticia fuerte. Vamos a empezar.",
        "items": [{"emoji": "N", "titulo": "Bitcoin sube",
                   "parrafo": "El BTC gana 5% en 24 horas."}],
        "radar": "Atentos a la Fed.",
    }
    msg = _msg(digest)
    for texto in ("El mercado cierra en verde.", "Una noticia fuerte. Vamos a empezar.",
                  "El BTC gana 5% en 24 horas.", "Atentos a la Fed."):
        assert texto in msg
    assert "*Bitcoin sube*" in msg


def test_campos_null_o_items_invalidos_no_rompen():
    digest = {
        "lede": None,
        "items": [None, "texto suelto", {"titulo": None, "parrafo": None},
                  {"titulo": "OK", "parrafo": None}],
    }
    msg = _msg(digest)
    assert "*OK*" in msg
    assert "texto suelto" not in msg


def test_news_section_con_items_no_dict_devuelve_aviso():
    assert "noticias no disponibles" in _build_news_section({"items": ["x", None]})
