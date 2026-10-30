# Code Review Report

**Run**: run-eventpulse24-020
**Intent**: onboarding-and-account
**Work item**: calendar-connect-api
**Reviewed**: 2026-10-29
**Files Reviewed**: 12

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Correctness | 0 | 4 | 0 |
| Contract / Architecture | 0 | 1 | 0 |
| Security | 0 | 2 | 0 |
| Observability | 0 | 0 | 0 |
| Code Quality | 0 | 2 | 0 |
| Documentation | 0 | 1 | 0 |
| **Total** | **0** | **10** | **0** |

**Tests Status**: Passing — 2909 passed, 0 failed; 98.98% coverage; 17/17 import contracts kept.

Ten findings, from two independent adversarial review agents reading the item
independently. Eight came from one agent, four from the other, and the two sets
converged on four root causes — which is itself the strongest signal in the report:
two reviewers, working separately, found the same four defects.

Every finding was a **defect**, not a style preference, and every one was fixed in the
same pass rather than deferred. Each was **reproduced with a failing test before it was
acted on** — a review finding is a claim, not a fact, and a finding that cannot be
reproduced is a finding that cannot be fixed.

The findings share a shape worth naming: **they are all cases where the code did not
fail — it failed to be safe.** Nothing here threw in the single-user, sequential case.
One was a *500 on an everyday sequence*, one was a *count read without a lock*, one was
*a bare exception escaping to the 500 handler*, and one was *a read that decrypted a
secret it had no use for*. All four are invisible to a sequential test suite, which is
exactly why they survived the first pass.

---

## Files Reviewed

### Created

| File | Purpose |
|------|---------|
| `backend/domain/address_policy.py` | The SSRF pre-flight — scheme, host and port rules, shared by the connect and the fetch |
| `backend/apps/personalization/migrations/0006_remove_calendarconnection_calendar_connection_user_credential_uq_and_more.py` | The unique constraint becomes **partial** |
| `backend/tests/personalization/test_calendar_connect_api.py` | The five endpoints' contract |
| `backend/tests/personalization/test_calendar_connection_reads.py` | The read projections and their guarantees |
| `backend/tests/personalization/test_calendar_connect_concurrency.py` | The commands under concurrency |
| `backend/tests/personalization/test_review_repro.py` | The twelve defect reproductions |

### Modified

| File | Change |
|------|--------|
| `backend/apps/personalization/api.py` | The five endpoints, on the `current_user` resolver |
| `backend/apps/personalization/schemas.py` | The wire shapes — **no field for the address** |
| `backend/apps/personalization/services/calendar_connections.py` | The commands and queries |
| `backend/apps/personalization/models.py` | The constraint became partial |
| `backend/domain/errors.py` | Three typed errors |
| `backend/adapters/crawl/address_policy.py` | The policy moved to `domain`; the adapter now reads it |

---

## Findings

### V1 — A disconnected connection squatted the address, so re-adding it was a 500 (Correctness, HIGH)

**Found by**: reading the unique constraint against the disconnect command.

The constraint was `UniqueConstraint(fields=["user_id", "credential_fingerprint"])` —
**without** a status qualifier. The disconnect command destroys the credential but leaves
the fingerprint on the row (a keyed HMAC of the old address), and the row waits for the
retention sweep (D7). So the fingerprint kept occupying the address, and the ordinary
everyday sequence —

> connect a calendar → disconnect it → connect the same calendar again

— hit the constraint and answered **500**. The user had lost a working calendar and
could not get it back.

**Reproduced first**: the second connect raised `IntegrityError`.

**Fixed** by making the constraint **partial**, which is what it always meant:

```python
models.UniqueConstraint(
    fields=["user_id", "credential_fingerprint"],
    condition=~models.Q(status="disconnected"),
    name="calendar_connection_user_credential_uq",
)
```

The same shape as `ingestion`'s `event_live_source_item_uq`
(`apps/ingestion/models.py:246`), so the repo has one precedent and one meaning:
*one **live** connection per address, per user.*

**Pinned by** `test_reconnecting_the_same_address_after_a_disconnect_does_not_raise` and
`test_a_disconnected_connection_does_not_squat_the_address`.

**A note on how the revert is verified.** The first version of the revert case patched
the **model** — and the test still passed, because the test database is rebuilt from the
**migrations**, so the partial index was still in place. The revert now patches the
migration file, and the case fails as it should. A revert case that cannot distinguish
the two states is not a revert case.

### V2 — The `needs_reconnect` reuse path skipped the cap (Correctness, HIGH)

**Found by**: reading the cap check against the reuse branch.

The cap check short-circuited on `existing is None`:

```python
if existing is None and occupying >= FREE_TIER_CALENDAR_PROVIDER_CAP:
```

A `needs_reconnect` row **still occupies the user's slot** — it is a live calendar whose
credential was revoked. But a connect that *reused* that row skipped the cap entirely,
so a user already at their cap could reuse a revoked row and turn a second live row
into a third.

**This one needed care, and the honest version is recorded here.** Under the Free cap
of one, the over-cap state is *not reachable through the API* — a user with one active
calendar plus one revoked row is already at the cap, and the reuse path does not add a
slot. The difference only shows at the **Pro tier** (a cap of three) or under a race.
The test therefore lifts the cap to one and builds the over-cap state directly with the
ORM, and the **rule** is pinned, not the Free tier's number.

**Fixed**:

```python
occupying = _slot_count(user_id)
if existing is not None:
    # The row being reused is already counted, so it does not add a slot.
    occupying -= 1
if occupying >= FREE_TIER_CALENDAR_PROVIDER_CAP:
```

The `existing is not None` branch is not a free pass — it *subtracts the row it is
reusing* and then goes through the same check. The reuse path is one row, so it does not
buy a second slot, and it does not wave the user past the cap.

**Pinned by** `test_a_needs_reconnect_row_does_not_buy_a_second_slot` and
`test_reusing_a_needs_reconnect_row_does_not_take_a_second_slot` — the first pins the
rule, the second pins the legitimate case that must **not** be refused.

### V3 — The cap was counted outside the lock (Correctness, HIGH)

**Found by**: reading the cap check against the transaction boundary.

The cap is a **count**. A count read without a lock is a race: two concurrent connects
both read zero, both pass the check, and both write a row — leaving a Free account with
**two** calendars, silently, against a rule the endpoint enforces.

**Fixed** by serialising the user's calendar commands with a **transaction-scoped
advisory lock** — `pg_advisory_xact_lock`, the pattern already established at
`apps/personalization/services/onboarding.py:99-114`. The key is derived with `blake2b`
under a dedicated personalisation (`b"eventpulse24-cal"`), so it cannot collide with
the onboarding lock keys, and it is stable across processes — never the per-process-salted
`hash()`.

The lock is taken **before** the cap is decided, inside the same transaction that writes
the row. `pg_advisory_xact_lock` is transaction-scoped, so a worker that dies mid-command
releases the lock on rollback and a user's calendar cannot be left wedged by a crash.

**Pinned by** `test_two_concurrent_connects_cannot_both_take_the_only_slot`, which
races two connects released by a `threading.Barrier` — no sleeps, no timing assumptions.

### V4 — A reconnect onto an address the user already holds was a 500 (Correctness, HIGH)

**Found by**: comparing `connect_calendar` against `reconnect_calendar`.

`connect_calendar` guards the duplicate case with `_refused_duplicate`. `reconnect_calendar`
**did not** — so a reconnect onto an address the user already holds fell through to the
unique constraint and answered 500, for an input the user can correct in one step.

**Fixed** by giving `reconnect_calendar` the same guard, with an `exclude_pk` so the row
being reconnected is exempt from counting as a duplicate of itself:

```python
_refused_duplicate(user_id=locked.user_id, digest=digest, exclude_pk=locked.pk)
```

**Pinned by** `test_reconnecting_onto_an_address_already_connected_is_refused_calmly`.

### V5 — The reconnect trusted the caller's copy of the status (Correctness, MEDIUM)

**Found by**: reading the reconnect's status checks against the transaction boundary.

The status was checked **before** the transaction opened, from the row the caller had
already fetched. A disconnect that committed in between was silently overwritten by the
reconnect — which would resurrect a calendar the user had just removed, and re-arm a
credential they had asked to destroy.

The row could also *vanish* between the lookup and the lock (the retention sweep removes
disconnected rows), and the second read found nothing — an `AttributeError` on `None`
where the answer should have been "not found".

**Fixed** by re-reading the row **under a row lock** inside the transaction:

```python
locked = (
    CalendarConnection.objects.using(PERSONAL)
    .select_for_update()
    .filter(pk=connection.pk)
    .first()
)
if locked is None:
    raise CalendarConnectionNotFoundError(details={"connection_id": str(connection.pk)})
```

**Pinned by** `test_a_row_that_vanishes_before_the_lock_is_not_found` and
`test_a_disconnect_committed_first_is_not_overwritten_by_a_reconnect`.

### V6 — A malformed host escaped as a 500 (Correctness, MEDIUM)

**Found by**: reading `urlsplit`'s error behaviour against the service's error handling.

`urlsplit` raises a bare `ValueError` on a malformed bracketed IPv6 host
(`https://[not-an-ip]/feed.ics`). It is not a `DomainError`, so it escaped to the 500
handler — a server fault for what is a **typo**. Every other bad address gets a calm
422; this one did not.

**Fixed** by catching it and refusing calmly, like every other bad address.

**Pinned by** `test_a_malformed_bracketed_host_is_refused_calmly`.

### V7 — An address on a port the fetch would refuse was accepted (Security, MEDIUM)

**Found by**: reading the pre-flight against the fetch client's actual policy.

The hardened fetch client only connects to the ports in `SOURCE_FETCH["allowed_ports"]`
(80 and 443) and refuses any other one — on every hop. So an address like
`https://example.com:8443/feed.ics` was **accepted at connect time**, stored with a live
encrypted credential, and shown to the user as **connected** — and then refused on
**every single poll**, with the only evidence a slug in the connection's error field.

That is precisely the "invisible at connect time" failure the SSRF pre-flight exists to
prevent. The pre-flight checked the host and not the port.

**Fixed** by adding `_refused_port`, which refuses a port the fetch adapter would not
allow, and which treats a malformed or out-of-range port as a typo rather than a crash
(`urlsplit`'s `port` property raises for both).

**Pinned by** `test_an_address_on_a_port_the_fetch_would_refuse_is_refused_calmly`,
`test_a_malformed_port_is_refused_calmly`, and
`test_an_address_on_an_allowed_port_is_accepted` — the last one matters, because a
pre-flight that refuses the ports the fetch really allows would be worse than none.

### V8 — The reads decrypted every credential (Security, MEDIUM)

**Found by**: reading the read path against the projection.

`EncryptedTextField.from_db_value` decrypts every row it fetches. The read loaded the
whole row — so a read **decrypted every address it touched**, for a projection that has
no field for it.

The security consequence is a **denial of service the user could not remedy**: one row
whose envelope cannot be read (a rotated key id, a corrupted ciphertext, a truncated
envelope) raised from the read and took down the **whole list**. And because the same
lookup backed the disconnect, the user could not disconnect the broken row either —
**the remedy refused itself**.

**Fixed** by naming the columns a read needs, and leaving `credential` out of them:

```python
_READ_COLUMNS = (
    "id", "provider", "status", "display_label",
    "last_polled_at", "next_poll_at", "sync_claimed_at", "last_error_kind", "created_at",
)
```

**Pinned by** `test_the_reads_do_not_decrypt_the_credentials` and
`test_a_user_can_disconnect_a_connection_whose_credential_cannot_be_read`.

Both tests write the corrupt envelope **straight to the column**. Without it, the old
code decrypted every credential successfully and the test passed **vacuously** — the
first version of this test was not a test at all.

### V9 — The ownership lookup decrypted the credential (Security, MEDIUM)

**Found by**: the same reading, applied to the ownership lookup.

`_owned_connection` loaded the whole row, so the lookup the **disconnect** depends on
also decrypted the credential. The consequence is the same one as V8, and it is the
more serious half of it: a row the user cannot disconnect is a row they cannot remove.

**Fixed** by restricting the lookup to the ownership columns.

**Pinned by** `test_a_user_can_disconnect_a_connection_whose_credential_cannot_be_read`.

### V10 — The CSRF check was duplicated, and the test could not tell (Code Quality, MEDIUM)

**Found by**: the revert verification, failing to fail.

The connect, reconnect and disconnect endpoints each called `require_csrf(request)`
explicitly, **and** the router declared `auth=current_user` — and `current_user` calls
`require_csrf(request)` itself. So the check ran **twice**, and the first version of
the revert case removed the explicit calls and **all 72 tests still passed**.

That was not a passing test. It was a test that **could not distinguish the two things
it was supposed to distinguish**. A duplicate mechanism with a test that cannot see
either copy is worse than one mechanism: it reads as defence in depth and provides
none.

**Fixed** by removing the three redundant calls and keeping the resolver's check — one
mechanism is easier to reason about than two — and by **re-aiming the revert case** at
the resolver, where it now fails the three CSRF-refusal tests.

The general lesson is worth stating, because it is the same lesson the review's first
pass over the cap made: **a revert case that does not fail is not a revert case.** It is
a hole in the suite wearing a harness's clothes.

---

## The Revert Verification

Every fix was verified by **reverting it and watching the test fail**. A regression test
that passes against the broken code is not a regression test.

The review's fixes have their own harness, `backend/revert_review_check.sh` — separate
from the item's own `backend/revert_check.sh`, because the two sets of rules are
different rules.

| Fix | Reverted | Result |
|-----|----------|--------|
| V1 — a disconnected row does not squat the address | the **migration**'s partial condition removed | **2 tests fail**: `test_reconnecting_the_same_address_after_a_disconnect_does_not_raise`, `test_a_disconnected_connection_does_not_squat_the_address` |
| V2 — the cap applies on the reuse path | the `occupying -= 1` removed | **1 test fails**: `test_a_needs_reconnect_row_does_not_buy_a_second_slot` |
| V3 — the cap is decided under the lock | `_lock_user(user_id)` removed | **2 tests fail**: both concurrency tests |
| V4 — the reconnect refuses a held address | `_refused_duplicate` removed from the reconnect | **1 test fails**: `test_reconnecting_onto_an_address_already_connected_is_refused_calmly` |
| V5 — the reconnect re-reads under a row lock | `select_for_update()` replaced by the unlocked row | **1 test fails**: `test_a_row_that_vanishes_before_the_lock_is_not_found` |
| V6 — a malformed host is refused calmly | `except ValueError` → `except ZeroDivisionError` | **1 test fails**: `test_a_malformed_bracketed_host_is_refused_calmly` |
| V7 — a refused port is refused | `_refused_port(parts)` removed | **2 tests fail**: the port tests |
| V8 — the reads do not decrypt | `.only(*_READ_COLUMNS)` removed | **1 test fails**: `test_the_reads_do_not_decrypt_the_credentials` |
| V9 — the lookup does not decrypt | `.only(...)` removed from `_owned_connection` | **1 test fails**: `test_a_user_can_disconnect_a_connection_whose_credential_cannot_be_read` |

**All nine caught.** And the item's own rules still hold after the review's fixes — the
original harness was re-run end to end and **R1 through R9 are all caught** as well:

```
R1 — the address never reaches the response body      1 test fails
R2 — the Free cap is a 409, not a 400                  1 test fails
R3 — the cap payload carries no modal semantics         1 test fails
R4 — the SSRF pre-flight refuses a denied address      5 tests fail
R5 — another user's connection is a 404, not a 403     4 tests fail
R6 — a stale claim is not a sync in progress           2 tests fail
R7 — the reads never write                             5 tests fail
R8 — the provider is validated against the known set   2 tests fail
R9 — the connect endpoint requires a CSRF token        3 tests fail
```

R7's pattern needed updating during this pass: the review's V8 fix rewrote the list
query with `.only(*_READ_COLUMNS)`, so the old patch no longer matched and the case
reported `SKIPPED (pattern not found)`. It was re-aimed at the rewritten query, and
the case now fails as it should.

---

## Notes

1. **The address is the credential.** That single fact drives most of this item. It is
   why the response shape has no field for it (not masked, not a fragment — **no
   field**), why the address is excluded from the request body in the logs, why another
   user's connection id is a **404** rather than a 403, and why the port check exists.

2. **The provider value changes no server behaviour.** The work item says so, and the
   code holds to it: the provider is validated against the known set and then carried.
   The port and host rules come from the fetch adapter's policy, not from a
   per-provider table.

3. **The first sync is enqueued, not run inline** (AD-11). The connect returns with the
   connection's status and sync state; the polling happens on the tick, in the worker.
   The endpoint's job is to tell the user "we're importing your calendar" — which is
   what onboarding step 1 needs, without leaving the flow (FR-3).

4. **The upgrade copy comes from EXPERIENCE.md/DESIGN.md.** It was not written fresh.
   The payload carries the copy and no modal semantics (R3) — the client decides
   whether to show a prompt, a banner, or a card.

5. **The SSRF policy moved to `domain`.** The pre-flight is a policy, not an adapter
   detail: both the connect path and the fetch path need it, and `domain` is where
   shared policy belongs. The import contracts are unchanged.

6. **One ruff error was found and fixed in this pass** — an unused local in the repro
   file (`F841`). The gate is clean.

---

## The Final Gate

```
pytest tests/ -q --cov --cov-report=term-missing
2909 passed in 85.87s (0:01:25)
TOTAL                                             6402     65    99%
157 files skipped due to complete coverage.
Required test coverage of 80.0% reached. Total coverage: 98.98%

ruff check .
All checks passed!

ruff format --check .
356 files already formatted

lint-imports
Contracts: 17 kept, 0 broken.

manage.py check
System check identified no issues (1 silenced).

manage.py makemigrations --check --dry-run
No changes detected

make client
lib/api/openapi.json → lib/api/schema.ts

pytest tests/api/test_contract.py -q
1 passed

pnpm --dir frontend test
149 passed (16 files)

frontend tsc --noEmit
clean
```

**The item's own service is at 100%** —
`apps/personalization/services/calendar_connections.py` and `domain/address_policy.py`
are both in the "skipped due to complete coverage" set.

---

## Test Result

**Passing.** 2909 passed, 0 failed, 98.98% coverage, ruff clean, format clean, 17/17
import contracts kept, no migration drift, the frontend suite green (149 tests), the
frontend typecheck clean, and the committed OpenAPI schema matches the live API.
