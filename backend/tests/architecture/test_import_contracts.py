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
    # AD-2's `delivery` half, and the one this intent's eleven items are most likely to
    # break. `delivery` owns `ScheduledSend` and `ReminderPlan`, and every other app
    # reaches them through `delivery`'s **services** — so another app importing
    # `apps.delivery.models` directly is reaching past the service boundary.
    #
    # **The contract protects the module, so the violation is an import *of* it.** The
    # planted file is in `apps.ingestion`, importing `apps.delivery.models` — which is
    # what breaks `models-delivery` and **nothing else**. `delivery` importing
    # `apps.ingestion.models` would break `models-ingestion` instead, because that
    # contract protects *ingestion's* models; the two contracts are mirror images, and
    # the test asserts the **exact** broken set, so a second break would fail the
    # assertion rather than hide inside it.
    "another app imports delivery's models": (
        {"apps/ingestion/_planted.py": "import apps.delivery.models\n"},
        {"models-delivery"},
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
    # AD-18: the cipher and the credential key handling belong to `apps.personalization`
    # alone. A *direct* import from another module is the violation — the indirect reach
    # through Django's model registry is the app's own code doing the encrypting.
    "app imports the cryptography library": (
        {"apps/catalog/_planted.py": "import cryptography\n"},
        {"crypto-library"},
    ),
    "domain imports the cryptography library": (
        {"domain/_planted.py": "from cryptography.hazmat.primitives.ciphers.aead import AESGCM\n"},
        {"crypto-library"},
    ),
    "another app borrows the credential module": (
        {"apps/catalog/_planted.py": "from apps.personalization import credentials\n"},
        {"credential-key"},
    ),
    "shared borrows the credential module": (
        {"shared/_planted.py": "from apps.personalization.credentials import encrypt\n"},
        # `shared` must not import an app either, so the layers contract breaks as well.
        {"credential-key", "layers"},
    ),
    # AD-2: there is one ICS parser, in `formats.ics`. A second module that reaches for
    # `icalendar` is a fork — two places for the same bug, and they would drift.
    "an app forks the ICS parser": (
        {"apps/catalog/_planted.py": "import icalendar\n"},
        {"single-ics-parser"},
    ),
    "the catalog's ICS parser forks the shared one": (
        {"apps/ingestion/_planted.py": "from icalendar import Calendar\n"},
        {"single-ics-parser"},
    ),
    "the calendar adapter forks the ICS parser": (
        {"adapters/calendar/_planted.py": "from icalendar import Calendar\n"},
        {"single-ics-parser"},
    ),
    # A module *beside* the parser, in the same package, is still a fork.
    "a sibling format module forks the ICS parser": (
        {"formats/ics/_planted.py": "from icalendar import Calendar\n"},
        {"single-ics-parser"},
    ),
    # AD-10: the two kinds of explanation never cross.
    "personalization reaches the Event Fit read": (
        {"apps/personalization/_planted.py": "import apps.ingestion.event_fit.reads\n"},
        {"event-fit-separation"},
    ),
    "personalization reaches the Event Fit writer": (
        {"apps/personalization/_planted.py": "from apps.ingestion.event_fit.writes import x\n"},
        {"event-fit-separation"},
    ),
    # The wall is the **package**, so importing the package itself is the violation —
    # and so is importing any module inside it, including one that does not exist yet.
    # This is what makes the wall default-safe: a new Event Fit module is inside it
    # without anybody having to add its name to a list.
    "personalization reaches the Event Fit package": (
        {"apps/personalization/_planted.py": "import apps.ingestion.event_fit\n"},
        {"event-fit-separation"},
    ),
    "personalization reaches a module inside the Event Fit package": (
        {"apps/personalization/_planted.py": "from apps.ingestion.event_fit import reads\n"},
        {"event-fit-separation"},
    ),
    "ingestion reaches for personalization": (
        {"apps/ingestion/_planted.py": "import apps.personalization.services.saved_events\n"},
        {"event-fit-catalog-only"},
    ),
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


def test_the_ics_parser_exception_is_narrow():
    """`single-ics-parser` allows exactly one import: the shared parser's own.

    The exception is an *import expression*, not a module, so a sibling module in
    `formats` importing `icalendar` still breaks the contract — the plant above proves
    it. This test pins the other half: the exception names the parser, and nothing else.
    """
    contract = CONTRACTS["single-ics-parser"]

    assert contract["forbidden_modules"] == ["icalendar"]
    assert contract["ignore_imports"] == ["formats.ics.parser -> icalendar"]
    assert "formats" in contract["source_modules"]


def test_the_event_fit_wall_is_a_package_and_not_a_list_of_names():
    """`event-fit-separation` forbids the Event Fit **package**, not its modules.

    AD-10 says the two kinds of explanation never cross. The first version of this
    contract named two leaves, and a third module that re-exported the read — two
    lines — gave `personalization` the Event Fit with the contract **green**. A wall
    made of names is opened by adding a name.

    So the contract names the package *and* its contents. Pinning it here is what
    makes that structural choice testable: without this assertion the contract could
    be narrowed back to two module names and nothing in the suite would notice. The
    architecture test in `test_event_fit_separation.py` carries a hard-coded prefix,
    so it keeps passing under a narrowed contract — which is precisely the hole this
    assertion closes.
    """
    contract = CONTRACTS["event-fit-separation"]

    assert contract["forbidden_modules"] == [
        "apps.ingestion.event_fit",
        "apps.ingestion.event_fit.*",
    ]
    assert contract["source_modules"] == ["apps.personalization"]


def test_every_adapter_is_covered_by_the_sdk_contracts():
    """Every adapter is held to every SDK contract, except the one it owns.

    **A contract may have more than one owner.** `http-client` has two: `adapters.crawl`,
    which fetches third-party sources (AD-9), and `adapters.revalidation`, which POSTs to
    our own frontend to tell it a public page is stale (FR-26, FR-27). Both are the
    adapters allowed to hold an HTTP client; every other adapter, and every package, is
    held to the contract.

    So the check is: **every adapter except the contract's owners appears in its
    `source_modules`, and no owner does.** A new HTTP-capable adapter therefore cannot
    appear without this contract being amended in the same commit — the widening is
    forced to be a deliberate, visible edit rather than something that happened.
    """
    adapters = _packages(BACKEND_DIR / "adapters")
    for contract_id, owners in (
        ("llm-sdk", {"llm"}),
        ("stripe-sdk", {"billing"}),
        ("http-client", {"crawl", "revalidation"}),
    ):
        sources = set(CONTRACTS[contract_id]["source_modules"])
        assert {f"adapters.{a}" for a in adapters - owners} <= sources, contract_id
        assert not sources & {f"adapters.{o}" for o in owners}


def test_only_the_throttle_adapter_and_the_health_check_talk_to_redis():
    """The redis-sdk contract: the Redis client is reached from two places, by name."""
    contract = CONTRACTS["redis-sdk"]

    assert contract["forbidden_modules"] == ["redis"]
    assert "adapters.throttle" not in contract["source_modules"]
    assert "config" not in contract["source_modules"]


def test_every_app_has_a_protected_models_contract():
    for app in _packages(BACKEND_DIR / "apps"):
        contract = CONTRACTS[f"models-{app}"]
        assert contract["protected_modules"] == [f"apps.{app}.models"]
        assert contract["allowed_importers"] == [f"apps.{app}"]


def test_package_lists_agree():
    """The root-package list lives in three places; they must not drift apart."""
    assert set(ROOT_PACKAGES) == set(CONFIG["root_packages"]) == PROJECT_PACKAGES
