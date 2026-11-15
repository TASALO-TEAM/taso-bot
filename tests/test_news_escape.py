"""H-040: _format_articles debe escapar el texto libre antes de insertarlo en Markdown v1."""
from src.handlers.news import _format_articles


def test_campos_de_texto_se_escapan():
    art = {
        "title": "A*B_[x]",
        "description": "desc `code` *negrita*",
        "source_name": "Fuente_*1",
        "url": "https://ejemplo.com/a_b",
    }
    out = _format_articles([art], "q_*[1]")
    assert "*Noticias — q\\_\\*\\[1]*" in out
    assert "*A\\*B\\_\\[x]*" in out
    assert "desc \\`code\\` \\*negrita\\*" in out
    assert "_Fuente\\_\\*1_" in out


def test_url_no_se_escapa():
    art = {"title": "t", "url": "https://ejemplo.com/a_b"}
    assert "[ver noticia](https://ejemplo.com/a_b)" in _format_articles([art], "x")


def test_descripcion_larga_no_corta_un_escape():
    # El recorte a 217 caracteres deja un "_" al final: se escapa entero (recortar primero, escapar después)
    art = {"title": "t", "description": "a" * 216 + "_" * 20}
    assert "a" * 216 + "\\_..." in _format_articles([art], "x")
