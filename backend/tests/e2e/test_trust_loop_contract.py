"""The contracts the trust loop is bound by, and the gaps it is honest about.

**What this file is.** `test_trust_loop_proof.py` proves the *loop* works. This file
proves the **contracts** that would let it work by accident, or stop working without
anything going red — and it writes the intent's **known gaps** down as assertions rather
than as prose, because a list in a docstring rots silently and an assertion does not.

**The four groups:**

1. **The endpoint this intent added is in the committed contract**, with its verb, its two
   shapes, their four categories, and the two things those shapes must *not* carry.
2. **The generated client is in sync with the document.** `make client` is the contract;
   regenerating must change nothing.
3. **The architecture invariants hold for this intent's seams.** AD-14's "`editorial` owns
   no table", AD-4's "`ingestion` is the sole writer of `catalog`", AD-5's "the admin never
   calls `obj.save()`", and the import contracts as a whole.
4. **The known gaps are still gaps.** Each one is a named test that will fail, loudly and
   on purpose, on the day the gap is closed — which is the only kind of "documented
   limitation" that cannot quietly become a lie.

**Why the gaps are tests and not a README section.** The intent brief lists six things it
deliberately did not build. A reader six months from now has no way to tell which of them
are still true. These tests tell them, every time CI runs.
"""

import ast
import json
import re
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FRONTEND = REPO / "frontend"

#: The OpenAPI document the frontend's client is generated from.
OPENAPI = FRONTEND / "lib/api/openapi.json"

#: The generated TypeScript types.
SCHEMA = FRONTEND / "lib/api/schema.ts"

#: The endpoint this intent added to the contract.
#:
#: **One path, one verb.** FR-59 is a single act — "this listing is wrong" — and it is a
#: `POST` because it creates a record. There is deliberately no `GET`: a client that could
#: read reports back could count other people's, which is a fact about other users.
INTENT_PATHS = {
    "/api/personal/event-reports": {"post"},
}

#: FR-59's four categories, in the order the modal offers them. There is no fifth, and
#: there is no free-text field.
CATEGORIES = ["wrong_date_time", "wrong_venue", "does_not_exist", "duplicate"]


def _executable(name: str) -> str:
    """The full path to an executable, or a failure that says so (ruff S607)."""
    found = shutil.which(name)
    if found is None:
        pytest.fail(f"{name} is not on PATH")
    return found


def _document() -> dict:
    assert OPENAPI.exists(), f"{OPENAPI} is missing: run `make client`"
    return json.loads(OPENAPI.read_text())


# ── 1. The contract this intent added ──────────────────────────────────────────────────


def test_the_endpoint_this_intent_added_is_in_the_committed_contract():
    """**The report endpoint is in the OpenAPI document, with exactly its own verb.**

    The document is a committed, generated artefact and `schema.ts` is generated from it,
    so a route that is not in the document is a route the frontend's client cannot call —
    which would make the Detail Screen's flag a button wired to nothing.
    """
    paths = _document()["paths"]

    for path, methods in INTENT_PATHS.items():
        assert path in paths, f"{path} is not in the committed contract"
        present = {method for method in paths[path] if method in {"get", "post", "put", "delete"}}
        assert present == methods, (
            f"{path} carries {sorted(present)}, and this intent added {sorted(methods)}"
        )


def test_the_report_shapes_are_in_the_committed_contract():
    """**`EventReportIn` and `EventReportOut`, by name and by field.**

    Asserted by name so a generator that emitted an empty components block would fail
    rather than pass.
    """
    components = _document()["components"]["schemas"]

    for shape in ("EventReportIn", "EventReportOut"):
        assert shape in components, f"{shape} is not in the committed contract"

    assert set(components["EventReportIn"]["properties"]) == {"event_id", "category"}
    assert set(components["EventReportOut"]["properties"]) == {"reported", "category"}


def test_the_four_categories_are_enumerated_on_the_wire():
    """**The categories are an enum in the document, not a free string.**

    An enum is what makes an invalid category a 422 from the parser, before any service
    sees it — and it is what puts the four options into the generated TypeScript union, so
    the modal's radio group and the API cannot drift apart.
    """
    components = _document()["components"]["schemas"]

    assert components["EventReportIn"]["properties"]["category"]["enum"] == CATEGORIES
    assert components["EventReportOut"]["properties"]["category"]["enum"] == CATEGORIES


def test_the_response_carries_no_report_id_and_no_tally():
    """**The toast's payload, and nothing else (FR-59).**

    A client that could read the tally could count other people's reports on an event,
    which is a fact about other users rather than about this one. A report id would let a
    client address a record it is not allowed to read back.
    """
    properties = _document()["components"]["schemas"]["EventReportOut"]["properties"]

    for leak in ("id", "report_id", "count", "report_count", "tally", "status", "review_item_id"):
        assert leak not in properties, f"the report response carries {leak}"


def test_the_generated_client_carries_this_intents_operation():
    """**The frontend's actual call site.**

    `components/detail/event-report-control.tsx` calls the endpoint by its operation id
    through the generated client, so asserting the id is asserting the control can reach
    the API at all.
    """
    schema = SCHEMA.read_text()

    assert "/api/personal/event-reports" in schema
    assert "apps_personalization_api_report_event_endpoint" in schema
    assert "EventReportIn" in schema
    assert "EventReportOut" in schema


# ── 2. The generated client is in sync ─────────────────────────────────────────────────


def test_the_generated_client_is_in_sync_with_the_document():
    """**`make client` is the contract, and this is the measurement.**

    The question is not "does git show a diff" but **"does regenerating change
    anything?"** If it does, the checked-in types are not what the generator produces and
    the frontend is reading shapes the API does not send. The file is restored afterwards,
    so the test leaves the tree exactly as it found it.
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
    try:
        after = SCHEMA.read_text()
    finally:
        # **The file is put back before anything is asserted.** The generator was already
        # pointed at `--output lib/api/schema.ts`, so a run that writes a partial file and
        # *then* exits non-zero (bad JSON, a version mismatch, an OOM) has already
        # clobbered the tracked file. Asserting the return code first — as the first draft
        # of this test did, copying its sibling — would raise before the restore and leave
        # the developer's tree corrupted by the test that promises not to touch it.
        SCHEMA.write_text(before)

    assert result.returncode == 0, result.stdout + result.stderr
    assert after == before, "the generated client is out of sync with the OpenAPI document"


# ── 3. The architecture invariants, for this intent's seams ────────────────────────────


def test_the_import_contracts_still_hold():
    """**Every contract, on the real tree**, and the count is pinned.

    `lint-imports` reads the contracts out of `pyproject.toml`; if one were deleted from
    that file the check would still pass — with one fewer wall. So the count is asserted
    too.
    """
    result = subprocess.run(
        [_executable("lint-imports"), "--config", "pyproject.toml", "--no-cache"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    # **Only the import-linter contracts are counted.** A bare `^id = "..."` scan over the
    # whole file counts any tool section that happens to use an `id` key, so an unrelated
    # addition could both break this test and *mask* a deleted contract — one added, one
    # removed, count unchanged. The section is isolated first.
    config = (BACKEND / "pyproject.toml").read_text()
    section = re.findall(
        r"\[\[tool\.importlinter\.contracts\]\](.*?)(?=\n\[|\Z)", config, flags=re.DOTALL
    )
    declared = [
        match
        for block in section
        for match in re.findall(r'^id\s*=\s*"([^"]+)"', block, flags=re.MULTILINE)
    ]
    assert len(declared) == 21, f"the contract count changed: {declared}"


def test_the_editorial_app_owns_no_table():
    """**AD-14, in its most literal form.** `editorial` reads `catalog` and writes only
    through `ingestion` commands — so it declares no model and holds no migration of its
    own beyond the package marker.
    """
    assert (BACKEND / "apps/editorial/models.py").read_text().strip() == ""

    migrations = sorted(
        path.name
        for path in (BACKEND / "apps/editorial/migrations").glob("*.py")
        if path.name != "__init__.py"
    )
    assert migrations == [], f"the editorial app has migrations: {migrations}"


def test_the_editorial_app_imports_no_ingestion_model():
    """**AD-2's `models-ingestion` contract, at the one place that wanted to break it.**

    A `ModelAdmin` for `ReviewItem` written in `apps/editorial/` would need the model
    class, and that import is exactly what the contract forbids. The queue's `ModelAdmin`
    therefore lives in `apps/ingestion/admin.py`, next to the table it renders.

    **The check parses the imports rather than scanning the text.** Both modules in this
    app *explain* the rule in their docstrings, naming `apps.ingestion.models` in prose —
    and a text scan would read that explanation as a breach. An import is a statement, so
    the statements are what is examined.
    """
    checked = 0
    for path in sorted((BACKEND / "apps/editorial").rglob("*.py")):
        checked += 1
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # **The module AND each imported name.** Checking `node.module` alone
                # catches `from apps.ingestion.models import ReviewItem` and sails past
                # `from apps.ingestion import models` — which is exactly the form someone
                # reaches for after being told the dotted path is forbidden.
                module = node.module or ""
                names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
            else:
                continue
            for name in names:
                assert not name.startswith("apps.ingestion.models"), (
                    f"{path.name} imports ingestion's models"
                )
    assert checked >= 4, "the editorial app's modules were not found — the scan is not scanning"


def test_the_editorial_app_writes_nothing_through_the_orm():
    """**AD-14's other half: it writes only through `ingestion` services.**

    A module that reads is fine — the editorial reading of the queue is the whole point of
    the app — but a module that could `create`, `update` or `delete` has a second write
    path, and a second write path is a second rule set.

    **The tree's own AST checker does the work, and the first version of this test did
    not.** It scanned for the literal strings `.objects.create(`, `.objects.update(`,
    `.save(` and `.bulk_create(` — and this codebase writes
    `Model.objects.using(CATALOG).create(...)`, so **not one of those four patterns matches
    anywhere in `apps/`**. The test asserted nothing: adding
    `ReviewItem.objects.using(CATALOG).create(...)` to this very app would have passed it.
    `checkers.direct_write_calls` parses the call instead, which is what the architecture
    suite uses and what cannot be side-stepped by an intervening `.using()`.
    """
    from tests.architecture.checkers import direct_write_calls

    checked = 0
    for path in sorted((BACKEND / "apps/editorial").rglob("*.py")):
        checked += 1
        writes = direct_write_calls(path.read_text())
        assert writes == [], f"{path.name} writes through the ORM: {writes}"
    assert checked >= 4, "the editorial app's modules were not found — the scan is not scanning"


def test_the_admin_never_calls_obj_save():
    """**AD-5/AD-14: every editorial write is a named `ingestion` command.**

    The base `ModelAdmin` in `apps/ingestion/admin.py` refuses `save_model` outright, so a
    subclass that forgot to route through a command raises rather than silently writing a
    row with no audit entry, no version bump and no propagation.
    """
    source = (BACKEND / "apps/ingestion/admin.py").read_text()

    assert "def save_model(self, request, obj, form, change):" in source
    assert re.search(
        r"def save_model\(self, request, obj, form, change\):\s*\n\s*raise PermissionDenied",
        source,
    ), "the admin's save_model no longer refuses by default"


def test_the_report_path_writes_no_catalog_row_from_personalization():
    """**AD-4: `ingestion` is the sole writer of `catalog`.**

    `report_event` lives in `personalization` and has to cause a `catalog` row to exist.
    It does that by **calling `ingestion`'s published command**, not by reaching across
    the wall — and the delegation is to the tree's own rule rather than a scan written
    here, which could drift from the one CI runs.
    """
    source = (BACKEND / "apps/personalization/services/event_reports.py").read_text()

    assert "from apps.ingestion.services.review_queue import" in source
    assert "apps.ingestion.models" not in source, "the report service reaches into catalog's models"
    assert "CATALOG" not in source, "the report service names the catalog connection"

    from tests.architecture.test_write_ownership import (
        test_no_app_writes_a_table_it_does_not_own as ownership_rule,
    )

    ownership_rule(BACKEND / "apps/personalization/services/event_reports.py")


def test_nothing_on_the_trust_loop_path_imports_a_network_client():
    """**The loop runs offline.**

    A module on this path that imported `httpx` or `requests` would be a module whose
    answer depends on the network, and a proof that exercised it could fail for a reason
    that has nothing to do with the system.
    """
    modules = [
        "apps/personalization/services/event_reports.py",
        "apps/ingestion/services/review_queue.py",
        "apps/ingestion/services/review_intake.py",
        "apps/ingestion/services/review_queue_read.py",
        "apps/ingestion/services/editorial_review.py",
        "apps/ingestion/services/editorial_state.py",
        "apps/ingestion/services/reliability.py",
        "apps/editorial/services/review_queue.py",
        "domain/reliability.py",
    ]

    # **The imports are parsed, not grepped.** `"import httpx" not in source` misses
    # `from httpx import AsyncClient` and `import httpx as http` — the two most idiomatic
    # ways to acquire the dependency. The module names are what matters, so the module
    # names are what is read.
    forbidden = {"httpx", "requests", "urllib.request", "socket", "http.client", "aiohttp"}

    for name in modules:
        tree = ast.parse((BACKEND / name).read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        for module in imported:
            root = module.split(".")[0]
            assert module not in forbidden and root not in forbidden, (
                f"{name} imports a network client ({module})"
            )


# ── 4. The known gaps, as assertions ───────────────────────────────────────────────────
#
# Each test below asserts that a gap the intent brief names is **still a gap**. They are
# written to fail on the day the gap is closed, so that closing it forces the list to be
# updated rather than letting it quietly become wrong.


def test_gap_fr25_dismissals_are_a_named_seam_and_not_an_input():
    """**Gap 1 — FR-25 dismissal signals.** Named, not faked.

    A dismissal is recorded as a fact (an editor looked and found no fault in the source)
    and contributes **zero** to the counts. Zero is not the same as absent: the row exists,
    and no term anywhere stands in for a dismissal *rate*.
    """
    from shared.constants import OBSERVATION_SIGNS

    assert OBSERVATION_SIGNS["dismissed"] == 0
    assert set(OBSERVATION_SIGNS) == {"approved", "rejected", "edited", "dismissed"}

    domain = (BACKEND / "domain/reliability.py").read_text()
    assert "dismissal_rate" not in domain, "a dismissal rate term has appeared: close this gap"


def test_gap_fr14_the_llm_path_leaves_the_extraction_gate_unreachable():
    """**Gap 2 — FR-14's LLM path.**

    Structured ingestion always writes `EXTRACTION_CONFIDENCE_STRUCTURED = 1.00`, so the
    `extraction_confidence < 0.70` gate has nothing that can reach it. The queue accepts
    `in_review` events generically, so the LLM path will inherit it at no cost — but until
    it ships, the only route into the queue's `in_review` reason is the timezone gate.
    """
    from shared.constants import EXTRACTION_CONFIDENCE_PUBLISH, EXTRACTION_CONFIDENCE_STRUCTURED

    assert EXTRACTION_CONFIDENCE_STRUCTURED == Decimal("1.00")
    assert EXTRACTION_CONFIDENCE_STRUCTURED >= EXTRACTION_CONFIDENCE_PUBLISH


def test_gap_free_text_reports_are_phase_two():
    """**Gap 3 — free-text reports.**

    FR-57 and FR-59 both put free text in Phase 2. Four fixed categories mean there is
    nothing to type into, so nothing to moderate, nothing to leak into an editor's screen,
    and nothing needing its own retention rule.
    """
    properties = _document()["components"]["schemas"]["EventReportIn"]["properties"]

    assert set(properties) == {"event_id", "category"}
    for free_text in ("note", "notes", "comment", "detail", "details", "message", "text"):
        assert free_text not in properties, f"a free-text field appeared: {free_text}"


def test_gap_the_fr29_dashboard_does_not_exist_and_the_metrics_live_in_admin():
    """**Gap 4 — the FR-29 AI Cost Dashboard.**

    The queue's three metrics are computed by `review_queue_read.queue_summary` and
    rendered by the admin changelist. **No HTTP route serves them**, so the dashboard can
    read them later without a second implementation existing in the meantime.
    """
    from apps.ingestion.services import review_queue_read

    assert hasattr(review_queue_read, "queue_summary")

    # **The tree's own router list, not a glob of `apps/`.** `checkers.api_modules`
    # discovers routers by shape (`api.py` and `*_api.py`) and appends `config/api.py` and
    # `config/health.py` by name — a glob under `apps/` misses both, and the root router is
    # exactly where an FR-29 dashboard route would most naturally be registered.
    #
    # **`api_modules`, not `surface_files`.** The latter includes every app's `admin.py`,
    # and the admin is *where the metrics are supposed to be*. The question here is whether
    # an HTTP **route** serves them, so the request handlers are the list to ask.
    from tests.architecture.checkers import api_modules

    surfaces = api_modules()
    assert surfaces, "no API routers were found — the scan is not scanning"
    assert any(path.name == "api.py" and path.parent.name == "config" for path in surfaces), (
        "the root router is not in the router list"
    )
    for path in surfaces:
        source = path.read_text()
        assert "queue_summary" not in source, f"{path.name} serves the queue metrics over HTTP"
        assert "QueueSummary" not in source, f"{path.name} serves the queue metrics over HTTP"


def test_gap_merging_duplicates_is_recorded_but_not_actionable():
    """**Gap 5 — merging duplicates.**

    "Duplicate" is a report category, so the signal is recorded and queued. The AD-14
    *merge* editorial action is a later item, and the admin offers three verdicts and an
    edit — no fourth.
    """
    assert "duplicate" in CATEGORIES

    admin = (BACKEND / "apps/ingestion/admin.py").read_text()
    assert "merge" not in admin.lower(), "a merge action appeared: close this gap"

    from apps.ingestion.models import ReviewItem

    assert set(ReviewItem.Resolution.values) >= {"approved", "rejected", "edited", "dismissed"}
    assert "merged" not in ReviewItem.Resolution.values


def test_gap_the_prd_amendments_owed_are_recorded_in_an_adr():
    """**Gap 6 — the PRD amendments owed.**

    Two departures from the PRD's literal text were taken deliberately: reject is a *soft*
    reject rather than FR-57's "deletes from registry", and FR-22's published ranking terms
    are implemented as the terms the product can actually compute. Neither is a silent
    divergence: both are recorded in an ADR, and the constant names it.
    """
    from shared.constants import RANKING_WEIGHTS_AMENDMENT

    adr = REPO / "docs/adr" / f"{RANKING_WEIGHTS_AMENDMENT}.md"
    assert adr.exists(), f"{RANKING_WEIGHTS_AMENDMENT} is named by the constants but not written"

    text = adr.read_text()
    assert "FR-22" in text
    assert "source_reliability" in text


def test_gap_an_editorially_released_event_still_cannot_reach_a_digest():
    """**Gap 7 — found by this item's own proof, not named in the brief (2026-11-11).**

    An editor can take a timezone-quarantined event out of `in_review`, and it becomes
    public: listed, reachable at its URL, in the sitemap. **It still cannot enter a Pulse
    Digest**, because `list_public_candidates` gates the pool on
    `tz_inference_confidence >= TZ_INFERENCE_CONFIDENCE_DIGEST` and no editorial command
    moves that column. `_incoming_for` carries it over by design.

    So the intent's founding problem — *"events can already get stuck, with no exit"* — is
    closed for the public catalog and **still open for the digest**.

    The proof pins the behaviour in
    `test_trust_loop_proof.TestTheStrandedEventGetsOut`; this test pins the *reason*, so
    that whoever lifts the gate is sent to both places at once.
    """
    source = (BACKEND / "apps/ingestion/services/editorial_review.py").read_text()

    # The approve command moves publication status and nothing else about the gates.
    assert "tz_inference_confidence=event.tz_inference_confidence" in source, (
        "the editorial edit no longer carries the old gate through: close this gap"
    )

    candidates = (BACKEND / "apps/ingestion/services/catalog_read.py").read_text()
    assert "TZ_INFERENCE_CONFIDENCE_DIGEST" in candidates, (
        "the digest candidate read no longer gates on the tz confidence: close this gap"
    )


def test_the_gaps_are_all_listed_here():
    """**The list itself is pinned**, so a gap cannot be dropped from it silently.

    The intent brief named six. This item's proof found a seventh — an editorially
    released event still cannot reach a digest — and it is listed with the rest rather
    than mentioned in a run log nobody reads again. If one is closed, its test fails and
    is removed with the work that closed it. Either way the list and the code change
    together.
    """
    gaps = [name for name in globals() if name.startswith("test_gap_")]
    assert len(gaps) == 7, f"the gap list changed: {sorted(gaps)}"
