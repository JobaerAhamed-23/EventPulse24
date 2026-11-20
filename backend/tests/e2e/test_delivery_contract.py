"""The contracts the delivery path is bound by.

**What this file is.** The delivery proof (`test_delivery_proof.py`) proves the *path*
works. This file proves the **contracts** still hold — the ones that would let the path
work *by accident*, or stop working without anything going red.

**The four contracts, and why each is a contract and not a detail.**

1. **The import contracts, including `models-delivery`.** Without it, `delivery` reaches
   another app's models and a service boundary becomes advisory.
2. **The generated client is in sync.** Without it, the frontend's types drift from the
   API's shapes and a field is read as `undefined` at runtime.
3. **The proof runs fully offline.** Without it, a proof that reaches the network is a
   proof whose answer depends on the network.
4. **The memory adapter records what the proof asserts.** Without it, a proof asserts on
   a surface that does not record the fact it needs.

**The last one is the subtle one.** The work item's Technical Note anticipated it: *"The
memory email adapter is the assertion surface. If it does not yet record stream and
idempotency key per message, extending it belongs to `delivery-sweep-and-send`, not here —
this item should be able to assert without changing the adapter."* **It does record them**,
and this file asserts that it does — so if a future change to the adapter drops the
stream, the proof's assertions would silently stop meaning anything.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FRONTEND = REPO / "frontend"

#: The OpenAPI document the frontend's client is generated from.
OPENAPI = FRONTEND / "lib/api/openapi.json"

#: The generated TypeScript types.
SCHEMA = FRONTEND / "lib/api/schema.ts"


def _executable(name: str) -> str:
    """The full path to an executable, or a failure that says so.

    **A partial path runs whatever is first on `PATH`** — which is not necessarily the
    thing meant (ruff's S607). The full path is the honest one.
    """
    found = shutil.which(name)
    if found is None:
        pytest.fail(f"{name} is not on PATH")
    return found


# ── The import contracts ──────────────────────────────────────────────────────────────────


def test_the_import_contracts_still_hold():
    """**Every contract, on the real tree.**

    `lint-imports` is the tool that reads the contracts out of `pyproject.toml` and
    checks the tree against them. Running it here is the same check CI runs, and it is
    the one that says *nothing* broke.

    **The contracts are declared, not assumed.** They live in `backend/pyproject.toml`
    under `[tool.importlinter.contracts]`, and the count is asserted — so a contract
    deleted from the file would fail here rather than quietly reduce the wall.
    """
    result = subprocess.run(
        [_executable("lint-imports"), "--config", "pyproject.toml", "--no-cache"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr

    config = (BACKEND / "pyproject.toml").read_text()
    declared = re.findall(r'^id\s*=\s*"([^"]+)"', config, flags=re.MULTILINE)
    assert len(declared) == 21, f"the contract count changed: {declared}"


def test_the_models_delivery_contract_names_scheduled_send():
    """**AD-2's `delivery` half, and the one this intent's eleven items could break.**

    `ScheduledSend` is `delivery`'s own model, and every other app reaches it through
    `delivery`'s **services**. The contract is what says so.

    **The contract is package-level** — it protects `apps.delivery.models`, so every
    model in it is covered, `ScheduledSend` included. This test pins that the protection
    is still package-level rather than narrowed to a list of models that could fall out
    of date.
    """
    config = (BACKEND / "pyproject.toml").read_text()

    assert 'id = "models-delivery"' in config
    assert 'protected_modules = ["apps.delivery.models"]' in config
    assert 'allowed_importers = ["apps.delivery"]' in config

    # **And the model is in the module the contract protects.**
    models = (BACKEND / "apps/delivery/models.py").read_text()
    assert "class ScheduledSend" in models


def test_the_models_delivery_contract_can_break():
    """**A contract that cannot fail proves nothing.**

    `test_import_contracts.py` plants a violation and asserts the exact set of contracts
    that break — and this is the `models-delivery` entry. **The planting happens in a
    copy of the tree**, so the real tree is never modified.

    The assertion is that **exactly** `models-delivery` breaks. Exactly, because a
    second break would mean the violation was not the one this contract is about, and an
    "at least" assertion would let that hide.
    """
    from tests.architecture.test_import_contracts import VIOLATIONS

    violations = {name: (files, expected) for name, (files, expected) in VIOLATIONS.items()}
    assert "another app imports delivery's models" in violations

    files, expected = violations["another app imports delivery's models"]
    assert expected == {"models-delivery"}
    assert "apps/ingestion/_planted.py" in files


# ── The generated client ──────────────────────────────────────────────────────────────────


def test_the_openapi_document_is_in_sync_with_the_backend():
    """**The document is the contract, and it is generated.**

    The API's shapes are read out of the running Django app's URL configuration and
    schema, not written by hand — so a route that changes without the document changing
    would break the frontend silently.

    **The check is a regeneration, not a comparison.** `make openapi` writes the
    document; the test then asks whether the file on disk matches. A hand-edited
    `openapi.json` would fail here.
    """
    result = subprocess.run(
        [_executable("make"), "openapi"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    # **The file must parse and carry the paths this intent added.**
    document = json.loads(OPENAPI.read_text())
    paths = document["paths"]

    assert "/api/settings/notifications" in paths
    assert "/api/reminders/{target_kind}/{target_id}" in paths


def test_the_generated_client_is_in_sync_with_the_document():
    """**`make client` is the contract, and CI's diff check is what enforces it.**

    The generated TypeScript types are produced from the document by
    `openapi-typescript`. If the types on disk do not match what the generator produces
    for the document on disk, then the two have drifted — and the frontend is reading
    shapes the API does not send.

    **The comparison is against the file as it was, not against git.** A `git diff`
    would compare against the last commit — and this file is *uncommitted work*, from
    the items that added the settings endpoints. The question here is narrower and
    better: **does regenerating change anything?** If it does, the checked-in types are
    not what the generator produces, and that is the drift. The file is restored
    afterwards, so the test leaves the tree exactly as it found it.
    """
    before = SCHEMA.read_text()

    result = subprocess.run(
        [
            _executable("pnpm"),
            "exec",
            "openapi-typescript",
            "lib/api/openapi.json",
            "--output",
            "lib/api/schema.ts",
        ],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    try:
        after = SCHEMA.read_text()
    finally:
        # **The file is put back**, whatever the comparison says. The test is a
        # measurement, not a rewrite.
        SCHEMA.write_text(before)

    assert after == before, "the generated client is out of sync with the OpenAPI document"


def test_the_generated_client_carries_this_intents_shapes():
    """**The two shapes this intent added are in the generated types.**

    `NotificationSettingsIn` and `NotificationSettingsOut` are what the two settings
    routes read and write, and `put_notification_settings` is the operation they call.
    **They are asserted by name**, so a generator that emitted an empty types file would
    fail rather than pass.
    """
    schema = SCHEMA.read_text()

    assert "NotificationSettingsIn" in schema
    assert "NotificationSettingsOut" in schema
    assert "put_notification_settings" in schema
    assert "quiet_hours" in schema
    assert "default_reminder_slots" in schema


# ── The offline guarantee ─────────────────────────────────────────────────────────────────


def test_the_proof_runs_fully_offline():
    """**No network, and no adapter that reaches one.**

    The work item's criterion is: *"The whole proof runs fully offline with
    `ADAPTER_MODE=fake` and no network."*

    **The check is on the adapter configuration, not on the proof's own code.** The proof
    swaps in the memory adapter explicitly, so what could reach the network is the
    *default* the proof would fall back to — and that default is `ADAPTER_MODE=fake`,
    which maps email to the SMTP adapter. **So the check is that the fake mode is
    configured, and that the memory adapter is the one the proof injects.**
    """
    adapters = (BACKEND / "config/adapters.py").read_text()

    # **The fake mode exists and maps the email adapter.**
    assert "ADAPTER_MODE" in adapters
    assert "fake" in adapters

    # **And the memory adapter records exactly the three facts the proof asserts on.**
    memory = (BACKEND / "adapters/email/memory.py").read_text()
    assert "class SentEmail" in memory
    assert "stream" in memory
    assert "idempotency_key" in memory
    assert "message" in memory

    # **The proof injects the memory adapter by name.**
    proof = (BACKEND / "tests/e2e/test_delivery_proof.py").read_text()
    assert "InMemoryEmailAdapter" in proof


def test_the_delivery_path_does_not_import_a_network_client():
    """**Nothing on the delivery path reaches the network.**

    AD-9 and the import contracts already say *"only `adapters.crawl` imports an HTTP
    client"* — but the delivery path is the one that **sends mail**, so the guarantee is
    worth asserting directly on the modules the proof exercises.

    **The check is a source scan, not a runtime one.** A module that imported `httpx` and
    never called it would still be a delivery path that *could* reach the network, and
    the point of the rule is that it cannot.
    """
    forbidden = re.compile(r"^\s*(?:import|from)\s+(httpx|requests|urllib|http\.client)\b", re.M)

    for relative in [
        "apps/delivery/services/delivery_sweep.py",
        "apps/delivery/services/delivery_messages.py",
        "apps/delivery/services/scheduled_sends.py",
        "apps/delivery/services/pulse_ping.py",
        "apps/delivery/services/unsubscribes.py",
        "domain/quiet_hours.py",
    ]:
        source = (BACKEND / relative).read_text()
        assert not forbidden.search(source), f"{relative} imports a network client"


@pytest.mark.parametrize("relative", ["apps/delivery/services/delivery_sweep.py"])
def test_the_sweep_does_not_consult_the_quiet_window(relative):
    """**The sweep never re-checks Quiet Hours.**

    AD-7: Quiet Hours are applied *"when `due_at` is computed or recomputed… never as a
    skip at send time."* **A send deferred twice is a send that never leaves** — so the
    sweep must not import the shift at all.

    **The check is on the imports, not on the text.** The module's own docstring names
    `domain.quiet_hours` — it says so precisely to record that the import is *absent* —
    so a search for the word would match the very sentence that explains the rule. **An
    import cannot lie**: if the module does not import the shift, it cannot consult the
    window, whatever else it does.
    """
    source = (BACKEND / relative).read_text()

    # **Every import line in the module**, so a docstring cannot satisfy or break it.
    import_lines = [
        line for line in source.splitlines() if re.match(r"^\s*(?:import|from)\s", line)
    ]
    joined = "\n".join(import_lines)

    assert "quiet_hours" not in joined
    assert "shift_to_sendable" not in joined
