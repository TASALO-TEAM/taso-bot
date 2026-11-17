"""F6-T7: todo comando tiene una entrada de botones, y las brechas son explicitas."""
from src import menu
from src.commands import COMANDOS

# Comandos publicos que hoy solo tienen una ficha de texto ("escribelo en el
# chat"). Al darles un flujo por botones, quitarlos de aqui (el test lo exige).
SOLO_FICHA = set()


def _publicos():
    return [c for c in COMANDOS if not c.admin]


def _hojas():
    return {h for _, _, hojas in menu.SECCIONES.values() for h in hojas}


def test_hojas_apuntan_a_algo_real():
    nombres = {c.name for c in COMANDOS}
    for h in _hojas():
        assert h in menu.ACCESO_DIRECTO or h in nombres, h


def test_acceso_directo_apunta_a_comando_real():
    nombres = {c.name for c in COMANDOS}
    assert set(menu.ACCESO_DIRECTO.values()) <= nombres


def test_todo_comando_publico_tiene_entrada_en_el_menu():
    hojas = _hojas()
    directos = set(menu.ACCESO_DIRECTO.values())
    sin_entrada = [
        c.name for c in _publicos()
        if c.name not in hojas and c.name not in directos and c.menu is None
        and c.name != "start"  # /start ES el menu
    ]
    assert sin_entrada == []


def test_comandos_solo_ficha_son_los_conocidos():
    hojas = _hojas()
    directos = set(menu.ACCESO_DIRECTO.values())
    solo_ficha = {
        c.name for c in _publicos()
        if c.name in hojas and c.name not in directos
        and c.name not in menu.EJECUTABLES and c.menu is None
    }
    assert solo_ficha == SOLO_FICHA


def test_todo_comando_admin_esta_en_la_seccion_admin():
    _, _, hojas = menu._seccion("admin", True)
    assert {c.name for c in COMANDOS if c.admin} == set(hojas)


def test_seccion_admin_no_visible_para_no_admin():
    assert menu._seccion("admin", False) is None
