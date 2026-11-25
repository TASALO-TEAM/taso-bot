"""Logos del mapa de calor: descarga con cache en disco. Sin red (HTTP inyectado)."""

import asyncio
import io

import pytest
from PIL import Image

from src.heatmap import logos


def _png(color=(255, 0, 255), lado=64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (lado, lado), color + (255,)).save(buf, format="PNG")
    return buf.getvalue()


class HttpFalso:
    """http_bytes(url) -> bytes. `respuestas` mapea id -> bytes o Exception."""

    def __init__(self, respuestas=None, defecto=None):
        self.respuestas = respuestas or {}
        self.defecto = defecto if defecto is not None else _png()
        self.urls = []
        self.activas = 0
        self.max_activas = 0

    async def __call__(self, url):
        self.urls.append(url)
        self.activas += 1
        self.max_activas = max(self.max_activas, self.activas)
        try:
            await asyncio.sleep(0)  # cede el turno: permite medir la concurrencia
            clave = int(url.rsplit("/", 1)[1].split(".")[0])
            r = self.respuestas.get(clave, self.defecto)
            if isinstance(r, Exception):
                raise r
            return r
        finally:
            self.activas -= 1


@pytest.fixture(autouse=True)
def _limpiar():
    logos.reset_cache()
    yield
    logos.reset_cache()


def _cargar(refs, http, carpeta):
    return asyncio.run(logos.cargar_logos(refs, http_bytes=http, carpeta=carpeta))


def test_descarga_guarda_en_disco_y_devuelve_los_bytes(tmp_path):
    http = HttpFalso()
    res = _cargar([1, 1027], http, tmp_path)
    assert set(res) == {1, 1027}
    assert (tmp_path / "1.png").read_bytes() == res[1]
    assert http.urls == [
        "https://s2.coinmarketcap.com/static/img/coins/128x128/1.png",
        "https://s2.coinmarketcap.com/static/img/coins/128x128/1027.png",
    ]


def test_la_segunda_llamada_sale_del_disco_sin_red(tmp_path):
    _cargar([1], HttpFalso(), tmp_path)
    http2 = HttpFalso()
    res = _cargar([1], http2, tmp_path)
    assert 1 in res and http2.urls == []


def test_ids_repetidos_se_piden_una_sola_vez(tmp_path):
    http = HttpFalso()
    _cargar([5, 5, 5], http, tmp_path)
    assert len(http.urls) == 1


@pytest.mark.parametrize("malo", [0, -5, "7", True, None, 1.5, 10**12])
def test_ids_invalidos_no_construyen_url(tmp_path, malo):
    http = HttpFalso()
    assert _cargar([malo], http, tmp_path) == {}
    assert http.urls == []


def test_un_error_de_red_omite_ese_logo_sin_romper_los_demas(tmp_path):
    http = HttpFalso({2: RuntimeError("404")})
    res = _cargar([1, 2, 3], http, tmp_path)
    assert set(res) == {1, 3}
    assert not (tmp_path / "2.png").exists()


def test_respuesta_que_no_es_png_se_omite_y_no_se_guarda(tmp_path):
    http = HttpFalso({4: b"<html>no soy una imagen</html>"})
    assert _cargar([4], http, tmp_path) == {}
    assert not (tmp_path / "4.png").exists()


def test_archivo_gigante_se_omite(tmp_path):
    http = HttpFalso({6: _png() + b"\x00" * (logos.MAX_BYTES + 1)})
    assert _cargar([6], http, tmp_path) == {}
    assert not (tmp_path / "6.png").exists()


def test_archivo_corrupto_en_disco_se_vuelve_a_pedir(tmp_path):
    (tmp_path / "7.png").write_bytes(b"basura")
    http = HttpFalso()
    res = _cargar([7], http, tmp_path)
    assert 7 in res and len(http.urls) == 1
    assert (tmp_path / "7.png").read_bytes() == res[7]


def test_la_concurrencia_esta_acotada(tmp_path):
    http = HttpFalso()
    _cargar(list(range(1, 41)), http, tmp_path)
    assert 1 < http.max_activas <= logos.CONCURRENCIA


def test_cache_negativa_evita_reintentar_en_cada_consulta(tmp_path):
    http = HttpFalso({8: RuntimeError("404")})
    _cargar([8], http, tmp_path)
    _cargar([8], http, tmp_path)
    assert len(http.urls) == 1  # el segundo intento no sale a la red


def test_carpeta_inexistente_se_crea(tmp_path):
    destino = tmp_path / "a" / "b"
    res = _cargar([9], HttpFalso(), destino)
    assert 9 in res and (destino / "9.png").exists()


def test_carpeta_no_escribible_no_rompe_y_devuelve_el_logo(tmp_path):
    bloqueo = tmp_path / "archivo"
    bloqueo.write_text("soy un archivo, no una carpeta")
    res = _cargar([10], HttpFalso(), bloqueo / "logos")
    assert 10 in res  # sin disco igual se usa el logo recien descargado
