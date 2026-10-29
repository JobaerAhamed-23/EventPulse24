"""AD-2: domain imports the stdlib, plus shared.constants / shared.ids (both stdlib-only).

This is the allowlist half; import-linter's "domain is pure" contract is the graph half.
"""

import pytest

from tests.architecture.checkers import (
    BACKEND_DIR,
    SHARED_STDLIB_ONLY_FILES,
    STDLIB_ONLY_FILES,
    non_stdlib_imports,
)

CHECKED_FILES = sorted((BACKEND_DIR / "domain").rglob("*.py")) + [
    BACKEND_DIR / path for path in STDLIB_ONLY_FILES
]


@pytest.mark.parametrize("path", CHECKED_FILES, ids=lambda p: str(p.relative_to(BACKEND_DIR)))
def test_file_imports_stdlib_and_allowed_modules_only(path):
    assert non_stdlib_imports(path) == []


@pytest.mark.parametrize("path", SHARED_STDLIB_ONLY_FILES)
def test_shared_stdlib_only_file_imports_no_project_module(path):
    assert non_stdlib_imports(BACKEND_DIR / path, allowed=()) == []


def test_shared_stdlib_only_check_reports_a_project_import(tmp_path):
    path = tmp_path / "shared" / "_planted.py"
    path.parent.mkdir()
    path.write_text("from shared.constants import SEND_KEY_SEPARATOR\n")

    assert len(non_stdlib_imports(path, root=tmp_path, allowed=())) == 1


@pytest.fixture
def domain_file(tmp_path):
    def write(source: str, name: str = "domain/_planted.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        return non_stdlib_imports(path, root=tmp_path)

    return write


@pytest.mark.parametrize(
    "source",
    [
        "import requests\n",
        "import django.db\n",
        "from ninja import Schema\n",
        "from shared import retention\n",
        "from shared.errors import ErrorOut\n",
        "import apps.catalog\n",
        "from .. import config\n",  # relative import escaping domain
    ],
)
def test_planted_non_stdlib_import_reported(domain_file, source):
    assert len(domain_file(source)) == 1


@pytest.mark.parametrize(
    "source",
    [
        "import datetime\nfrom decimal import Decimal\nfrom __future__ import annotations\n",
        "from domain import errors\nimport domain.errors\n",
        "from shared.constants import CONFLICT_MIN_OVERLAP\nfrom shared import constants, ids\n",
        "from . import errors\nfrom .errors import DomainError\n",
    ],
)
def test_allowed_imports_not_reported(domain_file, source):
    assert domain_file(source) == []


def test_relative_import_in_nested_domain_package_resolves(domain_file):
    assert domain_file("from .. import errors\n", name="domain/sub/_planted.py") == []
    assert len(domain_file("from ... import config\n", name="domain/sub/_planted.py")) == 1
