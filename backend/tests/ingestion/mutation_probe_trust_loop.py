#!/usr/bin/env python
"""Mutation probes for the trust loop (run-eventpulse24-026).

Covers `event-rejection-state` (1-11), `review-intake-and-backfill` (12-16),
`event-report-api` (17-21) and `editorial-review-commands` (22-26).

Each probe applies one real bug to the implementation, runs the rejection tests, and checks
that at least one test fails. A probe the suite survives means the tests don't actually prove
that rule, and the implementation or the test has to change.

**Why this file matters more than usual here.** The design's central claim is that a reject
needs *two* writes and that neither works alone. A suite that only asserted "the event is
hidden" would pass against an implementation that leaves every saver's reminders firing —
which is the exact bug the design exists to prevent. Probes 3 and 4 are that claim, made
falsifiable.

Run from the repo root:
    uv run --directory backend python tests/ingestion/mutation_probe_trust_loop.py
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
CATALOG_READ = BACKEND / "apps/ingestion/services/catalog_read.py"
EDITORIAL = BACKEND / "apps/ingestion/services/editorial_state.py"
EVENT_WRITES = BACKEND / "apps/ingestion/services/event_writes.py"
CONSTANTS = BACKEND / "shared/constants.py"
INGEST_ITEM = BACKEND / "apps/ingestion/services/ingest_item.py"
REVIEW_INTAKE = BACKEND / "apps/ingestion/services/review_intake.py"
REVIEW_QUEUE = BACKEND / "apps/ingestion/services/review_queue.py"
EVENT_REPORTS = BACKEND / "apps/personalization/services/event_reports.py"
PERSONAL_API = BACKEND / "apps/personalization/api.py"
EDITORIAL_REVIEW = BACKEND / "apps/ingestion/services/editorial_review.py"
NOTICES = BACKEND / "domain/notices.py"

ABSENCE = ["tests/ingestion/test_rejected_absence.py"]
REENTRY = ["tests/ingestion/test_rejected_reentry.py"]
COMMANDS = ["tests/ingestion/test_editorial_state.py"]
PROPAGATION = ["tests/worker/test_propagation_rejection.py"]
E2E = ["tests/e2e/test_rejection_proof.py"]
MAPS = ["tests/worker/test_propagation_tasks.py"]
INTAKE = ["tests/ingestion/test_review_intake.py"]
BACKFILL = ["tests/ingestion/test_backfill_review_items.py"]
REPORTS = ["tests/personalization/test_event_reports.py"]
REPORT_API = ["tests/personalization/test_event_report_api.py"]
EDITORIAL_TESTS = ["tests/ingestion/test_editorial_review.py"]
LOCK = ["tests/ingestion/test_editorial_lock.py"]

PROBES = [
    (
        "1. the catalog read's publication filter is dropped (a rejected event is listed again)",
        CATALOG_READ,
        "        .filter(publication_status=Event.PublicationStatus.PUBLISHED)\n",
        "",
        ABSENCE + E2E,
    ),
    (
        "2. the public page serves a rejected event by slug",
        CATALOG_READ,
        "    if event.publication_status != Event.PublicationStatus.PUBLISHED:",
        "    if False:",
        ABSENCE + E2E,
    ),
    (
        "3. the reject stops writing a state change (the event hides, reminders keep firing)",
        EDITORIAL,
        "        change = apply_publication_change(\n"
        "            event=event,\n"
        "            publication_status=Event.PublicationStatus.REJECTED,\n"
        "            kind=EventStateChange.Kind.DELISTED,\n"
        "            actor=actor,\n"
        "            now=now,\n"
        "        )",
        "        Event.objects.using(CATALOG).filter(pk=event.pk).update(\n"
        "            publication_status=Event.PublicationStatus.REJECTED\n"
        "        )\n"
        "        change = None",
        PROPAGATION + E2E,
    ),
    (
        "4. delisted keeps the sends instead of cancelling them",
        CONSTANTS,
        '    "delisted": LifecycleSendBehaviour.CANCEL,',
        '    "delisted": LifecycleSendBehaviour.KEEP,',
        PROPAGATION + E2E,
    ),
    (
        "5. the notice suppression is dropped (a reject emails the user a lie)",
        NOTICES,
        "    if change_kind in UNNOTIFIED_KINDS:\n        return False\n",
        "",
        PROPAGATION + E2E,
    ),
    (
        "6. the ingestion freeze is dropped (the next poll republishes a rejected event)",
        EVENT_WRITES,
        "        if stored is not None and stored.publication_status "
        '== Event.PublicationStatus.REJECTED:\n            del values["publication_status"]\n',
        "",
        REENTRY,
    ),
    (
        "7. the freeze is applied on the lifecycle path but not the detail path",
        EVENT_WRITES,
        "        **incoming.gating(stored=event),",
        "        **incoming.gating(),",
        REENTRY,
    ),
    (
        "8. the version is not bumped (no version for the outbox row to carry)",
        EVENT_WRITES,
        "    version = event.event_version + 1",
        "    version = event.event_version",
        COMMANDS + PROPAGATION + E2E,
    ),
    (
        "9. the reject is no longer idempotent (a second reject re-notifies every saver)",
        EDITORIAL,
        "        if event.publication_status == Event.PublicationStatus.REJECTED:\n"
        "            return PublicationResult(event=event, change=None, applied=False)\n",
        "",
        COMMANDS,
    ),
    (
        "10. a job may reject or reinstate (AD-14 attribution lost)",
        EDITORIAL,
        "    if actor.kind is not ActorKind.USER:",
        "    if False:",
        COMMANDS,
    ),
    (
        "11. delisted closes the user's conflict pairs (the AD-21 defect walked into)",
        CONSTANTS,
        '    "delisted": LifecyclePersonalBehaviour.NONE,',
        '    "delisted": LifecyclePersonalBehaviour.CANCEL,',
        PROPAGATION + MAPS,
    ),
    (
        "12. a new event in review gets no ticket (the stranding bug restored)",
        INGEST_ITEM,
        "        sync_review_item(event=event, actor=run.actor, now=run.now)\n"
        '        return ["new", *_flags(incoming)]',
        '        return ["new", *_flags(incoming)]',
        INTAKE,
    ),
    (
        "13. the ticket is raised best-effort, outside the write's failure path",
        INGEST_ITEM,
        "        sync_review_item(event=event, actor=run.actor, now=run.now)\n"
        '        return ["new", *_flags(incoming)]',
        "        try:\n"
        "            sync_review_item(event=event, actor=run.actor, now=run.now)\n"
        "        except Exception:\n"
        "            pass\n"
        '        return ["new", *_flags(incoming)]',
        INTAKE,
    ),
    (
        "14. re-gating out of review no longer withdraws the ticket",
        REVIEW_INTAKE,
        "    withdraw_review_item(event=event, now=moment)\n    return None",
        "    return None",
        INTAKE,
    ),
    (
        "15. a published-but-flagged event raises a ticket after all (D1 reversed)",
        REVIEW_INTAKE,
        "    if event.publication_status == Event.PublicationStatus.IN_REVIEW:",
        "    if event.publication_status == Event.PublicationStatus.IN_REVIEW or "
        "event.tz_review_pending:",
        INTAKE,
    ),
    (
        "16. the backfill stops excluding already-ticketed events (idempotence lost)",
        REVIEW_INTAKE,
        '        .exclude(pk__in=ticketed.values("event_id"))\n',
        "",
        BACKFILL,
    ),
    (
        "17. a report is raised as the reporter (AD-3: their id reaches a catalog audit row)",
        REVIEW_QUEUE,
        'actor=Actor.system("event_report"),',
        "actor=Actor.user(event_id),",
        REPORTS,
    ),
    (
        "18. the throttle is checked after the idempotence shortcut (a repeat is free)",
        EVENT_REPORTS,
        "    decision = get_throttle_port().check(",
        "    decision = _SKIP_THROTTLE or get_throttle_port().check(",
        REPORTS,
    ),
    (
        "19. the report is not stamped, so the reconciler raises it again (double counting)",
        EVENT_REPORTS,
        "        EventReport.objects.using(PERSONAL).filter(pk=report.pk, "
        "raised_at__isnull=True).update(\n            raised_at=now\n        )",
        "        pass",
        REPORTS,
    ),
    (
        "20. the visibility check is dropped (the endpoint probes hidden events)",
        PERSONAL_API,
        "    get_public_event(event_id=body.event_id, now=now)\n    report_event(",
        "    report_event(",
        REPORT_API,
    ),
    (
        "21. the response leaks the queue state back to the client",
        BACKEND / "apps/personalization/schemas.py",
        "    reported: bool = True\n    category: EventReportCategory",
        '    reported: bool = True\n    category: EventReportCategory\n    report_id: str = "x"',
        REPORT_API,
    ),
    (
        "22. a verdict closes only the item the editor clicked, not the event's others",
        EDITORIAL_REVIEW,
        "    open_items = ReviewItem.objects.using(CATALOG).filter(\n"
        "        event_id=event.pk, status=ReviewItem.Status.OPEN\n    )",
        "    open_items = ReviewItem.objects.using(CATALOG).filter(\n"
        "        event_id=event.pk, status=ReviewItem.Status.OPEN\n    )[:1]",
        EDITORIAL_TESTS,
    ),
    (
        "23. the stale-version guard is dropped (an editor overwrites an unseen update)",
        EDITORIAL_REVIEW,
        "    if expected_event_version is not None and event.event_version "
        "!= expected_event_version:",
        "    if False:",
        EDITORIAL_TESTS,
    ),
    (
        "24. a system actor may record an editorial verdict (AD-14 lost)",
        EDITORIAL_REVIEW,
        "    if actor.kind is not ActorKind.USER:",
        "    if False:",
        EDITORIAL_TESTS,
    ),
    (
        "25. no FR-16 observation is recorded, so the score has no input",
        EDITORIAL_REVIEW,
        "    return SourceObservation.objects.using(CATALOG).create(",
        "    return None  # type: ignore[return-value]\n"
        "    return SourceObservation.objects.using(CATALOG).create(",
        EDITORIAL_TESTS,
    ),
    (
        "26. a venue edit keeps the old fingerprint, so the venue silently never moves",
        EDITORIAL_REVIEW,
        "        fingerprint = venue.venue_fingerprint",
        "        pass",
        EDITORIAL_TESTS,
    ),
    (
        "27. the content-hash skip is removed (the editorial lock disappears)",
        INGEST_ITEM,
        "        and record.content_hash == content_hash\n",
        "",
        LOCK,
    ),
]


def run_tests(test_files: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *test_files, "-q", "--no-header", "-x"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def main() -> int:
    failures = []
    for description, path, original, mutated, test_files in PROBES:
        source = path.read_text()
        if original not in source:
            failures.append(f"PROBE DID NOT APPLY: {description}")
            print(f"SKIP  {description} (pattern not found)")
            continue

        path.write_text(source.replace(original, mutated, 1))
        try:
            code, output = run_tests(test_files)
        finally:
            path.write_text(source)

        if code == 0:
            failures.append(f"NOT CAUGHT: {description}")
            print(f"FAIL  {description} -- the suite still passed")
        else:
            print(f"OK    {description} -- caught ({output.strip().splitlines()[-1]})")

    print()
    if failures:
        for failure in failures:
            print(failure)
        return 1
    print(f"All {len(PROBES)} probes were caught by the suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
