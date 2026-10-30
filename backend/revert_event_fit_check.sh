#!/usr/bin/env bash
# The revert verification for the event-fit item (AD-10, FR-26).
#
# Every rule is verified by REVERTING it and watching the test FAIL. A regression test
# that passes against the broken code is not a regression test.
#
# Each case: patch the source, run the named tests, record the outcome, restore.
# The restore is verified by `git diff --stat` at the end.

set -uo pipefail
cd /Users/jobaer/Documents/EventPulse24/backend

TESTS="tests/domain/test_event_fit.py tests/ingestion/test_event_fit.py tests/ingestion/test_event_fit_command.py tests/architecture/test_event_fit_separation.py tests/architecture/test_import_contracts.py tests/worker/test_scheduling_tasks.py"

# A counter, so every case gets its own backup file.
CASE_NO=0

run_case () {
  local name="$1"; shift
  local file="$1"; shift
  local from="$1"; shift
  local to="$1"; shift

  echo "───────────────────────────────────────────────────────────────"
  echo "CASE: $name"
  echo "───────────────────────────────────────────────────────────────"

  # A UNIQUE backup per case. The first version keyed the backup on the file's
  # basename alone, so two cases that touched the same file shared one backup path:
  # case A's restore overwrote case B's backup, and the file was left reverted for
  # every case that followed. A restore that silently fails is worse than no restore.
  CASE_NO=$((CASE_NO + 1))
  local backup="/tmp/revert_backup_${CASE_NO}_$(basename "$file")"
  cp "$file" "$backup"

  # The replacement is given as a python expression operating on the file's text.
  python3 - "$file" "$from" "$to" <<'PYEOF'
import sys
path, frm, to = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path).read()
if frm not in text:
    print("!! PATTERN NOT FOUND — the revert did not apply")
    sys.exit(3)
open(path, "w").write(text.replace(frm, to, 1))
PYEOF
  if [ $? -ne 0 ]; then
    echo "RESULT: SKIPPED (pattern not found)"
    cp "$backup" "$file"
    rm -f "$backup"
    return
  fi

  .venv/bin/python -m pytest $TESTS -q 2>&1 | tail -6
  echo "--- restoring ---"
  cp "$backup" "$file"
  # The restore is verified, not assumed: if the file does not match the backup
  # byte for byte, the run is invalid and the next case would start from a lie.
  if ! cmp -s "$backup" "$file"; then
    echo "!! RESTORE FAILED — $file is not what it was"
    exit 4
  fi
  rm -f "$backup"
}

run_case \
  "R1 — the day boundary is the event's own local day, not UTC's" \
  domain/event_fit.py \
  '    start_local = start_time_utc.astimezone(zone)
    now_local = now.astimezone(zone)' \
  '    start_local = start_time_utc.astimezone(ZoneInfo(UTC_ZONE))
    now_local = now.astimezone(ZoneInfo(UTC_ZONE))'

run_case \
  "R2 — an event that has already started is in the last band, not the soonest" \
  domain/event_fit.py \
  '    if until_start <= timedelta(0):
        return 1
    if until_start < EVENT_FIT_TODAY:' \
  '    if until_start < EVENT_FIT_TODAY:'

run_case \
  "R3 — the score is the LOWER of the two bands" \
  domain/event_fit.py \
  '    score = max(EVENT_FIT_SCORE_MIN, min(proximity, confidence))' \
  '    score = max(EVENT_FIT_SCORE_MIN, max(proximity, confidence))'

run_case \
  "R4 — the confidence band is a band, not a pass-through" \
  domain/event_fit.py \
  '    if confidence >= EVENT_FIT_CONFIDENCE_HIGH:
        return 5
    if confidence >= EVENT_FIT_CONFIDENCE_GOOD:
        return 4
    if confidence >= EVENT_FIT_CONFIDENCE_FAIR:
        return 3
    return 2' \
  '    return EVENT_FIT_SCORE_MAX'

run_case \
  "R5 — the weekend is the one weekend in view, named by its Saturday" \
  domain/event_fit.py \
  '        event_date = start_local.date()
        event_saturday = event_date - timedelta(days=(event_date.weekday() - 5) % 7)
        if event_saturday == weekend_saturday:
            tags.append(EVENT_FIT_TAG_THIS_WEEKEND)' \
  '        if (start_local.date() - now_local.date()).days <= 7:
            tags.append(EVENT_FIT_TAG_THIS_WEEKEND)'

run_case \
  "R6 — the place tag is the venue's city, slugged" \
  domain/event_fit.py \
  '    ascii_city = normalize("NFKD", city.strip())' \
  '    ascii_city = city.strip()'

run_case \
  "R7 — the fit row records the version it was computed from" \
  apps/ingestion/event_fit/writes.py \
  '                "event_version": event.event_version,
                "computed_at": now,' \
  '                "event_version": 1,
                "computed_at": now,'

run_case \
  "R8 — a stale fit is never served" \
  apps/ingestion/event_fit/reads.py \
  '        if row.event_version != event.event_version:
            continue  # stale: the Event changed after this fit was computed' \
  '        if False:
            continue'

run_case \
  "R9 — the read serves the persisted score and tags; it computes nothing" \
  apps/ingestion/event_fit/reads.py \
  '                score=row.score,
                tags=tuple(row.tags),' \
  '                score=5,
                tags=(),'

run_case \
  "R10 — the preview is ordered by score, then by start time" \
  apps/ingestion/event_fit/reads.py \
  '        .order_by("-score", "event__start_time_utc", "event_id")' \
  '        .order_by("event__start_time_utc", "event_id")'

run_case \
  "R11 — the ingest path recomputes the fit when the event changes" \
  apps/ingestion/services/ingest_item.py \
  '    if outcome != "unchanged":' \
  '    if False:'

run_case \
  "R12 — the ingest hook re-reads the event, so the fit carries the new version" \
  apps/ingestion/services/ingest_item.py \
  '    event = Event.objects.using(CATALOG).select_related("venue").get(pk=event_id)
    write_event_fit(event=event, now=run.now, actor=run.actor)' \
  '    write_event_fit(event=event, now=run.now, actor=run.actor)'

run_case \
  "R13 — the backfill is an upsert, so it is idempotent" \
  apps/ingestion/event_fit/writes.py \
  '    row, _created = EventFit.objects.using(CATALOG).update_or_create(' \
  '    row, _created = EventFit.objects.using(CATALOG).get_or_create('

run_case \
  "R14 — the fit is written when the event is created, inside the same transaction" \
  apps/ingestion/services/ingest_item.py \
  '        _write_fit(run, event.pk)  # a new event has a fit from the moment it exists' \
  '        pass  # a new event has a fit from the moment it exists'

run_case \
  "R15 — the tick refreshes the fits every fifteen minutes" \
  worker/tasks.py \
  '    if _now().minute % EVENT_FIT_REFRESH_EVERY_MINUTES == 0:' \
  '    if False:'

run_case \
  "R16 — the read never reaches the personal schema" \
  apps/ingestion/event_fit/reads.py \
  'from shared.db import CATALOG' \
  'from shared.db import CATALOG, PERSONAL'

# --- The code review's fixes (step 6b) ---

run_case \
  "V1 — a fit for a city the event has left is retired" \
  apps/ingestion/event_fit/writes.py \
  '    EventFit.objects.using(CATALOG).filter(event_id=event.pk).exclude(city__iexact=city).delete()' \
  '    pass  # the old city keeps its row'

run_case \
  "V2 — a row that already matches is not rewritten (computed_at does not move)" \
  apps/ingestion/event_fit/writes.py \
  '    if (
        existing is not None
        and existing.score == score
        and list(existing.tags) == list(tags)
        and existing.event_version == event.event_version
    ):' \
  '    if False:'

run_case \
  "V3 — the Event Fit is a package, so the wall cannot be opened with a third name" \
  pyproject.toml \
  'forbidden_modules = [
    "apps.ingestion.event_fit",
    "apps.ingestion.event_fit.*",
]' \
  'forbidden_modules = [
    "apps.ingestion.event_fit.reads",
]'

run_case \
  "V4 — the wall checks the package PREFIX, so a re-export cannot slip through" \
  tests/architecture/test_event_fit_separation.py \
  '    assert any(name.startswith(EVENT_FIT_PACKAGE) for name in imported), (' \
  '    assert any(name in {EVENT_FIT_READ, EVENT_FIT_WRITES} for name in imported), ('

run_case \
  "V5 — the wall test can read a planted module outside the backend tree" \
  tests/architecture/test_event_fit_separation.py \
  '    try:
        parts = path.relative_to(BACKEND_DIR).with_suffix("").parts
    except ValueError:
        parts = path.with_suffix("").parts' \
  '    parts = path.relative_to(BACKEND_DIR).with_suffix("").parts'echo "═══════════════════════════════════════════════════════════════"
echo "RESTORING EVERYTHING"
echo "═══════════════════════════════════════════════════════════════"
cd /Users/jobaer/Documents/EventPulse24
git diff --stat backend/apps/ingestion backend/domain backend/worker backend/config
