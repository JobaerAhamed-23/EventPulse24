---
run: run-eventpulse24-022
work_item: e2e-proof-and-contract-tests
intent: timeline-and-conflicts
mode: confirm
checkpoint: plan
created: 2026-10-31
---

# Implementation Plan: The end-to-end proof for the Timeline and the conflicts

**This item writes proof, not product.** Seven work items built the Timeline, the
conflicts page, the conflict prompt and the digest-only home. Each was tested in
isolation. This item proves the whole thing **composes** — that one user's week, one
pair, and the resolve endpoint agree with each other — and that the contract between the
two halves of the system has not drifted.

## Approach

Two artefacts, and they are different in kind.

**1. A backend end-to-end scenario** (`backend/tests/e2e/test_timeline_and_conflict_proof.py`)
that drives the **real HTTP stack** through Django, with the fake adapters, as the
earlier proofs do. It creates one user, one personal event, one overlapping saved public
event, and then walks the whole chain: the 409, the conflict list, the resolve, and the
Timeline read — asserting that the **same** pair id appears in every one of them, and
that the Timeline's `conflict` flag follows FR-58.

**2. A frontend contract test** (`frontend/tests/ad19-endpoint-coverage.test.ts`, extended)
that pins the **generated client** against the endpoints this intent added. The
`NEW_ENDPOINTS` table already carries the digest and the detail read; this intent's
endpoints — the Timeline week, the conflicts list, the resolve, the personal-event
create, the saved-event create — are not in it.

**3. A mutation probe file** (`backend/tests/e2e/mutation_probe_timeline_conflicts.py`)
that plants a real bug in each key rule and **requires the suite to fail**, in the style
of `mutation_probe_contract_e2e.py`.

### Why one scenario and not several

The house pattern (`test_digest_and_detail_proof.py`) says it plainly: *"The point of a
proof is that the steps compose."* A digest composed in one test and read in another is
not the same digest. So the scenario is **one test, one user, one database** — and the
claims that only appear when the steps are chained (the pair id in the 409 is the pair id
in the list is the pair id in the resolve response) are the ones worth proving.

The paths that are genuinely independent — the isolation check, the `make client` drift
check — are separate tests, and separate for a reason.

## The claims to prove

| # | Claim | Where |
|---|-------|-------|
| 1 | A personal event + an overlapping saved public event → the week returns **both**, on the right local day, both flagged `conflict` | scenario |
| 2 | The conflicts list returns the pair **active**, with its allowed actions | scenario |
| 3 | Resolving with each action → the pair moves to `resolved` with the right wording | scenario |
| 4 | The Timeline flag follows FR-58: `keep_both` keeps it; `skip_public` and `delete_new` clear it | scenario |
| 5 | A clashing save answers **409** with a pair the resolve endpoint can close | scenario |
| 6 | A second user sees **none** of the first user's pairs or blocks | scenario |
| 7 | `make client` leaves `frontend/lib/api/` unchanged | contract test |
| 8 | The frontend contract tests cover the new endpoints | contract test |

## Files to Create or Modify

| File | Changes |
|------|---------|
| `backend/tests/e2e/test_timeline_and_conflict_proof.py` | **new** — the scenario |
| `backend/tests/e2e/mutation_probe_timeline_conflicts.py` | **new** — the probes |
| `frontend/tests/ad19-endpoint-coverage.test.ts` | **modified** — the new endpoints in `NEW_ENDPOINTS` |

Nothing in `backend/apps/` or `frontend/app/` changes. **This item writes tests; if a
test fails, the product is wrong and the product gets fixed — but not by weakening the
test.**

## The mechanism

**The client.** `tests/csrf.py`'s `CsrfClient` — a `django.test.Client` that fetches
the token the way a browser does and sends it on the unsafe methods. The personal
endpoints resolve their user through the session (`identity`'s resolver), so the client
is `force_login`-ed and the user id is `UUID(client.session["_auth_user_id"])`.

**The catalog.** The scenario needs a *published, upcoming* catalog event to save. The
`EventFactory` from `tests/ingestion/factories.py` writes to the catalog alias directly
and is the same factory the digest proof uses — so no seeding command and no tick are
needed. `last_seen_at` must be pinned, exactly as the digest proof pins it, or the
staleness bound drops the event before the read sees it.

**The pair.** The scenario creates the clash through the **real endpoint**
(`POST /api/personal/saved-events/{id}` against a personal event that overlaps), not by
writing a `ConflictPair` row. A pair written by hand proves the *read* but not the
*detection*; the AC says "a clashing save answers 409 with a pair the resolve endpoint
can close", and only a real clash proves that.

## Sequence

1. **The scenario file.** The fixtures (`_signed_in`, `_personal_event`, `_catalog_event`)
   and the claim-by-claim tests.
2. **The contract test.** The five endpoints added to `NEW_ENDPOINTS`, each of which
   gets the five existing assertions for free.
3. **The probes.** One per key rule, each shown to fail.
4. **The gates.** `make lint-backend`, `make coverage-backend`, `make client` (and the
   diff must be empty), `make lint-web`, `make test-web`, the production build.

## Decisions

**D1 — The scenario drives the HTTP stack, not the services.** The digest proof calls
the services directly; this one drives the **endpoints**, because the claim is about a
*round trip*: "the pair id in the 409 is the pair id in the list is the pair id in the
resolve". A service-level call cannot observe the 409 at all. The service-level
behaviour is already covered by the per-item tests; what is missing is the seam.

**D2 — The pair is created by a real clash.** A hand-written `ConflictPair` row would
make the scenario pass even if detection were broken — and detection is the thing most
worth proving.

**D3 — The week is named by a date, not a Monday.** `?week=` accepts *any* date in the
wanted week. The scenario asks for a Wednesday and asserts the response names the
Monday and the Sunday — which is the property the frontend's link relies on.

**D4 — The isolation claim is one test, two users.** The second user reads the same
week and the same conflicts list and sees **nothing**. Two users is the smallest number
that can prove a scoping claim.

**D5 — The probes target the rules the AC names.** The cross-midnight indicator, the
ownership scoping, and keep-both keeping the flag are the three the AC calls out. Each
probe is a text replacement that **still parses** and still produces a wrong answer — a
probe that broke the file so badly the suite could not collect would pass the harness
while proving nothing.

**D6 — `make client` is verified by a diff, not by a test.** The Makefile's `client`
target regenerates `frontend/lib/api/` from the live schema; the contract is that the
committed tree is **unchanged** by that regeneration. `backend/tests/api/test_contract.py`
already asserts the committed `openapi.json` equals the live schema, so the check here
is the `git diff --exit-code -- frontend/lib/api/` after `make client` — the same check
CI runs.

## What is deliberately not changed

- **The product code.** This item is proof. A failing assertion is a finding to report,
  not a licence to change the behaviour.
- **The service-level tests.** They exist and they pass; the scenario adds the seam, not
  a second copy of the unit.
- **The `NEW_ENDPOINTS` table's shape.** The resolve endpoint has **three** call sites
  (`conflicts-panel.tsx`, `detail-actions.tsx`, `personal-events-panel.tsx`), and the
  table's `caller` field is a single module path. Rather than reshape the table for one
  endpoint, the table's `caller` becomes a **list** — a small, general change that keeps
  every existing row working.
