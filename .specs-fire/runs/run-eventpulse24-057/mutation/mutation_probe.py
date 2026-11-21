#!/usr/bin/env python3
"""The item's mutation check: each mutation must make at least one test fail.

**A test must be able to fail.** A green suite proves the code does what it does; it
does not prove the tests *notice* when it stops doing it. Each mutation below is a
plausible way this code could be wrong, applied one at a time, and each is expected to
turn the suite red.

Run from the repository root:
`uv run --directory backend python ../.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py`

**Why it lives outside `tests/`.** It is a verification tool, not a test: pytest would
collect it, and the test tree's lint rules would apply to a file whose whole job is to
contain deliberately broken copies of the source.

**It covers both halves of the application.** A mutation in the Python service is
caught by pytest; a mutation in a React component is caught by vitest. The two runners
are addressed by the file's own location — a path under `backend/` runs pytest, a path
under `frontend/` runs vitest — so a mutation names the test that must fail and the
probe works out the rest.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"

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
        return RunClassification(counter_effect=CounterEffect.LEAVE, published=False, yielded=True)""",
        """    if outcome == "not_modified":
        return RunClassification(counter_effect=CounterEffect.RESET, published=False, yielded=True)""",
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
    #
    # ── item 9: browse-collecting-states ────────────────────────────────────
    #
    ("the status is never read — every city is quiet",
     "apps/personalization/services/browse_read.py",
     "    collection_status = read_city_collection_status(city=city)",
     '    collection_status = type("S", (), {"status": "", "source_count": 0})()',
     "tests/personalization/test_browse_read.py"),
    ("the status read mints a City",
     "apps/ingestion/services/city_status_read.py",
     """    row = (
        City.objects.using(CATALOG)""",
     """    from apps.ingestion.services.cities import resolve_city

    resolve_city(city=name, country_code="US")
    row = (
        City.objects.using(CATALOG)""",
     "tests/ingestion/test_city_status_read.py"),
    ("the collecting state is folded into the quiet state",
     "../frontend/app/browse/page.tsx",
     "  const isCollecting = status === \"collecting\";",
     "  const isCollecting = false;",
     "../frontend/tests/browse-states.test.tsx"),
    ("a live city with no cards is told its sources failed",
     "../frontend/app/browse/page.tsx",
     """  const hasNoSources =
    status === "no_providers" ||
    status === "failed" ||
    status === "yielded_nothing" ||
    status === "paused";""",
     """  const hasNoSources =
    status === "no_providers" ||
    status === "failed" ||
    status === "yielded_nothing" ||
    status === "paused" ||
    status === "live";""",
     "../frontend/tests/browse-states.test.tsx"),
    ("a user with no city is told collection is under way",
     "../frontend/app/browse/page.tsx",
     """         */
        <BrowseEmpty />
      ) : isCollecting ? (""",
     """         */
        <BrowseCollecting city={browse.city} />
      ) : isCollecting ? (""",
     "../frontend/tests/browse-states.test.tsx"),
    ("the collecting state does not announce itself",
     "../frontend/components/browse/browse-states.tsx",
     """      role="status"
      aria-live="polite"
      aria-label={`Collecting events for ${city}`}""",
     """      aria-label={`Collecting events for ${city}`}""",
     "../frontend/tests/browse-states.test.tsx"),
    ("the city page's collection note is dropped",
     "../frontend/components/city-page/city-page.tsx",
     "          {collectionNote(page.name, page.city_collection_status)}",
     "          {null}",
     "../frontend/tests/city-page-states.test.tsx"),
    ("the frontend learns a status the backend does not have",
     "../frontend/app/browse/page.tsx",
     "  const isCollecting = status === \"collecting\";",
     "  const isCollecting = status === \"collecting\" || status === \"a_status_from_the_future\";",
     "../frontend/tests/city-collection-vocabulary.test.ts"),
    #
    # ── item 10: city-coverage-request ─────────────────────────────────────
    #
    ("the one-row guarantee is removed from the schema",
     "apps/ingestion/models.py",
     '            models.UniqueConstraint(fields=["city"], name="city_coverage_request_city_uq"),',
     '            models.UniqueConstraint(fields=["city", "request_count"], name="city_coverage_request_city_uq"),',
     "tests/ingestion/test_coverage_requests.py"),
    ("a repeat creates a second row instead of raising the count",
     "apps/ingestion/services/coverage_requests.py",
     """        row, created = CityCoverageRequest.objects.using(CATALOG).get_or_create(
            city=city_row,
            defaults={"request_count": 1, "created_at": moment},
        )""",
     """        row, created = CityCoverageRequest.objects.using(CATALOG).get_or_create(
            city=city_row,
            defaults={"request_count": 1, "created_at": moment},
        )
        if not created:
            CityCoverageRequest.objects.using(CATALOG).create(
                city=city_row,
                request_count=1,
                created_at=moment,
            )""",
     "tests/ingestion/test_coverage_requests.py"),
    ("the request mints a city it has never heard of",
     "apps/ingestion/services/coverage_requests.py",
     """        city_row = _find_city(name)
        if city_row is None:
            # **Refused before anything is written**, so an unknown city leaves no row, no
            # audit row and no count behind. The reader is told to pick the city instead,
            # which is the action that actually covers it.
            raise UnknownHomeCityError()""",
     """        city_row = _find_city(name)
        if city_row is None:
            # **The mutation mints the city instead of refusing it.**
            city_row = City.objects.using(CATALOG).create(
                name=name,
                country_code="US",
                normalized_key=name.lower(),
                slug=f"slug-{name.lower().replace(' ', '-')}",
                region="",
            )""",
     "tests/ingestion/test_coverage_requests.py"),
    ("the count does not move on a repeat",
     "apps/ingestion/services/coverage_requests.py",
     """            CityCoverageRequest.objects.using(CATALOG).filter(pk=row.pk).update(
                request_count=F("request_count") + 1, updated_at=moment
            )""",
     """            CityCoverageRequest.objects.using(CATALOG).filter(pk=row.pk).update(
                request_count=F("request_count"), updated_at=moment
            )""",
     "tests/ingestion/test_coverage_requests.py"),
    ("the audit details carry the city name",
     "apps/ingestion/services/coverage_requests.py",
     '            details={"city_id": str(city_row.id), "request_count": row.request_count},',
     '            details={"city": city_row.name, "request_count": row.request_count},',
     "tests/ingestion/test_coverage_requests.py"),
    ("the throttle is checked after the idempotence shortcut",
     "apps/ingestion/services/coverage_requests.py",
     """    decision = get_throttle_port().check(
        throttle_key(actor.id),
        limit=COVERAGE_REQUEST_LIMIT,
        window_seconds=COVERAGE_REQUEST_WINDOW_SECONDS,
    )
    if not decision.allowed:""",
     """    decision = get_throttle_port().check(
        throttle_key(actor.id),
        limit=COVERAGE_REQUEST_LIMIT,
        window_seconds=COVERAGE_REQUEST_WINDOW_SECONDS,
    )
    if False:""",
     "tests/ingestion/test_coverage_requests.py"),
    ("the endpoint drops its authentication",
     "apps/ingestion/coverage_api.py",
     'router = Router(tags=["catalog"], auth=current_user)',
     'router = Router(tags=["catalog"])',
     "tests/api/test_coverage_request_api.py"),
    ("the control is offered in the collecting state as well",
     "../frontend/app/browse/page.tsx",
     "  const coverageRequest = hasNoSources ? <CoverageRequestControl city={browse.city} /> : null;",
     "  const coverageRequest = <CoverageRequestControl city={browse.city} />;",
     "../frontend/tests/browse-states.test.tsx"),
    ("the control stays visible after a successful ask",
     "../frontend/components/browse/coverage-request-control.tsx",
     """      {recorded ? (""",
     """      {false ? (""",
     "../frontend/tests/browse-coverage-request.test.tsx"),
    ("a failed ask leaves a confirmation behind",
     "../frontend/components/browse/coverage-request-control.tsx",
     """      if (response.response.status < 200 || response.response.status >= 300) {
        setFailure(response.error?.message ?? OFFLINE_MESSAGE);
        return;
      }""",
     """      if (response.response.status < 200 || response.response.status >= 300) {
        setFailure(response.error?.message ?? OFFLINE_MESSAGE);
        setRecorded(true);
        return;
      }""",
     "../frontend/tests/browse-coverage-request.test.tsx"),
    #
    # ── item 11: home-city-dropdown-catalog ────────────────────────────────
    #
    ("the option shows the value instead of the label",
     "../frontend/components/settings/home-city.tsx",
     """            {options.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}""",
     """            {options.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.value}
              </option>
            ))}""",
     "../frontend/components/settings/home-city.test.tsx"),
    ("the option submits the label instead of the value",
     "../frontend/components/settings/home-city.tsx",
     """            {options.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}""",
     """            {options.map((choice) => (
              <option key={choice.value} value={choice.label}>
                {choice.label}
              </option>
            ))}""",
     "../frontend/components/settings/home-city.test.tsx"),
    ("the stored city is dropped from the options",
     "../frontend/components/settings/home-city.tsx",
     """  const options: CityChoice[] =
    city === null || stored !== undefined ? choices : [{ value: city, label: city }, ...choices];""",
     """  const options: CityChoice[] = choices;""",
     "../frontend/components/settings/home-city.test.tsx"),
    ("the synthesised option shows an empty label",
     "../frontend/components/settings/home-city.tsx",
     "    city === null || stored !== undefined ? choices : [{ value: city, label: city }, ...choices];",
     '    city === null || stored !== undefined ? choices : [{ value: city, label: "" }, ...choices];',
     "../frontend/components/settings/home-city.test.tsx"),
    ("the stored city is matched by its label rather than its value",
     "../frontend/components/settings/home-city.tsx",
     "  const stored = city === null ? null : choices.find((choice) => choice.value === city);",
     "  const stored = city === null ? null : choices.find((choice) => choice.label === city);",
     "../frontend/components/settings/home-city.test.tsx"),
    ("the placeholder is always offered",
     "../frontend/components/settings/home-city.tsx",
     "            {city === null ? <option value={NO_CITY}>Choose a city</option> : null}",
     '            <option value={NO_CITY}>Choose a city</option>',
     "../frontend/components/settings/home-city.test.tsx"),
    ("the picker goes back to the preview's city list",
     "../frontend/lib/home-city-read.ts",
     '      api.GET("/api/public/cities", {}),',
     '      api.GET("/api/public/preview/cities", {}),',
     "../frontend/tests/endpoint-coverage.test.ts"),
]


def run(target: str) -> tuple[int, str]:
    """Run the test that must fail, in whichever half of the app it lives.

    **The runner is chosen by the target's own path.** A target under `backend/` is a
    pytest file; a target under `frontend/` is a vitest file. Nothing else distinguishes
    them, and nothing else needs to.
    """
    if target.startswith("../frontend/"):
        relative = target[len("../frontend/") :]
        result = subprocess.run(
            ["pnpm", "vitest", "run", relative],
            cwd=FRONTEND,
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout + result.stderr
    result = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "-p", "no:randomly"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout


def resolve(relative: str) -> Path:
    """The file a mutation is applied to.

    **A path starting with `../frontend/` is relative to `backend/`**, because that is
    how the backend's own paths are written in the mutation table — `apps/ingestion/...`
    means `backend/apps/ingestion/...`. The frontend sibling is one level up and one
    level over, and the path is *normalised* so the `..` segment is collapsed rather
    than followed out of the repository.
    """
    if relative.startswith("../frontend/"):
        return (BACKEND / relative).resolve()
    return BACKEND / relative


def main() -> int:
    survivors = []
    for name, relative, old, new, target in MUTATIONS:
        path = resolve(relative)
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
        tail = [
            line
            for line in output.splitlines()
            if "passed" in line or "failed" in line or "Tests " in line
        ]
        caught = code != 0
        print(f"{'CAUGHT' if caught else 'SURVIVED'}  {name}  ({tail[-1].strip() if tail else '?'})")
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
