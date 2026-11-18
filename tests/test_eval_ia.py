import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parents[1] / "scripts" / "eval_ia.py"
_s = importlib.util.spec_from_file_location("eval_ia", _p)
ev = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ev)

ENTRADA = "BTC: precio $64,250.50, cambio 24h -6.74%, RSI 55.3, capital 1,230,000,000,000"


def test_cifras_respaldadas_no_se_marcan():
    texto = "BTC cayó 6.74% y cotiza en $64,250.50. RSI en 55.3."
    assert ev.numeros_inventados(texto, ENTRADA) == []


def test_cifra_inventada_se_marca():
    texto = "BTC cayó 8.10% hasta $61,000."
    assert ev.numeros_inventados(texto, ENTRADA) == ["8.10", "61,000"]


def test_redondeo_y_escalas_se_toleran():
    texto = "Capital cercano a $1.23 billones y precio de $64.3 mil"
    assert ev.numeros_inventados("$1230 mil millones", ENTRADA) == []
    assert ev.numeros_inventados("precio de $64,250", ENTRADA) == []
    assert ev.numeros_inventados(texto, ENTRADA) != []


def test_formato_europeo_y_signo():
    assert ev.numeros_inventados("cayó -6,74 %", ENTRADA) == []


def test_enteros_chicos_fechas_y_horas_se_ignoran():
    texto = "3 escenarios a 4h, 24 horas, 2026, 16:38, 7 d"
    assert ev.numeros_inventados(texto, ENTRADA) == []


def test_entrada_vacia_marca_todo_lo_relevante():
    assert ev.numeros_inventados("subió 5.5%", "") == ["5.5"]


def test_informe_resume_casos():
    casos = [
        {"id": "a", "entrada": ENTRADA, "salida": "RSI 55.3"},
        {"id": "b", "entrada": ENTRADA, "salida": "RSI 71.9"},
    ]
    r = ev.informe(casos)
    assert [x["id"] for x in r] == ["a", "b"]
    assert r[0]["inventadas"] == [] and r[1]["inventadas"] == ["71.9"]
    assert r[1]["largo"] == len("RSI 71.9")
