"""El texto de Categorias debe llenar la burbuja como las demas pantallas (ancho del teclado)."""

from src.menu import SECCIONES, render


def test_categorias_lista_cada_categoria_con_su_descripcion():
    texto, _ = render(("all",), False)
    for etiqueta, desc, _hojas in SECCIONES.values():
        assert f"{etiqueta} — {desc}" in texto


def test_categorias_texto_suficientemente_ancho():
    texto, _ = render(("all",), False)
    assert max(len(l) for l in texto.split("\n")) >= 40


def test_categorias_admin_solo_para_admin():
    t_user, _ = render(("all",), False)
    t_admin, _ = render(("all",), True)
    assert "Admin" not in t_user
    assert "Admin" in t_admin
