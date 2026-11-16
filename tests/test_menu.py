"""F6-T4: menu principal y submenus por botones (Inicio/Atras, edicion en sitio)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from telegram.error import BadRequest


def _datas(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def _alcanzables(es_admin: bool) -> set[str]:
    """Todos los callback_data alcanzables desde el inicio siguiendo botones `menu:`."""
    from src import callback_data as cd
    from src.menu import render

    vistos, pendientes, todos = set(), [()], set()
    while pendientes:
        args = pendientes.pop()
        if args in vistos:
            continue
        vistos.add(args)
        _, markup = render(args, es_admin)
        for d in _datas(markup):
            todos.add(d)
            p = cd.parse_v2(d)
            if p and p[0] == "menu":
                pendientes.append(p[1])
    return todos


def test_inicio_lista_las_categorias_y_no_se_enlaza_a_si_mismo():
    from src.menu import render

    texto, markup = render(("all",), es_admin=False)
    datas = _datas(markup)
    for sec in ("tasas", "cripto", "analisis", "alertas", "noticias", "mercado", "ayuda"):
        assert f"menu:{sec}" in datas
    assert "menu:admin" not in datas
    assert "menu:all" not in datas  # no se enlaza a si mismo
    assert "menu:home" in datas  # Inicio = la bienvenida
    assert texto


def test_admin_solo_aparece_para_admins():
    from src.menu import render

    assert "menu:admin" in _datas(render(("all",), es_admin=True)[1])
    assert "menu:admin" not in _datas(render(("all",), es_admin=False)[1])


def test_toda_pantalla_distinta_del_inicio_tiene_boton_inicio():
    from src import callback_data as cd
    from src.menu import render

    for es_admin in (False, True):
        for d in _alcanzables(es_admin):
            if d.startswith("menu:") and d != "menu:home" and not d.startswith("menu:run:"):
                _, markup = render(cd.parse_v2(d)[1], es_admin)
                assert "menu:home" in _datas(markup), d


def test_secciones_tienen_atras_a_las_categorias():
    from src.menu import SECCIONES, render

    for sec in SECCIONES:
        assert "menu:all" in _datas(render((sec,), es_admin=False)[1]), sec
    assert "menu:all" in _datas(render(("admin",), es_admin=True)[1])


def test_el_inicio_es_la_bienvenida_y_ofrece_mas():
    from src.handlers.start import build_start_keyboard
    from src.menu import _resolve

    texto, markup, html = _resolve((), es_admin=False)
    assert html is True and "TASALO" in texto
    assert _datas(markup) == _datas(build_start_keyboard())
    assert "menu:all" in _datas(markup)
    assert _resolve(("all",), False)[2] is False


def test_pantalla_de_comando_tiene_atras_a_su_seccion():
    from src.menu import render

    _, markup = render(("cmd", "qp", "tasas"), es_admin=False)
    datas = _datas(markup)
    assert "menu:tasas" in datas and "menu:home" in datas


def test_todo_callback_data_cabe_en_64_bytes():
    for es_admin in (False, True):
        for d in _alcanzables(es_admin):
            assert len(d.encode()) <= 64, d


def test_cada_comando_publico_es_alcanzable_con_botones():
    from src.commands import COMANDOS
    from src.menu import ACCESO_DIRECTO

    todos = _alcanzables(es_admin=False)
    cubiertos = {d.split(":")[2] for d in todos if d.startswith("menu:cmd:")}
    cubiertos |= {ACCESO_DIRECTO[d] for d in todos if d in ACCESO_DIRECTO}
    faltan = {c.name for c in COMANDOS if not c.admin and c.name != "start"} - cubiertos
    assert not faltan, faltan


def test_cada_comando_admin_es_alcanzable_solo_para_admin():
    from src.commands import COMANDOS

    nombres = {c.name for c in COMANDOS if c.admin}
    admin = {d.split(":")[2] for d in _alcanzables(True) if d.startswith("menu:cmd:")}
    normal = {d.split(":")[2] for d in _alcanzables(False) if d.startswith("menu:cmd:")}
    assert nombres <= admin
    assert not (nombres & normal)


def test_no_admin_que_falsifica_el_callback_recibe_el_inicio():
    from src.menu import render

    inicio = render((), es_admin=False)
    assert render(("admin",), es_admin=False) == inicio
    assert render(("cmd", "status", "admin"), es_admin=False) == inicio


def test_pantalla_desconocida_cae_en_el_inicio():
    from src.menu import render

    assert render(("zzz",), False) == render((), False)
    assert render(("cmd", "noexiste", "tasas"), False) == render((), False)
    assert render(("cmd",), False) == render((), False)


def test_modulo_registrado_por_contrato_aparece_en_su_seccion(monkeypatch):
    from src import commands
    from src.commands import Cmd
    from src.menu import render

    async def cb(update, context, data):
        pass

    monkeypatch.setattr(
        commands, "COMANDOS",
        commands.COMANDOS + (Cmd("explorer", None, "d", callback=cb, menu=("mercado", "Explorador")),),
    )
    assert "explorer_open" in _datas(render(("mercado",), False)[1])


def _query(data: str, edit_exc=None):
    q = MagicMock()
    q.data = data
    q.from_user.id = 1
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock(side_effect=edit_exc)
    q.message.reply_text = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    return u, q


def test_el_menu_edita_el_mensaje_en_sitio(monkeypatch):
    from src import menu
    from src.handlers import callback_router as r

    monkeypatch.setattr(menu, "_es_admin", lambda uid: False)
    u, q = _query("menu:tasas")
    asyncio.run(r.callback_router(u, MagicMock()))
    q.edit_message_text.assert_awaited_once()
    q.message.reply_text.assert_not_awaited()
    q.answer.assert_awaited_once_with()  # una sola respuesta: la del router


def test_si_no_se_puede_editar_se_envia_mensaje_nuevo(monkeypatch):
    from src import menu
    from src.handlers import callback_router as r

    monkeypatch.setattr(menu, "_es_admin", lambda uid: False)
    u, q = _query("menu:tasas", edit_exc=BadRequest("There is no text in the message to edit"))
    asyncio.run(r.callback_router(u, MagicMock()))
    q.message.reply_text.assert_awaited_once()


def test_mensaje_sin_cambios_no_envia_nada(monkeypatch):
    from src import menu
    from src.handlers import callback_router as r

    monkeypatch.setattr(menu, "_es_admin", lambda uid: False)
    u, q = _query("menu:home", edit_exc=BadRequest("Message is not modified"))
    asyncio.run(r.callback_router(u, MagicMock()))
    q.message.reply_text.assert_not_awaited()


def test_start_trae_el_boton_de_menu_completo_sin_mover_las_filas_existentes():
    from src.handlers.start import build_start_keyboard

    kb = build_start_keyboard().inline_keyboard
    assert "menu:all" in [b.callback_data for row in kb for b in row]
    assert kb[0][0].callback_data == "start_tasalo"
    assert kb[1][0].callback_data == "start_bcc"
    assert kb[2][0].callback_data == "start_p_help"


def test_volver_al_inicio_edita_con_html(monkeypatch):
    from src import menu
    from src.handlers import callback_router as r

    monkeypatch.setattr(menu, "_es_admin", lambda uid: False)
    u, q = _query("menu:home")
    asyncio.run(r.callback_router(u, MagicMock()))
    assert q.edit_message_text.await_args.kwargs["parse_mode"] == "HTML"
    u, q = _query("menu:tasas")
    asyncio.run(r.callback_router(u, MagicMock()))
    assert q.edit_message_text.await_args.kwargs["parse_mode"] is None
