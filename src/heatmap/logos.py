"""Logos de monedas para el mapa de calor: se descargan una vez y se guardan en disco.

Aislado como data.py: el HTTP se recibe por parametro, asi se prueba sin red. Un logo que
falla (404, corrupto, demasiado grande, sin red) se omite: el mapa se dibuja igual con el
simbolo. Los datos vienen de un CDN externo, por eso se valida todo antes de usarlo.
"""

import asyncio
import io
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable, Iterable, Optional

from PIL import Image

logger = logging.getLogger(__name__)

LOGO_URL = "https://s2.coinmarketcap.com/static/img/coins/128x128/{id}.png"
CARPETA = Path(__file__).resolve().parents[2] / "data" / "logos"  # data/ esta en .gitignore
MAX_BYTES = 100_000  # un logo de 128x128 pesa unos pocos KB
CONCURRENCIA = 8
TIMEOUT = 5.0
TTL_FALLO = 3600  # no reintentar en cada consulta un logo que acaba de fallar
ID_MAX = 10**9

_fallos: dict = {}


def reset_cache() -> None:
    _fallos.clear()


def id_valido(valor) -> Optional[int]:
    """Entero positivo razonable (no bool) o None. Evita armar URLs con datos raros."""
    if isinstance(valor, int) and not isinstance(valor, bool) and 0 < valor <= ID_MAX:
        return valor
    return None


def _es_png(datos: bytes) -> bool:
    if not datos or len(datos) > MAX_BYTES:
        return False
    try:
        with Image.open(io.BytesIO(datos)) as im:
            im.verify()
            return im.format == "PNG"
    except Exception:
        return False


async def http_bytes(url: str) -> bytes:
    import httpx  # import perezoso: solo si hay que descargar

    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


async def cargar_logos(
    refs: Iterable,
    http_bytes: Callable[[str], Awaitable[bytes]] = http_bytes,
    carpeta: Path = CARPETA,
) -> dict:
    """{id: bytes PNG} de los logos disponibles. Nunca lanza por un logo individual."""
    ids = list(dict.fromkeys(i for i in map(id_valido, refs) if i is not None))
    carpeta = Path(carpeta)
    sem = asyncio.Semaphore(CONCURRENCIA)

    async def uno(i: int):
        ruta = carpeta / f"{i}.png"
        try:
            datos = ruta.read_bytes()
            if _es_png(datos):
                return i, datos
        except OSError:
            pass  # no esta en disco: se descarga
        if time.time() - _fallos.get(i, 0.0) < TTL_FALLO:
            return i, None
        async with sem:
            try:
                datos = await asyncio.wait_for(http_bytes(LOGO_URL.format(id=i)), TIMEOUT + 1)
                if not _es_png(datos):
                    raise ValueError("no es un PNG valido")
            except Exception as e:
                logger.warning("Logo %s no disponible: %s", i, type(e).__name__)
                _fallos[i] = time.time()
                return i, None
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(datos)
        except OSError as e:
            logger.warning("No se pudo guardar el logo %s: %s", i, type(e).__name__)
        return i, datos

    return {i: d for i, d in await asyncio.gather(*(uno(i) for i in ids)) if d}
