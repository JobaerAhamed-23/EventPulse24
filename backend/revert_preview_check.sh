#!/usr/bin/env bash
# The revert verification for the pulse-preview-api-and-geo item (FR-2, AD-12).
#
# Every rule is verified by REVERTING it and watching the test FAIL. A regression test
# that passes against the broken code is not a regression test — and the run's standing
# rule is that a revert case that does not fail is a hole in the suite wearing a
# harness's clothes.
#
# Each case: patch the source, run the named tests, record the outcome, restore.
#
# The backup is UNIQUE per case. The first version of the event-fit harness keyed the
# backup on the file's basename alone, so two cases touching the same file shared one
# backup path: case A's restore overwrote case B's backup, and the file was left
# reverted for every case that followed. A restore that silently fails is worse than
# no restore, because it makes every later result a claim about a tree that does not
# exist. So the restore is verified byte for byte, and a mismatch ends the run.

set -uo pipefail
cd /Users/jobaer/Documents/EventPulse24/backend

TESTS="tests/ports/test_geo.py tests/api/test_preview_api.py tests/ingestion/test_preview_read.py tests/architecture/test_preview_anonymity.py"

# A counter, so every case gets its own backup file.
CASE_NO=0

# The overall verdict: 0 = every case failed the suite (good), 1 = a case passed
# against the broken code (a hole), 2 = a case was skipped (a pattern drifted).
HOLES=0
SKIPPED=0
FAILED_CASES=""

run_case () {
  local name="$1"; shift
  local file="$1"; shift
  local from="$1"; shift
  local to="$1"; shift
  # An optional SECOND patch on the same file, given as two lines separated by a line
  # containing only `%%SEP%%`. Some reverts need a name to exist before the rule can be
  # broken by it — a `cache.set(...)` that names an unimported `cache` raises a
  # NameError, and the suite then fails for a reason that has nothing to do with the
  # rule. A revert that fails for the wrong reason is not a verification.
  local extra="${1:-}"

  echo "───────────────────────────────────────────────────────────────"
  echo "CASE: $name"
  echo "───────────────────────────────────────────────────────────────"

  # A UNIQUE backup per case.
  CASE_NO=$((CASE_NO + 1))
  local backup="/tmp/revert_preview_backup_${CASE_NO}_$(basename "$file")"
  cp "$file" "$backup"

  # The replacement is given as a python expression operating on the file's text.
  python3 - "$file" "$from" "$to" "$extra" <<'PYEOF'
import sys
path, frm, to = sys.argv[1], sys.argv[2], sys.argv[3]
extra = sys.argv[4] if len(sys.argv) > 4 else ""
text = open(path).read()
if frm not in text:
    print("!! PATTERN NOT FOUND — the revert did not apply")
    sys.exit(3)
text = text.replace(frm, to, 1)
if extra:
    # The extra patch is a `from -> to` pair separated by a line holding only `%%SEP%%`.
    extra_from, _, extra_to = extra.partition("\n%%SEP%%\n")
    if extra_from not in text:
        print("!! EXTRA PATTERN NOT FOUND — the revert did not apply")
        sys.exit(3)
    text = text.replace(extra_from, extra_to, 1)
open(path, "w").write(text)
PYEOF
  if [ $? -ne 0 ]; then
    echo "RESULT: SKIPPED (pattern not found)"
    cp "$backup" "$file"
    rm -f "$backup"
    HOLES=$((HOLES + 1))
    SKIPPED=$((SKIPPED + 1))
    FAILED_CASES="$FAILED_CASES\n  - $name (SKIPPED: pattern not found)"
    return
  fi

  # The suite must FAIL. `--no-cov` keeps the output short and the run quick; a
  # coverage report says nothing about whether the rule was caught.
  .venv/bin/python -m pytest $TESTS -q --no-cov 2>&1 | tail -6
  local status=${PIPESTATUS[0]}

  echo "--- restoring ---"
  cp "$backup" "$file"
  # The restore is verified, not assumed: if the file does not match the backup byte
  # for byte, the run is invalid and the next case would start from a lie.
  if ! cmp -s "$backup" "$file"; then
    echo "!! RESTORE FAILED — $file is not what it was"
    exit 4
  fi
  rm -f "$backup"

  if [ "$status" -eq 0 ]; then
    echo "RESULT: !! HOLE — the suite PASSED against the broken code"
    HOLES=$((HOLES + 1))
    FAILED_CASES="$FAILED_CASES\n  - $name (HOLE: passed against the broken code)"
  else
    echo "RESULT: caught (the suite failed, exit $status)"
  fi
}

# ── The geo port ───────────────────────────────────────────────────────────────────

run_case \
  "R1 — the real adapter reads the edge's geo header" \
  adapters/geo/header.py \
  '        raw = _header_value(headers, GEO_HEADER_NAME)' \
  '        raw = None'

run_case \
  "R2 — the header value is URL-decoded exactly once" \
  adapters/geo/header.py \
  '        decoded = unquote(raw)' \
  '        decoded = unquote(unquote(raw))'

run_case \
  "R3 — the header value is length-bounded before it is used" \
  adapters/geo/header.py \
  '        if len(raw) > GEO_CITY_MAX_LENGTH:
            return None' \
  '        if False:
            return None'

run_case \
  "R4 — the header lookup is case-insensitive" \
  adapters/geo/header.py \
  '    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None' \
  '    return headers.get(name)'

run_case \
  "R5 — the header value is normalized into a city shape" \
  adapters/geo/header.py \
  '    kept = "".join(ch for ch in collapsed if ch in _ALLOWED_CITY_CHARS)' \
  '    kept = collapsed'

# ── The fake adapter ───────────────────────────────────────────────────────────────

run_case \
  "R6 — the fake adapter is configurable to return a chosen city" \
  adapters/geo/fake.py \
  '        city = getattr(settings, "GEO_FAKE_CITY", None)' \
  '        city = None'

# ── The city resolution ────────────────────────────────────────────────────────────

run_case \
  "R7 — the fallback city is the named constant" \
  apps/catalog/preview_api.py \
  '    return PREVIEW_FALLBACK_CITY, CITY_SOURCE_FALLBACK' \
  '    return "Nowhere-in-particular", CITY_SOURCE_FALLBACK'

run_case \
  "R8 — an explicit city overrides geo" \
  apps/catalog/preview_api.py \
  '        if len(wanted) <= GEO_CITY_MAX_LENGTH:
            return _canonical(supported, wanted), CITY_SOURCE_QUERY' \
  '        if len(wanted) <= GEO_CITY_MAX_LENGTH:
            return _canonical(supported, supported.cities[0]) if supported.cities else wanted, CITY_SOURCE_QUERY'

run_case \
  "R9 — a geo city outside the supported set falls back" \
  apps/catalog/preview_api.py \
  '        if geo_city and supported.supports(geo_city):' \
  '        if geo_city:'

run_case \
  "R9b — the answer carries the catalog's spelling of the city" \
  apps/catalog/preview_api.py \
  '        if len(wanted) <= GEO_CITY_MAX_LENGTH:
            return _canonical(supported, wanted), CITY_SOURCE_QUERY' \
  '        if len(wanted) <= GEO_CITY_MAX_LENGTH:
            return wanted, CITY_SOURCE_QUERY'

run_case \
  "R10 — the opt-out does not consult the geo port at all" \
  apps/catalog/preview_api.py \
  '    if use_geo:
        geo_city = get_geo_port().resolve_city(request.headers)' \
  '    if True:
        geo_city = get_geo_port().resolve_city(request.headers)'

run_case \
  "R11 — an unsupported explicit city returns an empty preview, not the fallback's cards" \
  apps/catalog/preview_api.py \
  '        if len(wanted) <= GEO_CITY_MAX_LENGTH:
            return _canonical(supported, wanted), CITY_SOURCE_QUERY' \
  '        if len(wanted) <= GEO_CITY_MAX_LENGTH:
            if not supported.supports(wanted):
                return PREVIEW_FALLBACK_CITY, CITY_SOURCE_FALLBACK
            return wanted, CITY_SOURCE_QUERY'

# ── The cacheable surface ──────────────────────────────────────────────────────────

run_case \
  "R12 — the response is cacheable as a public document" \
  apps/catalog/preview_api.py \
  '    response["Cache-Control"] = PREVIEW_CACHE_CONTROL' \
  '    pass'

run_case \
  "R13 — the response does not vary on the cookie" \
  apps/catalog/preview_api.py \
  '    response["Vary"] = PREVIEW_VARY' \
  '    response["Vary"] = "Cookie"'

run_case \
  "R14 — a refused request is not cached" \
  apps/catalog/preview_api.py \
  '        response["Cache-Control"] = "no-store"' \
  '        pass'

# ── The per-IP limit ───────────────────────────────────────────────────────────────

run_case \
  "R15 — the public preview is rate limited per IP" \
  apps/catalog/preview_api.py \
  '        limit=PREVIEW_THROTTLE_IP,
        window_seconds=PREVIEW_THROTTLE_WINDOW_SECONDS,
    )' \
  '        limit=10**9,
        window_seconds=PREVIEW_THROTTLE_WINDOW_SECONDS,
    )'

run_case \
  "R16 — the limit is keyed on the caller address, so one host cannot spend another's" \
  apps/catalog/preview_api.py \
  '    return f"{scope}:ip:{ip_address or '"'"'unknown'"'"'}"' \
  '    return f"{scope}:ip:everyone"'

run_case \
  "R17 — a refused request says when to retry" \
  apps/catalog/preview_api.py \
  '        response["Retry-After"] = str(decision.retry_after_seconds)' \
  '        pass'

run_case \
  "R17b — the cities endpoint can answer a refusal at all" \
  apps/catalog/preview_api.py \
  '    response={200: PreviewCitiesOut, 429: ErrorOut},' \
  '    response={200: PreviewCitiesOut},'

# ── The published read ─────────────────────────────────────────────────────────────

run_case \
  "R18 — a city is supported only when it has a current Event Fit" \
  apps/ingestion/services/preview_read.py \
  '        if row.event_version != row.event.event_version:
            continue  # stale: the Event changed after this fit was computed' \
  '        if False:
            continue'

run_case \
  "R19 — a city with no upcoming event is not supported" \
  apps/ingestion/services/preview_read.py \
  '        .filter(event__start_time_utc__gte=now)' \
  '        .filter(event__start_time_utc__gte=now).none()'

run_case \
  "R20 — a superseded event does not support its city" \
  apps/ingestion/services/preview_read.py \
  '        .exclude(event__status=Event.Status.SUPERSEDED)' \
  '        .exclude(event__status=Event.Status.SUPERSEDED).none()'

run_case \
  "R21 — the supported cities are listed alphabetically" \
  apps/ingestion/services/preview_read.py \
  '    return PreviewCities(cities=tuple(sorted(names, key=str.casefold)))' \
  '    return PreviewCities(cities=tuple(names))'

# The sort must be the Python one and not the database's locale collation: `ORDER BY`
# on text is a locale collation, so two deployments with different locales would list
# the same cities in a different order. This case puts the database's sort back AND
# takes the Python one away, which is what the code would look like if the order were
# left to the database — and the test must fail, because the locale collation orders
# `"St. John's"` and `"St Johns"` the other way round from `str.casefold`.
run_case \
  "R21b — the order is the Python one, not the database's locale collation" \
  apps/ingestion/services/preview_read.py \
  '    return PreviewCities(cities=tuple(sorted(names, key=str.casefold)))' \
  '    return PreviewCities(cities=tuple(names))' \
  '        .select_related("event")
    )
%%SEP%%
        .select_related("event")
        .order_by("city")
    )'

run_case \
  "R22 — one city spelled two ways is listed once" \
  apps/ingestion/services/preview_read.py \
  '        if name and name.casefold() not in {existing.casefold() for existing in names}:
            names.append(name)' \
  '        if name:
            names.append(name)'

run_case \
  "R23 — the support check is case-insensitive" \
  apps/ingestion/services/preview_read.py \
  '        wanted = city.strip().casefold()
        return any(name.casefold() == wanted for name in self.cities)' \
  '        return city in self.cities'

run_case \
  "R24 — the preview shows at most three cards" \
  apps/catalog/preview_api.py \
  'PREVIEW_SIZE = 3' \
  'PREVIEW_SIZE = 99'

# ── The Source Badge ───────────────────────────────────────────────────────────────

run_case \
  "R25 — a crawled source gets the crawled badge, whatever its type" \
  apps/ingestion/services/preview_read.py \
  '    if source.acquisition_method == "crawl":
        return SOURCE_BADGE_CRAWLED' \
  '    if False:
        return SOURCE_BADGE_CRAWLED'

run_case \
  "R26 — an unknown source type is the least specific claim, the aggregator" \
  apps/ingestion/services/preview_read.py \
  '    return _BY_SOURCE_TYPE.get(source.source_type, SOURCE_BADGE_AGGREGATOR)' \
  '    return _BY_SOURCE_TYPE.get(source.source_type, SOURCE_BADGE_OFFICIAL)'

# ── The walls ──────────────────────────────────────────────────────────────────────

run_case \
  "R27 — the catalog does not reach the Event Fit package directly" \
  apps/catalog/preview_api.py \
  'from apps.ingestion.services.preview_read import' \
  'from apps.ingestion.event_fit.reads import'

run_case \
  "R28 — the preview surface never reads the session" \
  apps/catalog/preview_api.py \
  '    resolved, source = _resolve_city(request, city=city, use_geo=use_geo, supported=supported)' \
  '    resolved, source = _resolve_city(request, city=city, use_geo=use_geo, supported=supported)
    _ = request.user'

run_case \
  "R29 — the preview surface never touches the personal schema" \
  apps/catalog/preview_api.py \
  'from shared.errors import ErrorOut' \
  'from shared.db import PERSONAL
from shared.errors import ErrorOut'

run_case \
  "R30 — the preview never stores the resolved city" \
  apps/catalog/preview_api.py \
  '    _cacheable(response)
    return PreviewOut(' \
  '    cache.set("preview:city", resolved)
    _cacheable(response)
    return PreviewOut(' \
  'from django.utils import timezone
%%SEP%%
from django.core.cache import cache
from django.utils import timezone'

run_case \
  "R31 — the preview never logs the resolved city" \
  apps/catalog/preview_api.py \
  '    _cacheable(response)
    return PreviewOut(' \
  '    logging.getLogger(__name__).info("resolved city %s", resolved)
    _cacheable(response)
    return PreviewOut(' \
  'from django.utils import timezone
%%SEP%%
import logging

from django.utils import timezone'

run_case \
  "R32 — the router is mounted at /public" \
  config/api.py \
  'api.add_router("/public", preview_router)' \
  'api.add_router("/not-public", preview_router)'

run_case \
  "R33 — the explicit city is bounded, like the header" \
  apps/catalog/preview_api.py \
  '        if len(wanted) <= GEO_CITY_MAX_LENGTH:
            return _canonical(supported, wanted), CITY_SOURCE_QUERY' \
  '        return _canonical(supported, wanted), CITY_SOURCE_QUERY'

echo "═══════════════════════════════════════════════════════════════"
echo "RESTORING EVERYTHING"
echo "═══════════════════════════════════════════════════════════════"
cd /Users/jobaer/Documents/EventPulse24
git diff --stat backend/apps backend/adapters backend/config backend/ports backend/shared

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "SUMMARY"
echo "═══════════════════════════════════════════════════════════════"
echo "cases run: $CASE_NO"
echo "holes:      $HOLES (skipped: $SKIPPED)"
if [ "$HOLES" -ne 0 ]; then
  echo "the following cases did not catch their revert:"
  printf '%b\n' "$FAILED_CASES"
  exit 1
fi
echo "every revert was caught."
