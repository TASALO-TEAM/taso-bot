import py_compile
import traceback
import sys
import subprocess

files = [
    r"C:\Users\ernes\Documents\tasalo\taso-bot\src\handlers\ta.py",
    r"C:\Users\ernes\Documents\tasalo\taso-bot\src\handlers\trading.py",
    r"C:\Users\ernes\Documents\tasalo\taso-bot\src\handlers\callback_router.py",
]

errors = []

for filepath in files:
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'py_compile', filepath],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"OK: {filepath}")
        else:
            error_msg = result.stderr or result.stdout
            errors.append({"file": filepath, "message": error_msg.strip()})
            print(f"ERROR in {filepath}:")
            print(f"  {error_msg}")
    except subprocess.TimeoutExpired:
        errors.append({"file": filepath, "message": "Compilation timed out"})
        print(f"TIMEOUT: {filepath}")
    except Exception as e:
        errors.append({"file": filepath, "message": str(e)})
        print(f"UNEXPECTED ERROR in {filepath}: {e}")

if errors:
    print(f"\n{len(errors)} file(s) had syntax errors:")
    for err in errors:
        print(f"  - {err['file']}: {err['message']}")
    sys.exit(1)
else:
    print("\nAll files compiled successfully!")
    sys.exit(0)
