"""AST checks for rules import-linter and Ruff can't express (AD-2 stdlib-only, AD-3 aliases).

They read syntax only, so dynamic forms (aliasing a module to another name, `import django.db`
then `django.db.connection`, calls built at runtime) are out of reach; code review covers those.
"""

import ast
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_PACKAGES = ("domain", "apps", "ports", "adapters", "config", "worker", "shared")

# domain may import the stdlib, itself, and these two stdlib-only shared modules.
DOMAIN_ALLOWED_PROJECT_MODULES = ("domain", "shared.constants", "shared.ids")
# Files that must be stdlib-only because domain imports them (shared/__init__ runs on import).
STDLIB_ONLY_FILES = ("shared/__init__.py", "shared/constants.py", "shared/ids.py")
# Stdlib-only by design, not because domain imports them; they may import no project module.
SHARED_STDLIB_ONLY_FILES = ("shared/actor.py",)


def _module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_allowed(module: str, allowed: tuple[str, ...]) -> bool:
    if module.split(".")[0] in sys.stdlib_module_names:
        return True
    return any(module == m or module.startswith(f"{m}.") for m in allowed)


def non_stdlib_imports(
    path: Path,
    root: Path = BACKEND_DIR,
    allowed: tuple[str, ...] = DOMAIN_ALLOWED_PROJECT_MODULES,
) -> list[str]:
    """Imports in `path` outside the stdlib + `allowed` project modules."""
    module = _module_name(path, root)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    violations = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            violations += [
                f"{node.lineno}: import {a.name}"
                for a in node.names
                if not _is_allowed(a.name, allowed)
            ]
        elif isinstance(node, ast.ImportFrom):
            target = node.module or ""
            if node.level:  # resolve `from ..x import y` against this file's package
                parts = package.split(".") if package else []
                base = parts[: max(len(parts) - (node.level - 1), 0)]
                target = ".".join([*base, node.module] if node.module else base)
            names = [f"{target}.{a.name}" if target else a.name for a in node.names]
            if not (target and _is_allowed(target, allowed)) and not all(
                _is_allowed(n, allowed) for n in names
            ):
                source = "." * node.level + (node.module or "")
                violations.append(f"{node.lineno}: from {source} import ...")
    return violations


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _is_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and (node.value is None or isinstance(node.value, str))


def alias_violations(source: str) -> list[str]:
    """Database calls that don't name their alias with shared.db.PERSONAL / CATALOG (AD-3)."""
    violations = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            keywords = {kw.arg: kw.value for kw in node.keywords}
            if name in ("atomic", "on_commit") and "using" not in keywords:
                violations.append(f"{node.lineno}: {name}() without using=")
            if "using" in keywords and _is_literal(keywords["using"]):
                violations.append(f"{node.lineno}: using= literal")
            if name == "using" and isinstance(node.func, ast.Attribute):
                if node.args and _is_literal(node.args[0]):
                    violations.append(f"{node.lineno}: .using() literal")
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id == "connections":
                if _is_literal(node.slice):
                    violations.append(f"{node.lineno}: connections[] literal")
        elif isinstance(node, ast.ImportFrom) and node.module == "django.db":
            if any(alias.name == "connection" for alias in node.names):
                violations.append(f"{node.lineno}: django.db.connection is always 'default'")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) and _call_name(decorator) == "atomic":
                    violations.append(f"{decorator.lineno}: bare @atomic")
    return violations


def project_files() -> list[Path]:
    return sorted(p for root in ROOT_PACKAGES for p in (BACKEND_DIR / root).rglob("*.py"))
