#!/usr/bin/env bash
# The revert verification for the calendar-connect-api item.
#
# Every rule is verified by REVERTING it and watching the test FAIL. A regression test
# that passes against the broken code is not a regression test.
#
# Each case: patch the source, run the named tests, record the outcome, restore.
# The restore is verified by `git diff --stat` at the end.

set -uo pipefail
cd /Users/jobaer/Documents/EventPulse24/backend

TESTS="tests/personalization/test_calendar_connect_api.py tests/personalization/test_calendar_connection_reads.py"

run_case () {
  local name="$1"; shift
  local file="$1"; shift
  local from="$1"; shift
  local to="$1"; shift

  echo "───────────────────────────────────────────────────────────────"
  echo "CASE: $name"
  echo "───────────────────────────────────────────────────────────────"
  cp "$file" "/tmp/revert_backup_$(basename "$file")"

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
    cp "/tmp/revert_backup_$(basename "$file")" "$file"
    return
  fi

  .venv/bin/python -m pytest $TESTS -q 2>&1 | tail -6
  echo "--- restoring ---"
  cp "/tmp/revert_backup_$(basename "$file")" "$file"
}

run_case \
  "R1 — the address never reaches the response body (the shape has no field for it)" \
  apps/personalization/schemas.py \
  '    id: UUID
    provider: str
    status: str
    display_label: str = ""' \
  '    id: UUID
    provider: str
    status: str
    address: str = ""
    display_label: str = ""'

run_case \
  "R2 — the Free cap is a 409 (a conflict with the account), not a 400" \
  domain/errors.py \
  'class CalendarProviderCapReached(ConflictError):' \
  'class CalendarProviderCapReached(DomainError):'

run_case \
  "R3 — the cap payload carries no modal semantics" \
  apps/personalization/services/calendar_connections.py \
  '                    "upgrade_hint": "Save more with Pro.",
' \
  '                    "upgrade_hint": "Save more with Pro.",
                    "modal": True,
                    "title": "Upgrade to Pro",
                    "actions": [{"label": "Upgrade", "href": "/settings/plan"}],
'

run_case \
  "R4 — the SSRF pre-flight refuses a denied address" \
  apps/personalization/services/calendar_connections.py \
  '    if is_denied(address):
        raise InvalidCalendarCredentialError(details={"field": "url"})' \
  '    if False:
        raise InvalidCalendarCredentialError(details={"field": "url"})'

run_case \
  "R5 — another user's connection is a 404, not a 403" \
  apps/personalization/services/calendar_connections.py \
  '    if row is None:
        raise CalendarConnectionNotFoundError(details={"connection_id": str(connection_id)})
    return _view(row, now=now)' \
  '    if row is None:
        raise PermissionDeniedError(details={"connection_id": str(connection_id)})
    return _view(row, now=now)'

run_case \
  "R6 — the sync-in-progress flag treats a stale claim as not-in-progress" \
  apps/personalization/services/calendar_connections.py \
  '    fresh = claimed and connection.sync_claimed_at > now - CALENDAR_CLAIM_TTL' \
  '    fresh = claimed'

run_case \
  "R7 — the reads never write (a read that mutates is a cross-site write)" \
  apps/personalization/services/calendar_connections.py \
  '    rows = (
        CalendarConnection.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .only(*_READ_COLUMNS)
        .order_by("created_at", "id")
    )' \
  '    rows = (
        CalendarConnection.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .only(*_READ_COLUMNS)
        .order_by("created_at", "id")
    )
    for row in rows:
        row.sync_claimed_at = now
        row.save(using=PERSONAL, update_fields=["sync_claimed_at"])'

run_case \
  "R8 — the provider is validated against the known set" \
  apps/personalization/services/calendar_connections.py \
  '    known = {choice.value for choice in CalendarConnection.Provider}
    if provider not in known:
        raise InvalidCalendarCredentialError(details={"field": "provider"})
    return provider' \
  '    return provider'

run_case \
  "R9 — the connect endpoint requires a CSRF token" \
  apps/identity/api_auth.py \
  '    require_csrf(request)
    return user' \
  '    return user'

echo "═══════════════════════════════════════════════════════════════"
echo "RESTORING EVERYTHING"
echo "═══════════════════════════════════════════════════════════════"
cd /Users/jobaer/Documents/EventPulse24
git diff --stat backend/apps/personalization backend/domain backend/adapters
