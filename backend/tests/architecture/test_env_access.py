"""Only config/ reads the environment: Ruff TID251 banned-api (config/, manage.py, tests exempt)."""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.architecture.checkers import BACKEND_DIR

RUFF = Path(sys.executable).with_name("ruff")


def ruff_codes(source: str, filename: str) -> str:
    result = subprocess.run(
        [str(RUFF), "check", "--stdin-filename", filename, "--output-format", "concise", "-"],
        input=source,
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


@pytest.mark.parametrize(
    "source",
    [
        'import os\n\nVALUE = os.environ["X"]\n',
        'import os\n\nVALUE = os.environ.get("X")\n',
        'import os\n\nVALUE = os.getenv("X")\n',
        'from os import environ\n\nVALUE = environ["X"]\n',
        "import os\n\nVALUE = os.environb\n",
    ],
)
@pytest.mark.parametrize("filename", ["apps/catalog/x.py", "worker/x.py", "adapters/llm/x.py"])
def test_environment_read_outside_config_reported(source, filename):
    assert "TID251" in ruff_codes(source, filename)


@pytest.mark.parametrize(
    "filename", ["config/x.py", "config/celery.py", "manage.py", "tests/config/x.py"]
)
def test_environment_read_allowed_in_config_manage_and_tests(filename):
    source = 'import os\n\nos.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")\n'

    assert "TID251" not in ruff_codes(source, filename)
