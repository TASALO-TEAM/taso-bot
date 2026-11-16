"""Guardas del explorador (F4-T8): limite por usuario y redaccion para logs.

Solo memoria, acotado. Sin red ni dependencias.
"""
import time
from collections import deque


class UserLimiter:
    """Ventana deslizante por usuario. Los intentos rechazados no cuentan."""

    def __init__(self, max_calls=5, window=60.0, max_users=1000, clock=time.monotonic):
        self.max_calls = max_calls
        self.window = window
        self.max_users = max_users
        self._clock = clock
        self._hits = {}

    def allow(self, user_id):
        """Devuelve (permitido, segundos_de_espera)."""
        now = self._clock()
        q = self._hits.get(user_id)
        if q is None:
            q = self._hits[user_id] = deque()
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.max_calls:
            return False, self.window - (now - q[0])
        q.append(now)
        if len(self._hits) > self.max_users:
            self._purge(now)
        return True, 0.0

    def _purge(self, now):
        for uid in [u for u, h in self._hits.items() if not h or now - h[-1] >= self.window]:
            del self._hits[uid]
        # Si siguen sobrando usuarios activos, se descartan los mas antiguos.
        extra = len(self._hits) - self.max_users
        if extra > 0:
            for uid in sorted(self._hits, key=lambda u: self._hits[u][-1])[:extra]:
                del self._hits[uid]


def redact(text):
    """Resumen seguro para logs: longitud y extremos, nunca la entrada completa."""
    n = len(text)
    if n <= 12:
        return f"[{n} chars]"
    return f"[{n} chars {text[:4]}...{text[-4:]}]"