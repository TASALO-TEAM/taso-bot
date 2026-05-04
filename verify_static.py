#!/usr/bin/env python3
"""
Comprehensive static analysis for taso-bot.
Performs: syntax check, import resolution, dependency verification.
"""

import ast
import sys
import os
from pathlib import Path
from typing import List, Tuple, Set

# Setup paths
BOT_ROOT = Path(__file__).resolve().parent
SRC = BOT_ROOT / "src"
sys.path.insert(0, str(BOT_ROOT))

# Files to check from the task
 TARGET_REL_PATHS = [
     "handlers/ta.py",
     "handlers/trading.py",
     "utils/chart_generator.py",
     "core/btc_advanced_analysis.py",
     "core/config.py",
     "core/ai_logic.py",
     "utils/ads_manager.py",
     "utils/file_manager.py",
     "utils/subscription_manager.py",
 ]

def parse_requirements() -> Set[str]:
    """Extract package names from requirements.txt (lowercased, no version constraints)."""
    req_file = BOT_ROOT / "requirements.txt"
    if not req_file.exists():
        return set()
    pkgs = set()
    for line in req_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Strip version specifiers and extras
        pkg = line.split(';')[0].strip()
        for sep in ['>=', '==', '<=', '>', '<', '~=', '===']:
            if sep in pkg:
                pkg = pkg.split(sep)[0].strip()
        # Remove extras like [job-queue]
        if '[' in pkg:
            pkg = pkg.split('[')[0].strip()
        pkg = pkg.lower().replace('-', '_')
        if pkg:
            pkgs.add(pkg)
    return pkgs

def get_third_party_imports(tree: ast.AST) -> Set[str]:
    """Extract third-party import names from AST (excluding stdlib, src.*)."""
    stdlib_mods = {
        'asyncio', 'json', 'pytz', 'requests', 'io', 'datetime', 'logging',
        'os', 'sys', 'math', 'random', 'traceback', 'typing', 'collections',
        'itertools', 'functools', 'pathlib', 'weakref', 'copy', 're',
    }
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split('.')[0]
                if name not in stdlib_mods and not name.startswith('src'):
                    imports.add(name.lower().replace('-', '_'))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                if node.module.startswith('src.'):
                    continue  # handled separately
                root_mod = node.module.split('.')[0]
                if root_mod not in stdlib_mods:
                    imports.add(root_mod.lower().replace('-', '_'))
    return imports

def check_syntax(filepath: Path) -> Tuple[bool, List[str]]:
    """Check syntax errors; return (is_ok, error_list)."""
    try:
        with open(filepath, encoding='utf-8') as f:
            source = f.read()
        ast.parse(source, filename=str(filepath))
        return True, []
    except SyntaxError as e:
        return False, [f"SyntaxError line {e.lineno}: {e.msg}"]
    except Exception as e:
        return False, [f"Parse error: {e}"]

def check_src_imports(filepath: Path) -> List[str]:
    """Check that imports starting with 'src.' resolve to existing files."""
    errors = []
    with open(filepath, encoding='utf-8') as f:
        source = f.read()
    try:
        tree = ast.parse(source, filename=str(filepath))
    except Exception:
        return []  # syntax errors already caught

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('src.'):
            parts = node.module.split('.')
            rel_path = Path(*parts[1:]).with_suffix('.py')  # skip 'src'
            full_path = SRC / rel_path
            if not full_path.exists():
                errors.append(f"Import target missing: {node.module} → {full_path.relative_to(BOT_ROOT)}")
    return errors

def check_undefined_names(filepath: Path) -> List[str]:
    """Detect likely NameErrors from f-strings using undefined variables (simple heuristic)."""
    warnings = []
    with open(filepath, encoding='utf-8') as f:
        source = f.read()
    try:
        tree = ast.parse(source, filename=str(filepath))
    except Exception:
        return []

    # Collect assigned names in each function scope
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Collect variable names assigned in this function
            assigned = set()
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            assigned.add(target.id)
                        elif isinstance(target, ast.Tuple):
                            for elt in target.elts:
                                if isinstance(elt, ast.Name):
                                    assigned.add(elt.id)
                elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
                    assigned.add(stmt.target.id)
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    assigned.add(stmt.target.id)
                elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                    # handle iterator variable(s)
                    if isinstance(stmt.target, ast.Name):
                        assigned.add(stmt.target.id)
                    elif isinstance(stmt.target, ast.Tuple):
                        for elt in stmt.target.elts:
                            if isinstance(elt, ast.Name):
                                assigned.add(elt.id)
                elif isinstance(stmt, ast.ExceptHandler):
                    if stmt.name and isinstance(stmt.name, str):
                        assigned.add(stmt.name)

            # Now scan for f-strings and format calls that might use undefined names
            for sub in ast.walk(node):
                # f-strings: JoinedStr with FormattedValue nodes
                if isinstance(sub, ast.JoinedStr):
                    for fmt_val in sub.values:
                        if isinstance(fmt_val, ast.FormattedValue):
                            if isinstance(fmt_val.value, ast.Name):
                                name = fmt_val.value.id
                                if name not in assigned and name not in node.args.args and not any(name == p.arg for p in ast.walk(node) if isinstance(p, ast.arg)):
                                    warnings.append(f"Possible undefined variable '{name}' in f-string at line {sub.lineno or '?'}")
                # .format() calls: check keyword arguments
                if isinstance(sub, ast.Call):
                    if isinstance(sub.func, ast.Attribute) and sub.func.attr == 'format':
                        # If first arg is a Constant (string) and keywords present, check if keywords are assigned
                        # But this is complex; we'll skip for now
                        pass
    return warnings

def main():
    print(f"🔬 taso-bot static verification — {len(TARGET_REL_PATHS)} files\n")
    print(f"Project root: {BOT_ROOT}\n")

    req_pkgs = parse_requirements()
    total_errors = 0
    total_warnings = 0

    for rel in TARGET_REL_PATHS:
        fp = SRC / rel
        status = "✅"
        msgs = []

        # 1. Syntax
        ok, syn_errors = check_syntax(fp)
        if not ok:
            status = "❌"
            msgs.extend(syn_errors)
            total_errors += len(syn_errors)
            print(f"{status} {rel}")
            for e in syn_errors:
                print(f"   {e}")
            continue

        # 2. src.* import resolution
        imp_errors = check_src_imports(fp)
        if imp_errors:
            status = "⚠️ "
            msgs.extend(imp_errors)
            total_errors += len(imp_errors)
            # We'll still continue to dependency check

        # 3. Undefined name detection (basic)
        # Only do for handlers as they are larger
        if 'handlers/' in rel or 'core/' in rel:
            name_warns = check_undefined_names(fp)
            if name_warns:
                total_warnings += len(name_warns)
                msgs.extend([f"Potential runtime error: {w}" for w in name_warns])

        # 4. Dependency check
        with open(fp, encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(fp))
        third_party = get_third_party_imports(tree)
        missing = [pkg for pkg in third_party if pkg not in req_pkgs]
        if missing:
            status = "⚠️ "
            msgs.append(f"Undeclared deps: {', '.join(sorted(missing))}")
            total_errors += len(missing)

        if status == "✅":
            print(f"{status} {rel}")
        else:
            print(f"{status} {rel}")
            for m in msgs:
                print(f"   • {m}")

    print("\n" + "=" * 50)
    if total_errors == 0:
        print("✅ All files passed syntax and import checks.")
    else:
        print(f"❌ {total_errors} issue(s) found.")
    if total_warnings:
        print(f"⚠️  {total_warnings} warning(s) (potential runtime issues).")
    print("=" * 50)
    return 1 if total_errors else 0

if __name__ == "__main__":
    sys.exit(main())
