#!/usr/bin/env python
"""Mutation probes for the end-to-end proof (run-eventpulse24-018, plan step 6).

Each probe applies one real bug to the implementation, runs the end-to-end suite, and checks
that at least one test fails. A probe that passes the suite means the tests don't prove that
rule, and the implementation or the test has to change.

Run from the repo root:  uv run --directory backend python tests/e2e/mutation_probe_e2e.py
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
SEED_COMMAND = BACKEND / "config/management/commands/seed_local_stack.py"
SCHEDULING = BACKEND / "apps/ingestion/services/scheduling.py"
INGEST_ITEM = BACKEND / "apps/ingestion/services/ingest_item.py"
INGEST_SOURCE = BACKEND / "apps/ingestion/services/ingest_source.py"
JSONLD_PARSER = BACKEND / "apps/ingestion/parsers/jsonld.py"

E2E_TESTS = ["tests/e2e/test_end_to_end.py"]

PROBES = [
    (
        "the editorial group gets an extra permission (delete_source)",
        SEED_COMMAND,
        '    "source": ("add", "change", "view"),\n',
        '    "source": ("add", "change", "delete", "view"),\n',
    ),
    (
        "the editorial group's permissions are appended instead of assigned",
        SEED_COMMAND,
        "        group.permissions.set(permissions)\n",
        "        group.permissions.add(*permissions)\n",
    ),
    (
        "the operator is made a superuser",
        SEED_COMMAND,
        "            if user.is_superuser:\n"
        "                user.is_superuser = False\n"
        '                changed.append("is_superuser")\n',
        '            if user.is_superuser:\n                changed.append("is_superuser")\n',
    ),
    (
        "the seed command registers the source without its ToS review",
        SEED_COMMAND,
        "            source = register_source(actor=actor, tos_review=review, **values)\n",
        "            source = register_source(actor=actor, **values)\n",
    ),
    (
        "the seed command is not idempotent: an existing source is registered again",
        SEED_COMMAND,
        '        source = find_source_by_url(feed["url"])\n',
        "        source = None\n",
    ),
    (
        "the due sources are not claimed, so the tick schedules nothing",
        SCHEDULING,
        "            .filter(\n"
        "                Q(last_attempted_at__isnull=True)\n"
        '                | Q(last_attempted_at__lte=_minus(now, F("ingestion_cadence")))\n'
        "            )\n",
        "            .filter(pk__in=[])\n",
    ),
    (
        "a JSON-LD series' sub-events are not expanded, so its instances never land",
        JSONLD_PARSER,
        '                for name in ("subEvent", "subEvents"):\n',
        "                for name in ():\n",
    ),
    (
        "the content hash ignores the venue's timezone, so a corrected venue never re-resolves",
        INGEST_ITEM,
        "    material = {\n"
        '        "payload": payload,\n'
        '        "venue_id": str(venue.id) if venue else None,\n'
        '        "venue_tz": venue.tz if venue else None,\n'
        "    }\n",
        "    material = {\n"
        '        "payload": payload,\n'
        '        "venue_id": str(venue.id) if venue else None,\n'
        "    }\n",
    ),
    (
        "the source's last attempt is not recorded, so the source is always due",
        INGEST_SOURCE,
        "        source.last_attempted_at = now\n"
        '        source.save(using=CATALOG, update_fields=["last_attempted_at", "updated_at"])\n',
        '        source.save(using=CATALOG, update_fields=["updated_at"])\n',
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
    for description, path, original, mutated in PROBES:
        source = path.read_text()
        if original not in source:
            failures.append(f"PROBE DID NOT APPLY: {description}")
            print(f"SKIP  {description} (pattern not found)")
            continue

        path.write_text(source.replace(original, mutated, 1))
        try:
            code, output = run_tests(E2E_TESTS)
        finally:
            path.write_text(source)

        if code == 0:
            failures.append(f"NOT CAUGHT: {description}")
            print(f"FAIL  {description} -- the suite still passed")
        else:
            last = output.strip().splitlines()[-1] if output.strip() else "failed"
            print(f"OK    {description} -- caught ({last})")

    print()
    if failures:
        for failure in failures:
            print(failure)
        return 1
    print(f"All {len(PROBES)} probes were caught by the suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
