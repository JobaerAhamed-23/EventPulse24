"""import-linter contracts (AD-1, AD-2, AD-8) hold on the tree, and each one catches a plant.

Plants go into a copy of the root packages in tmp_path; the real tree is never modified. Each
case asserts the *exact* set of broken contracts, so a plant (or a mutation) can't pass by
breaking some other contract instead.
"""

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from config.checks import PROJECT_PACKAGES
from tests.architecture.checkers import BACKEND_DIR, ROOT_PACKAGES

LINT_IMPORTS = Path(sys.executable).with_name("lint-imports")
CONFIG = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text())["tool"]["importlinter"]
CONTRACTS = {contract["id"]: contract for contract in CONFIG["contracts"]}


def lint_imports(root: Path) -> tuple[int, set[str]]:
    env = {key: value for key, value in os.environ.items() if key != "DJANGO_SETTINGS_MODULE"}
    env["PYTHONPATH"] = str(root)  # replaced, not prepended: the real tree must not shadow it
    result = subprocess.run(
        [str(LINT_IMPORTS), "--config", "pyproject.toml", "--no-cache"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = " ".join(result.stdout.split())  # long names wrap across lines
    broken = {
        cid for cid, c in CONTRACTS.items() if f"{' '.join(c['name'].split())} BROKEN" in output
    }
    return result.returncode, broken


@pytest.fixture
def planted(tmp_path):
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for package in ROOT_PACKAGES:
        shutil.copytree(BACKEND_DIR / package, tmp_path / package, ignore=ignore)
    shutil.copy(BACKEND_DIR / "pyproject.toml", tmp_path / "pyproject.toml")

    def plant(files: dict[str, str]) -> tuple[int, set[str]]:
        for relative, source in files.items():
            (tmp_path / relative).write_text(source)
        return lint_imports(tmp_path)

    return plant


def test_clean_tree_keeps_every_contract():
    returncode, broken = lint_imports(BACKEND_DIR)

    assert (returncode, broken) == (0, set())


VIOLATIONS = {
    "domain imports django": ({"domain/_planted.py": "import django\n"}, {"domain-pure"}),
    "domain imports shared.retention": (
        {"domain/_planted.py": "from shared import retention\n"},
        {"domain-pure"},
    ),
    "domain imports ports": ({"domain/_planted.py": "import ports\n"}, {"layers"}),
    "ports imports apps": ({"ports/_planted.py": "import apps.catalog\n"}, {"layers"}),
    "shared imports config": ({"shared/_planted.py": "import config.env\n"}, {"layers"}),
    "apps imports adapters": ({"apps/catalog/_planted.py": "import adapters.email\n"}, {"layers"}),
    "adapters import apps": ({"adapters/email/_planted.py": "import apps.identity\n"}, {"layers"}),
    "config imports worker": ({"config/_planted.py": "import worker\n"}, {"layers"}),
    # config.api assembles the app routers, so reaching it reaches the API surface too:
    # both the layers contract (worker is below config) and worker-not-api break.
    "worker imports config.api": (
        {"worker/_planted.py": "import config.api\n"},
        {"layers", "worker-not-api"},
    ),
    "worker imports an app's API router": (
        {"worker/_planted.py": "import apps.catalog.api\n"},
        {"worker-not-api"},
    ),
    "app imports another app's models": (
        {"apps/catalog/_planted.py": "import apps.ingestion.models\n"},
        {"models-ingestion"},
    ),
    "adapter imports another adapter": (
        {"adapters/email/_planted.py": "import adapters.llm\n"},
        {"adapters-independent"},
    ),
    "app imports an LLM SDK": ({"apps/catalog/_planted.py": "import anthropic\n"}, {"llm-sdk"}),
    "app imports stripe": ({"apps/delivery/_planted.py": "import stripe\n"}, {"stripe-sdk"}),
    "billing adapter imports an LLM SDK": (
        {"adapters/billing/_planted.py": "import openai\n"},
        {"llm-sdk"},
    ),
    "app imports httpx": ({"apps/ingestion/_planted.py": "import httpx\n"}, {"http-client"}),
    "email adapter imports httpcore": (
        {"adapters/email/_planted.py": "import httpcore\n"},
        {"http-client"},
    ),
    "worker imports requests": ({"worker/_planted.py": "import requests\n"}, {"http-client"}),
}


@pytest.mark.parametrize(("files", "expected"), VIOLATIONS.values(), ids=VIOLATIONS.keys())
def test_planted_violation_breaks_exactly_the_expected_contracts(planted, files, expected):
    returncode, broken = planted(files)

    assert broken == expected
    assert returncode == 1


ALLOWED = {
    "domain imports shared.constants": {
        "domain/_planted.py": "from shared.constants import CONFLICT_MIN_OVERLAP\n"
    },
    "app imports its own models": {
        "apps/ingestion/_planted.py": "from apps.ingestion import models\n"
    },
    "app reaches another app's models through its services": {
        "apps/ingestion/services/_planted.py": "import apps.ingestion.models\n",
        "apps/catalog/_planted.py": "import apps.ingestion.services._planted\n",
    },
    "llm adapter imports its SDK": {"adapters/llm/_planted.py": "import anthropic\n"},
    "billing adapter imports stripe": {"adapters/billing/_planted.py": "import stripe\n"},
    "crawl adapter imports httpx": {"adapters/crawl/_planted.py": "import httpx\n"},
    "config wires in the crawl adapter": {"config/_planted.py": "import adapters.crawl.http\n"},
    "worker wires in the llm adapter": {
        "adapters/llm/_planted.py": "import anthropic\n",
        "worker/_planted.py": "import adapters.llm._planted\n",
    },
    "config wires in the llm adapter": {
        "adapters/llm/_planted.py": "import anthropic\n",
        "config/_planted.py": "import adapters.llm._planted\n",
    },
}


@pytest.mark.parametrize("files", ALLOWED.values(), ids=ALLOWED.keys())
def test_allowed_import_breaks_nothing(planted, files):
    assert planted(files) == (0, set())


def _packages(directory: Path) -> set[str]:
    return {p.parent.name for p in directory.glob("*/__init__.py")}


def test_every_backend_package_is_a_root_package():
    assert _packages(BACKEND_DIR) - {"tests"} == set(CONFIG["root_packages"])


def test_every_adapter_is_covered_by_the_sdk_contracts():
    adapters = _packages(BACKEND_DIR / "adapters")
    for contract_id, owner in (
        ("llm-sdk", "llm"),
        ("stripe-sdk", "billing"),
        ("http-client", "crawl"),
    ):
        sources = set(CONTRACTS[contract_id]["source_modules"])
        assert {f"adapters.{a}" for a in adapters - {owner}} <= sources, contract_id
        assert f"adapters.{owner}" not in sources


def test_every_app_has_a_protected_models_contract():
    for app in _packages(BACKEND_DIR / "apps"):
        contract = CONTRACTS[f"models-{app}"]
        assert contract["protected_modules"] == [f"apps.{app}.models"]
        assert contract["allowed_importers"] == [f"apps.{app}"]


def test_package_lists_agree():
    """The root-package list lives in three places; they must not drift apart."""
    assert set(ROOT_PACKAGES) == set(CONFIG["root_packages"]) == PROJECT_PACKAGES
