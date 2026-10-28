#!/usr/bin/env python
"""Mutation probes for the public catalog API (run-eventpulse24-017, plan step 6).

Each probe applies one real bug to the implementation, runs the catalog tests, and checks
that at least one test fails. A probe that passes the suite means the tests don't prove that
rule, and the implementation or the test has to change.

Run from the repo root:  uv run --directory backend python tests/api/mutation_probe_catalog.py
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
READ_SERVICE = BACKEND / "apps/ingestion/services/catalog_read.py"
CATALOG_API = BACKEND / "apps/catalog/api.py"

PROBES = [
    (
        "the publication_status filter is dropped (an in_review event leaks into the list)",
        READ_SERVICE,
        "        .filter(publication_status=Event.PublicationStatus.PUBLISHED)\n",
        "",
        ["tests/api/test_catalog_api.py", "tests/api/test_catalog_read_service.py"],
    ),
    (
        "the superseded exclusion is dropped",
        READ_SERVICE,
        "        .exclude(status=Event.Status.SUPERSEDED)\n",
        "",
        ["tests/api/test_catalog_api.py", "tests/api/test_catalog_read_service.py"],
    ),
    (
        "the upcoming filter is dropped (an event that already started leaks in)",
        READ_SERVICE,
        "    queryset = _public_events().filter(start_time_utc__gte=now)\n",
        "    queryset = _public_events()\n",
        ["tests/api/test_catalog_api.py", "tests/api/test_catalog_read_service.py"],
    ),
    (
        "the id tiebreak is dropped (the order is no longer total)",
        READ_SERVICE,
        '    queryset = queryset.order_by("start_time_utc", "id")\n',
        '    queryset = queryset.order_by("start_time_utc")\n',
        ["tests/api/test_catalog_read_service.py"],
    ),
    (
        "the city filter is dropped",
        READ_SERVICE,
        "    if city:\n        queryset = queryset.filter(venue__city__iexact=city)\n",
        "",
        ["tests/api/test_catalog_api.py", "tests/api/test_catalog_read_service.py"],
    ),
    (
        "the date-range filter is dropped",
        READ_SERVICE,
        "    if starts_after is not None:\n"
        "        queryset = queryset.filter(start_time_utc__gte=starts_after)\n",
        "",
        ["tests/api/test_catalog_api.py", "tests/api/test_catalog_read_service.py"],
    ),
    (
        "the page size is not applied (pagination returns everything)",
        READ_SERVICE,
        "    items = [_to_public_event(event) for event in "
        "queryset[offset : offset + page_size]]\n",
        "    items = [_to_public_event(event) for event in queryset[offset:]]\n",
        ["tests/api/test_catalog_read_service.py"],
    ),
    (
        "a missing event raises a plain Exception instead of the domain error (no 404)",
        READ_SERVICE,
        '        raise EventNotFoundError(details={"event_id": str(event_id)}) from None\n',
        '        raise RuntimeError("not found")\n',
        ["tests/api/test_catalog_api.py", "tests/api/test_catalog_read_service.py"],
    ),
    (
        "the query parameters are read from the body instead of the query string",
        CATALOG_API,
        "def list_events(request, filters: EventPage = EVENT_PAGE_QUERY):",
        "def list_events(request, filters: EventPage = EventPage()):",
        ["tests/api/test_catalog_api.py"],
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
