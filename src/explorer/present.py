"""F4-T5: presentacion del explorador. Pura (sin red): recibe la Entrada y los datos ya consultados.

HTML de Telegram. Todo dato de terceros pasa por html.escape. Nunca supera 4096 caracteres.
"""
import html
from datetime import datetime, timezone

from src.explorer.classify import Entrada

MAX = 4096
_e = html.escape

_ERRORES = {
    "no_encontrado": "No encontré ese dato. Revisa que esté bien escrito.",
    "fuente_no_disponible": "Las fuentes públicas no responden ahora. Intenta de nuevo en un momento.",
    "no_disponible": "Las fuentes públicas no responden ahora. Intenta de nuevo en un momento.",
    "limite": "Hay demasiadas consultas ahora mismo. Espera un momento e intenta de nuevo.",
    "respuesta_invalida": "Una fuente respondió con datos que no pude interpretar.",
}
_AYUDA = ("No reconocí ese texto. Puedo consultar:\n• direcciones y transacciones de Bitcoin\n"
          "• usuarios y transacciones de Hive (@usuario)\n• direcciones y transacciones EVM (0x…)\n"
          "• facturas Lightning (solo decodificar)")
_NO_CONSULTA = {
    "lnurl": "LNURL reconocida. No se consulta ni se abre: puede apuntar a un servicio externo.",
    "lightning_address": "Lightning address reconocida. No se consulta: resolverla implica contactar un servidor externo.",
}


def mensaje_error(codigo: str) -> str:
    return "⚠️ " + _ERRORES.get(codigo, "No pude completar la consulta. Intenta de nuevo más tarde.")


def enlace(e: Entrada) -> str | None:
    """URL fija a un explorador publico; el valor ya fue validado por el clasificador."""
    base = {"btc_address": "https://mempool.space/address/", "btc_tx": "https://mempool.space/tx/",
            "hive_tx": "https://hiveblocks.com/tx/", "evm_address": "https://etherscan.io/address/",
            "evm_tx": "https://etherscan.io/tx/"}.get(e.tipo)
    if base:
        return base + e.valor
    if e.tipo == "hive_account":
        return "https://hiveblocks.com/@" + e.valor
    return None


def _btc(sats) -> str:
    return f"{sats / 1e8:.8f} BTC"


def _usd(sats, precio) -> str:
    if not precio:
        return ""
    usd, fuente, hora = precio
    return f" (≈ ${sats / 1e8 * usd:,.2f} · {_e(str(fuente))} {_e(str(hora))})"


def _n(v) -> str:
    return f"{v:,}"


def _fecha(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


def _corto(txid: str) -> str:
    return f"{txid[:8]}…{txid[-6:]}"


def _linea_enlace(e: Entrada) -> list:
    u = enlace(e)
    return [f'🔗 <a href="{_e(u, quote=True)}">Abrir en el explorador</a>'] if u else []


def _btc_address(e, d, txs, precio):
    cab = [f"🔎 <b>Dirección Bitcoin</b> · {_e(e.red or '?')} · {_e(e.info('formato', '?'))}", f"<code>{_e(e.valor)}</code>", ""]
    cuerpo = [f"💰 Saldo: <b>{_btc(d['saldo_sats'])}</b>{_usd(d['saldo_sats'], precio)}"]
    if d.get("pendiente_sats"):
        cuerpo.append(f"⏳ Pendiente (sin confirmar): {d['pendiente_sats'] / 1e8:+.8f} BTC")
    cuerpo += [f"📥 Recibido total: {_btc(d['recibido_sats'])}", f"📤 Gastado total: {_btc(d['gastado_sats'])}",
               f"🔁 Transacciones: {_n(d['tx_count'])}" + (f" (+{d['tx_pendientes']} pendientes)" if d.get("tx_pendientes") else "")]
    if not precio:
        cuerpo.append("ℹ️ Sin precio disponible: no se muestra valor en USD.")
    return cab + cuerpo, _lineas_txs(txs)


def _lineas_txs(txs):
    if not txs:
        return []
    out = ["", "<b>Últimas transacciones</b>"]
    for t in txs:
        estado = f"bloque {_n(t['altura'])}" if t.get("confirmada") and t.get("altura") is not None else "pendiente"
        fecha = f" · {_e(str(t['fecha']))}" if t.get("fecha") else ""
        out.append(f"• <code>{_corto(str(t['txid']))}</code> {t['neto_sats'] / 1e8:+.8f} BTC · {estado}{fecha}")
    return out


def _btc_tx(e, d, precio):
    if d["confirmada"]:
        conf = d.get("confirmaciones")
        est = f"✅ Confirmada · {_n(conf)} confirmaciones" if conf is not None else "✅ Confirmada"
        est += f" · bloque {_n(d['altura'])}" + (f" · {_e(str(d['fecha']))}" if d.get("fecha") else "")
    else:
        est = "⏳ Sin confirmar (en mempool)"
    return [f"🔎 <b>Transacción Bitcoin</b>", f"<code>{_e(e.valor)}</code>", "", est,
            f"↔️ {_n(d['entradas'])} entradas · {_n(d['salidas'])} salidas",
            f"💸 Total en salidas: <b>{_btc(d['total_salidas_sats'])}</b>{_usd(d['total_salidas_sats'], precio)}",
            f"⛏️ Comisión: {_n(d['fee_sats'])} sats · {_n(d['tamano'])} bytes"], []


def _hv(v, mon):
    return "?" if v is None else f"{v:,.3f} {mon}"


def _hive_cuenta(e, d):
    c = [f"🔎 <b>Cuenta Hive</b> · @{_e(str(d['nombre']))}", ""]
    c += [f"💰 {_hv(d.get('hive'), 'HIVE')} · {_hv(d.get('hbd'), 'HBD')} · {_hv(d.get('hp'), 'HP')}",
          f"📝 Publicaciones: {_n(d.get('posts', 0))}"]
    if d.get("creada"):
        c.append(f"📅 Creada: {_e(str(d['creada']))}")
    if d.get("ultimo_post"):
        c.append(f"🕒 Última publicación: {_e(str(d['ultimo_post']))}")
    return c, []


def _hive_tx(e, d):
    c = [f"🔎 <b>Transacción Hive</b>", f"<code>{_e(e.valor)}</code>", "",
         f"🧱 Bloque: {_n(d['bloque']) if d.get('bloque') is not None else '?'}",
         f"⚙️ Operaciones: {_n(d['total_operaciones'])}"]
    for o in d.get("operaciones", []):
        t = o.get("transferencia")
        c.append(f"• transferencia: @{_e(t['de'])} → @{_e(t['a'])} · {t['monto']:,.3f} {_e(t['moneda'])}" if t
                 else f"• {_e(str(o.get('tipo', '?')))}")
    return c, []


def _eth(wei, simbolo) -> str:
    return f"{wei / 10**18:.6f} {_e(str(simbolo))}"


_TIPO_EVM = {"cuenta": "cuenta normal", "delegacion": "cuenta con delegación EIP-7702 (no es un contrato)",
             "contrato": "contrato"}


def _evm_address(e, d):
    c = ["🔎 <b>Dirección EVM</b>", f"<code>{_e(e.valor)}</code>", ""]
    if d["redes"]:
        c += [f"• <b>{_e(str(r['red']))}</b>: {_eth(r['saldo_wei'], r['simbolo'])} · nonce {_n(r['nonce'])}"
              f" · {_TIPO_EVM.get(r['tipo'], 'cuenta')}" for r in d["redes"]]
    else:
        c.append("ℹ️ Sin actividad (saldo y nonce en cero) en las redes que respondieron.")
    if d.get("sin_respuesta"):
        c.append("⚠️ Sin respuesta de: " + ", ".join(_e(str(x)) for x in d["sin_respuesta"]) + ". Ese dato puede faltar.")
    c.append("ℹ️ Solo saldo nativo y nonce: no incluye tokens ni nombres ENS.")
    return c, []


def _evm_tx(e, d):
    est = {"exitosa": "✅ Exitosa", "fallida": "❌ Fallida", "pendiente": "⏳ Sin confirmar (pendiente)"}.get(d["estado"], "?")
    if d["estado"] != "pendiente":
        if d.get("confirmaciones") is not None:
            est += f" · {_n(d['confirmaciones'])} confirmaciones"
        if d.get("bloque") is not None:
            est += f" · bloque {_n(d['bloque'])}"
    destino = f"↘️ A: <code>{_e(str(d['a']))}</code>" if d.get("a") else "📄 Creación de contrato (sin destino)"
    return ["🔎 <b>Transacción EVM</b> · Ethereum", f"<code>{_e(e.valor)}</code>", "", est,
            f"↗️ De: <code>{_e(str(d['de']))}</code>", destino, f"💸 Valor: <b>{_eth(d['valor_wei'], 'ETH')}</b>",
            "ℹ️ Solo se consulta Ethereum: las otras redes no se consultan."], []


def _ln(e):
    sats = e.info("sats")
    monto = f"{_n(sats)} sats" if sats is not None else (f"{_n(e.info('msat'))} msat" if e.info("msat") else "sin monto fijado")
    c = [f"⚡ <b>Factura Lightning</b> · {_e(e.red or '?')}", "", f"💸 Monto: <b>{monto}</b>"]
    if e.info("creada"):
        c.append(f"📅 Creada: {_fecha(e.info('creada'))}")
    if e.info("expira_en") is not None:
        c.append(f"⏱️ Expira {_n(e.info('expira_en'))} s después de crearse")
    c.append("ℹ️ Solo se decodifica localmente: no se consulta ni se paga nada.")
    return c, []


def formatear(e: Entrada, datos=None, *, txs=None, precio=None) -> str:
    """Texto HTML <= 4096. `precio` = (usd_por_btc, fuente, hora) o None."""
    if e.tipo == "btc_address" and datos:
        cab, cola = _btc_address(e, datos, txs, precio)
    elif e.tipo == "btc_tx" and datos:
        cab, cola = _btc_tx(e, datos, precio)
    elif e.tipo == "hive_account" and datos:
        cab, cola = _hive_cuenta(e, datos)
    elif e.tipo == "hive_tx" and datos:
        cab, cola = _hive_tx(e, datos)
    elif e.tipo == "evm_address" and datos:
        cab, cola = _evm_address(e, datos)
    elif e.tipo == "evm_tx" and datos:
        cab, cola = _evm_tx(e, datos)
    elif e.tipo == "ln_invoice":
        cab, cola = _ln(e)
    elif e.tipo in _NO_CONSULTA:
        cab, cola = ["ℹ️ " + _NO_CONSULTA[e.tipo]], []
    elif e.tipo == "desconocido":
        cab, cola = [_AYUDA], []
    else:
        return mensaje_error("no_encontrado")
    pie = _linea_enlace(e)
    while cola and len("\n".join(cab + cola + pie)) > MAX:
        cola.pop()
    txt = "\n".join(cab + cola + pie)
    if len(txt) > MAX:   # solo si la cabecera sola ya excede: no ocurre con datos acotados
        txt = txt[:MAX].rsplit("\n", 1)[0]
    return txt
