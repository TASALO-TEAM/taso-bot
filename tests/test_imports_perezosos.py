"""El arranque no debe cargar el stack de analisis tecnico.

pandas + pandas_ta (arrastra numba/llvmlite) + matplotlib son ~140 MB de RSS
y solo los usan /ta, /graf y /mk. Se importan en la primera llamada.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

RAIZ = Path(__file__).resolve().parent.parent
PESADOS = ("pandas", "pandas_ta", "numba", "llvmlite", "matplotlib")


def test_arranque_no_carga_pandas_ni_numba_ni_matplotlib():
    # Subproceso limpio: en el de pytest otros tests ya cargaron esas libs.
    codigo = (
        "import sys\n"
        "import src.commands, src.handlers.callback_router\n"
        f"print([m for m in {PESADOS!r} if m in sys.modules])"
    )
    r = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=RAIZ, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr[-500:]
    assert r.stdout.strip().splitlines()[-1] == "[]"


@pytest.mark.asyncio
async def test_lazy_delega_al_handler_real():
    from src.commands import _lazy

    with patch("src.handlers.ta.ta_command", new=AsyncMock()) as real:
        handler = _lazy("src.handlers.ta", "ta_command")
        await handler("update", "context")

    real.assert_awaited_once_with("update", "context")


def test_comandos_ta_graf_mk_siguen_registrados():
    from src.commands import COMANDOS

    nombres = {c.name for c in COMANDOS}
    assert {"ta", "graf", "mk"} <= nombres
