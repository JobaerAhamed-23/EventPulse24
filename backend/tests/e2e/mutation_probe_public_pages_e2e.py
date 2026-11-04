#!/usr/bin/env python
"""Mutation probes for the public-pages proof of run-eventpulse24-024's last item.

**What this file is.** The acceptance criterion says: *"Each assertion is shown to fail
when its behaviour is removed, recorded in the walkthrough."* This file is the mechanism:
**apply one real bug to the implementation, run the suite that is supposed to catch it,
and require that at least one test fails.** A probe that passes the suite means the
tests do not prove that rule — and a test that cannot fail is not a test.

**The bug each probe plants is a real bug, not a syntax error.** A probe that broke the
file so badly the suite failed to collect would "pass" the harness while proving
nothing — so each mutation still parses, still runs, and still produces a *wrong
answer*. The point of the technique is that the bug must be **subtle enough to be
plausible** and **shallow enough to be applied by a text replacement**.

**The three rules the earlier runs learned, and this file inherits them:**

1. **Plant a CALL, not an import.** An imported-but-uncalled function computes nothing.
2. **The mutation must still parse and run.** A `SyntaxError` is a *false green* — the
   suite "caught" it, because a suite that cannot be collected fails.
3. **Never plant a bug in dead code.** A probe that mutates a branch the scenario never
   runs proves nothing.

**Every probe names the exact suite that must go red.** A probe that mutated the
implementation and ran the *whole* backend suite would pass for the wrong reason — some
unrelated test would go red, and the probe would look like it proved the rule when it
proved nothing about *this* rule.

**The probes come in pairs where the promise has two halves.** The `in_review`
invisibility is carried by three separate mechanisms — the slug read refuses it, the
city listing filters it, and the feed filters it — and **one probe per mechanism**
because each is a separate line of code that could be broken independently. A single
probe on the slug read would prove nothing about the feed.

Run from the repo root:
    uv run --directory backend python tests/e2e/mutation_probe_public_pages_e2e.py
"""

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FRONTEND = REPO / "frontend"

#: The backend proof. Every backend probe below is a mutation that **this** file must
#: catch, because every backend probe targets a rule the proof asserts.
#:
#: **The suite is one file on purpose.** A probe that mutated the implementation and ran
#: the *whole* backend suite would pass for the wrong reason — some unrelated test would
#: go red, and the probe would look like it proved the rule when it proved nothing about
#: *this* rule. Naming the exact file makes the failure attributable.
PROOF_SUITE = [
    "tests/e2e/test_public_pages_proof.py",
]

#: The backend contract file — the structural properties (no session, the import walls).
CONTRACT_SUITE = [
    "tests/e2e/test_public_pages_contract.py",
]

#: The frontend crawl proof.
CRAWL_SUITE = ["tests/public-crawl-proof.test.tsx"]


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
    #: The suite that must fail: `backend`, `backend-contract` or `frontend`.
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


# ── The probes ────────────────────────────────────────────────────────────────────────

PROBES: list[Probe] = [
    # 1. **The stale fit is served.** The staleness rule's whole claim.
    #
    # The bug is the real one: the staleness check **always says yes**. A fit row
    # records the Event version it was computed from, and a row whose version no longer
    # matches describes an event that no longer exists — so it is skipped. With the
    # check neutered, the city page serves a fit describing a *different* version of the
    # event: a score and a tag set that no longer mean anything.
    #
    # **The mutation is on the live comparison, in Python** — the read loads the rows
    # and compares the two versions in Python, because SQL cannot compare two joined
    # columns in one `WHERE`.
    Probe(
        description="a stale Event Fit is served instead of skipped",
        path=BACKEND / "apps/ingestion/event_fit/reads.py",
        edits=[
            (
                "    return row.event_version == row.event.event_version\n",
                "    # The planted bug: every fit is treated as current, so a fit that\n"
                "    # describes an older version of its event is served anyway.\n"
                "    return True\n",
            ),
        ],
        suite="backend",
        note="AD-10: a stale fit is absent from the city page, never rendered wrong.",
    ),
    # 2. **The stale fit is counted.** The count and the listing, separately.
    #
    # The city page's *qualifying count* is computed by its own load, in
    # `city_read._current_rows`, with its own staleness comparison — a second
    # implementation of the same rule. So it can be broken independently of the listing,
    # and the consequence is worse: a city would **claim to qualify** on a count that
    # includes a fit the listing would not show.
    Probe(
        description="a stale Event Fit is counted towards the city's threshold",
        path=BACKEND / "apps/ingestion/services/city_read.py",
        edits=[
            (
                "    return [row for row in rows "
                "if row.event_version == row.event.event_version]\n",
                "    # The planted bug: the count keeps the stale rows, so a city can\n"
                "    # qualify on events its own listing would not show.\n"
                "    return list(rows)\n",
            ),
        ],
        suite="backend",
        note="FR-27: the threshold is a count, and the count is computed by the "
        "listing's own filters.",
    ),
    # 3. **The `in_review` event is at its own slug.** The slug read's whole claim.
    #
    # The bug is the real one: the slug read **stops refusing** unpublished rows. An
    # `in_review` event is not publicly listed (AD-6, AD-8) — it reads as absent,
    # exactly as an unknown slug does, because a 403 would confirm that it exists.
    Probe(
        description="an in_review event is addressable at its own slug",
        path=BACKEND / "apps/ingestion/services/catalog_read.py",
        edits=[
            (
                "    if event.publication_status != Event.PublicationStatus.PUBLISHED:\n",
                "    if False and event.publication_status != Event.PublicationStatus.PUBLISHED:\n",
            ),
        ],
        suite="backend",
        note="AD-6, AD-8: an unpublished event reads as absent, exactly as an unknown slug does.",
    ),
    # 4. **The `in_review` event is in the URL feed.** The feed's own filter.
    #
    # The feed is the sitemap's source, so an `in_review` event in the feed is a URL in
    # the sitemap that a crawler would fetch — and the fetch would answer a page the
    # site says does not exist. **The feed has its own filter**, separate from the slug
    # read's, so it can be broken independently.
    Probe(
        description="an in_review event leaks into the URL feed",
        path=BACKEND / "apps/ingestion/services/url_feed_read.py",
        edits=[
            (
                "        .filter(publication_status=Event.PublicationStatus.PUBLISHED)\n"
                "        .exclude(status=Event.Status.SUPERSEDED)\n",
                "        .exclude(status=Event.Status.SUPERSEDED)\n",
            ),
        ],
        suite="backend",
        note="The sitemap lists exactly the URLs the site serves.",
    ),
    # 5. **The `in_review` event is on the city page.** The listing's own filter.
    #
    # **The third of the three mechanisms.** The city page's listing filters on
    # `publication_status` in its own queryset — a fourth place the promise is
    # implemented, and a fourth place it could be broken.
    Probe(
        description="an in_review event leaks onto the city page",
        path=BACKEND / "apps/ingestion/services/city_read.py",
        edits=[
            (
                "        .filter(event__publication_status=Event.PublicationStatus.PUBLISHED)\n"
                "        .exclude(event__status=Event.Status.SUPERSEDED)\n",
                "        .exclude(event__status=Event.Status.SUPERSEDED)\n",
            ),
        ],
        suite="backend",
        note="AD-6, AD-8: an unreviewed event is not publicly listed.",
    ),
    # 6. **The revalidation signal names only the event's own page.**
    #
    # The bug is the real one: the city page is **not** named. The city's listing still
    # shows the cancelled event, so the cached city page keeps showing it — and the
    # signal that was supposed to fix it never fires. This is the intent's central
    # freshness promise, and it is broken by *one missing path*.
    Probe(
        description="the revalidation signal drops the city's path",
        path=BACKEND / "domain/revalidation.py",
        edits=[
            (
                "    if facts.is_public or facts.is_superseded:\n"
                "        paths.extend(facts.city_paths())\n",
                "    if False and (facts.is_public or facts.is_superseded):\n"
                "        paths.extend(facts.city_paths())\n",
            ),
        ],
        suite="backend",
        note="FR-26, FR-27: one change, every path it made stale — the event's page "
        "and the city's.",
    ),
    # 7. **The structured data drops the cancelled state.**
    #
    # The bug is the real one: the JSON-LD **carries no `eventStatus`** for a cancelled
    # event. The visible page would still say "Cancelled" — but a crawler reads the
    # structured data, and a search result would show a cancelled concert as one that is
    # still going ahead. **This is AD-12's drift, and the proof asserts the two halves
    # together precisely so it can be caught.**
    Probe(
        description="the structured data drops the cancelled event's status",
        path=BACKEND / "domain/schema_org.py",
        edits=[
            (
                "    event_status = SCHEMA_ORG_EVENT_STATUS.get(status)\n"
                "    if event_status is not None:\n"
                '        event["eventStatus"] = event_status\n',
                "    # The planted bug: the structured data says nothing about the\n"
                "    # lifecycle, so a cancelled event reads as one that is still on.\n"
                "    event_status = None\n"
                "    if event_status is not None:\n"
                '        event["eventStatus"] = event_status\n',
            ),
        ],
        suite="backend",
        note="AD-12: the structured data and the rendered page are emitted from the "
        "same data, so they cannot disagree.",
    ),
    # 8. **A public read forwards the session's cookies.** The frontend half.
    #
    # The bug is the real one: the public event read **forwards the visitor's cookie
    # jar**. The page would still render, and every existing test that logs in first
    # would still pass — but the first requester would bake their session into a cache
    # that is meant to hold one copy for everybody.
    #
    # **The mutation is on the live call**, and the `sessionHeaders` import is planted
    # with it so the file still parses — a half-planted bug that does not compile is
    # caught by the interpreter, which is a false green.
    #
    # **A frontend bug is caught by a frontend test.** The backend contract file
    # asserts the *source*; the crawl proof asserts the *render*. This probe names the
    # contract file, because that is the suite whose claim is "the public reads carry
    # no session".
    Probe(
        description="a public read forwards the visitor's cookies",
        path=FRONTEND / "lib/public-event-read.ts",
        edits=[
            (
                'import { api } from "@/lib/backend-client";\n',
                'import { api } from "@/lib/backend-client";\n'
                'import { sessionHeaders } from "@/lib/session";\n',
            ),
            (
                '      const response = await api.GET("/api/catalog/events/by-slug/{slug}", {\n'
                "        params: { path: { slug } },\n"
                "      });\n",
                '      const response = await api.GET("/api/catalog/events/by-slug/{slug}", {\n'
                "        params: { path: { slug } },\n"
                "        headers: await sessionHeaders(),\n"
                "      });\n",
            ),
        ],
        suite="backend-contract",
        note="AD-12: a public read carries no session, so a cached copy can hold nothing personal.",
    ),
    # 9. **The public page's JSON-LD leaves the markup.** The frontend half.
    #
    # The bug is the real one: the JSON-LD is **not rendered into the server's
    # markup**. A crawler that does not execute JavaScript sees nothing — which defeats
    # the entire point of the structured data, and which no DOM test could see.
    Probe(
        description="the JSON-LD is not in the server-rendered markup",
        path=FRONTEND / "components/public-event/public-event-page.tsx",
        edits=[
            (
                '        type="application/ld+json"\n',
                '        type="application/ld+json"\n        hidden\n',
            ),
            (
                "        dangerouslySetInnerHTML={{\n"
                "          __html: serializeJsonLd(page.schema_org),\n"
                "        }}\n",
                '        dangerouslySetInnerHTML={{\n          __html: "",\n        }}\n',
            ),
        ],
        suite="frontend",
        note="FR-26, AD-12: the structured data is in the server-rendered HTML — a "
        "crawler reads bytes, not a hydrated tree.",
    ),
]


def run_backend_suite(paths: list[str]) -> tuple[int, str]:
    """Run a backend suite. Returns `(returncode, output)`."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q", "--no-header"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
        env=_backend_env(),
    )
    return result.returncode, result.stdout + result.stderr


def run_frontend_suite() -> tuple[int, str]:
    """Run the frontend crawl proof. Returns `(returncode, output)`."""
    # The full path, not "pnpm": a partial path runs whatever `pnpm` is first on PATH (S607).
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        return 127, "pnpm is not on PATH"
    result = subprocess.run(
        [pnpm, "vitest", "run", *CRAWL_SUITE],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def _backend_env() -> dict[str, str]:
    """The backend's environment, with the database role the test database needs."""
    import os

    env = dict(os.environ)
    env.setdefault("DJANGO_DB_ROLE", "owner")
    return env


def run_suite(suite: str) -> tuple[int, str]:
    """Run the named suite."""
    if suite == "frontend":
        return run_frontend_suite()
    if suite == "backend-contract":
        return run_backend_suite(CONTRACT_SUITE)
    return run_backend_suite(PROOF_SUITE)


def _is_a_test_failure(code: int, output: str) -> bool:
    """**Did the suite fail a *test*, rather than fail to run at all?**

    **This is the difference between a probe that proved something and a false green.**
    The harness's own second rule says a `SyntaxError` is a false green — the suite
    "caught" it only because it could not be collected. **A non-zero exit code alone
    does not say which happened**, and a probe that counted an unusable run as a catch
    would report success while proving nothing.

    So the exit code is read *and* the output is inspected:

    - **pytest's exit codes are specific.** `0` is a pass; `1` is *tests failed*;
      `2` is interrupted; `3` is an internal error; `4` is a usage error; and `5` is
      **no tests collected** — which is exactly the "the suite could not run" case.
      So only `1` counts, and the output must show a failure summary rather than an
      error summary.
    - **vitest's exit codes are not specific**, so the output carries the answer: a
      collection error says *"Failed to load"* / *"Error:"* and reports no failed
      test count, whereas a real failure reports `N failed`.

    **A suite that ran no tests cannot have caught anything**, so it is a `fail` — the
    probe did not prove the rule.
    """
    plain = re.sub(r"\x1b\[[0-9;]*m", "", output)

    if "Failed to load" in plain or "Failed to resolve import" in plain:
        return False

    if code == 1:
        # **A failure summary, not an error summary.** pytest prints `1 failed, 33
        # passed`; a collection error prints `1 error` and no failure count.
        if re.search(r"\d+ failed", plain):
            return True
        return False

    return False


def run_probe(probe: Probe) -> ProbeResult:
    """Apply the bug, run the suite, and put the file back.

    **The file is always restored**, whether the suite failed, passed, or the process
    died — the `finally` is not conditional. A probe that leaves a broken file behind
    would make every probe after it meaningless.

    **Every edit is checked before any is applied.** A probe with two edits where only
    one pattern matches would otherwise plant half a bug — and a half-planted bug that
    does not compile is caught by the interpreter, which is a false green.

    **And the run must have failed a *test*.** A suite that could not be collected, or
    that collected nothing, has not caught anything — so the outcome is `fail`, not
    `ok`. See `_is_a_test_failure`.
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
    if not _is_a_test_failure(code, output):
        return ProbeResult(probe, "fail", "the suite did not fail a test — it could not run")
    return ProbeResult(probe, "ok", _tail(output))


def _tail(output: str) -> str:
    """The most meaningful line of a suite's output.

    **The ANSI escapes are stripped**, because vitest colours its output and the raw
    line is unreadable in a walkthrough — and the walkthrough quotes this line.

    **And the last line is not the best line.** Vitest ends a failing run with a box
    drawn in Unicode box-drawing characters, which says nothing about what happened. So
    the summary line is preferred when there is one — pytest's `N failed, M passed` and
    vitest's `Test Files N failed` — and the box is the last resort.
    """
    plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    lines = [line for line in plain.strip().splitlines() if line.strip()]
    if not lines:
        return "the suite failed"
    for line in reversed(lines):
        if re.search(r"\d+ failed.*\d+ passed", line) or line.startswith("Test Files"):
            return line.strip()
    return lines[-1].strip()


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

    print(f"All {len(results)} public-pages probes were caught by the suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
