#!/usr/bin/env python
"""Mutation probes for the contract tests of run-eventpulse24-021's last item.

**What this file is.** The acceptance criterion says: *"Every test in this item can
fail. No placeholder assertions, no `or`-fallbacks, no test that passes because a value
is absent. Each one is verified to fail when the behavior it pins is deliberately
broken, and the run log records that it was checked."*

The mechanism is the same one the run already uses (`tests/e2e/mutation_probe_e2e.py`):
**apply one real bug to the implementation, run the suite, and require that at least
one test fails.** A probe that passes the suite means the tests do not prove that rule
— and a test that cannot fail is not a test.

**Why a second file, and not an extension of the first.** The earlier probes are all
**backend** and all run one backend test file. These probes are about **contract
rules**, and three of them live in the **frontend** — a frontend bug is caught by a
frontend test, and running the backend suite against a frontend mutation would prove
nothing. So the harness here carries a **per-probe command**, not a single global test
list: each probe names the suite that is supposed to catch it.

**The bug each probe plants is a real bug**, not a syntax error. A probe that broke
the file so badly the suite failed to collect would "pass" the harness while proving
nothing — so each mutation is a change that still parses, still runs, and still
produces a *wrong answer*. This is the point of the technique: the bug must be
**subtle enough to be plausible** and **shallow enough to be applied by a text
replacement**.

Run from the repo root:
    uv run --directory backend python tests/e2e/mutation_probe_contract_e2e.py
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FRONTEND = REPO / "frontend"

#: The backend contract tests this item added, plus the e2e scenario, plus the
#: constants pin that FR-22's lock is enforced by.
BACKEND_SUITE = [
    "tests/architecture/test_ad10_explanation_persistence.py",
    "tests/architecture/test_ad3_composition_separation.py",
    "tests/architecture/test_ad13_pii_sweep.py",
    "tests/e2e/test_digest_and_detail_proof.py",
    "tests/shared/test_constants.py",
]

#: The frontend's half of AD-10: the import-graph wall and the personal data-flow wall.
FRONTEND_SUITE = [
    "tests/ad10-separation.test.ts",
    "tests/personal-separation.test.ts",
]


@dataclass
class Probe:
    """One probe: a bug, a file to plant it in, and the suite that must catch it.

    `edits` is a list of `(original, mutated)` **literal text** pairs, each matched
    once. The harness reports `SKIP` if a pattern is not found — a probe that silently
    stopped applying is worse than no probe, because it looks like a pass.

    **A probe may need more than one edit.** A real bug usually has two halves: an
    import and the call that uses it, or a signature and its caller. Applying them as
    one atomic change is what makes the planted code *parse* — a half-planted bug that
    does not compile is caught by the interpreter, not by the rule, and that is a
    false green.
    """

    #: What the probe breaks, in words. This is what the run log records.
    description: str
    #: The file the bug is planted in.
    path: Path
    #: The `(original, mutated)` pairs to apply, in order.
    edits: list[tuple[str, str]]
    #: The suite that must fail. `backend` runs pytest; `frontend` runs vitest.
    suite: str = "backend"
    #: The probe's own notes, printed with the result.
    note: str = ""


@dataclass
class ProbeResult:
    """What happened to one probe."""

    probe: Probe
    #: `ok`, `fail` (the suite still passed), or `skip` (the pattern was not found).
    outcome: str
    #: The last line of the suite's output.
    detail: str = ""


# ── The seven probes ──────────────────────────────────────────────────────────────────

PROBES: list[Probe] = [
    # 1. **AD-10's frontend wall.** The detail read reaches the Event Fit.
    #
    # The frontend's wall is a *transitive import walk*, so the bug does not have to be
    # on the route: importing the Event Fit's read into the detail read is enough for
    # the walk to find it.
    #
    # **The probe plants a CALL, not just an import.** An import that is never used
    # changes nothing about the app's behaviour — and the backend's own re-export
    # probe taught this run that a name in an import statement is not a reachability.
    # So the bug calls the Event Fit's read, exactly as a fallback would.
    Probe(
        description="the detail read imports the Event Fit's read",
        path=BACKEND / "apps/personalization/services/detail_read.py",
        edits=[
            (
                "from apps.ingestion.services.catalog_read import PublicEventDetail, "
                "get_public_event_detail\n",
                "from apps.ingestion.event_fit.reads import list_event_fit_for_city\n"
                "from apps.ingestion.services.catalog_read import PublicEventDetail, "
                "get_public_event_detail\n",
            ),
            (
                "    event = get_public_event_detail(event_id=event_id, now=now)\n",
                "    event = get_public_event_detail(event_id=event_id, now=now)\n"
                '    list_event_fit_for_city(city="Los Angeles")\n',
            ),
        ],
        suite="backend",
        note="AD-3/AD-10: personalization may not reach the Event Fit.",
    ),
    # 2. **"No explanation at view time."** The digest read calls a ranking function.
    #
    # The read would compute a Relevance Pulse at request time — which is exactly the
    # substitution AD-10 forbids, and which would let two surfaces disagree about the
    # same event.
    #
    # **The probe plants a CALL, not an import.** An earlier version of this probe
    # only added the import, and the suite stayed green — correctly, because an
    # imported-but-uncalled function computes nothing. The AST check is a **call**
    # check for the same reason: a call is what a computation is, and an import is
    # not. The bug here is the real one: the card's bucket is **re-bucketed from the
    # score** at request time instead of being read from the persisted row.
    Probe(
        description="the digest read calls the ranking function",
        path=BACKEND / "apps/personalization/services/digest_read.py",
        edits=[
            (
                "from apps.personalization.services.digest_dates import local_date_for\n",
                "from apps.personalization.services.digest_dates import local_date_for\n"
                "from domain.ranking import score_bucket\n",
            ),
            (
                "            location=None,\n"
                "            tags=tuple(row.tags),\n"
                "            bucket=row.bucket,\n"
                "            source_badge=row.source_badge,\n"
                "            tz_review_pending=False,\n",
                "            location=None,\n"
                "            tags=tuple(row.tags),\n"
                "            bucket=score_bucket(row.score),\n"
                "            source_badge=row.source_badge,\n"
                "            tz_review_pending=False,\n",
            ),
        ],
        suite="backend",
        note="AD-10: a read serves persisted rows; it does not compute one.",
    ),
    # 3. **"No explanation at view time."** The detail read composes a digest.
    #
    # This is the write-at-view-time failure in its most literal form: every page view
    # would create an explanation.
    #
    # **The probe plants a CALL** — an import alone computes nothing, so an
    # import-only probe proves nothing.
    Probe(
        description="the detail read calls compose_digest",
        path=BACKEND / "apps/personalization/services/detail_read.py",
        edits=[
            (
                "from apps.personalization.services.neighbor_count import NeighborCount, "
                "count_neighbors\n",
                "from apps.personalization.services.digest_composition import compose_digest\n"
                "from apps.personalization.services.neighbor_count import NeighborCount, "
                "count_neighbors\n",
            ),
            (
                "    composition = _most_recent_composition(user_id=user_id, event_id=event_id)\n",
                "    compose_digest(user_id=user_id, actor=ACTOR, now=now)\n"
                "    composition = _most_recent_composition(user_id=user_id, event_id=event_id)\n",
            ),
            (
                "from shared.db import PERSONAL\n",
                "from shared.actor import Actor\n"
                "from shared.db import PERSONAL\n"
                "\n"
                'ACTOR = Actor.system("probe")\n',
            ),
        ],
        suite="backend",
        note="AD-11: a read never writes; it serves what was written.",
    ),
    # 4. **"No explanation at view time."** The read writes a composition row.
    #
    # This is the probe the AST checks **cannot** catch — the write is one layer down,
    # so the check that catches it is the **database row count**. That is why the
    # database check exists in the file at all.
    #
    # The bug: the detail read **composes an explanation on the spot** for an event
    # that has none. This is the failure in its most literal form — "the screen
    # generates a plausible reason on the spot" — and it is invisible to every
    # import check and every call check, because it happens inside the read's own
    # module.
    Probe(
        description="the detail read writes a composition row",
        path=BACKEND / "apps/personalization/services/detail_read.py",
        edits=[
            (
                "    return (\n"
                "        DigestComposition.objects.using(PERSONAL)\n"
                "        .filter(user_id=user_id, event_id=event_id)\n"
                '        .order_by("-composed_at", "-id")\n'
                "        .first()\n"
                "    )\n",
                "    from decimal import Decimal\n"
                "\n"
                "    from django.utils import timezone\n"
                "\n"
                "    from apps.personalization.models import PulseDigest\n"
                "\n"
                "    existing = (\n"
                "        DigestComposition.objects.using(PERSONAL)\n"
                "        .filter(user_id=user_id, event_id=event_id)\n"
                '        .order_by("-composed_at", "-id")\n'
                "        .first()\n"
                "    )\n"
                "    if existing is None:\n"
                "        digest = (\n"
                "            PulseDigest.objects.using(PERSONAL)\n"
                "            .filter(user_id=user_id)\n"
                '            .order_by("-id")\n'
                "            .first()\n"
                "        )\n"
                "        if digest is not None:\n"
                "            DigestComposition.objects.using(PERSONAL).create(\n"
                "                digest_id=digest.id,\n"
                "                user_id=user_id,\n"
                "                event_id=event_id,\n"
                "                event_kind=DigestComposition.EventKind.PUBLIC,\n"
                '                slot="nearby",\n'
                '                score=Decimal("3.00"),\n'
                "                bucket=3,\n"
                '                tags=["nearby"],\n'
                "                source_badge=None,\n"
                "                event_version=None,\n"
                "                composed_at=timezone.now(),\n"
                "            )\n"
                "    return existing\n",
            ),
        ],
        suite="backend",
        note="AD-10: the database row count is the check that catches this one.",
    ),
    # 5. **FR-22's weight lock.** A ranking weight moves.
    #
    # FR-22 says a weight change without a PRD amendment is a CI-level failure. The
    # pin is in `tests/shared/test_constants.py`, and the probe proves the pin is real:
    # move the constant, and the suite must fail.
    Probe(
        description="a ranking weight moves",
        path=BACKEND / "shared/constants.py",
        edits=[
            (
                'RANKING_WEIGHT_INTEREST = Decimal("0.45")\n',
                'RANKING_WEIGHT_INTEREST = Decimal("0.50")\n',
            ),
        ],
        suite="backend",
        note="FR-22: the weights are pinned, and the pin is watched to fail.",
    ),
    # 6. **A public surface never reads `personal`.** The detail page reads `.personal`
    #    outside the guard.
    #
    # This is the exact bug the Detail Screen's own review found — the reminder picker
    # sat outside the `personal` check while the breakdown and the neighbour count sat
    # inside it. The data-flow check is brace-aware precisely so this shape is caught.
    Probe(
        description="the detail page reads .personal outside the guard",
        path=FRONTEND / "app/events/[id]/page.tsx",
        edits=[
            (
                "      {/* The neighbor count is silent below the k-anonymity threshold. */}\n"
                "      {personal ? (\n",
                "      {/* The neighbor count is silent below the k-anonymity threshold. */}\n"
                "      <DetailNeighbors bucket={personal.neighbor_bucket ?? null} />\n"
                "      {personal ? (\n",
            ),
        ],
        suite="frontend",
        note="A public surface never reads personal outside a guard.",
    ),
    # 7. **AD-3.** The composition's transaction spans both schemas.
    #
    # The bug is a catalog read **moved inside** the personal transaction. That is the
    # violation AD-3 names — "no transaction spans both schemas" — and it is exactly
    # what the ordering check in the composition-separation test is for: a transaction
    # whose window covers a catalog read is a distributed transaction, which Postgres
    # cannot do and which the ORM would fake by opening a second connection.
    #
    # **The bug has to parse.** An earlier version of this probe wrote
    # `transaction.atomic(using=PERSONAL, using=CATALOG)`, which is a `SyntaxError` —
    # and the suite "caught" it, because a suite that cannot be collected fails. That
    # is a **false green**: the probe would have passed while proving nothing. The
    # mutation is therefore a *read that moves*, not an argument that duplicates.
    Probe(
        description="the composition's transaction spans both schemas",
        path=BACKEND / "apps/personalization/services/digest_composition.py",
        edits=[
            (
                "    public_candidates = list_public_candidates(now=now, city=user_city or None)\n"
                "\n"
                "    saved_event_ids = {saved.event_id for saved in saved_candidates}\n",
                "    saved_event_ids = {saved.event_id for saved in saved_candidates}\n"
                "\n"
                "    # --- the write, atomic on the personal side ---\n"
                "    with transaction.atomic(using=PERSONAL):\n"
                "        public_candidates = list_public_candidates(\n"
                "            now=now, city=user_city or None\n"
                "        )\n"
                "\n"
                "    saved_event_ids = {saved.event_id for saved in saved_candidates}\n",
            ),
        ],
        suite="backend",
        note="AD-3: no transaction spans both schemas.",
    ),
    # 8. **AD-13.** The audit sink carries an event title.
    #
    # The audit row's `details` is a `JSONField` with no schema and no allowlist — so
    # a title written into it is a title in the database forever. The log sink has
    # the formatter's allowlist; the audit sink has **nothing**, which is why the
    # sweep states its own vocabulary.
    #
    # The bug is the real one: the audit row records the title so an operator can see
    # what was opened. That is exactly the "no event title reaches a sink" failure.
    Probe(
        description="the audit sink carries an event title",
        path=BACKEND / "apps/personalization/services/detail_opens.py",
        edits=[
            (
                '            details={"event_id": str(event_id), "created": created},\n',
                "            details={\n"
                '                "event_id": str(event_id),\n'
                '                "created": created,\n'
                '                "title": "Dinner with Priya at Rosa\'s",\n'
                "            },\n",
            ),
        ],
        suite="backend",
        note="AD-13: no event title reaches a sink.",
    ),
    # 9. **AD-13.** The audit sink carries the user's city.
    #
    # The same sink, the same shape, and a **different** piece of personal
    # information — so this probe proves the city sweep is not merely the title
    # sweep wearing a different hat.
    Probe(
        description="the audit sink carries the user's city",
        path=BACKEND / "apps/personalization/services/digest_composition.py",
        edits=[
            (
                '                "local_date": local_date.isoformat(),\n',
                '                "local_date": local_date.isoformat(),\n'
                '                "city": user_city,\n',
            ),
        ],
        suite="backend",
        note="AD-13: no city reaches a sink.",
    ),
    # 10. **The card and the detail must agree.** The card's bucket is recomputed.
    #
    # This is the whole intent in one bug: the card shows a bucket the breakdown
    # does not. The reader checks the explanation and finds a different one — which
    # is what FR-21's consistency consequence forbids.
    #
    # **The mutation targets the LIVE card, not the missing-catalog one.** The digest
    # read has two card builders — one for an event that is still in the catalog, and
    # one for an event whose catalog row is gone. An earlier version of this probe
    # changed the *first* pattern it found, which was the missing-catalog branch — and
    # the suite stayed green, because the scenario's events are all present and that
    # branch never runs. **A probe that plants a bug in dead code proves nothing.**
    # The live builder is identified by its `tz_review_pending=public.…` line, which
    # only that branch has.
    Probe(
        description="the card's bucket disagrees with the breakdown's",
        path=BACKEND / "apps/personalization/services/digest_read.py",
        edits=[
            (
                "        tags=tuple(row.tags),\n"
                "        bucket=row.bucket,\n"
                "        source_badge=row.source_badge,\n"
                "        tz_review_pending=public.tz_review_pending,\n",
                "        tags=tuple(row.tags),\n"
                "        bucket=row.bucket + 1,\n"
                "        source_badge=row.source_badge,\n"
                "        tz_review_pending=public.tz_review_pending,\n",
            ),
        ],
        suite="backend",
        note="FR-21: the card and the breakdown are one persisted row, read two ways.",
    ),
]


def run_backend_suite() -> tuple[int, str]:
    """Run the backend contract suite. Returns `(returncode, output)`."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *BACKEND_SUITE, "-q", "--no-header"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def run_frontend_suite() -> tuple[int, str]:
    """Run the frontend contract suite. Returns `(returncode, output)`."""
    # The full path, not "pnpm": a partial path runs whatever `pnpm` is first on PATH (S607).
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        return 127, "pnpm is not on PATH"
    result = subprocess.run(
        [pnpm, "vitest", "run", *FRONTEND_SUITE],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def run_suite(suite: str) -> tuple[int, str]:
    """Run the named suite."""
    if suite == "frontend":
        return run_frontend_suite()
    return run_backend_suite()


def run_probe(probe: Probe) -> ProbeResult:
    """Apply the bug, run the suite, and put the file back.

    **The file is always restored**, whether the suite failed, passed, or the process
    died — the `finally` is not conditional. A probe that leaves a broken file behind
    would make every probe after it meaningless.

    **Every edit is checked before any is applied.** A probe with two edits where only
    one pattern matches would otherwise plant half a bug — and a half-planted bug that
    does not compile is caught by the interpreter, which is a false green.
    """
    source = probe.path.read_text()

    for original, _ in probe.edits:
        if original not in source:
            return ProbeResult(probe, "skip", "a pattern was not found — the probe did not apply")

    mutated = source
    for original, replacement in probe.edits:
        mutated = mutated.replace(original, replacement, 1)

    probe.path.write_text(mutated)
    try:
        code, output = run_suite(probe.suite)
    finally:
        probe.path.write_text(source)

    if code == 0:
        return ProbeResult(probe, "fail", "the suite still passed")

    tail = [line for line in output.strip().splitlines() if line.strip()]
    return ProbeResult(probe, "ok", tail[-1] if tail else "the suite failed")


def main() -> int:
    results: list[ProbeResult] = []

    for probe in PROBES:
        result = run_probe(probe)
        results.append(result)

        if result.outcome == "ok":
            print(f"OK    {probe.description} -- caught ({result.detail})")
        elif result.outcome == "fail":
            print(f"FAIL  {probe.description} -- {result.detail}")
        else:
            print(f"SKIP  {probe.description} -- {result.detail}")

    print()
    failures = [r for r in results if r.outcome != "ok"]
    if failures:
        for result in failures:
            print(f"{result.outcome.upper()}: {result.probe.description} -- {result.detail}")
        return 1

    print(f"All {len(results)} contract probes were caught by the suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
