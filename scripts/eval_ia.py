"""Evaluacion de salidas de TASALO IA: detecta cifras que no estan en los datos de entrada.

Uso: python scripts/eval_ia.py casos.json
casos.json: lista de {"id", "entrada", "salida"}; "entrada" es el contexto exacto dado a la IA.
Limite: una cifra derivada (una resta, un promedio) se marca como no respaldada; hay que revisarla a mano.
"""
import json
import re
import sys

_NUM = re.compile(r"(?<![\w.])(\d[\d.,]*\d|\d)(?:\s?(mil millones|millones|miles|mil|[MBK])\b)?")
_ESCALA = {"mil millones": 1e9, "millones": 1e6, "M": 1e6, "B": 1e9, "miles": 1e3, "mil": 1e3, "K": 1e3}
_MILES = re.compile(r"^\d{1,3}(,\d{3})+$|^\d{1,3}(\.\d{3})+$")


def _parse(raw: str) -> tuple[float, int]:
    """Devuelve (valor, decimales escritos)."""
    if "," in raw and "." in raw:
        dec_sep = "," if raw.rfind(",") > raw.rfind(".") else "."
    elif _MILES.match(raw) and ("," in raw or raw.count(".") > 1):
        dec_sep = None
    else:
        dec_sep = "," if "," in raw else ("." if "." in raw else None)
    if dec_sep is None:
        return float(re.sub(r"[.,]", "", raw)), 0
    ent, _, dec = raw.rpartition(dec_sep)
    return float(re.sub(r"[.,]", "", ent) + "." + dec), len(dec)


def _numeros(texto: str):
    for m in _NUM.finditer(texto):
        raw, suf = m.group(1), m.group(2)
        valor, dec = _parse(raw)
        escala = _ESCALA.get(suf, 1.0)
        yield m, raw, valor * escala, dec, escala


def numeros_inventados(texto: str, entrada: str) -> list[str]:
    base = [v for _, _, v, _, _ in _numeros(entrada)]
    fuera = []
    for m, raw, valor, dec, escala in _numeros(texto):
        antes = texto[max(0, m.start() - 1):m.start()]
        despues = texto[m.end():m.end() + 2].lstrip()
        anio = raw.isdigit() and len(raw) == 4 and 1900 <= int(raw) <= 2100
        relevante = (
            dec > 0 or "," in raw or antes == "$" or despues.startswith("%")
            or escala != 1.0 or (valor >= 100 and not anio)
        )
        if not relevante:
            continue
        tol = 0.5 * 10 ** -dec * escala
        if not any(abs(abs(valor) - abs(b)) <= tol * (1 + 1e-9) + 1e-9 for b in base):
            fuera.append(raw)
    return fuera


def informe(casos: list[dict]) -> list[dict]:
    return [
        {
            "id": c["id"],
            "inventadas": numeros_inventados(c["salida"], c["entrada"]),
            "largo": len(c["salida"]),
        }
        for c in casos
    ]


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        for r in informe(json.load(f)):
            estado = "OK" if not r["inventadas"] else "REVISAR " + ", ".join(r["inventadas"])
            print(f"{r['id']}: {r['largo']} car. | {estado}")
