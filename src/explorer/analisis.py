"""Contexto agregado para el analisis de TASALO IA sobre una consulta del explorador (F4-T6).

Pura y sin red. Regla de privacidad (D-026): solo cifras. Nunca la direccion, el hash, el
usuario de Hive ni los nombres de cuentas de una transferencia; a la IA no se le dice a quien
pertenece nada. Devuelve None si el tipo no se consulta o faltan datos.
"""

import re
from datetime import date, datetime, timezone

_CONSULTABLES = ("btc_address", "btc_tx", "hive_account", "hive_tx")


def _btc(sats) -> str:
    return f"{sats / 1e8:.8f} BTC"


def _texto(valor, defecto="?") -> str:
    """Etiqueta propia acotada (formato de direccion, red): minusculas y signos simples."""
    t = re.sub(r"[^a-z0-9_ .-]", "", str(valor or "").lower())[:30].strip()
    return t or defecto


def _limpio(valor) -> str:
    """Fuente u hora propias: conserva mayusculas y ':' (p. ej. "12:03 UTC")."""
    return re.sub(r"[^A-Za-z0-9 :._-]", "", str(valor))[:30].strip()


def _usd(sats, precio) -> str | None:
    if not precio:
        return None
    usd, fuente, hora = precio
    return f"Valor en USD: ${sats / 1e8 * usd:,.2f} (fuente {_limpio(fuente)}, {_limpio(hora)})"


def _btc_address(e, d, txs, precio) -> list:
    out = [f"Tipo: direccion Bitcoin (red {_texto(e.red)}, formato {_texto(e.info('formato'))})",
           f"Saldo: {_btc(d['saldo_sats'])}",
           f"Recibido total: {_btc(d['recibido_sats'])}",
           f"Gastado total: {_btc(d['gastado_sats'])}",
           f"Transacciones: {d['tx_count']:,}" + (f" (pendientes: {d['tx_pendientes']})" if d.get("tx_pendientes") else "")]
    if d.get("pendiente_sats"):
        out.append(f"Movimiento sin confirmar: {d['pendiente_sats'] / 1e8:+.8f} BTC")
    if txs:
        netos = ", ".join(f"{t['neto_sats'] / 1e8:+.8f}" for t in txs[:5])
        out.append(f"Ultimos movimientos (neto en BTC, el mas reciente primero): {netos}")
    usd = _usd(d["saldo_sats"], precio)
    return out + ([usd] if usd else [])


def _btc_tx(e, d, txs, precio) -> list:
    if d["confirmada"]:
        conf = d.get("confirmaciones")
        estado = f"confirmada, {conf:,} confirmaciones" if conf is not None else "confirmada"
    else:
        estado = "sin confirmar (en mempool)"
    comision = f"Comision: {d['fee_sats']:,} sats ({d['tamano']:,} bytes"
    if d.get("peso"):
        comision += f", {d['fee_sats'] / (d['peso'] / 4):.2f} sat/vB"
    out = ["Tipo: transaccion Bitcoin", f"Estado: {estado}",
           f"Entradas: {d['entradas']:,}; salidas: {d['salidas']:,}",
           f"Total en salidas: {_btc(d['total_salidas_sats'])}", comision + ")"]
    usd = _usd(d["total_salidas_sats"], precio)
    return out + ([usd] if usd else [])


def _antiguedad(creada) -> str | None:
    try:
        y = (datetime.now(timezone.utc).date() - date.fromisoformat(str(creada)[:10])).days // 365
    except (TypeError, ValueError):
        return None
    return f"Antiguedad de la cuenta: {max(y, 0)} anos"


def _hive_account(e, d, txs, precio) -> list:
    saldos = [f"{n}: {d[k]:,.3f}" for n, k in (("HIVE", "hive"), ("HBD", "hbd"), ("HP", "hp")) if d.get(k) is not None]
    out = ["Tipo: cuenta Hive", "Saldos: " + (", ".join(saldos) or "sin datos"),
           f"Publicaciones: {int(d.get('posts', 0)):,}"]
    a = _antiguedad(d.get("creada"))
    return out + ([a] if a else [])


def _hive_tx(e, d, txs, precio) -> list:
    tipos, totales, n_transf = [], {}, 0
    for o in d.get("operaciones", []):
        m = re.match(r"[a-z0-9_]{1,30}", str(o.get("tipo", "")).lower())
        t = m.group(0) if m else "otra"
        if t not in tipos:
            tipos.append(t)
        tr = o.get("transferencia")
        if tr:
            mon = re.sub(r"[^A-Z]", "", str(tr["moneda"]).upper())[:10] or "?"
            totales[mon] = totales.get(mon, 0.0) + float(tr["monto"])
            n_transf += 1
    out = ["Tipo: transaccion Hive", f"Operaciones: {d['total_operaciones']:,}", "Tipos: " + ", ".join(tipos[:8])]
    if n_transf:
        out.append(f"Transferencias: {n_transf} por un total de " + " + ".join(f"{v:,.3f} {k}" for k, v in totales.items()))
    return out


_ARMAR = {"btc_address": _btc_address, "btc_tx": _btc_tx, "hive_account": _hive_account, "hive_tx": _hive_tx}


def contexto(e, datos, txs=None, precio=None) -> str | None:
    if e.tipo not in _CONSULTABLES or not datos:
        return None
    try:
        return "\n".join(_ARMAR[e.tipo](e, datos, txs, precio))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
