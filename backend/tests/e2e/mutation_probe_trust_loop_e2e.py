#!/usr/bin/env python
"""Mutation probes for run-eventpulse24-026's last item: the trust loop's proof.

**What this file is.** The acceptance criterion says: *"Each e2e assertion is shown to be
able to fail, either by a recorded mutation probe in the style of
`tests/e2e/mutation_probe_contract_e2e.py` or by an explicit negative control."* This is
the probe half; the negative controls are inside the proof itself (the healthy source
beside the collapsed one, the control event beside the rejected one, the clean re-ingest
beside the barred event).

The mechanism is the one the run already uses: **apply one real bug to the implementation,
run the suite, and require that at least one test fails.** A probe the suite does not catch
means the tests do not prove that rule — and a test that cannot fail is not a test.

**The bug each probe plants is a real bug**, not a syntax error. Each mutation still
parses, still runs, and still produces a *wrong answer*: subtle enough to be plausible,
shallow enough to be a text replacement.

**Every probe here is aimed at this item's own two files.** A probe caught only by some
other suite would say nothing about whether *this* proof can fail, which is the question
the criterion asks. Where the honest answer was "my suite cannot distinguish that" — the
`and` in `should_escalate`, whose first half the `RELIABILITY_NEW_SOURCE_FLOOR` makes
unreachable below the minimum N — the probe was **changed to one the suite can catch** (the
off-by-one on the minimum itself) rather than pointed at a suite that would flatter it.

Run from the repo root:
    uv run --directory backend python tests/e2e/mutation_probe_trust_loop_e2e.py
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

#: This item's own suites. Nothing else — see the module docstring.
SUITE = [
    "tests/e2e/test_trust_loop_proof.py",
    "tests/e2e/test_trust_loop_contract.py",
]


@dataclass
class Probe:
    """One probe: a bug, a file to plant it in, and what it breaks.

    `edits` is a list of `(original, mutated)` **literal text** pairs, each matched once.
    The harness reports `SKIP` if a pattern is not found — a probe that silently stopped
    applying is worse than no probe, because it looks like a pass.
    """

    #: What the probe breaks, in words. This is what the run log records.
    description: str
    #: The file the bug is planted in.
    path: Path
    #: The `(original, mutated)` pairs to apply, in order.
    edits: list[tuple[str, str]]
    #: Which claim of the proof is supposed to notice.
    note: str = ""


@dataclass
class ProbeResult:
    probe: Probe
    #: `ok`, `fail` (the suite still passed), or `skip` (the pattern was not found).
    outcome: str
    detail: str = ""


# ── The ten probes ─────────────────────────────────────────────────────────────────────

PROBES: list[Probe] = [
    # 1. **A report hides the event.** FR-59's calmest promise, inverted: raising the
    #    item also pulls the listing, so one person — or one troll — can take an event
    #    down without an editor.
    Probe(
        description="a user report quarantines the event it reports",
        path=BACKEND / "apps/ingestion/services/review_queue.py",
        edits=[
            (
                "    event = Event.objects.using(CATALOG).filter(pk=event_id).first()\n"
                "    if event is None:\n"
                "        return None\n"
                "    return raise_review_item(\n",
                "    event = Event.objects.using(CATALOG).filter(pk=event_id).first()\n"
                "    if event is None:\n"
                "        return None\n"
                "    Event.objects.using(CATALOG).filter(pk=event.pk).update(\n"
                "        publication_status=Event.PublicationStatus.IN_REVIEW\n"
                "    )\n"
                "    return raise_review_item(\n",
            )
        ],
        note="'the event is still in the digest' — a report never changes visibility.",
    ),
    # 2. **The report raises nothing.** The report is recorded and the editor never hears
    #    about it: the loop's first joint, silently unwelded.
    Probe(
        description="a report records its row but raises no review item",
        path=BACKEND / "apps/personalization/services/event_reports.py",
        edits=[
            (
                "    _raise_and_stamp(report, now=moment)\n    return report\n",
                "    return report\n",
            )
        ],
        note="'a user_reported ReviewItem appears'.",
    ),
    # 3. **A rejected event stays in the sitemap.** The page 404s and the crawler keeps
    #    being sent to it — the crawl-budget leak the feed exists to prevent.
    Probe(
        description="the sitemap keeps serving a rejected event's URL",
        path=BACKEND / "apps/ingestion/services/url_feed_read.py",
        edits=[
            (
                "        .filter(publication_status=Event.PublicationStatus.PUBLISHED)\n"
                "        .exclude(status=Event.Status.SUPERSEDED)\n",
                "        .exclude(status=Event.Status.SUPERSEDED)\n",
            )
        ],
        note="'the event leaves ... the sitemap'.",
    ),
    # 4. **The reject teaches the source nothing.** The observation is recorded with the
    #    one kind whose sign is zero, so the verdict happens and the score never moves —
    #    FR-16 wired to a dead input.
    Probe(
        description="a reject is recorded as a dismissal, so it carries no weight",
        path=BACKEND / "apps/ingestion/services/editorial_review.py",
        edits=[
            (
                "            kind=SourceObservation.Kind.REJECTED,\n",
                "            kind=SourceObservation.Kind.DISMISSED,\n",
            )
        ],
        note="'the source's observation count rises' and the escalation.",
    ),
    # 5. **The minimum-N is off by one.** A source with exactly `RELIABILITY_MIN_OBSERVATIONS`
    #    observations is one short of escalating — the classic boundary slip, and the
    #    reason the proof drives exactly thirty rejects rather than a comfortable forty.
    Probe(
        description="escalation needs more than the minimum N, not at least it",
        path=BACKEND / "domain/reliability.py",
        edits=[
            (
                "    return score < RELIABILITY_ESCALATION_SCORE and "
                "observations >= RELIABILITY_MIN_OBSERVATIONS\n",
                "    return score < RELIABILITY_ESCALATION_SCORE and "
                "observations > RELIABILITY_MIN_OBSERVATIONS\n",
            )
        ],
        note="'a source_reliability item appears' at exactly 30 observations.",
    ),
    # 6. **Ranking drops the reliability term.** FR-22's published weight silently absent:
    #    the formula still computes, the cards still rank, and the collapsed source's
    #    event sits exactly where the healthy one does.
    Probe(
        description="the relevance score drops the source_reliability term",
        path=BACKEND / "domain/ranking.py",
        edits=[("        + RANKING_WEIGHT_RELIABILITY * inputs.source_reliability\n", "")],
        note="'that source's next event ranks below an otherwise-identical event'.",
    ),
    # 7. **The quarantine raises no ticket.** The gate still holds the event out of every
    #    public read, and now nothing tells an editor it is there: the exact bug the
    #    intent was captured to fix, restored.
    Probe(
        description="an in_review event is never ticketed",
        path=BACKEND / "apps/ingestion/services/review_intake.py",
        edits=[
            (
                "    if event.publication_status == Event.PublicationStatus.IN_REVIEW:\n",
                "    if event.publication_status == Event.PublicationStatus.REJECTED:\n",
            )
        ],
        note="'a low-timezone-confidence event ... gets a queue item'.",
    ),
    # 8. **Being staff is enough to read the queue.** The group grant stops being the
    #    gate, and every staff account in the admin can see editorial work.
    Probe(
        description="the queue's read gate accepts any staff user",
        path=BACKEND / "apps/ingestion/admin.py",
        edits=[
            (
                "        return editorial_review_queue.may_view(request.user)\n",
                "        return bool(request.user.is_staff)\n",
            )
        ],
        note="'a non-editor is refused by the admin'.",
    ),
    # 9. **The daily cap is off by one.** Six reports a day, not five — the limit still
    #    exists, still refuses, and refuses one report too late.
    Probe(
        description="the report cap admits one more than FR-59 allows",
        path=BACKEND / "apps/personalization/services/event_reports.py",
        edits=[
            (
                "        limit=EVENT_REPORT_DAILY_LIMIT,\n",
                "        limit=EVENT_REPORT_DAILY_LIMIT + 1,\n",
            )
        ],
        note="'a sixth report in a day is refused'.",
    ),
    # 10. **The optimistic lock is handed nothing.** The form still renders the token and
    #     still collects it; the commands are simply never told, so their
    #     `expected_event_version is not None` check short-circuits and a stale editor's
    #     edit lands on an event that moved under them.
    #
    #     **Both call sites, because the defence is deliberately doubled.** The form's
    #     `clean()` calls `check_review_edit` outside the transaction and `save_form`
    #     calls `edit_and_publish` inside it — "the checks run twice on purpose", as the
    #     command's own docstring says. A probe that mutated only the second one was
    #     **not caught**, and correctly so: the first check still refused. That is a fact
    #     about the implementation's depth, not a hole in the proof, so the probe was
    #     widened to the bug it claims to be — the admin stops passing the token at all —
    #     rather than the proof being weakened to notice a half-bug.
    Probe(
        description="the admin's edit never passes the staleness token to the commands",
        path=BACKEND / "apps/ingestion/admin.py",
        edits=[
            (
                '                expected_event_version=cleaned.get("expected_event_version"),\n',
                "                expected_event_version=None,\n",
            ),
            (
                "            expected_event_version=form.cleaned_data.get"
                '("expected_event_version"),\n',
                "            expected_event_version=None,\n",
            ),
        ],
        note="'a stale-version resolve is refused'.",
    ),
]


def run_suite() -> tuple[int, str]:
    """Run this item's two suites. Returns `(returncode, output)`.

    **No `-x`.** Stopping at the first failure would let one environmental failure
    short-circuit the run, and the baseline below needs to see the whole picture anyway.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *SUITE, "-q", "--no-header"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def baseline() -> tuple[bool, str]:
    """Run the suite **unmutated** and require it to be green.

    **This is the check that makes every result below mean anything.** `run_probe` reads a
    non-zero exit as "the bug was caught" — and the contract suite shells out to `pnpm`,
    `openapi-typescript` and `lint-imports`, and `pytest.fail`s when they are missing. On a
    machine with no Node, *every* probe would exit non-zero for a reason that has nothing to
    do with the planted bug, and this script would print "all 10 probes were caught" and
    return 0.

    That is a false green on precisely the acceptance criterion the script exists to
    satisfy, which is the worst failure a harness like this can have. So the suite is run
    once, clean, before anything is mutated, and a red baseline aborts the run.
    """
    code, output = run_suite()
    if code == 0:
        return True, ""
    tail = [line for line in output.strip().splitlines() if line.strip()]
    return False, tail[-1] if tail else "the suite failed"


def run_probe(probe: Probe) -> ProbeResult:
    """Apply the bug, run the suite, and put the file back.

    **The file is always restored**, whether the suite failed, passed, or the process
    died — the `finally` is not conditional. A probe that left a broken file behind would
    make every probe after it meaningless.

    **Every edit is checked before any is applied.** A probe with two edits where only one
    pattern matches would plant half a bug, and a half-planted bug that does not compile is
    caught by the interpreter rather than by the rule — a false green.
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
        code, output = run_suite()
    finally:
        probe.path.write_text(source)

    if code == 0:
        return ProbeResult(probe, "fail", "the suite still passed")

    tail = [line for line in output.strip().splitlines() if line.strip()]
    return ProbeResult(probe, "ok", tail[-1] if tail else "the suite failed")


def main() -> int:
    ok, detail = baseline()
    if not ok:
        print("ABORT the suite is not green before any mutation -- every probe below")
        print(f"      would report 'caught' for a reason unrelated to its bug: {detail}")
        return 2
    print("BASE  the suite is green unmutated -- a non-zero exit below means the bug")
    print()

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

    print(f"All {len(results)} trust-loop probes were caught by the suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
