"""AD-2: `domain` is pure logic, importable with Django absent.

The check runs in a fresh interpreter, so Django already loaded by pytest-django in this
process cannot hide a leak.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]

IMPORT_ALL_DOMAIN_MODULES = """
import importlib, pkgutil, sys
import domain
for module in pkgutil.walk_packages(domain.__path__, "domain."):
    importlib.import_module(module.name)
leaked = sorted(name for name in sys.modules if name == "django" or name.startswith("django."))
if leaked:
    sys.exit("domain imported Django: " + ", ".join(leaked[:5]))
"""


def _run_in_fresh_interpreter(code: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key != "DJANGO_SETTINGS_MODULE"}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_domain_import_all_modules_django_not_loaded():
    result = _run_in_fresh_interpreter(IMPORT_ALL_DOMAIN_MODULES)

    assert result.returncode == 0, result.stderr


def test_domain_check_with_django_imported_fails():
    # Guards the guard: the same check must fail when Django does get imported.
    result = _run_in_fresh_interpreter("import django\n" + IMPORT_ALL_DOMAIN_MODULES)

    assert result.returncode != 0
    assert "domain imported Django" in result.stderr
