"""F7-T3 (H-023): ningun `except:` desnudo en src.

Un `except:` sin tipo captura tambien BaseException (CancelledError,
KeyboardInterrupt), lo que puede tragarse la cancelacion de una tarea.
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def test_sin_except_desnudo():
    desnudos = []
    for py in sorted(SRC.rglob("*.py")):
        arbol = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ExceptHandler) and nodo.type is None:
                desnudos.append(f"{py.relative_to(SRC.parent).as_posix()}:{nodo.lineno}")
    assert not desnudos, f"except desnudo en: {desnudos}"
