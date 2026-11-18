"""ElToque en el bot: lista fija y orden EUR, USD, ZELLE, MLC, CLA + cripto (BTC, TRX, USDT, BNB)."""

from src.formatters import build_eltoque_block, build_toque_new_message

# La API manda ~20 monedas; el bot solo muestra las de la lista fija
DATA = {
    "eltoque": {
        c: {"rate": 100.0 + i, "change": "neutral", "prev_rate": 100.0 + i}
        for i, c in enumerate(
            ["AUD", "BNB", "BTC", "CLA", "EUR", "GBP", "MLC", "RUR", "TRX", "USD", "USDT", "ZELLE"]
        )
    },
    "updated_at": "2026-11-17T23:57:58Z",
}


def _orden(texto, codigos):
    return [c for c in sorted(codigos, key=texto.find) if texto.find(c) >= 0]


def test_tasalo_lista_fija_y_en_orden():
    out = build_eltoque_block(DATA)
    assert _orden(out, ["*EUR:*", "*USD:*", "*ZELLE:*", "*MLC:*", "*CLA:*", "*BTC:*", "*TRX:*", "*USDT:*", "*BNB:*"]) == [
        "*EUR:*", "*USD:*", "*ZELLE:*", "*MLC:*", "*CLA:*", "*BTC:*", "*TRX:*", "*USDT:*", "*BNB:*",
    ]
    for fuera in ("AUD", "GBP", "RUR"):
        assert fuera not in out


def test_toque_lista_fija_y_en_orden():
    out = build_toque_new_message(DATA)
    pos = [out.find(f" {c} ") for c in ["EUR", "USD", "ZELLE", "MLC", "CLA", "BTC", "TRX", "USDT", "BNB"]]
    assert all(p >= 0 for p in pos) and pos == sorted(pos)
    for fuera in ("AUD", "GBP", "RUR"):
        assert fuera not in out


def test_si_falta_una_moneda_se_omite_sin_romper():
    data = {"eltoque": {"USD": {"rate": 930.0}, "EUR": {"rate": 1000.0}}}
    assert "ZELLE" not in build_eltoque_block(data)
    assert "ZELLE" not in build_toque_new_message(data)