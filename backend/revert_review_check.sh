#!/usr/bin/env bash
# The revert verification for the code review's fixes.
#
# Every rule the review established is verified by REVERTING it and watching the test
# FAIL. A regression test that passes against the broken code is not a regression test.
#
# Each case: patch the source, run the named tests, record the outcome, restore.
# The restore is verified by `git diff --stat` at the end.

set -uo pipefail
cd /Users/jobaer/Documents/EventPulse24/backend

TESTS="tests/personalization/test_review_repro.py tests/personalization/test_calendar_connect_concurrency.py tests/personalization/test_calendar_connect_api.py tests/personalization/test_calendar_connection_reads.py"

run_case () {
  local name="$1"; shift
  local file="$1"; shift
  local from="$1"; shift
  local to="$1"; shift

  echo "───────────────────────────────────────────────────────────────"
  echo "CASE: $name"
  echo "───────────────────────────────────────────────────────────────"
  cp "$file" "/tmp/revert_review_backup_$(basename "$file")"

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
    cp "/tmp/revert_review_backup_$(basename "$file")" "$file"
    return
  fi

  .venv/bin/python -m pytest $TESTS -q --no-cov 2>&1 | tail -6
  echo "--- restoring ---"
  cp "/tmp/revert_review_backup_$(basename "$file")" "$file"
}

run_case \
  "V1 — a disconnected connection does not squat the address" \
  apps/personalization/migrations/0006_remove_calendarconnection_calendar_connection_user_credential_uq_and_more.py \
  '            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "disconnected"), _negated=True),
                fields=("user_id", "credential_fingerprint"),
                name="calendar_connection_user_credential_uq",
            ),' \
  '            constraint=models.UniqueConstraint(
                fields=("user_id", "credential_fingerprint"),
                name="calendar_connection_user_credential_uq",
            ),'

run_case \
  "V2 — the cap applies on the needs_reconnect reuse path" \
  apps/personalization/services/calendar_connections.py \
  '        occupying = _slot_count(user_id)
        if existing is not None:
            # The row being reused is already counted, so it does not add a slot.
            occupying -= 1
        if occupying >= FREE_TIER_CALENDAR_PROVIDER_CAP:' \
  '        occupying = _slot_count(user_id)
        if existing is None and occupying >= FREE_TIER_CALENDAR_PROVIDER_CAP:'

run_case \
  "V3 — the cap is decided under the advisory lock" \
  apps/personalization/services/calendar_connections.py \
  '        _lock_user(user_id)

' \
  ''

run_case \
  "V4 — a reconnect refuses an address the user already holds" \
  apps/personalization/services/calendar_connections.py \
  '        _refused_duplicate(user_id=locked.user_id, digest=digest, exclude_pk=locked.pk)
' \
  ''

run_case \
  "V5 — the reconnect re-reads the status under a row lock" \
  apps/personalization/services/calendar_connections.py \
  '        locked = (
            CalendarConnection.objects.using(PERSONAL)
            .select_for_update()
            .filter(pk=connection.pk)
            .first()
        )' \
  '        locked = connection'

run_case \
  "V6 — a malformed host or port is refused calmly, not with a 500" \
  apps/personalization/services/calendar_connections.py \
  '    try:
        parts = urlsplit(text)
    except ValueError:' \
  '    try:
        parts = urlsplit(text)
    except ZeroDivisionError:'

run_case \
  "V7 — an address on a port the fetch would refuse is refused" \
  apps/personalization/services/calendar_connections.py \
  '    _refused_port(parts)
' \
  ''

run_case \
  "V8 — the reads do not decrypt the credential" \
  apps/personalization/services/calendar_connections.py \
  '        .only(*_READ_COLUMNS)
        .order_by("created_at", "id")' \
  '        .order_by("created_at", "id")'

run_case \
  "V9 — the ownership lookup does not decrypt the credential" \
  apps/personalization/services/calendar_connections.py \
  '        .only(
            "id",
            "provider",
            "status",
            "display_label",
            "user_id",
            "created_at",
        )
        .first()' \
  '        .first()'

echo "═══════════════════════════════════════════════════════════════"
echo "RESTORING EVERYTHING"
echo "═══════════════════════════════════════════════════════════════"
cd /Users/jobaer/Documents/EventPulse24
git diff --stat backend/apps backend/domain backend/adapters
