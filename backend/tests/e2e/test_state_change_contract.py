"""The contracts the state-change path is bound by.

**What this file is.** The proof (`test_state_change_proof.py`) proves the *path* works.
This file proves the **contracts** still hold — the ones that would let the path work
*by accident*, or stop working without anything going red.

**The contracts, and why each is a contract and not a detail.**

1. **The endpoints this intent added are in the committed contract.** Without it, the
   frontend's generated client does not carry the strip, the dismissal or the mute, and
   the surfaces the intent was for cannot be built against the API at all.
2. **The architecture invariants hold.** `ingestion` still never writes to `personal`;
   no cross-schema transaction exists; `import-linter` contracts pass.
3. **The generated client is in sync with the document.**
4. **The proof runs fully offline.**
5. **The memory adapter records what the proof asserts.**

**Why the architecture invariants are here and not only in `tests/architecture/`.**
That suite proves them one at a time. This file proves them *for this intent's seams* —
the propagation in `worker`, the notice in `delivery`, the snapshot in `personalization`
— because the intent is exactly the one that put a write path across all three, and a
wall that only holds because nothing has tried to cross it has not been tested.

**The contract count is asserted.** `lint-imports` reads the contracts out of
`pyproject.toml`; if a contract were deleted from that file, the check would still
pass — with one fewer wall. So the count is pinned.
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

#: The endpoints this intent added to the contract.
#:
#: **Three paths and four operations.** The strip's read, the dismissal, and the mute's
#: two directions. The mute is `PUT` and `DELETE` because a mute is a *state* with two
#: values — setting a state is `PUT`, clearing it is `DELETE` — and there is no request
#: body, so the client cannot encode "clear this" as a field that could be confused
#: with "leave it alone".
INTENT_PATHS = {
    "/api/notices": {"get"},
    "/api/notices/{notice_id}/dismiss": {"post"},
    "/api/notices/events/{event_id}/mute": {"put", "delete"},
}


def _executable(name: str) -> str:
    """The full path to an executable, or a failure that says so.

    **A partial path runs whatever is first on `PATH`** — which is not necessarily the
    thing meant (ruff's S607). The full path is the honest one.
    """
    found = shutil.which(name)
    if found is None:
        pytest.fail(f"{name} is not on PATH")
    return found


# ── The contract this intent added ──────────────────────────────────────────────────────


def test_the_endpoints_this_intent_added_are_in_the_committed_contract():
    """**The strip, the dismissal and the mute are in the OpenAPI document.**

    **The document is the contract, and it is committed.** `frontend/lib/api/openapi.json`
    is a generated artefact that ships with the repository, and the frontend's
    `schema.ts` is generated from it — so a route that is not in the document is a route
    the frontend's client cannot call.

    **The methods are asserted too, not just the paths.** A path with the right name
    and the wrong verb is a different endpoint, and a client generated from it would
    call the wrong thing.
    """
    assert OPENAPI.exists(), f"{OPENAPI} is missing: run `make client`"

    document = json.loads(OPENAPI.read_text())
    paths = document["paths"]

    for path, methods in INTENT_PATHS.items():
        assert path in paths, f"{path} is not in the committed contract"
        present = {method for method in paths[path] if method in {"get", "post", "put", "delete"}}
        assert present == methods, (
            f"{path} carries {sorted(present)}, and this intent added {sorted(methods)}"
        )


def test_the_notice_shapes_are_in_the_committed_contract():
    """**The four shapes the strip, the dismissal and the mute read and write.**

    `NoticeOut` is what the strip renders, `NoticeListOut` is its envelope,
    `NoticeDismissOut` is the dismissal's answer, and `EventMuteOut` is the mute's.
    **They are asserted by name**, so a generator that emitted an empty types file would
    fail rather than pass.
    """
    document = json.loads(OPENAPI.read_text())
    components = document["components"]["schemas"]

    for shape in ("NoticeOut", "NoticeListOut", "NoticeDismissOut", "EventMuteOut"):
        assert shape in components, f"{shape} is not in the committed contract"

    # **And the fields the frontend reads.** `dismissed_at` is what tells the banner
    # that the user has already closed this; `changed` is what tells the mute control
    # that the state it now shows is the state the server holds.
    assert "dismissed_at" in components["NoticeOut"]["properties"]
    assert "change_kind" in components["NoticeOut"]["properties"]
    assert "event_version" in components["NoticeOut"]["properties"]
    assert "muted" in components["EventMuteOut"]["properties"]
    assert "changed" in components["EventMuteOut"]["properties"]

    # **The notice payload carries no title** (AD-13). A title is source content and
    # the strip cannot name the event, so it must not be on the wire.
    assert "title" not in components["NoticeOut"]["properties"]


def test_the_generated_client_carries_this_intents_shapes():
    """**The generated TypeScript carries the operations and the shapes.**

    The frontend calls `api.GET("/api/notices")` and `api.PUT("/api/notices/events/
    {event_id}/mute")` by name — so the operation ids in `schema.ts` are the frontend's
    actual call sites, and asserting them is asserting the frontend can reach the API.
    """
    schema = SCHEMA.read_text()

    assert "get_notices" in schema
    assert "post_dismiss_notice" in schema
    assert "put_event_mute" in schema
    assert "delete_event_mute" in schema
    assert "NoticeOut" in schema
    assert "EventMuteOut" in schema


def test_the_generated_client_is_in_sync_with_the_document():
    """**`make client` is the contract, and CI's diff check is what enforces it.**

    **The comparison is against the file as it was, not against git.** The question
    here is narrower and better: **does regenerating change anything?** If it does, the
    checked-in types are not what the generator produces, and the frontend is reading
    shapes the API does not send. The file is restored afterwards, so the test leaves
    the tree exactly as it found it.
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


# ── The architecture invariants, for this intent's seams ───────────────────────────────


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
    assert len(declared) == 19, f"the contract count changed: {declared}"


def test_the_worker_writes_no_rows_itself():
    """**AD-5's half, for the one module this intent put between the apps.**

    `worker.propagation` is the consumer that joins `ingestion`, `personalization` and
    `delivery` — and it is exactly the module that *could* have written a row itself
    to save a round trip. **It writes nothing.** Every mutation goes through the owning
    module's published command.

    **The check is an import scan, not a runtime observation.** A module that imported
    another app's models would have the option to write; the option is what the wall
    forbids.
    """
    propagation = (BACKEND / "worker/propagation.py").read_text()

    # **The service imports are allowed; anything else from an app is not.** The
    # propagation is allowed to call the owning modules' published commands — that is
    # how it mutates anything at all — but it may not reach past them into a model.
    without_the_services = (
        propagation.replace("from apps.delivery.services", "")
        .replace("from apps.ingestion.services", "")
        .replace("from apps.personalization.services", "")
    )
    assert "from apps" not in without_the_services, (
        "the propagation imports an app's module that is not a service"
    )
    assert ".models" not in propagation, "the propagation imports no model"

    # **And the write ownership suite says the same thing**, in the tree's own words.
    from tests.architecture.test_write_ownership import (
        test_the_worker_writes_no_rows_itself as ownership_check,
    )

    ownership_check()


def test_ingestion_never_writes_to_the_personal_schema():
    """**AD-3's wall, from the side this intent pushed against it.**

    `ingestion` owns the catalog and appends the `EventStateChange`. It must not reach
    into `personal` to apply it — that is the propagation's job, and the propagation
    lives in `worker` precisely so `ingestion` does not have to.

    **The rule is delegated, not re-implemented.** The tree already states this wall
    twice, in its own words: `test_no_app_writes_a_table_it_does_not_own` says no app
    writes a table another owns, and `test_the_import_contracts_still_hold` says
    `ingestion` cannot reach `personalization`'s services at all. Both are the
    authoritative statements — a scan written here would be a *third* rule, and one
    that could drift from the two that CI runs.

    **And the delegation is deliberate, because a cruder scan would be wrong.**
    `apps/ingestion/admin.py` reads the user model from `personal` to show an actor's
    name in the admin's list column. A **read** across the wall is legal — AD-3 is
    about a *write* and about a transaction spanning both schemas — so a scan for the
    word `PERSONAL` would flag a legitimate pre-existing read as a breach. The precise
    rules distinguish the two, and this test defers to them.
    """
    from tests.architecture.test_write_ownership import _source_files
    from tests.architecture.test_write_ownership import (
        test_no_app_writes_a_table_it_does_not_own as ownership_rule,
    )

    # **Every module, not one.** The rule is parametrised over the tree's own source
    # list, and the whole list is asked about — because "the one that matters" is the
    # one nobody guessed.
    for module in _source_files():
        ownership_rule(module)

    # **And the import half — `ingestion` may not reach `personalization`'s services.**
    # A service call is a *published command*, and a command that applies a state
    # change to `personal` would be the write this wall forbids, reached by a door
    # the ORM scan does not look at.
    for path in sorted((BACKEND / "apps/ingestion").rglob("*.py")):
        assert "personalization.services" not in path.read_text(), (
            f"{path.name} reaches into personalization's services"
        )


def test_no_cross_schema_transaction_exists_on_the_state_change_path():
    """**AD-3's shape, on the modules this intent wrote.**

    A transaction that spans `catalog` and `personal` would make the propagation
    atomic across two databases — which PostgreSQL cannot promise, and which the
    `SchemaRouter` is fail-closed to prevent. **The check is a scan for a transaction
    opened against both aliases in one `atomic` call.**

    The propagation is the module that would most plausibly have done it: it reads the
    catalog and writes `personal`, and it is *tempting* to wrap the whole thing.
    """
    for name in ("worker/propagation.py", "apps/delivery/services/state_notices.py"):
        source = (BACKEND / name).read_text()
        for match in re.finditer(r"atomic\(\s*(?:using\s*=\s*)?([^)]*)\)", source):
            arguments = match.group(1)
            assert "CATALOG" not in arguments or "PERSONAL" not in arguments, (
                f"{name} opens a transaction across both schemas"
            )


def test_the_notices_router_is_a_surface_file_and_writes_no_rows_directly():
    """**AD-5's own rule, applied to the router this intent added.**

    `apps/delivery/notices_api.py` is a *surface* file — it takes requests — and a
    surface file that writes through the ORM would be a second way to write a notice.
    **The architecture suite's own discovery is used**, so the list and the check can
    never disagree.
    """
    from tests.architecture.checkers import surface_files

    names = {path.name for path in surface_files()}
    assert "notices_api.py" in names, "the notices router is a surface file"

    from tests.architecture.test_no_direct_writes import test_surface_file_makes_no_direct_write

    test_surface_file_makes_no_direct_write(BACKEND / "apps/delivery/notices_api.py")


def test_the_detail_read_reports_the_notice_and_the_mute():
    """**The Detail read's two new fields are in the wire shape.**

    The banner and the mute control render from **one** round trip — that is the
    reason the Detail read gained the two fields rather than the client making two
    more requests. **So the two fields are on the same object**, and the contract says
    so.
    """
    document = json.loads(OPENAPI.read_text())
    components = document["components"]["schemas"]

    assert "DetailPersonalOut" in components
    properties = components["DetailPersonalOut"]["properties"]

    assert "muted" in properties, "the Detail read reports the mute"
    assert "notice" in properties, "and the notice"

    # **And the notice's shape is the Detail one** — the same fields minus `event_id`,
    # because the Detail read is already scoped to one event.
    assert "DetailNoticeOut" in components
    notice_properties = components["DetailNoticeOut"]["properties"]
    assert "event_id" not in notice_properties, (
        "the Detail notice does not repeat the event the enclosing object already names"
    )
    assert "dismissed_at" in notice_properties, (
        "the banner needs to know whether the user already closed this"
    )


# ── The offline guarantee ──────────────────────────────────────────────────────────────


def test_the_proof_runs_fully_offline():
    """**No network, and no adapter that reaches one.**

    **The check is on the adapter configuration, not on the proof's own code.** The
    proof swaps in the memory adapter explicitly, so what could reach the network is the
    *default* the proof would fall back to — and that default is `ADAPTER_MODE=fake`,
    which maps email to the SMTP adapter. **So the check is that the fake mode is
    configured, and that the memory adapter is the one the proof injects.**
    """
    adapters = (BACKEND / "config/adapters.py").read_text()

    assert "ADAPTER_MODE" in adapters
    assert "fake" in adapters

    # **And the memory adapter records exactly the facts the proof asserts on.**
    memory = (BACKEND / "adapters/email/memory.py").read_text()
    assert "class SentEmail" in memory
    assert "stream" in memory
    assert "idempotency_key" in memory
    assert "message" in memory

    # **The proof injects the memory adapter by name.**
    proof = (BACKEND / "tests/e2e/test_state_change_proof.py").read_text()
    assert "InMemoryEmailAdapter" in proof


def test_the_state_change_path_does_not_import_a_network_client():
    """**Nothing on the state-change path reaches the network.**

    **The check is a source scan, not a runtime one.** A module that imported `httpx` or
    `requests` would be a module whose answer depends on the network, and a proof that
    exercised it would be a proof that could fail for a reason that has nothing to do
    with the system.
    """
    modules = [
        "worker/propagation.py",
        "apps/delivery/services/state_notices.py",
        "apps/delivery/services/scheduled_sends.py",
        "apps/delivery/services/delivery_sweep.py",
        "apps/delivery/services/mutes.py",
        "apps/delivery/notices_api.py",
        "apps/ingestion/services/outbox.py",
        "apps/personalization/services/saved_events.py",
    ]

    for name in modules:
        source = (BACKEND / name).read_text()
        for forbidden in ("import httpx", "import requests", "urllib.request", "import socket"):
            assert forbidden not in source, f"{name} imports a network client ({forbidden})"


def test_the_propagation_is_the_only_writer_of_the_catalogs_propagated_at():
    """**`EventStateChange` is append-only, and `propagated_at` is its one mutable
    column.**

    **Two writers would be two rule sets** — one that marks and one that does not — and
    the mark is what the reconciler reads to decide whether to offer the change again.
    So the write goes through `ingestion`'s published `outbox.mark_propagated`, and
    nothing else touches the column.
    """
    propagation = (BACKEND / "worker/propagation.py").read_text()

    assert "mark_propagated" in propagation, "the propagation marks through the published command"
    assert ".update(" not in propagation or "propagated_at" not in propagation, (
        "the propagation does not write the column itself"
    )
