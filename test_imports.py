import importlib.util
import traceback
import sys

modules = [
    ("ta", r"C:\Users\ernes\Documents\tasalo\taso-bot\src\handlers\ta.py"),
    ("trading", r"C:\Users\ernes\Documents\tasalo\taso-bot\src\handlers\trading.py"),
    ("callback_router", r"C:\Users\ernes\Documents\tasalo\taso-bot\src\handlers\callback_router.py"),
]

for name, path in modules:
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        print(f"✓ {name} imported successfully")
    except Exception as e:
        print(f"✗ {name} failed:")
        traceback.print_exc()
        print()
