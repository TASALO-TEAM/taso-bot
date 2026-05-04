"""Minimal test runner script for taso-bot."""
import subprocess
import sys
import os

project_dir = r"C:\Users\ernes\Documents\tasalo\taso-bot"
venv_python = os.path.join(project_dir, ".venv", "bin", "python")
if not os.path.exists(venv_python):
    venv_python = sys.executable

env = os.environ.copy()
env["PYTHONPATH"] = project_dir

result = subprocess.run(
    [venv_python, "-m", "pytest", "-v"],
    capture_output=True,
    text=True,
    env=env,
    cwd=project_dir
)

print(result.stdout)
print(result.stderr)
sys.exit(result.returncode)