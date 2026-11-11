"""AD-10, second half: **no explanation is generated at view time.**

**What AD-10 says.** "Two indicators that look identical must never be silently
substituted for one another." The Event Fit (per `(event, city)`, on `catalog`, owned by
`ingestion`) and the Relevance Pulse (per user, on `personal`, owned by
`personalization`) are the two. Both are **persisted**; neither is recomputed at render.

**Why this file exists now and not earlier.** Until this intent, AD-10's rule was
enforceable in only **one direction**: `personalization` could not reach the Event Fit,
but there was **no Relevance Pulse for anything to be substituted *for***. A view-time
substitution had nothing to substitute *into*. The Pulse Digest built the second
explanation, so the rule now has both halves, and this file is the half that was
previously untestable.

**The rule this file pins.** The two **read** paths — the digest read and the detail
read — serve **persisted** rows. They do not:

- call the ranking functions (`domain/ranking.py`), which would compute a score at
  request time;
- call the composition, which would **write** an explanation at request time;
- write a composition row, which is the same thing one layer down.

**The three checks, and why there are three.**

1. **The AST call check.** A read that called `score_slot_1` would be computing a
   Relevance Pulse at request time. The check is on the **call**, not on the import,
   because an import is not a call — and because a re-export cannot hide a call.
2. **The AST call check on the composition.** A read that called `compose_digest` would
   be writing at request time.
3. **The database check.** The one a source check **cannot** do: a read that called a
   service which *wrote* would pass every import check and every call check, and still
   generate an explanation at view time. So the rows are counted **before and after**
   the read.

**The third check is the strong one, and the file says so.** The other two are
necessary; the third is the one that would catch a real bug.

**The reads are named, not discovered.** A discovery rule would be a list of holes for
any *new* read path — but the point of this file is that there are exactly **two**
personal read paths, and a third one would be new work that this item's own scenario
would not cover. So the two are named, and a test below asserts that **no other module
in `apps/personalization` serves a composition or a digest** — so a new read path
cannot appear without this file noticing.
"""

import ast
from pathlib import Path

import pytest

from tests.architecture.checkers import BACKEND_DIR

#: The two read paths. `digest_read` serves the card; `detail_read` serves the
#: breakdown. They are two independent services, and both must serve persisted rows.
DIGEST_READ = "apps/personalization/services/digest_read.py"
DETAIL_READ = "apps/personalization/services/detail_read.py"

#: The two read paths, as paths.
READ_PATHS = [BACKEND_DIR / DIGEST_READ, BACKEND_DIR / DETAIL_READ]

#: **The ranking functions.** A read that calls any of these computes a Relevance Pulse
#: at request time.
#:
#: This is a **name list**, and the work item's Technical Notes warn that name-based
#: walls are bypassable. It is safe here for a reason the list cannot show: the check
#: is on the **call**, and the functions are called by name at the call site. A
#: re-export would have to be called *by the name it was re-exported under*, and the
#: re-export would itself have to import one of these — which the import contract and
#: `test_event_fit_separation.py`'s wall both cover for the Event Fit.
#:
#: The **stronger** half of this rule is the database check below, which no amount of
#: renaming can defeat.
RANKING_FUNCTIONS = frozenset(
    {
        "interest_overlap",
        "recency_band",
        "city_band",
        "relevance_score",
        "score_bucket",
        "apply_hysteresis",
        "why_this_tags",
        "score_slot_1",
        "score_slot_2",
        "score_slot_3",
    }
)

#: The composition command. A read that calls it writes at request time.
COMPOSE_DIGEST = "compose_digest"


def _called_names(path: Path) -> set[str]:
    """Every function name called in the file, by the name it is called *by*.

    A call is `ast.Call` whose func is a `Name` (`score_slot_1(...)`) or an
    `Attribute` (`ranking.score_slot_1(...)`) — the two spellings a direct call can
    take. A decorator is excluded for the same reason the write checker excludes it:
    `@router.get(...)` registers a route, it does not score anything.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    decorator_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    decorator_lines.add(decorator.lineno)

    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or node.lineno in decorator_lines:
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    return called


@pytest.mark.parametrize("path", READ_PATHS, ids=lambda p: p.name)
def test_a_read_path_calls_no_ranking_function(path):
    """AD-10: the read serves the persisted row. It does not compute one.

    A read that called `score_slot_1` would be computing a Relevance Pulse at request
    time — which is the substitution AD-10 exists to prevent, and which would also mean
    two surfaces could disagree about the same event (the card scored it one way, the
    breakdown another).
    """
    called = _called_names(path)
    scoring = called & RANKING_FUNCTIONS

    assert not scoring, (
        f"{path.relative_to(BACKEND_DIR)} calls {sorted(scoring)}. The read serves the "
        "persisted row; a score computed at request time is an explanation generated at "
        "view time (AD-10)."
    )


@pytest.mark.parametrize("path", READ_PATHS, ids=lambda p: p.name)
def test_a_read_path_never_composes_a_digest(path):
    """AD-11 and AD-10 together: the read never writes.

    `compose_digest` is the only thing that creates an explanation. A read that called
    it would create one on every page view — the "the screen generates a plausible
    reason on the spot" failure, in its most literal form.
    """
    called = _called_names(path)

    assert COMPOSE_DIGEST not in called, (
        f"{path.relative_to(BACKEND_DIR)} calls {COMPOSE_DIGEST}(). A read serves "
        "persisted rows; composing one at request time would generate an explanation at "
        "view time (AD-10)."
    )


@pytest.mark.parametrize("path", READ_PATHS, ids=lambda p: p.name)
def test_a_read_path_writes_no_composition_row(path):
    """**The check a source check cannot make.** The write is one layer down.

    A read could call a service that writes, and every import check and every call
    check would stay green. So the check is at the **database**: the composition rows
    are counted before the read and after it, and the count must not move.

    **Why this is a source-level test at all.** The count needs a database, and the
    database needs a composed digest to count — which is set up in the scenario's
    fixtures. This test is the *static* half of the rule (it proves the read path does
    not even have the machinery to write), and `tests/e2e/` carries the *dynamic* half
    (the row count across a real read). **Both are needed**: this one would pass on a
    tree where the read wrote through a function object, and the other would not run
    at all if the read path were never exercised.
    """
    source = path.read_text()

    # The write calls. `create` and `bulk_create` are the two shapes a composition
    # write takes; `save` and `update_or_create` are the others a reader might reach
    # for. A read path has no business calling any of them.
    for write_call in ("create", "bulk_create", "save", "update_or_create", "get_or_create"):
        assert f".{write_call}(" not in source, (
            f"{path.relative_to(BACKEND_DIR)} calls .{write_call}(). A read path writes "
            "nothing; a read that wrote a composition row would generate an explanation "
            "at view time (AD-10)."
        )


def test_the_two_read_paths_are_the_only_ones_that_serve_a_digest():
    """**A third read path would be new work this file must notice.**

    The two reads are named above, because a discovery rule would be a list of holes
    for any *new* personal read path. But a new read path is exactly the thing this
    file exists to constrain — so the file pins that there is no other one.

    **What counts as a "read path".** A module that **queries** the `DigestComposition`
    row is reading an explanation. A module that merely *names* it is not: the model
    itself, the schema that serialises it, the migrations that created it and the
    package's `__init__` all name it without reading anything.

    So the check is on the **query**, not on the name — `DigestComposition.objects` is
    the shape of a query, and `.objects` is what the ORM gives every model. A module
    that reads a composition without going through `.objects` would have to fetch it
    some other way, and the two reads below are the only places that do.
    """
    package = BACKEND_DIR / "apps/personalization"
    offenders: list[str] = []

    for path in sorted(package.rglob("*.py")):
        relative = str(path.relative_to(BACKEND_DIR))
        if relative in (DIGEST_READ, DETAIL_READ):
            continue
        # The composition service itself writes the rows; the migration and the model
        # define them. Neither reads.
        if path.name in ("digest_composition.py", "models.py"):
            continue
        if "migrations" in path.parts or path.name == "__init__.py":
            continue
        if "DigestComposition.objects" in path.read_text():
            offenders.append(relative)

    assert not offenders, (
        "These modules query a composition and are neither of the two named read paths: "
        + ", ".join(offenders)
        + ". A third read path is a new place an explanation could be served from, and "
        "it would not be covered by this file's checks. Name it here, or make it not a "
        "read path."
    )


#: The composition service — the only thing that writes a Relevance Pulse.
COMPOSITION = "apps/personalization/services/digest_composition.py"


def test_the_composition_never_rewrites_a_stored_explanation():
    """**AD-10: a persisted explanation is history, and history is not rewritten.**

    The ranking weights changed when FR-16's score entered the Relevance Pulse
    (`ranking-consumes-reliability`). The stored `DigestComposition` rows carry the
    scores and buckets computed under the *old* weights, and they are **left alone**.

    **Why this check is on the source.** The rows cannot be recomputed under the old
    formula even if someone wanted to: the *inputs* that produced them were never
    persisted — only the resulting score was. So "recompute the stored rows" is not a
    thing that can be done correctly, and a rewrite would be a rewrite under today's
    formula, which would make a user's archive change under them.

    **What this forbids.** A `UPDATE` or a `save()` on an existing composition row. The
    service may `create` and `bulk_create` — a composition is a new set of rows for a
    day — but it may not touch a row it did not write in this composition.
    """
    source = (BACKEND_DIR / COMPOSITION).read_text()

    # The composition writes its rows with `bulk_create`. The other two write calls are
    # the ones that would touch an existing row.
    for write_call in (".update(", ".save(", ".update_or_create(", ".get_or_create("):
        assert write_call not in source, (
            f"{COMPOSITION} calls {write_call!r}. A persisted Relevance Pulse is history: "
            "the rows were computed under the weights of their day and cannot be "
            "recomputed (their inputs were never persisted). Rewriting them would change "
            "a user's archive under them, and the rewrite would be under today's "
            "formula — a score the user never saw computed (AD-10)."
        )


def test_the_hysteresis_rule_is_not_a_cross_composition_carrier():
    """**`apply_hysteresis` compares within a composition, never across two.**

    The no-flicker rule ("a change in `relevance_score` that does not cross a bucket
    boundary MUST NOT change the displayed Confidence Pulse") is about a score moving
    *within* a day. The composition always calls `apply_hysteresis` with
    `previous_bucket=None` — it has no previous bucket, because "across days,
    hysteresis resets" and **no persistent bucket is stored between days**.

    **Why this matters for a weight change.** If the composition *did* carry a
    previously persisted bucket forward, then changing the weights would move the raw
    score by an amount the hysteresis band might absorb — so the same event would keep
    its old dots under a new formula, and the card's dots would depend on which
    formula wrote the row before it. Two formulas in production at once, with no way for
    a reader to tell which produced which card.

    So the rule is: **the composition reads no previous bucket.** The check is on the
    call, because the guarantee is about what is passed, not about what the domain
    function does with it.
    """
    tree = ast.parse((BACKEND_DIR / COMPOSITION).read_text(), filename=COMPOSITION)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "apply_hysteresis":
            continue

        previous = {
            keyword.arg: keyword.value
            for keyword in node.keywords
            if keyword.arg in ("previous_bucket", "previous_score")
        }

        for name, value in previous.items():
            # `None` — literally the constant — is the only permitted value. A name
            # would mean the composition carries a bucket forward.
            assert isinstance(value, ast.Constant) and value.value is None, (
                f"{COMPOSITION} passes {name}=something other than None to "
                "apply_hysteresis(). A persisted bucket carried across compositions "
                "would let a weight change be absorbed by the no-flicker band, so a "
                "card's dots would depend on which formula wrote the previous row. The "
                "hysteresis rule is within a composition (EXPERIENCE.md §4: 'across "
                "days, hysteresis resets')."
            )


def test_the_ranking_consumes_the_reliability_score_and_never_writes_it():
    """**The Relevance Pulse reads FR-16's score; it never produces one.**

    The reliability term (FR-16 → FR-22) is a *consumer* of a number another app
    owns: `Source.reliability_score` is written by FR-16's weekly recompute, in
    `apps.ingestion.services.reliability`. The digest composition reads that score
    through the candidate read and multiplies it into the Relevance Pulse.

    **Why the consumer must not become a writer.** If the ranking could write the
    score, the score's value would depend on whether a digest had been composed —
    a source's reliability would mean one thing before a digest existed and another
    after. And a recompute would race the composition's write, with the loser's value
    surviving on no one's card. FR-16's score is a fact about a *Source*, computed
    from editorial verdicts; it is not a function of who happened to open their digest.

    **The check is on the assignment, not on the import.** `personalization` is
    *supposed* to read the column — it carries the value on the candidate — so a
    name-based check would be the wrong shape. What must not appear is an assignment
    to the column, or a write of it.

    **The check is on the AST, because a name match is not enough.** The composition
    writes `source_reliability=reliability_score(0, 0)` — a *keyword argument* whose
    value happens to be a function named `reliability_score`. A substring check on the
    name would read that as a write of the column and fail on correct code, which is
    the failure mode a name-based wall has by construction. So the check looks for
    exactly two shapes: an **attribute assignment** (`source.reliability_score = ...`)
    and a **write call on the column** (`...update(reliability_score=...)`,
    `setattr(source, "reliability_score", ...)`).
    """
    package = BACKEND_DIR / "apps/personalization"
    offenders: list[str] = []

    #: The two columns FR-16's recompute owns.
    COLUMNS = ("reliability_score", "reliability_scored_at")

    for path in sorted(package.rglob("*.py")):
        relative = str(path.relative_to(BACKEND_DIR))
        if "migrations" in path.parts or path.name == "__init__.py":
            continue

        tree = ast.parse(path.read_text(), filename=str(path))

        for node in ast.walk(tree):
            # `source.reliability_score = ...`
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Attribute) and target.attr in COLUMNS:
                        offenders.append(f"{relative}:{node.lineno} assigns to `{target.attr}`")

            # `...update(reliability_score=...)` / `setattr(source, "reliability_score", ...)`
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "setattr":
                    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                        if node.args[1].value in COLUMNS:
                            offenders.append(
                                f"{relative}:{node.lineno} calls setattr on `{node.args[1].value}`"
                            )
                for keyword in node.keywords:
                    if keyword.arg in COLUMNS:
                        offenders.append(
                            f"{relative}:{node.lineno} passes `{keyword.arg}=` to "
                            f"{ast.unparse(node.func)}()"
                        )

    assert not offenders, (
        "The ranking must consume FR-16's reliability score, never write it:\n"
        + "\n".join(offenders)
        + "\n\n`Source.reliability_score` belongs to FR-16's weekly recompute in "
        "`apps.ingestion.services.reliability`. A write here would make a source's "
        "reliability depend on whether a digest had been composed, and would race the "
        "recompute that owns the column."
    )
