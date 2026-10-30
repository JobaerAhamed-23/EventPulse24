"""AD-2: `formats` is a format layer — it parses, it does not reach out.

A format module reads bytes and produces values. It must not open a socket, touch the
database, or reach into Django's settings: the same parser has to work the same way in
the API process, the worker process, and a test with no database at all.

**The one third-party library it may use is `icalendar`** — the ICS format's own
grammar. That is what the `single-ics-parser` import contract is for: it pins *which
module* reaches for it, so the fork is impossible, not merely discouraged.

This file is the allowlist half; the import-linter contract is the graph half.
"""

import ast
import sys
from pathlib import Path

import pytest

from tests.architecture.checkers import BACKEND_DIR, _module_name

FORMATS_DIR = BACKEND_DIR / "formats"

#: The only non-stdlib packages a format module may import. `icalendar` parses the
#: format's grammar; nothing else does any work on its behalf.
ALLOWED_THIRD_PARTY = frozenset({"icalendar"})

#: Project packages a format module may import. A format is a *leaf* in the layering:
#: it knows nothing of the catalog, the ports, or the domain's identity policy.
ALLOWED_PROJECT = frozenset({"formats"})

#: The modules that reach for the network, the database, or the process environment.
FORBIDDEN_NAMES = frozenset(
    {
        "django",
        "ninja",
        "pydantic",
        "pydantic_settings",
        "psycopg",
        "celery",
        "httpx",
        "httpcore",
        "requests",
        "urllib3",
        "redis",
        "cryptography",
    }
)

FORMAT_FILES = sorted(FORMATS_DIR.rglob("*.py"))


def _imported_names(path: Path) -> list[tuple[str, int]]:
    """The absolute module names `path` imports, with the line each was on.

    Relative imports are resolved against the file's own package, so a `from .. import x`
    cannot hide a reach outside `formats`.
    """
    module = _module_name(path, BACKEND_DIR)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    names = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            names += [(alias.name, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            target = node.module or ""
            if node.level:  # resolve `from ..x import y` against this file's package
                parts = package.split(".") if package else []
                base = parts[: max(len(parts) - (node.level - 1), 0)]
                target = ".".join([*base, node.module] if node.module else base)
            names.append((target, node.lineno))
    return names


@pytest.mark.parametrize("path", FORMAT_FILES, ids=lambda p: str(p.relative_to(BACKEND_DIR)))
def test_a_format_module_reaches_only_for_the_format_library(path):
    """The only non-stdlib import a format module may make is `icalendar` (or a sibling)."""
    violations = []
    for name, lineno in _imported_names(path):
        root = name.split(".")[0]
        if root in ALLOWED_THIRD_PARTY or root in sys.stdlib_module_names:
            continue
        if root in ALLOWED_PROJECT:
            continue
        violations.append(f"{lineno}: {name}")

    assert violations == []


@pytest.mark.parametrize("path", FORMAT_FILES, ids=lambda p: str(p.relative_to(BACKEND_DIR)))
def test_a_format_module_imports_no_project_package_but_its_own(path):
    """A format is a leaf: it does not know the catalog, the ports, or the domain.

    The stdlib is free, `icalendar` is free (it is the format's own grammar), and the
    format's own siblings are free. Nothing else is — in particular not Django, not the
    HTTP client, not the database.
    """
    violations = []
    for name, lineno in _imported_names(path):
        if not name:
            continue
        root = name.split(".")[0]
        if root in ALLOWED_PROJECT or root in sys.stdlib_module_names:
            continue
        if root in FORBIDDEN_NAMES or (BACKEND_DIR / root).is_dir():
            violations.append(f"{lineno}: {name}")

    assert violations == []


def test_a_format_module_cannot_reach_for_the_network_the_database_or_django():
    """The rule, exercised on a planted source — the three reaches that would break it."""
    source = "import httpx\nimport django.db\nfrom shared import retention\n"

    violations = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            if root in sys.stdlib_module_names:
                continue
            if root in FORBIDDEN_NAMES or root not in ALLOWED_THIRD_PARTY | ALLOWED_PROJECT:
                violations.append(name)

    assert violations == ["httpx", "django.db", "shared"]


def test_the_format_layer_is_not_empty():
    """A guard against the package being emptied by a refactor and the tests going quiet."""
    assert {p.relative_to(BACKEND_DIR).as_posix() for p in FORMAT_FILES} >= {
        "formats/__init__.py",
        "formats/ics/__init__.py",
        "formats/ics/events.py",
        "formats/ics/parser.py",
        "formats/ics/windows_zones.py",
        "formats/text.py",
        "formats/times.py",
    }
