"""Clasificador de entradas del explorador (F4-T3). Puro: sin red, sin estado.

Reglas (orden fijo, ver DECISIONS D-005): se limpia la entrada, se descarta lo que
no sea un unico token razonable y se valida por checksum donde existe (base58check,
bech32/bech32m, BOLT11). Nunca se sigue ninguna URL: LNURL y lightning address solo
se reconocen. Un nombre de Hive suelto solo se acepta si el llamador lo pide
(`nombre_hive_suelto=True`, p. ej. dentro de un comando); con "@" siempre.
"""

import hashlib
import re
from dataclasses import dataclass

MAX_ENTRADA = 2000   # una factura BOLT11 larga ronda los 1200
_HEX = re.compile(r"^[0-9a-fA-F]+$")
_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_GEN = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
_RED_BECH32 = {"bc": "mainnet", "tb": "testnet", "bcrt": "regtest"}
_RED_B58 = {0x00: ("mainnet", "p2pkh"), 0x05: ("mainnet", "p2sh"),
            0x6F: ("testnet", "p2pkh"), 0xC4: ("testnet", "p2sh")}
_HIVE_SEG = re.compile(r"^[a-z](?:-?[a-z0-9])+$")
_LN_ADDR = re.compile(r"^[A-Za-z0-9._+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
_LN_HRP = re.compile(r"^ln(bcrt|tbs|bc|tb)(\d+)?([munp])?$")
_MULT_MSAT = {None: 100_000_000_000, "m": 100_000_000, "u": 100_000, "n": 100, "p": 0.1}


@dataclass(frozen=True)
class Entrada:
    tipo: str            # btc_address, btc_tx, ln_invoice, lnurl, lightning_address,
    valor: str           # hive_account, hive_tx, evm_address, evm_tx, desconocido
    red: str | None = None
    detalle: tuple = ()  # pares (clave, valor) acotados, p. ej. ("formato", "p2tr")

    def info(self, clave: str, defecto=None):
        return dict(self.detalle).get(clave, defecto)


def etiqueta_log(e: Entrada) -> str:
    """Para logs: solo tipo y ultimos 4 caracteres (F4-T8)."""
    return f"{e.tipo}…{e.valor[-4:]}" if e.valor else e.tipo


def _polymod(values) -> int:
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= _GEN[i] if (top >> i) & 1 else 0
    return chk


def bech32_decode(s: str, max_len: int = 90):
    """-> (hrp, datos5bit, spec) con spec 'bech32'|'bech32m', o None."""
    if not s or len(s) > max_len or s != s.lower() and s != s.upper():
        return None
    s = s.lower()
    pos = s.rfind("1")
    if pos < 1 or pos + 7 > len(s) or any(ord(c) < 33 or ord(c) > 126 for c in s):
        return None
    if any(c not in _CHARSET for c in s[pos + 1:]):
        return None
    hrp, data = s[:pos], [_CHARSET.find(c) for c in s[pos + 1:]]
    const = _polymod([ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp] + data)
    spec = {1: "bech32", 0x2BC830A3: "bech32m"}.get(const)
    return (hrp, data[:-6], spec) if spec else None


def _convertbits(data, frm: int, to: int, pad: bool):
    acc = bits = 0
    out, maxv = [], (1 << to) - 1
    for v in data:
        acc = (acc << frm) | v
        bits += frm
        while bits >= to:
            bits -= to
            out.append((acc >> bits) & maxv)
    if pad and bits:
        out.append((acc << (to - bits)) & maxv)
    elif not pad and (bits >= frm or (acc << (to - bits)) & maxv):
        return None
    return out


def _b58check(s: str):
    n = 0
    for c in s:
        i = _B58.find(c)
        if i < 0:
            return None
        n = n * 58 + i
    raw = n.to_bytes(25, "big") if n.bit_length() <= 200 else None
    if raw is None or len(s) - len(s.lstrip("1")) != len(raw) - len(raw.lstrip(b"\0")):
        return None
    return raw if hashlib.sha256(hashlib.sha256(raw[:21]).digest()).digest()[:4] == raw[21:] else None


def _btc_address(s: str) -> Entrada | None:
    low = s.lower()
    for hrp, red in _RED_BECH32.items():
        if low.startswith(hrp + "1"):
            d = bech32_decode(s)
            if not d or d[0] != hrp:
                return None
            ver, prog = d[1][0] if d[1] else -1, _convertbits(d[1][1:], 5, 8, False)
            if prog is None or not 0 <= ver <= 16 or not 2 <= len(prog) <= 40:
                return None
            if ver == 0 and (d[2] != "bech32" or len(prog) not in (20, 32)):
                return None
            if ver != 0 and d[2] != "bech32m":
                return None
            fmt = {(0, 20): "p2wpkh", (0, 32): "p2wsh", (1, 32): "p2tr"}.get((ver, len(prog)), f"segwit_v{ver}")
            return Entrada("btc_address", low, red, (("formato", fmt),))
    if s[:1] in "13mn2" and 26 <= len(s) <= 35:
        raw = _b58check(s)
        if raw and raw[0] in _RED_B58:
            red, fmt = _RED_B58[raw[0]]
            return Entrada("btc_address", s, red, (("formato", fmt),))
    return None


def _bolt11(s: str) -> Entrada | None:
    low = s.lower()
    d = bech32_decode(low, max_len=MAX_ENTRADA)
    m = _LN_HRP.match(d[0]) if d else None
    if not d or not m or d[2] != "bech32" or len(d[1]) < 7 + 104:
        return None
    red = {"bc": "mainnet", "tb": "testnet", "tbs": "signet", "bcrt": "regtest"}[m.group(1)]
    det = []
    if m.group(2):
        msat = int(m.group(2)) * _MULT_MSAT[m.group(3)]
        if msat == int(msat) and msat % 1000 == 0:
            det.append(("sats", int(msat) // 1000))
        elif msat == int(msat):
            det.append(("msat", int(msat)))
    ts = 0
    for v in d[1][:7]:
        ts = ts << 5 | v
    det.append(("creada", ts))
    i, fin = 7, len(d[1]) - 104
    while i + 3 <= fin:
        tag, ln = d[1][i], d[1][i + 1] << 5 | d[1][i + 2]
        if tag == 6 and ln <= 7 and i + 3 + ln <= fin:   # 'x' expiry
            det.append(("expira_en", int("".join(f"{v:05b}" for v in d[1][i + 3:i + 3 + ln]) or "0", 2)))
            break
        i += 3 + ln
    else:
        det.append(("expira_en", 3600))
    return Entrada("ln_invoice", low, red, tuple(det))


def _hive_name(n: str) -> bool:
    return 3 <= len(n) <= 16 and all(len(p) >= 3 and _HIVE_SEG.match(p) for p in n.split("."))


def _limpiar(texto: str) -> str | None:
    if not isinstance(texto, str):
        return None
    t = texto.strip()
    if not t or len(t) > MAX_ENTRADA:
        return None
    low = t.lower()
    for pref in ("bitcoin:", "lightning:"):
        if low.startswith(pref):
            t = t[len(pref):].split("?", 1)[0]
            break
    return t if t and len(t.split()) == 1 else None


def clasificar(texto: str, *, nombre_hive_suelto: bool = False) -> Entrada:
    t = _limpiar(texto)
    if t is None:
        return Entrada("desconocido", "")
    low = t.lower()
    if low.startswith("lnurl1") and bech32_decode(low, MAX_ENTRADA):
        return Entrada("lnurl", low)   # solo reconocida: nunca se sigue
    if low.startswith("ln") and (e := _bolt11(t)):
        return e
    if (e := _btc_address(t)):
        return e
    if _LN_ADDR.match(t):
        return Entrada("lightning_address", t)
    if low.startswith("0x") and _HEX.match(low[2:]):
        if len(low) == 42:
            return Entrada("evm_address", low, "evm")
        if len(low) == 66:
            return Entrada("evm_tx", low, "evm")
    if _HEX.match(t):
        if len(t) == 64:
            return Entrada("btc_tx", low, "bitcoin")
        if len(t) == 40:
            return Entrada("hive_tx", low, "hive")
    nombre = t[1:] if t.startswith("@") else t
    if (t.startswith("@") or nombre_hive_suelto) and _hive_name(nombre.lower()) and nombre == nombre.lower():
        return Entrada("hive_account", nombre, "hive")
    return Entrada("desconocido", "")
