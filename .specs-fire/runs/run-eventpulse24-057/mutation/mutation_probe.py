#!/usr/bin/env python3
"""The item's mutation check: each mutation must make at least one test fail.

**A test must be able to fail.** A green suite proves the code does what it does; it
does not prove the tests *notice* when it stops doing it. Each mutation below is a
plausible way this code could be wrong, applied one at a time, and each is expected to
turn the suite red.

Run from `backend/`:
`uv run python ../.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py`

**Why it lives outside `tests/`.** It is a verification tool, not a test: pytest would
collect it, and the test tree's lint rules would apply to a file whose whole job is to
contain deliberately broken copies of the source.
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4] / "backend"

#: (name, file, old, new, the test that must fail)
MUTATIONS = [
    (
        "threshold lowered to one",
        "shared/constants.py",
        "ZERO_YIELD_RUN_THRESHOLD = 3",
        "ZERO_YIELD_RUN_THRESHOLD = 1",
        "tests/ingestion/test_city_probation.py",
    ),
    (
        "`unchanged` removed from the yield set",
        "shared/constants.py",
        """    "silent_updated",
    "unchanged",
    "bound_other_source",""",
        """    "silent_updated",
    "bound_other_source",""",
        "tests/ingestion/test_city_probation.py",
    ),
    (
        "`not_modified` resets the counter instead of leaving it",
        "apps/ingestion/services/city_probation.py",
        """    if outcome == "not_modified":
        return RunClassification(
            counter_effect=CounterEffect.LEAVE, published=False, yielded=True
        )""",
        """    if outcome == "not_modified":
        return RunClassification(
            counter_effect=CounterEffect.RESET, published=False, yielded=True
        )""",
        "tests/ingestion/test_city_probation.py",
    ),
    (
        "a fetch failure counts toward the probation",
        "apps/ingestion/services/city_probation.py",
        """    return RunClassification(counter_effect=CounterEffect.LEAVE, published=False, yielded=False)""",
        """    if outcome in ("fetch_failed", "parse_failed"):
        return RunClassification(
            counter_effect=CounterEffect.INCREMENT, published=False, yielded=False
        )
    return RunClassification(counter_effect=CounterEffect.LEAVE, published=False, yielded=False)""",
        "tests/ingestion/test_city_probation.py",
    ),
    (
        "a `live` city is overwritten by the probation",
        "apps/ingestion/services/city_probation.py",
        """        if provisioning.status == CityProvisioning.Status.LIVE:
            return provisioning.status, False
        if provisioning.status in (
            CityProvisioning.Status.NO_PROVIDERS,
            CityProvisioning.Status.FAILED,
        ):
            return provisioning.status, False

        sources = list(Source.objects.using(CATALOG).filter(city_ref_id=city_id))""",
        """        if provisioning.status in (
            CityProvisioning.Status.NO_PROVIDERS,
            CityProvisioning.Status.FAILED,
        ):
            return provisioning.status, False

        sources = list(Source.objects.using(CATALOG).filter(city_ref_id=city_id))""",
        "tests/ingestion/test_city_probation.py",
    ),
    (
        "a hand-pause is treated as a zero-yield pause",
        "apps/ingestion/services/city_probation.py",
        'if any(s.paused_reason != Source.PausedReason.ZERO_YIELD for s in paused_sources):',
        "if any(False for s in paused_sources):",
        "tests/ingestion/test_city_probation.py",
    ),
    (
        "the resume path stops backfilling the city link",
        "apps/ingestion/services/city_provisioning.py",
        """        if existing_source.city_ref_id is None:
            existing_source.city_ref = city
            existing_source.save(using=CATALOG, update_fields=["city_ref", "updated_at"])""",
        """        if False:
            existing_source.city_ref = city
            existing_source.save(using=CATALOG, update_fields=["city_ref", "updated_at"])""",
        "tests/ingestion/test_city_provisioning.py",
    ),
    (
        "the resume path registers a duplicate instead of resuming",
        "apps/ingestion/services/city_provisioning.py",
        """        if existing_source.status == Source.Status.PAUSED:
            resume_source(actor=actor, source_id=existing_source.id)
            resumed += 1""",
        """        if existing_source.status == Source.Status.PAUSED:
            resumed += 1""",
        "tests/ingestion/test_city_provisioning.py",
    ),
    (
        "the resume path does not reset the city's status",
        "apps/ingestion/services/city_provisioning.py",
        "    provisioning.status = CityProvisioning.Status.COLLECTING",
        "    provisioning.status = provisioning.status",
        "tests/ingestion/test_city_provisioning.py",
    ),
    (
        "the counter is not reset on a resumed source",
        "apps/ingestion/services/source_registry.py",
        """            source.paused_reason = ""
            source.consecutive_zero_yield_runs = 0
            changed += ["paused_reason", "consecutive_zero_yield_runs"]""",
        """            source.paused_reason = ""
            changed += ["paused_reason"]""",
        "tests/ingestion/test_source_registry.py",
    ),
    (
        "the pause reason is written into the audit details",
        "apps/ingestion/services/source_registry.py",
        '        details={"from": previous, "to": status},',
        '        details={"from": previous, "to": status, "reason": reason},',
        "tests/ingestion/test_source_registry.py",
    ),
    (
        "the city link is written into the register audit details",
        "apps/ingestion/services/source_registry.py",
        '            details={"fields": fields},',
        '            details={"fields": {**fields, "city_ref": str(city_ref)}},',
        "tests/ingestion/test_city_probation.py",
    ),
    (
        "the probation runs inside the ingest transaction",
        "apps/ingestion/services/ingest_source.py",
        """    try:
        probate_after_run(
            source=source,
            outcome=outcome,
            counts=counts,
            zero_yield_runs=source.consecutive_zero_yield_runs,
            actor=run.actor,
        )
    except Exception:
        logger.warning("City probation failed after an ingest run")""",
        """    probate_after_run(
        source=source,
        outcome=outcome,
        counts=counts,
        zero_yield_runs=source.consecutive_zero_yield_runs,
        actor=run.actor,
    )""",
        "tests/ingestion/test_city_probation.py",
    ),
    (
        "the counter is moved outside the run's transaction",
        "apps/ingestion/services/ingest_source.py",
        """        classification = classify_run(outcome, counts)
        if classification.counter_effect is CounterEffect.RESET:
            source.consecutive_zero_yield_runs = 0
            changed.append("consecutive_zero_yield_runs")
        elif classification.counter_effect is CounterEffect.INCREMENT:
            source.consecutive_zero_yield_runs += 1
            changed.append("consecutive_zero_yield_runs")""",
        """        classification = classify_run(outcome, counts)""",
        "tests/ingestion/test_city_probation.py",
    ),
]


def run(target: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "-p", "no:randomly"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout


def main() -> int:
    survivors = []
    for name, relative, old, new, target in MUTATIONS:
        path = BACKEND / relative
        original = path.read_text()
        if old not in original:
            print(f"SKIP  {name}: the text to mutate was not found in {relative}")
            survivors.append(name)
            continue
        path.write_text(original.replace(old, new, 1))
        try:
            code, output = run(target)
        finally:
            path.write_text(original)
        tail = [line for line in output.splitlines() if "passed" in line or "failed" in line]
        caught = code != 0
        print(f"{'CAUGHT' if caught else 'SURVIVED'}  {name}  ({tail[-1] if tail else '?'})")
        if not caught:
            survivors.append(name)

    print()
    if survivors:
        print(f"{len(survivors)} mutation(s) survived:")
        for name in survivors:
            print(f"  - {name}")
        return 1
    print(f"All {len(MUTATIONS)} mutations were caught.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
