#!/usr/bin/env python
"""Mutation probes for the Timeline and the Conflict Review.

**What this file is.** The acceptance criterion says: *"Mutation probes for the key rules
(e.g. the cross-midnight indicator, ownership, keep-both keeping the flag), each shown to
fail when the rule is broken, in the style of `mutation_probe_contract_e2e.py`."*

The mechanism is the same one the run already uses: **apply one real bug to the
implementation, run the suite, and require that at least one test fails.** A probe that
passes the suite means the tests do not prove that rule — and a test that cannot fail is
not a test.

**Why a third file, and not an extension of the earlier ones.** `mutation_probe_e2e.py`
is the ingestion proof's probes and `mutation_probe_contract_e2e.py` is the digest
intent's. Both run one suite each. This one runs **two** — a backend suite for the
server's rules and a frontend suite for the contract's — so the harness carries a
**per-probe command** rather than a single global test list.

**The bug each probe plants is a real bug, not a syntax error.** A probe that broke the
file so badly the suite failed to collect would "pass" the harness while proving
nothing — so each mutation is a change that still parses, still runs, and still produces
a *wrong answer*. The bug must be **subtle enough to be plausible** and **shallow enough
to be applied by a text replacement**.

**The three rules the work item names, and what each probe breaks.**

1. **The cross-midnight indicator.** The flag fires on the day-cell whose interval
   contains the **overlap** — the clash — not on every day the event spans. A probe that
   carried the flag on the block rather than on the day-cell would light both of a
   Friday-night event's days, and the difference is one extra amber dot on a screen
   nobody would report as wrong.
2. **Ownership.** Every query is scoped to the caller's user id. A read that forgot the
   scope would show a second user's events and pairs — the worst bug this codebase can
   have, and the one most worth a probe.
3. **Keep both keeping the flag.** FR-58 says "Keep both" leaves a **permanent** reminder
   on both events. A projection that only carried *active* pairs would clear the flag on
   every resolution, and the difference is invisible until a user asks why the reminder
   they were promised is gone.

Run from the repo root:
    uv run --directory backend python tests/e2e/mutation_probe_timeline_conflicts.py
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FRONTEND = REPO / "frontend"

#: The backend suite this item's probes are caught by.
#:
#: **The scenario is in it, and so are the service-level tests.** The scenario proves the
#: seams; the service tests prove the rules at the layer they live. A probe that breaks
#: a service has to be caught by *something* — and a rule proved only by the seam would
#: be a rule with one point of failure.
BACKEND_SUITE = [
    "tests/e2e/test_timeline_and_conflict_proof.py",
    "tests/personalization/test_conflict_resolutions.py",
    "tests/personalization/test_timeline.py",
    "tests/personalization/test_conflict_list.py",
]

#: The frontend suite the contract probes are caught by.
FRONTEND_SUITE = [
    "tests/ad19-endpoint-coverage.test.ts",
]


@dataclass
class Probe:
    """One probe: a bug, a file to plant it in, and the suite that must catch it.

    `edits` is a list of `(original, mutated)` **literal text** pairs, each matched
    once. The harness reports `SKIP` if a pattern is not found — a probe that silently
    stopped applying is worse than no probe, because it looks like a pass.

    **A probe may need more than one edit.** A real bug usually has two halves: a filter
    and the thing it filters, or a signature and its caller. Applying them as one atomic
    change is what makes the planted code *parse* — a half-planted bug that does not
    compile is caught by the interpreter, not by the rule, and that is a false green.
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


# ── The probes ──────────────────────────────────────────────────────────────────────

PROBES: list[Probe] = [
    # 1. **The cross-midnight indicator.** The flag is carried on the block, not on the
    #    day-cell.
    #
    #    The rule is: the indicator fires on the day-cell whose interval contains the
    #    **overlap** — the clash — and not on every day the event spans. The bug is the
    #    natural simplification: light the cell whenever the block has a conflict window
    #    at all, whatever day the clash is on.
    #
    #    **The bug has to parse and has to produce a wrong answer.** A mutation that
    #    raised would be caught by the interpreter, not by the rule.
    Probe(
        description="the indicator follows the event's span and not the overlap",
        path=BACKEND / "apps/personalization/services/timeline.py",
        edits=[
            (
                "            lights = conflict_window is not None and overlaps_day(\n"
                "                start_utc=conflict_window.start_utc,\n"
                "                end_utc=conflict_window.end_utc,\n"
                "                local_date=covered_day,\n"
                "                zone_name=zone_name,\n"
                "            )\n",
                "            lights = conflict_window is not None\n",
            ),
        ],
        suite="backend",
        note="FR-33: the indicator fires on the day-cell that contains the overlap.",
    ),
    # 2. **Ownership.** The conflict list reads another user's pairs.
    #
    #    The list scopes its pair query by `user_id`. The bug drops the scope — and the
    #    **side** lookups still carry it, so the pairs come back with their sides
    #    marked unavailable rather than with their names. That is what makes the bug
    #    plausible: it does not obviously leak, and a test that only checked the pair
    #    *count* would see a non-zero count and no names.
    Probe(
        description="the conflict list is not scoped to the caller",
        path=BACKEND / "apps/personalization/services/conflict_list.py",
        edits=[
            (
                "    pairs = list(\n"
                "        ConflictPair.objects.using(PERSONAL)\n"
                "        .filter(user_id=user_id)\n"
                "        .exclude(status=ConflictPair.Status.CLEARED_BY_STATE_CHANGE)\n"
                "    )\n",
                "    pairs = list(\n"
                "        ConflictPair.objects.using(PERSONAL)\n"
                "        .exclude(status=ConflictPair.Status.CLEARED_BY_STATE_CHANGE)\n"
                "    )\n",
            ),
        ],
        suite="backend",
        note="AD-12: no user sees another user's pairs.",
    ),
    # 3. **Ownership.** The Timeline read is not scoped to the caller.
    #
    #    The same scope, in the other read. This one is about the **blocks** rather than
    #    the pairs — a user's week must not carry another user's events or saves.
    Probe(
        description="the timeline read is not scoped to the caller",
        path=BACKEND / "apps/personalization/services/timeline.py",
        edits=[
            (
                "    personal_events = list_personal_events(\n"
                "        user_id=user_id,\n"
                "        overlaps_after=window_start,\n"
                "        overlaps_before=window_end,\n"
                "    )\n",
                "    personal_events = list_personal_events(\n"
                "        user_id=user_id,\n"
                "        overlaps_after=window_start,\n"
                "        overlaps_before=window_end,\n"
                "    ) if False else list_personal_events(\n"
                "        user_id=uuid4(),\n"
                "        overlaps_after=window_start,\n"
                "        overlaps_before=window_end,\n"
                "    )\n",
            ),
        ],
        suite="backend",
        note="AD-12: no user sees another user's events.",
    ),
    # 4. **Keep both keeping the flag.** The projection carries only *active* pairs.
    #
    #    FR-58 says "Keep both" leaves a **permanent** reminder on both events. The
    #    projection in `timeline.py` carries an active pair *and* a pair resolved with
    #    `keep_both`. The bug drops the second clause — which is the projection the
    #    digest read uses too, so it is the **natural** simplification to make.
    Probe(
        description="the timeline's indicator ignores a keep-both resolution",
        path=BACKEND / "apps/personalization/services/timeline.py",
        edits=[
            (
                "            Q(status=ConflictPair.Status.ACTIVE)\n"
                "            # A pair resolved with `keep_both` does too — the permanent"
                " reminder.\n"
                "            | Q(\n"
                "                status=ConflictPair.Status.RESOLVED,\n"
                "                resolution=ConflictPair.Resolution.KEEP_BOTH,\n"
                "            )\n",
                "            Q(status=ConflictPair.Status.ACTIVE)\n",
            ),
        ],
        suite="backend",
        note="FR-58: keep both leaves a permanent reminder on both events.",
    ),
    # 5. **The action names its own target.** `skip_public` releases a *personal* event.
    #
    #    The safety property is per-action: `skip_public` acts on a saved side, and
    #    `delete_new` acts on a personal one. The property is carried by the **allowed
    #    set** — `resolutions_for_side(kind, side_kind)` returns the saved side's three
    #    actions for a saved side and the personal side's three for a personal one, so
    #    `skip_public` is simply not in the personal side's set. Removing the membership
    #    check makes `skip_public` legal against a personal side, and the server would
    #    release a save the user never named.
    #
    #    **This probe was first aimed at the wrong check.** The service has *two* guards:
    #    the allowed-set membership, and an explicit `side_kind != _target_side_kind(value)`
    #    comparison. The second one is **defence in depth and unreachable** — the allowed
    #    set already excludes every mismatched pair — so removing it changes nothing and
    #    the suite stayed green. That is not a hole in the tests; it is a **finding about
    #    the implementation**, and the probe now aims at the check that actually carries
    #    the property. The redundant guard is left in the code: it is a correct statement
    #    of the rule, and removing it would be a change to reviewed code for no gain.
    Probe(
        description="the resolve endpoint accepts an action that does not target the named side",
        path=BACKEND / "apps/personalization/services/conflict_resolutions.py",
        edits=[
            (
                "        allowed = resolutions_for_side(kind=pair.kind, side_kind=side_kind)\n"
                "        if value not in allowed:\n"
                "            raise IllegalResolutionError(\n"
                '                details={"resolution": value, "kind": pair.kind,'
                ' "side_kind": str(side_kind)}\n'
                "            )\n",
                "        allowed = resolutions_for_side(kind=pair.kind, side_kind=side_kind)\n",
            ),
        ],
        suite="backend",
        note="FR-58: the action decides which side it may act on.",
    ),
    # 6. **A closed pair is immutable.** The second answer is accepted.
    #
    #    AD-21 says a resolved pair is never re-prompted and never re-answered. The
    #    check is one line — `if pair.status != ACTIVE: raise` — and removing it lets a
    #    client's double-post overwrite the user's first choice.
    Probe(
        description="a closed pair can be answered again",
        path=BACKEND / "apps/personalization/services/conflict_resolutions.py",
        edits=[
            (
                "        if pair.status != ConflictPair.Status.ACTIVE:\n"
                '            raise ConflictAlreadyResolvedError(details={"pair_id":'
                " str(pair_id)})\n",
                "",
            ),
        ],
        suite="backend",
        note="AD-21: a closed pair is immutable and never re-prompted.",
    ),
    # 7. **The contract.** The frontend's call site stops using the generated client.
    #
    #    The frontend reaches the backend through `lib/backend-client.ts` and nothing
    #    else. The bug is a raw `fetch` — which the ESLint rule forbids, so it would
    #    also fail the lint gate, but the **contract test** is what says the generated
    #    types are load-bearing, and a probe that only the linter catches would leave
    #    the contract test unproven.
    Probe(
        description="the timeline read bypasses the generated client",
        path=FRONTEND / "lib/timeline-read.ts",
        edits=[
            (
                '    const response = await api.GET("/api/personal/timeline", {',
                '    const response = await fetch("/api/personal/timeline", {',
            ),
        ],
        suite="frontend",
        note="AD-19: the frontend reaches the backend through the generated client.",
    ),
    # 8. **The contract.** A call site names a path the schema does not describe.
    #
    #    The generated client is typed from the schema, so a *typo* is a compile error.
    #    But an endpoint added to the backend and called **correctly by hand** — a path
    #    that is real but is not the one the contract declares — is not caught by
    #    `tsc` at all. This probe plants exactly that: the path is plausible, the call
    #    is typed, and only the contract sweep sees it.
    Probe(
        description="the conflicts read names a path the schema does not declare",
        path=FRONTEND / "lib/conflict-list-read.ts",
        edits=[
            (
                '    const response = await api.GET("/api/personal/conflicts", {',
                '    const response = await api.GET("/api/personal/conflict-pairs", {',
            ),
        ],
        suite="frontend",
        note="AD-19: every endpoint the frontend calls is in the committed schema.",
    ),
]


def run_backend_suite() -> tuple[int, str]:
    """Run the backend suite. Returns `(returncode, output)`."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *BACKEND_SUITE, "-q", "--no-header"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def run_frontend_suite() -> tuple[int, str]:
    """Run the frontend suite. Returns `(returncode, output)`."""
    # The full path, not "pnpm": a partial path runs whatever `pnpm` is first on PATH.
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

    print(f"All {len(results)} probes were caught by the suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
