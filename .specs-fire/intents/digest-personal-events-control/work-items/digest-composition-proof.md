---
id: digest-composition-proof
title: The Proof — That Opting Out Changes the Digest
intent: digest-personal-events-control
complexity: medium
mode: confirm
status: completed
depends_on:
  - digest-preference-read-helper
  - personal-events-digest-toggle
  - digest-settings-route
created: 2026-11-13
run_id: run-eventpulse24-030
completed_at: 2026-11-13T01:53:31.913Z
---

# Work Item: The Proof — That Opting Out Changes the Digest

## Description

A settings screen that saves a flag is not the same as a product that honours the flag.
This item proves the second thing.

The backend already honours it — `compose_digest()` reads the preference at
`services/digest_composition.py:628` and gates Slot 1 at `:489` — and the backend tests
already cover the composition behaviour (`test_digest_composition.py` asserts the opt-out
at several points). **So this is not about discovering a backend bug; it is about
closing the loop the intent exists to close.**

The gap this item closes is *specific*: today, nothing proves that the value a user sets
**through the new settings screen** is the same value the **composition service** reads.
Those are two different paths that happen to meet at a database column. A regression in
the write path — a field dropped from the PUT body, a wrong key name, a field the
endpoint silently ignores because it was omitted — would leave every existing backend
test green and the product broken.

**The test that matters therefore spans the seam**, not the two sides of it.

It must fail if:
- the settings save stops sending `include_personal_events`
- the endpoint stops accepting it
- the command stops writing it
- the composition stops reading it
- the toggle's value and the composition's value diverge

**How it must not be tested.** Not by asserting that a PUT body contains a key — the
existing frontend test already does that, and it proves only that the client tried. Not
by asserting a database row has `False` — the existing backend test already does that,
and it proves only that the command can write. **The proof is that the user who opted
out gets a digest with no personal event in it, driven from the same value the settings
screen writes.**

## Acceptance Criteria

- [x] A test drives the **full path**: set the preference the way the settings screen does (the same PUT body), then compose a digest for that user, and assert the resulting digest contains **no personal event**
- [x] The test asserts the **positive** case too — a user who has *not* opted out gets their personal event in Slot 1 — so the proof cannot be satisfied by a digest that never contains personal events at all
- [x] The test asserts the **inverted** case — a user who opts out and then opts back **in** gets their personal event back, proving the control is not write-once
- [x] The test freezes time explicitly and uses a personal event inside the 48-hour eligibility window (`RANKING_PERSONAL_EVENT_WINDOW`)
- [x] The test uses a real database, marked `@pytest.mark.django_db(databases=[PERSONAL, CATALOG])`, because the composition reads a real preference row
- [x] **The seam is exercised, not simulated.** The value must travel through the same write path the frontend uses — not be set by a direct ORM write in the test
- [x] The existing composition tests are **untouched and still pass**
- [x] Every assertion can fail — no `or`-fallbacks, no assertions that hold either way

## Technical Notes

- **Where the test lives.** The backend suite is `backend/tests/<module>/`, and the
  personalization module has 56 files. `backend/tests/personalization/` is the home —
  the existing opt-out assertions are in `test_digest_composition.py`, and the write-path
  assertions are in `test_onboarding_api.py` and `test_digest_preferences.py`. A new file
  named for the behaviour (rather than appending to a large existing file) makes the
  seam's proof findable. **Check whether an existing file already covers this seam**
  before adding a new one — if `test_digest_composition.py` already composes a digest for
  a user whose preference was written through the endpoint, this item's work may be a
  smaller addition than a new file.
- **The composition entry point.** `compose_digest(user_id, actor, now)`
  (`services/digest_composition.py:597-778`) is the command. It runs **in the worker,
  never in a request** (AD-11), and
  `backend/tests/architecture/test_digest_composition_separation.py` enforces that
  separation with an AST call-based check. **Calling it from a test is fine** — the
  architecture test is about production call sites, and the existing composition tests
  already call it directly.
- **Personal-event eligibility.** A personal event qualifies when its `start_utc` is
  within the next 48 hours — `list_personal_candidates(user_id, now, window_end)` at
  `services/digest_candidates.py:191-257`, with both window ends inclusive. The test
  must place its event inside that window or Slot 1 will fall through to the public
  fallback (`digest_composition.py:503-519`) and the assertion will pass for the wrong
  reason.
- **Slot 1's personal branch.** `digest_composition.py:488-501` — `if
  include_personal_events:` — and the fallback to the highest-scoring public event is at
  `:503-519`. A test that asserts "no personal event in the digest" must therefore also
  confirm the fallback ran, or a broken fallback will look like a passing opt-out.
- **The opt-out also suppresses a count.** `digest_composition.py:679-683` suppresses
  `personal_qualifying_count` when the user is opted out. Assert this too — it is the
  difference between "the personal event is not shown" and "the product does not know
  about it", and a dashboard metric that counts opted-out events would be a second,
  quieter leak of the same bug.
- **Fake at the port boundary, never the ORM.** The testing standard says so. If the
  composition reaches for a clock, freeze time; if it reaches for a source fetch, fake
  the port. Never mock the ORM to make a preference row appear.
- **Freeze time explicitly.** The suite has a history of hardcoded absolute datetimes
  that expired and turned the suite red — the defect class that run 029's
  `test-clock-seam` work item addressed. **Do not add a new absolute datetime.**

## Dependencies

- digest-preference-read-helper
- personal-events-digest-toggle
- digest-settings-route
