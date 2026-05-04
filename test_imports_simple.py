import importlib.util, traceback
import sys

tests = [
    ("ta", r"C:\Users\ernes\Documents\tasalo\taso-bot\src\handlers\ta.py"),
    ("trading", r"C:\Users\ernes\Documents\tasalo\taso-bot\src\handlers\trading.py"),
    ("callback_router", r"C:\Users\ernes\Documents\tasalo\taso-bot\src\handlers\callback_router.py"),
]

for mod_name, path in tests:
    try:
        spec = importlib.util.spec_from_file_location(mod_name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        traceback.print_exc()
