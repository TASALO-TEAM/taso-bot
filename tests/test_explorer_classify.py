"""Tests del clasificador del explorador (F4-T3). Solo vectores publicos."""

import pytest

from src.explorer.classify import MAX_ENTRADA, clasificar, etiqueta_log

GENESIS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
P2SH = "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"
P2WPKH = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"        # BIP-173
P2WSH_TB = "tb1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3q0sl5k7"
TAPROOT = "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0"  # BIP-350
TESTNET_B58 = "mipcBbFg9gMiCh81Kj8tqqdgoZub1ZJRfn"
TXID = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"
HIVE_TX = "e4229778388632e32946905dc5dca26c538c6ec0"
EVM_ADDR = "0x" + "ab" * 20
EVM_TX = "0x" + "cd" * 32
# Factura de ejemplo de la especificacion BOLT11 (donacion, 2500u).
BOLT11 = ("lnbc2500u1pvjluezpp5qqqsyqcyq5rqwzqfqqqsyqcyq5rqwzqfqqqsyqcyq5rqwzqfqypqdq5xysxxatsyp3k7"
          "enxv4jsxqzpuaztrnwngzn3kdzw5hydlzf03qdgm2hdq27cqv3agm2awhz5se903vruatfhq77w3ls4evs3ch9zw97j25"
          "emudupq63nyw24cg27h2rspfj9srp")


@pytest.mark.parametrize("texto,formato,red", [
    (GENESIS, "p2pkh", "mainnet"), (P2SH, "p2sh", "mainnet"), (TESTNET_B58, "p2pkh", "testnet"),
    (P2WPKH, "p2wpkh", "mainnet"), (P2WSH_TB, "p2wsh", "testnet"), (TAPROOT, "p2tr", "mainnet"),
    (P2WPKH.upper(), "p2wpkh", "mainnet"), (f"  {GENESIS}\n", "p2pkh", "mainnet"),
    (f"bitcoin:{GENESIS}?amount=0.1&label=x", "p2pkh", "mainnet"),
])
def test_direcciones_btc_validas(texto, formato, red):
    e = clasificar(texto)
    assert (e.tipo, e.info("formato"), e.red) == ("btc_address", formato, red)


@pytest.mark.parametrize("texto", [
    GENESIS[:-1] + "b",                       # checksum base58 roto
    GENESIS[:10] + "0" + GENESIS[11:],        # caracter fuera del alfabeto
    "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5",   # checksum bech32 roto
    "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqh2y7hd",  # v1 con bech32 (no m)
    "tc1qw508d6qejxtdg4y5r3zarvary0c5xw7kg3g4ty",   # hrp desconocido
    "Bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",   # mayusculas mezcladas
    "bc1", "1", "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4 extra",
])
def test_direcciones_btc_invalidas(texto):
    assert clasificar(texto).tipo == "desconocido"


def test_txid_y_hive_tx_y_evm():
    assert clasificar(TXID).tipo == "btc_tx"
    assert clasificar(TXID.upper()).valor == TXID
    assert clasificar(HIVE_TX).tipo == "hive_tx"
    assert clasificar(EVM_ADDR).tipo == "evm_address"
    assert clasificar(EVM_TX).tipo == "evm_tx"
    assert clasificar("0x" + "a" * 39).tipo == "desconocido"
    assert clasificar("g" * 64).tipo == "desconocido"


def test_bolt11():
    e = clasificar(BOLT11)
    assert (e.tipo, e.red, e.info("sats")) == ("ln_invoice", "mainnet", 250000)
    assert e.info("expira_en") == 60 and e.info("creada") == 1496314658  # valores del vector de la spec
    assert clasificar(BOLT11.upper()).tipo == "ln_invoice"
    assert clasificar("lightning:" + BOLT11).tipo == "ln_invoice"
    assert clasificar(BOLT11[:-1] + ("q" if BOLT11[-1] != "q" else "p")).tipo == "desconocido"


def test_lnurl_y_lightning_address_solo_se_reconocen():
    assert clasificar("alice@getalby.com").tipo == "lightning_address"
    assert clasificar("lnurl1dp68gurn8ghj7").tipo == "desconocido"   # checksum invalido


def test_hive_requiere_arroba_o_contexto():
    assert clasificar("@hiveio").tipo == "hive_account"
    assert clasificar("hiveio").tipo == "desconocido"            # texto suelto: no
    assert clasificar("hiveio", nombre_hive_suelto=True).valor == "hiveio"
    assert clasificar("@blocktrades.test", nombre_hive_suelto=True).tipo == "hive_account"
    for malo in ("@ab", "@Hiveio", "@1abc", "@abc-", "@abc--def", "@a" * 9, "@zzzzzz-no-existe-12", "@ab.cde"):
        assert clasificar(malo).tipo == "desconocido", malo


@pytest.mark.parametrize("texto", ["", "   ", None, 123, "hola mundo", "a" * (MAX_ENTRADA + 1),
                                   "https://evil.example/x", "mira " + GENESIS])
def test_entradas_basura(texto):
    assert clasificar(texto).tipo == "desconocido"


def test_etiqueta_log_no_expone_la_entrada():
    assert etiqueta_log(clasificar(GENESIS)) == "btc_address…vfNa"
    assert GENESIS not in etiqueta_log(clasificar(GENESIS))
    assert etiqueta_log(clasificar("hola")) == "desconocido"


def test_nunca_lanza_con_entradas_aleatorias():
    import random
    rnd = random.Random(7)
    alfabetos = ["0123456789abcdef", "qpzry9x8gf2tvdw0s3jn54khce6mua7l1", "1A1zP1eP5QGefi2DMPTfTL5SLmv7Dvf3",
                 "abc@.:-_/? 0x", "ñ\u200b\x00日本"]
    for _ in range(3000):
        base = rnd.choice(alfabetos)
        pref = rnd.choice(["", "bc1", "lnbc", "tb1", "0x", "@", "bitcoin:", "lnurl1", "1", "3"])
        clasificar(pref + "".join(rnd.choice(base) for _ in range(rnd.randint(0, 120))), nombre_hive_suelto=bool(rnd.getrandbits(1)))
