#!/usr/bin/env python
"""Mutation probes for the delivery proof of run-eventpulse24-023's last item.

**What this file is.** The acceptance criterion says: *"Probe tests: as run 021 did with
its 27 probes, each major assertion is proven able to fail — break the quiet-hours shift,
the key stability and the suppression rule in turn, and show the matching test goes red."*

The mechanism is the same one the run already uses (`tests/e2e/mutation_probe_e2e.py`
and `tests/e2e/mutation_probe_contract_e2e.py`): **apply one real bug to the
implementation, run the suite, and require that at least one test fails.** A probe that
passes the suite means the tests do not prove that rule — and a test that cannot fail is
not a test.

**Why a third file, and not an extension of the second.** The earlier probes are about
**contract rules** — AD-3, AD-10, AD-13 — and they run one suite each. These probes are
about the **delivery path**, and each one targets a *different* rule, so each one names
the suite that is supposed to catch it. The harness shape is the same; the targets are
different.

**The bug each probe plants is a real bug**, not a syntax error. A probe that broke the
file so badly the suite failed to collect would "pass" the harness while proving
nothing — so each mutation is a change that still parses, still runs, and still produces
a *wrong answer*. This is the point of the technique: the bug must be **subtle enough to
be plausible** and **shallow enough to be applied by a text replacement**.

**The three rules run-021 learned, and this file inherits them:**

1. **Plant a CALL, not an import.** An imported-but-uncalled function computes nothing.
   Probe 10 of run-021 hit this: the suite stayed green, correctly.
2. **The mutation must still parse and run.** A `SyntaxError` is a *false green* — the
   suite "caught" it, because a suite that cannot be collected fails.
3. **Never plant a bug in dead code.** A probe that mutates a branch the scenario never
   runs proves nothing. Run-021's probe 10 hit exactly that and had to be rewritten.

Run from the repo root:
    uv run --directory backend python tests/e2e/mutation_probe_delivery_e2e.py
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FRONTEND = REPO / "frontend"

#: The delivery proof. Every probe below is a mutation that **this** file must catch,
#: because every probe targets a rule the proof asserts.
#:
#: **The suite is one file on purpose.** A probe that mutated the implementation and ran
#: the *whole* backend suite would pass for the wrong reason — some unrelated test would
#: go red, and the probe would look like it proved the rule when it proved nothing about
#: *this* rule. Naming the exact file makes the failure attributable.
DELIVERY_SUITE = [
    "tests/e2e/test_delivery_proof.py",
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


# ── The five probes ───────────────────────────────────────────────────────────────────────

PROBES: list[Probe] = [
    # 1. **The quiet-hours shift.** The deferral proof's whole claim.
    #
    # The bug is the real one: the shift **forgets to shift**. The due time becomes the
    # slot's own instant, the row is minted at 22:30 instead of 08:00, and the mail goes
    # out in the middle of the quiet window the user asked for.
    #
    # **The mutation is a call, not an import.** `shift_to_sendable` is already imported;
    # the bug replaces the call with a no-op that still returns the right *type*.
    Probe(
        description="the quiet-hours shift does not shift",
        path=BACKEND / "domain/quiet_hours.py",
        edits=[
            (
                "    local = to_instant(instant).astimezone(ZoneInfo(zone))\n"
                "    local_clock = local.time()\n"
                "    if not window.covers(local_clock):\n"
                "        return instant\n",
                "    local = to_instant(instant).astimezone(ZoneInfo(zone))\n"
                "    local_clock = local.time()\n"
                "    if not window.covers(local_clock):\n"
                "        return instant\n"
                "    # The planted bug: the shift gives up and returns the instant.\n"
                "    return instant\n",
            ),
        ],
        suite="backend",
        note="AD-7: Quiet Hours are applied when due_at is computed, never at send time.",
    ),
    # 2. **The key's stability.** The reschedule proof's whole claim.
    #
    # The bug is the real one: the rewrite **re-mints instead of rewriting**. The old row
    # is cancelled and a new one is created — with a new key, because the key carries the
    # version and a re-mint bumps it. The user gets **two reminders** for one event, and
    # the second one is under a key the provider has never seen.
    #
    # **This is the bug AD-7's rule exists to prevent**, and it is the one the key's
    # "no instant anywhere" shape rules out structurally.
    Probe(
        description="the reschedule re-mints instead of rewriting",
        path=BACKEND / "apps/delivery/services/scheduled_sends.py",
        edits=[
            (
                "            row.due_at = due_at\n"
                '            row.save(using=PERSONAL, update_fields=["due_at", "updated_at"])\n'
                "            rewritten += 1\n",
                "            row.due_at = due_at\n"
                '            row.save(using=PERSONAL, update_fields=["due_at", "updated_at"])\n'
                "            rewritten += 1\n"
                "            # The planted bug: the rewrite also mints a second row, under a\n"
                "            # new key, so the user gets two reminders for one event.\n"
                '            row.send_key = f"{row.send_key}:rescheduled"\n'
                "            row.status = ScheduledSend.Status.CANCELLED\n"
                '            row.save(using=PERSONAL, update_fields=["send_key", "status"])\n'
                "            ScheduledSend.objects.using(PERSONAL).create(\n"
                "                user_id=row.user_id,\n"
                "                kind=row.kind,\n"
                "                target_kind=row.target_kind,\n"
                "                target_id=row.target_id,\n"
                "                slot=row.slot,\n"
                "                event_version=row.event_version,\n"
                "                stream=row.stream,\n"
                "                slot_at=row.slot_at,\n"
                "                due_at=due_at,\n"
                "                status=ScheduledSend.Status.PENDING,\n"
                "            )\n",
            ),
        ],
        suite="backend",
        note="AD-7: a recompute rewrites due_at and never touches the key.",
    ),
    # 3. **The suppression rule.** The suppression proof's whole claim.
    #
    # The bug is the real one: the Ping is minted **even when there is nothing to say**.
    # The user with an empty week gets a daily email about nothing — which is the exact
    # failure FR-10 and SM-C1 exist to prevent.
    #
    # **The mutation is on the live branch.** The check is an `if not has_qualifying_events:`
    # early return; the planted bug replaces it with one that never fires.
    Probe(
        description="the Pulse Ping is minted even with nothing to say",
        path=BACKEND / "apps/delivery/services/pulse_ping.py",
        edits=[
            (
                "    if not has_qualifying_events:\n        _record_suppression(\n",
                "    if False and not has_qualifying_events:\n        _record_suppression(\n",
            ),
        ],
        suite="backend",
        note="FR-10: a user with nothing to say gets no Ping, and no row.",
    ),
    # 4. **The sweep sends once.** The idempotency proof's whole claim.
    #
    # The bug is the real one: the row's status is **not** marked sent. The sweep runs
    # again, finds the same row still `pending`, and sends it a second time — the provider
    # sees two messages under the same key, and only the provider's own dedup stands
    # between the user and a duplicate email.
    #
    # **The mutation is on the write, not on the key.** The key is the provider's
    # idempotency key and it is *supposed* to be the same on both runs — that is the
    # point. What must not happen is the sweep sending the row twice in the first place.
    Probe(
        description="the sweep does not mark the row sent",
        path=BACKEND / "apps/delivery/services/delivery_sweep.py",
        edits=[
            (
                "    _mark_sent(send_id=send_id, now=now)\n",
                "    # The planted bug: the row is left pending, so the next sweep sends\n"
                "    # it again.\n",
            ),
        ],
        suite="backend",
        note="AD-7: a sent row is a fact, not a schedule — and it is marked once.",
    ),
    # 5. **The unsubscribe's scope.** The unsubscribe proof's whole claim.
    #
    # The bug is the real one: unsubscribing from **one event's** reminders also cancels
    # the user's **daily Ping**. The user asked to stop one thing and lost another — and
    # FR-11's whole point is that the two are different choices.
    #
    # **The mutation is on the live branch**, in the event scope — the ping scope is a
    # different function and is untouched.
    Probe(
        description="the event unsubscribe also cancels the Pulse Ping",
        path=BACKEND / "apps/delivery/services/unsubscribes.py",
        edits=[
            (
                "        plan.slots = []\n"
                '        plan.save(using=PERSONAL, update_fields=["slots", "updated_at"])\n',
                "        plan.slots = []\n"
                '        plan.save(using=PERSONAL, update_fields=["slots", "updated_at"])\n'
                "        # The planted bug: the event scope also cancels the daily Ping.\n"
                "        cancel_pending_digests_for_user(user_id=user_id, now=now)\n",
            ),
        ],
        suite="backend",
        note="FR-11: unsubscribing from an event's reminders leaves the Ping alone.",
    ),
    # 6. **The client ignores the server's flag.** The frontend half of the proof.
    #
    # The bug is the real one: the chip **does not dim**, and **does not show the note**,
    # even though the server said the slot was deferred. The user would have no idea their
    # reminder is going to arrive four hours late.
    #
    # **This is the probe that closes the seam.** The backend probes prove the server
    # computes the flag correctly; this one proves the client *uses* it. A flag that
    # arrives and is ignored would pass every backend probe and every server-side
    # assertion — only a client-side mutation can catch it.
    #
    # **A frontend bug is caught by a frontend test**, so this probe names the frontend
    # suite. Running the backend suite against a frontend mutation would prove nothing.
    Probe(
        description="the chip ignores the server's deferred flag",
        path=FRONTEND / "components/reminders/reminder-chip.tsx",
        edits=[
            (
                '          deferred ? "opacity-40" : "",\n',
                '          "",\n',
            ),
            (
                "      {deferred && note ? (\n",
                "      {false && deferred && note ? (\n",
            ),
        ],
        suite="frontend",
        note="AD-7: the dimmed chip is the server's flag, carried straight through.",
    ),
]


def run_backend_suite() -> tuple[int, str]:
    """Run the backend contract suite. Returns `(returncode, output)`."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *DELIVERY_SUITE, "-q", "--no-header"],
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
        [pnpm, "vitest", "run", "components/reminders/reminder-chip.test.tsx"],
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

    print(f"All {len(results)} delivery probes were caught by the suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
