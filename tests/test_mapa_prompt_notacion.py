from src.core import ai_logic


def test_prompt_del_mapa_fija_notacion_de_montos_y_porcentajes():
    p = ai_logic.MAPA_PROMPT
    assert "mil millones de USD" in p
    assert "MM" in p and "MUSD" in p  # se nombran para prohibirlas
    assert "sin truncar" in p
