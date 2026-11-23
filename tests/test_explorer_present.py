"""F4-T5: presentacion del explorador (pura, sin red). HTML de Telegram, <= 4096 caracteres."""
import re

from src.explorer.classify import Entrada
from src.explorer import present as p

PRECIO = (100_000.0, "CoinMarketCap", "12:30 UTC")
ADDR = Entrada("btc_address", "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq", "mainnet", (("formato", "p2wpkh"),))
TX = Entrada("btc_tx", "a" * 64, "bitcoin")
DATOS_ADDR = {"direccion": ADDR.valor, "saldo_sats": 150_000_000, "pendiente_sats": 0, "recibido_sats": 300_000_000,
              "gastado_sats": 150_000_000, "tx_count": 12, "tx_pendientes": 0}
TXS = [{"txid": "b" * 64, "confirmada": True, "altura": 800000, "fecha": "2026-11-01", "neto_sats": -5000},
       {"txid": "c" * 64, "confirmada": False, "altura": None, "fecha": None, "neto_sats": 7000}]


def _sin_tags_rotos(txt: str):
    assert txt.count("<b>") == txt.count("</b>")
    assert txt.count("<code>") == txt.count("</code>")
    assert not re.search(r"<(?!/?(b|i|code|a)[ >])", txt)


def test_direccion_con_usd_fuente_y_hora():
    txt = p.formatear(ADDR, DATOS_ADDR, txs=TXS, precio=PRECIO)
    assert "1.50000000 BTC" in txt and "$150,000.00" in txt
    assert "CoinMarketCap" in txt and "12:30 UTC" in txt
    assert "p2wpkh" in txt and "mainnet" in txt and "12" in txt
    assert "pendiente" in txt.lower()          # la tx sin confirmar
    _sin_tags_rotos(txt)


def test_sin_precio_no_inventa_usd():
    txt = p.formatear(ADDR, DATOS_ADDR, precio=None)
    assert "$" not in txt and "1.50000000 BTC" in txt


def test_tx_confirmaciones_y_fee():
    d = {"txid": TX.valor, "confirmada": True, "altura": 800000, "confirmaciones": 7, "fecha": "2026-11-01",
         "tamano": 225, "peso": 900, "fee_sats": 1800, "entradas": 1, "salidas": 2, "total_salidas_sats": 50_000}
    txt = p.formatear(TX, d, precio=PRECIO)
    assert "7" in txt and "1,800" in txt and "0.00050000 BTC" in txt and "$50.00" in txt
    d["confirmada"], d["confirmaciones"], d["altura"] = False, 0, None
    assert "sin confirmar" in p.formatear(TX, d, precio=None).lower()


def test_hive_cuenta_y_transaccion():
    e = Entrada("hive_account", "alice", "hive")
    d = {"nombre": "alice", "creada": "2020-01-02", "hive": 10.5, "hbd": 2.0, "hp": 123.456, "posts": 9, "ultimo_post": None}
    txt = p.formatear(e, d)
    assert "@alice" in txt and "10.500 HIVE" in txt and "2.000 HBD" in txt and "123.456 HP" in txt
    t = Entrada("hive_tx", "d" * 40, "hive")
    dt = {"id": t.valor, "bloque": 99, "total_operaciones": 1,
          "operaciones": [{"tipo": "transfer", "transferencia": {"de": "a", "a": "b", "monto": 1.5, "moneda": "HIVE"}}]}
    out = p.formatear(t, dt)
    assert "@a" in out and "@b" in out and "1.500 HIVE" in out and "99" in out


def test_factura_lightning_solo_decodificada_sin_seguir_nada():
    e = Entrada("ln_invoice", "lnbc1" + "q" * 120, "mainnet", (("sats", 2500), ("creada", 1_496_314_658), ("expira_en", 60)))
    txt = p.formatear(e, None)
    assert "2,500" in txt and "expir" in txt.lower() and "no se consulta" in txt.lower()


def test_reconocidas_pero_no_consultadas():
    for tipo, valor in (("lnurl", "lnurl1xyz"), ("lightning_address", "a@b.com")):
        txt = p.formatear(Entrada(tipo, valor, None), None)
        assert txt and "no" in txt.lower()
        _sin_tags_rotos(txt)


def test_evm_escapa_html_de_terceros():
    e = Entrada("evm_address", "0x" + "ab" * 20, "evm")
    d = {"direccion": e.valor, "sin_respuesta": ["<b>x</b>"],
         "redes": [{"red": "<i>x</i>", "simbolo": "<b>", "saldo_wei": 1, "nonce": 1, "tipo": "cuenta"}]}
    txt = p.formatear(e, d)
    assert "<i>x</i>" not in txt and "<b>x</b>" not in txt and len(txt) <= p.MAX
    _sin_tags_rotos(txt)


def test_desconocido_da_ayuda():
    assert "bitcoin" in p.formatear(Entrada("desconocido", ""), None).lower()


def test_escapa_html_de_terceros():
    e = Entrada("hive_account", "alice", "hive")
    d = {"nombre": "<b>x</b>", "creada": "<i>", "hive": None, "hbd": None, "hp": None, "posts": 0, "ultimo_post": None}
    txt = p.formatear(e, d)
    assert "<b>x</b>" not in txt and "&lt;b&gt;" in txt


def test_nunca_pasa_de_4096():
    txs = [{"txid": f"{i:064x}", "confirmada": True, "altura": i, "fecha": "2026-11-01", "neto_sats": i} for i in range(400)]
    txt = p.formatear(ADDR, DATOS_ADDR, txs=txs, precio=PRECIO)
    assert len(txt) <= 4096
    _sin_tags_rotos(txt)


def test_enlaces_al_explorador_son_fijos():
    assert p.enlace(ADDR) == f"https://mempool.space/address/{ADDR.valor}"
    assert p.enlace(TX) == f"https://mempool.space/tx/{TX.valor}"
    assert p.enlace(Entrada("hive_account", "alice", "hive")).startswith("https://")
    assert p.enlace(Entrada("lnurl", "lnurl1xyz")) is None


def test_mensajes_de_error_fijos():
    for cod in ("no_encontrado", "no_disponible", "limite", "respuesta_invalida", "otro"):
        m = p.mensaje_error(cod)
        assert m and "Traceback" not in m and len(m) < 300
