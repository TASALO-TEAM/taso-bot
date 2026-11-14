"""H-041: build_bcc_block no debe repetir las monedas fuera de la lista de prioridad."""

from src.formatters import build_bcc_block, build_bcc_only_message


def test_bcc_block_no_duplica_moneda_no_prioritaria():
    texto = build_bcc_block({"bcc": {"USD": 478.0, "NOK": 44.5}})
    assert texto.count("NOK") == 1
    assert texto.count("USD") == 1


def test_bcc_block_incluye_moneda_no_prioritaria_al_final():
    lineas = build_bcc_block({"bcc": {"NOK": 44.5, "USD": 478.0}}).splitlines()
    monedas = [l.split("*")[1].rstrip(":") for l in lineas if l.startswith(" *")]
    assert monedas == ["USD", "NOK"]


def test_bcc_only_message_no_duplica():
    assert build_bcc_only_message({"bcc": {"USD": 478.0, "NOK": 44.5}}).count("NOK") == 1
