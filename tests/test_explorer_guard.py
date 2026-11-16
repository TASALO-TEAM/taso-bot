"""F4-T8: limite por usuario y redaccion de entradas para logs."""
from src.explorer.guard import UserLimiter, redact


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_permite_hasta_el_maximo_y_luego_bloquea():
    r = Reloj()
    lim = UserLimiter(max_calls=3, window=60, clock=r)
    assert [lim.allow(1)[0] for _ in range(3)] == [True, True, True]
    ok, espera = lim.allow(1)
    assert ok is False and 0 < espera <= 60


def test_usuarios_independientes():
    lim = UserLimiter(max_calls=1, window=60, clock=Reloj())
    assert lim.allow(1)[0] is True
    assert lim.allow(2)[0] is True
    assert lim.allow(1)[0] is False


def test_se_libera_al_pasar_la_ventana():
    r = Reloj()
    lim = UserLimiter(max_calls=1, window=60, clock=r)
    assert lim.allow(1)[0] is True
    assert lim.allow(1)[0] is False
    r.t += 61
    assert lim.allow(1)[0] is True


def test_el_bloqueo_no_extiende_la_espera():
    r = Reloj()
    lim = UserLimiter(max_calls=1, window=60, clock=r)
    lim.allow(1)
    for _ in range(50):
        r.t += 1
        lim.allow(1)  # intentos rechazados no cuentan
    r.t += 11  # 61 s desde la unica llamada aceptada
    assert lim.allow(1)[0] is True


def test_memoria_acotada():
    r = Reloj()
    lim = UserLimiter(max_calls=1, window=60, max_users=100, clock=r)
    for uid in range(1000):
        r.t += 0.001
        lim.allow(uid)
    assert len(lim._hits) <= 100


def test_redact_no_expone_la_entrada_completa():
    addr = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
    s = redact(addr)
    assert addr not in s
    assert str(len(addr)) in s


def test_redact_corto_y_vacio():
    assert "hola" not in redact("hola")
    assert redact("") == "[0 chars]"