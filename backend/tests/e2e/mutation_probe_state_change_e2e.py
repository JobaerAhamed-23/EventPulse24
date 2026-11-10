#!/usr/bin/env python
"""Mutation probes for the state-change proof of run-eventpulse24-025's last item.

**What this file is.** The acceptance criterion asks for a proof that the whole path
works, and a proof that cannot fail is not a proof. So this file applies **one real
bug at a time** to the implementation and requires that the matching test goes red.

The mechanism is the one the run already uses (`tests/e2e/mutation_probe_e2e.py`,
`tests/e2e/mutation_probe_contract_e2e.py`,
`tests/e2e/mutation_probe_delivery_e2e.py`): **plant a bug, run the suite, and
require that at least one test fails.** A probe whose suite stays green means the
tests do not prove that rule.

**The bug each probe plants is a real bug, not a syntax error.** A probe that broke
the file so badly the suite failed to collect would "pass" the harness while proving
nothing — so each mutation still parses, still runs, and still produces a *wrong
answer*. The bug must be **subtle enough to be plausible** and **shallow enough to be
applied by a text replacement**.

**The three rules the earlier probes learned, and this file inherits them:**

1. **Plant a CALL, not an import.** An imported-but-uncalled function computes nothing.
2. **The mutation must still parse and run.** A `SyntaxError` is a *false green* — the
   suite "caught" it, because a suite that cannot be collected fails.
3. **Never plant a bug in dead code.** A probe that mutates a branch the scenario never
   runs proves nothing.

**Why these six, and why these six seams.** The state-change path crosses three apps
and a worker, and each crossing is a place where a plausible mistake would leave
every *other* test green:

| Seam | The bug that would be plausible |
| --- | --- |
| `worker/propagation.py` | the change is applied but never marked propagated |
| `worker/propagation.py` | the `CANCEL` branch forgets to cancel |
| `apps/delivery/services/scheduled_sends.py` | the `KEEP` branch cancels the sends anyway |
| `apps/delivery/services/state_notices.py` | the mute is never consulted |
| `apps/delivery/services/delivery_sweep.py` | the hold does not exclude the row from the claim |
| `apps/delivery/services/state_notices.py` | a notice is raised for every kind, terminal or not |

**Each seam is one a reader would actually write.** A `KEEP` branch that cancels the
sends is the single most likely mistake in the whole path — "sold out, so stop
nagging" reads as sensible and is exactly wrong. The mute-not-consulted bug is the
one FR-55 exists to prevent. The hold-not-excluding bug is AD-17's own race, and it
is the one no unit test can catch alone.

Run from the repo root:
    uv run --directory backend python tests/e2e/mutation_probe_state_change_e2e.py
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

#: The state-change proof and its contract file.
#:
#: **The suite is one file on purpose.** A probe that mutated the implementation and ran
#: the *whole* backend suite would pass for the wrong reason — some unrelated test would
#: go red, and the probe would look like it proved the rule when it proved nothing about
#: *this* rule. Naming the exact file makes the failure attributable.
#:
#: **The contract file is in the list too**, because two of the probes are about the
#: *contract* rather than the behaviour: the one that stops the propagation marking the
#: change propagated is caught by the reconciler's own test, and the one that breaks the
#: wall is caught by the architecture assertions.
STATE_CHANGE_SUITE = [
    "tests/e2e/test_state_change_proof.py",
    "tests/e2e/test_state_change_contract.py",
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
    does not compile is caught by the interpreter, not by the rule, and that is a false
    green.
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


# ── The six probes ───────────────────────────────────────────────────────────────────────

PROBES: list[Probe] = [
    # 1. **The propagation applies the change but never marks it propagated.**
    #
    # The bug is the real one: the work is done, and the row is left unmarked. So the
    # reconciler re-offers it forever — every five minutes, for the life of the row —
    # and the user is re-told about the same cancellation. The re-offer is *idempotent*,
    # so nothing user-visible is wrong; the damage is a job that churns on a change
    # that is finished.
    #
    # **The mutation is on the write, not on the read.** The proof asserts the row is
    # marked, and the reconciler's own test asserts the backlog drains — both go red.
    Probe(
        description="the propagation never marks the change propagated",
        path=BACKEND / "worker/propagation.py",
        edits=[
            (
                "    if result.failed == 0:\n"
                "        marked = outbox.mark_propagated(state_change_id, now=now)\n",
                "    if result.failed == 0:\n"
                "        # The planted bug: the work is done, but the row is never\n"
                "        # marked, so the reconciler re-offers it forever.\n"
                "        marked = False\n",
            ),
        ],
        suite="backend",
        note="AD-17: a change is propagated only when every affected user is done.",
    ),
    # 2. **The `CANCEL` branch forgets to cancel.**
    #
    # The bug is the real one: the personal side's `CANCEL` branch does nothing. The
    # user's saved event keeps its old start and its old version, and the conflict pair
    # the cancellation was supposed to close stays open — so the app keeps asking about
    # an overlap with an event that is not happening.
    #
    # **The mutation removes a call, not a condition.** The branch still exists and still
    # runs; it just no longer cancels. A reader would write this by accident — a branch
    # that falls through to "nothing to do" because the author thought the *send* side
    # would handle it.
    Probe(
        description="the cancellation does not cancel the saved event",
        path=BACKEND / "worker/propagation.py",
        edits=[
            (
                "    elif behaviour is LifecyclePersonalBehaviour.CANCEL:\n"
                "        cancel_saved_event(\n"
                "            event_id=change.event_id,\n"
                "            user_id=user_id,\n"
                "            new_version=change.event_version,\n"
                "            actor=PROPAGATOR,\n"
                "            now=now,\n"
                "        )\n",
                "    elif behaviour is LifecyclePersonalBehaviour.CANCEL:\n"
                "        # The planted bug: the branch runs and cancels nothing.\n"
                "        pass\n",
            ),
        ],
        suite="backend",
        note="AD-21: a cancelled event closes its pairs and leaves the personal side.",
    ),
    # 3. **The `KEEP` branch cancels the sends anyway.**
    #
    # The bug is the real one, and it is the most plausible mistake in the whole path:
    # "the event is sold out, so stop nagging about it" reads as sensible and is exactly
    # wrong. `sold_out` maps to `KEEP` because **the event still happens** — a user who
    # saved a sold-out concert still wants to be reminded to go to it. The planted bug
    # sends the user to a show they were told is sold out, by silently deleting the
    # reminder that would have told them to go.
    #
    # **The mutation flips the branch, so the `else` does the cancelling.** The `KEEP`
    # path still runs — it still re-stamps the version — but the row is also cancelled,
    # so the re-stamp is invisible: a cancelled row is terminal whatever its version says.
    Probe(
        description="the sold-out change cancels the reminder anyway",
        path=BACKEND / "apps/delivery/services/scheduled_sends.py",
        edits=[
            (
                "            for row in stale:\n"
                "                row.event_version = target.version\n"
                "                row.held_at = None\n"
                "                row.save(using=PERSONAL, "
                'update_fields=["event_version", "held_at", "updated_at"])\n'
                '                result["restamped"] += 1\n',
                "            for row in stale:\n"
                "                row.event_version = target.version\n"
                "                row.held_at = None\n"
                "                # The planted bug: a KEEP change cancels the row anyway, so\n"
                "                # the user loses the reminder for an event that still\n"
                "                # happens.\n"
                "                row.status = ScheduledSend.Status.CANCELLED\n"
                "                row.save(using=PERSONAL, "
                'update_fields=["event_version", "held_at", "status", "updated_at"])\n'
                '                result["restamped"] += 1\n',
            ),
        ],
        suite="backend",
        note="FR-55 and AD-17: sold_out is KEEP — the event still happens.",
    ),
    # 4. **The mute is never consulted.**
    #
    # The bug is the real one: the mute row exists, the user asked for silence, and the
    # notice goes out anyway. FR-55's whole promise is that a mute silences the
    # correction — and a mute that is stored but never read is a promise the system does
    # not keep.
    #
    # **The mutation removes the consultation, not the mute.** The mute machinery — the
    # API, the row, the service — is untouched, so every mute test that writes a mute
    # and reads it back stays green. Only the *use* of the mute is broken, and only a
    # journey that mutes and then waits for a change can catch it.
    Probe(
        description="the mute is never consulted",
        path=BACKEND / "apps/delivery/services/state_notices.py",
        edits=[
            (
                "        if not terminal and is_muted(user_id=user_id, event_id=event_id):\n"
                "            return False\n",
                "        if False and not terminal and is_muted(\n"
                "            user_id=user_id, event_id=event_id\n"
                "        ):\n"
                "            return False\n",
            ),
        ],
        suite="backend",
        note="FR-55: a mute silences the correction about that event.",
    ),
    # 5. **The hold does not exclude the row from the claim.**
    #
    # The bug is the real one: the sweep holds a send because the catalog has moved
    # ahead, and then the *next* sweep claims it anyway and sends it. The user is told
    # about the event's new time by a reminder that carries the **old** one — which is
    # the exact contradiction the propagation exists to prevent, and the reason the
    # sweep's guard holds rather than sends.
    #
    # **This is AD-17's race, and it is the one no unit test can catch alone.** A unit
    # test of `hold_stale_sends` proves the row is held. A unit test of `claim_due_sends`
    # proves the claim filters on what it filters on. Only a test that holds a row and
    # *then claims again* proves that the hold is what stops it — and that is the
    # hold-and-release journey.
    Probe(
        description="the hold does not exclude the row from the next claim",
        path=BACKEND / "apps/delivery/services/delivery_sweep.py",
        edits=[
            (
                "            .filter(held_at__isnull=True)\n",
                "            # The planted bug: the hold no longer excludes the row, so the\n"
                "            # next sweep claims and sends a send whose event has moved.\n",
            ),
        ],
        suite="backend",
        note="AD-17: the sweep holds a send whose catalog version is newer.",
    ),
    # 6. **A notice is raised for every kind, terminal or not.**
    #
    # The bug is the real one, and it is the mirror of probe 4: the terminal exception
    # is gone, so a **muted** event's cancellation is silenced along with everything
    # else. FR-55 says a mute silences the correction — but a cancellation is the one
    # thing the user must hear about, because the event they were going to is not
    # happening.
    #
    # **The mutation removes the `not terminal` condition**, so the terminal change is
    # treated like every other kind and a mute silences it. The mute journey asserts
    # exactly this, which is why the probe is the mirror of the one above rather than a
    # second copy of it.
    Probe(
        description="the terminal change is silenced by the mute",
        path=BACKEND / "apps/delivery/services/state_notices.py",
        edits=[
            (
                "        if not terminal and is_muted(user_id=user_id, event_id=event_id):\n"
                "            return False\n",
                "        if is_muted(user_id=user_id, event_id=event_id):\n"
                "            # The planted bug: the terminal exception is gone, so a mute\n"
                "            # silences a cancellation too.\n"
                "            return False\n",
            ),
        ],
        suite="backend",
        note="FR-55: a mute silences the correction, but never a terminal change.",
    ),
]


def run_backend_suite() -> tuple[int, str]:
    """Run the state-change suite. Returns `(returncode, output)`."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *STATE_CHANGE_SUITE, "-q", "--no-header"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def run_frontend_suite() -> tuple[int, str]:
    """Run the frontend's state-change surfaces. Returns `(returncode, output)`."""
    # The full path, not "pnpm": a partial path runs whatever `pnpm` is first on PATH (S607).
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        return 127, "pnpm is not on PATH"
    result = subprocess.run(
        [
            pnpm,
            "vitest",
            "run",
            "components/state/notice-strip.test.tsx",
            "components/state/detail-notice-banner.test.tsx",
        ],
        cwd=BACKEND.parent / "frontend",
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
    return ProbeResult(probe, "ok", _tail(output))


def _tail(output: str) -> str:
    """The last meaningful line of a suite's output."""
    lines = [line for line in output.strip().splitlines() if line.strip()]
    return lines[-1] if lines else "the suite failed"


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

    print(f"All {len(results)} state-change probes were caught by the suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
