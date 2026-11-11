---
run: run-eventpulse24-027
work_item: subscription-model-and-entitlement
intent: pro-tier-and-monetization
mode: validate
checkpoint: plan (checkpoint 2)
approved_at: 2026-11-11
---

# Implementation Plan: Something to be Pro with — the Subscription entity and the one entitlement read

## Approach

Four pieces, in dependency order, each landing green before the next starts.

1. **`Subscription` on the model layer**, in `apps/identity/models.py`, alias `PERSONAL`,
   `retention_category = BILLING_RECORDS`. One migration carries the table, the partial
   unique index and the user index.

2. **`services/entitlement.py`** — the one published read. Written as a near-sibling of the
   existing `services/recipients.py`: a module whose docstring argues for its own shape, a
   single function returning a primitive, and `__all__` naming just that function.

3. **`services/subscriptions.py`** — three commands, each inside
   `transaction.atomic(using=PERSONAL)`, each calling `audit_service.write_audit`, each
   refusing an event older than `last_event_at`.

4. **Tests**, including an import-contract test that plants the forbidden import and proves
   `models-identity` catches it.

The actor on every webhook-driven transition is a **system actor** — `Actor(kind=SYSTEM,
label="stripe_webhook")` — because `shared/actor.py` requires a system actor to carry a
lowercase label and no id, and the mutation has no human behind it. An admin-initiated
transition would carry a user actor, which is why the commands take `Actor` rather than
assuming one.

## Files to Create

| File | Purpose |
|---|---|
| `backend/apps/identity/services/entitlement.py` | `is_pro(user_id) -> bool` — the single published read |
| `backend/apps/identity/services/subscriptions.py` | `record_subscription_started` / `_changed` / `_ended`, the ordering guard, audit |
| `backend/apps/identity/migrations/000X_subscription.py` | Table, partial unique index, user index |
| `backend/tests/apps/identity/test_subscription_model.py` | Constraints, retention category, no-delete |
| `backend/tests/apps/identity/test_subscription_commands.py` | Idempotency, ordering guard, audit rows |
| `backend/tests/apps/identity/test_entitlement.py` | The status→entitlement mapping, absent row, `past_due` |

## Files to Modify

| File | Change |
|---|---|
| `backend/apps/identity/models.py` | Add `Subscription` and its `SubscriptionStatus` enum |
| `backend/tests/architecture/test_import_contracts.py` | Plant `personalization → apps.identity.models`, assert `models-identity` fails |

`backend/shared/constants.py` is listed in the work item but is **expected to go untouched**:
this item introduces no threshold or duration. Grace timing belongs to Stripe (design
decision), so there is no window constant to name. If that turns out to be wrong during
implementation it will be recorded as a deviation rather than slipped in.

## The interface

```python
# apps/identity/services/entitlement.py
def is_pro(*, user_id: UUID) -> bool: ...

# apps/identity/services/subscriptions.py
def record_subscription_started(
    *, actor: Actor, user_id: UUID, plan: ProPlan,
    customer_ref: str, subscription_ref: str | None,
    current_period_end: datetime | None, event_at: datetime,
) -> Subscription | None: ...

def record_subscription_changed(
    *, actor: Actor, subscription_ref: str, status: SubscriptionStatus,
    plan: ProPlan | None = None, current_period_end: datetime | None = None,
    event_at: datetime,
) -> Subscription | None: ...

def record_subscription_ended(
    *, actor: Actor, subscription_ref: str, event_at: datetime,
) -> Subscription | None: ...
```

Every command is keyword-only, takes an explicit `Actor` and never a `request` — matching the
spine's *"Auth resolved at the API edge"* and the convention `sign_up` already follows.

**`None` is the return for a refused stale event**, not an exception. An out-of-order webhook
is an expected, routine occurrence, not an error condition — item 2's receiver must return
success to Stripe so it stops retrying, and raising here would push that decision into
exception handling.

## Tests

Every test below can fail; none asserts a tautology.

**Model**
- The partial unique index refuses a second `active` row for one user
- It *permits* a second row when the first is `canceled` — history is allowed
- `past_due` also occupies the live slot (it is in the index predicate)
- `retention_category` is `BILLING_RECORDS`, and the `eventpulse.E003/E004` checks pass
- No delete path: a grep-style test asserts no `.delete()` on `Subscription` in `apps/`

**Entitlement**
- Absent row → `False` (total, not an exception)
- `active` → `True`; `past_due` → **`True`**; `canceled` → `False`; `expired` → `False`
- A user with a `canceled` row *and* an `active` row reads `True` (the live row wins)
- `is_pro` returns a `bool`, never a model — asserted by type, so a refactor that leaks a
  `Subscription` fails

**Commands**
- Each writes exactly one `IdentityAuditEntry` with the right `action` and `target_id`
- A replayed command (same `event_at`) applies once; the second returns `None` and writes
  no second audit row
- A **stale** `event_at`, older than the stored one, is refused and leaves the row unchanged
  — including the case that matters most: a stale `_changed(active)` arriving *after*
  `_ended`, which must not restore entitlement
- Concurrent `record_subscription_started` for one user yields one live row, the loser
  catching `IntegrityError` as `sign_up` does
- `write_audit` outside a transaction raises `AuditOutsidePersonalTransaction` — i.e. the
  commands really do open `transaction.atomic(using=PERSONAL)`

**Architecture**
- Planting `from apps.identity.models import Subscription` in `apps/personalization` makes
  the `models-identity` contract fail, and only that contract

## Technical Details

- **`SubscriptionStatus`** is a `StrEnum` on the model module, four members. The
  status→entitlement mapping lives **only** in `entitlement.py`; no caller compares status.
- **The partial unique index** uses `condition=Q(status__in=[ACTIVE, PAST_DUE])` on a
  `UniqueConstraint`, named `subscription_one_live_per_user_uq`, following the existing
  naming convention (`saved_event_user_event_uq`, `notification_preference_quiet_hours_pair_ck`).
- **The ordering guard** compares `event_at` against the stored `last_event_at` with
  `>`, so an equal timestamp is treated as a replay and refused. Stripe can deliver two
  events in one second; the design flagged this, and the `_changed` command therefore also
  compares the incoming status against the stored one so an equal-timestamp *different*
  status is not silently dropped. **This is the one place the plan goes beyond the design
  doc** — see Deviations.
- **No email in any audit row** (AD-13): `details` carries the plan value, the status and the
  subscription reference. The `stripe_customer_ref` is deliberately excluded from `details`,
  since audit rows are long-lived under `AUDIT_LOG` retention.
- **`stripe_customer_ref` must not reach a log sink.** Check it against the allowlist in
  `adapters/logging/redaction.py` during implementation and extend the redaction test if the
  allowlist's shape permits the value through.

## Deviations from the Design

1. **Equal-timestamp handling is specified more tightly than the design doc.** The design
   says commands "refuse an event older than `last_event_at`". Strictly applied, two Stripe
   events in the same second would see the second refused, which could drop a real status
   change. The plan therefore refuses an equal timestamp **only when the status is
   unchanged**, and applies it otherwise. The design's risk table anticipated this
   ("Stripe can deliver two events in the same second"), but its checklist did not. If you
   prefer the stricter literal reading, say so and the test for it changes accordingly.

2. **`shared/constants.py` is expected to be untouched**, where the work item's affected-files
   list named it. Stated above, with the reason.

## Based on Design Doc

`.specs-fire/intents/pro-tier-and-monetization/work-items/subscription-model-and-entitlement-design.md`
(checkpoint 1 approved 2026-11-11), including its correction that this is an **AD-2
`models-identity`** concern, not an AD-3 wall crossing.

---

## Work Item: billing-adapter-and-webhooks

*(checkpoint 2 — plan. Design doc approved 2026-11-11.)*

### Approach

Five pieces, bottom-up, each green before the next.

1. **`stripe` pinned in `pyproject.toml`.** The `stripe-sdk` contract already exists and needs
   no edit. Verify `lint-imports` still reports 19 kept.
2. **`ports/billing.py`** gains `BillingEventKind`, `BillingEvent`, `InvalidWebhookSignature`
   and `parse_event`. The port is what `apps` imports; the SDK never leaves `adapters.billing`.
3. **`adapters/billing/fake.py`** implements `parse_event` **first**, before the real adapter.
   Everything above the adapter can then be built and tested without the SDK, which is the
   whole point of the seam.
4. **`adapters/billing/stripe.py`** — checkout, portal, parse-and-verify, status mapping.
5. **`apps/identity/webhooks_api.py`** — raw-body read, dispatch to item 1's three commands,
   200/400 discipline.

### Files to Create

| File | Purpose |
|---|---|
| `backend/adapters/billing/stripe.py` | The real adapter |
| `backend/apps/identity/webhooks_api.py` | The receiver |
| `backend/tests/adapters/test_billing_stripe.py` | Adapter tests, no network |
| `backend/tests/identity/test_billing_webhooks.py` | Receiver tests, through the fake |

### Files to Modify

| File | Change |
|---|---|
| `backend/pyproject.toml` | Pin `stripe` |
| `backend/ports/billing.py` | The event value, its kinds, the exception, `parse_event` |
| `backend/adapters/billing/fake.py` | Implement `parse_event` deterministically |
| `backend/config/adapters.py` | `billing` into `REAL_ADAPTERS` |
| `backend/config/api.py` | Mount the webhook router |
| `backend/config/env.py` | `stripe_api_key`, `stripe_webhook_secret` — required, no default |
| `.env.example` | Local-only placeholders |
| `backend/tests/config/test_adapters.py` | Assertion now names `email, embedding, llm` |
| `backend/tests/adapters/test_fakes.py` | Cover the fake's new `parse_event` |

### Tests

- **Signature:** a wrong signature raises `InvalidWebhookSignature` in the adapter, and the
  endpoint answers 400 with no state change.
- **Raw bytes:** a payload whose re-serialised JSON differs byte-for-byte from what was posted
  still verifies — proving the endpoint did not parse before verifying.
- **Each kind** reaches exactly one command.
- **Replay:** the same event twice changes state once, answered 200 both times.
- **Out of order:** a stale `updated` after a `deleted` does not restore entitlement, asserted
  through the endpoint rather than only at the command level.
- **Unknown event type** → 200, no state change.
- **Unknown subscription** → 200, no state change.
- **Unmapped Stripe status** → the conservative fallback, not a crash.
- **`ADAPTER_MODE=real` still refuses to boot**, naming `email, embedding, llm`.

### Risk to flag early

`stripe` is a new dependency and `uv` may need network to resolve it. This is checked **first**,
before any code is written, so a blocked install is discovered immediately rather than after
four files exist. If it cannot be installed, the item stops and is reported — the port, the
fake and the receiver would still be buildable, but shipping a real adapter that was never
imported is not something to claim.

### Deviations from the Design

None at plan time. Two design decisions are worth restating because they are the ones most
likely to be "simplified" later: **no idempotency table** (item 1's row guards already cover
it) and **`PAYMENT_FAILED` as its own kind** (Stripe does not say what the status became).

### Based on Design Doc

`.specs-fire/intents/pro-tier-and-monetization/work-items/billing-adapter-and-webhooks-design.md`
(checkpoint 1 approved 2026-11-11).

---

## Work Item: checkout-and-portal-api

*(checkpoint 1 — plan. No design doc; the decisions were taken in items 1 and 2.)*

### Approach

The endpoints are thin. The work is in the **refusals** and in **where the URLs come from**.

Four pieces, bottom-up, each green before the next.

1. **`apps/identity/services/billing.py`** — the service layer. It resolves the caller's
   subscription, decides whether checkout or portal may proceed, and calls the billing port.
   The API layer stays thin: it resolves the user, parses the body, calls the service,
   projects the result.
2. **`apps/identity/billing_api.py`** — the two endpoints. Auth on the **router**
   (`auth=current_user`), as `personalization`'s and `delivery`'s are, so the user id comes
   from the session and never from a payload.
3. **`frontend/app/dev/fake-billing/`** — the checkout and portal stand-in pages, matching
   the query parameters `FakeBillingAdapter` emits.
4. **`config/env.py`** — the success and cancel URLs, derived from `frontend_base_url`.

#### The three refusals, and what each says

| Situation | Answer | Why not something else |
|---|---|---|
| The caller is already Pro | 409, pointing at the portal | A second checkout would create a second subscription the user has to cancel. The portal is where an existing subscription is managed. |
| The caller has no subscription | 409, on the portal endpoint | A clear refusal, not a provider error. `create_portal_session` needs a `customer_ref`, and a user with no subscription has none — so the endpoint must refuse before it calls the port, not translate a missing customer into a provider error. |
| A client-supplied success or cancel URL | The URL is ignored entirely | The request body carries **only the plan**. Success and cancel URLs come from configuration. Taking them from the request is the classic open-redirect in a checkout flow: a crafted `success_url` sends a paying user to an attacker's page and the `next` parameter carries the session id. |

#### Entitlement is never granted here

**Returning from a successful checkout changes nothing by itself.** Only the webhook from
`billing-adapter-and-webhooks` moves `Subscription` state. So the checkout endpoint creates a
session and returns a URL — it writes nothing. There is no `Subscription` row, no audit entry,
and no entitlement read that could be mistaken for a grant.

The fake dev page makes this walkable: its "complete" button **does not** grant Pro either. It
shows the URL the real provider would redirect to and, in fake mode, explains that the
webhook is what flips entitlement. The end-to-end proof in `e2e-proof-and-contract-tests`
posts the fake webhook.

#### The URLs are derived, never transmitted

`success_url` and `cancel_url` are built from `settings.FRONTEND_BASE_URL` plus a fixed path
each. The plan the user chose reaches the provider as the price id, chosen by the adapter from
`settings.STRIPE_PRICE_IDS` — never from the client.

The fake adapter needs the *plan* in its URL so the dev page can name it; that is the fake's
own shape and it is not a URL the client supplied.

### Files to Create

| File | Purpose |
|---|---|
| `backend/apps/identity/services/billing.py` | The service layer: refusals, port calls, URL derivation |
| `backend/apps/identity/billing_api.py` | The two endpoints |
| `backend/tests/identity/test_checkout_portal_api.py` | Contract tests for both endpoints |
| `frontend/app/dev/fake-billing/checkout/page.tsx` | The fake checkout page |
| `frontend/app/dev/fake-billing/portal/page.tsx` | The fake portal page |
| `frontend/app/dev/fake-billing/fake-billing-panel.tsx` | The shared harness UI |
| `frontend/app/dev/fake-billing/checkout/page.test.tsx` | Vitest for the checkout page |
| `frontend/app/dev/fake-billing/portal/page.test.tsx` | Vitest for the portal page |

### Files to Modify

| File | Change |
|---|---|
| `backend/apps/identity/schemas.py` | `CheckoutIn`, `CheckoutOut`, `PortalOut` |
| `backend/config/api.py` | Mount the billing router |
| `backend/config/env.py` | `billing_checkout_path`, `billing_cancel_path`, `billing_portal_return_path` — the fixed paths the URLs are built from |
| `backend/config/settings.py` | Expose `FRONTEND_BASE_URL` and the three paths to `settings` |
| `frontend/lib/api/openapi.json` | Regenerated |
| `frontend/lib/api/schema.ts` | Regenerated |

### Tests

- **A Pro user cannot start a second checkout** — 409, and the response points at the portal.
- **A user with no subscription gets a clear refusal** from the portal endpoint — not a
  provider error, and the port is never called.
- **A checkout grants nothing** — after the endpoint answers 200 and the user visits the
  success URL, `is_pro` is still `False` and there is no `Subscription` row. **This is the
  acceptance criterion that matters most**, and it is a test rather than a comment.
- **A client-supplied success or cancel URL is ignored** — the returned URL comes from
  configuration. A body carrying `success_url` pointing at an attacker's host is refused or
  ignored, and the minted session URL contains only the configured origin.
- **The plan reaches the adapter**, and an unknown plan is a 422.
- **An anonymous caller gets 401** on both endpoints.
- **The dev pages** render for the fake's query parameters and offer both outcomes.

### Risks to flag early

- **The fake dev page must not be mistaken for the pricing page.** `frontend-pricing-page`
  is a separate item and a different route; this one lives under `/dev/`, is `notFound()` in
  production, and says plainly that it is a development stand-in.
- **`frontend/lib/api/schema.ts` is regenerated**, and CI's contract job diffs it. If the
  OpenAPI export drifts, that job fails — so `make client` is run and committed with the
  change, not left for CI to complain about.

### Deviations from the Design

No design doc for this item. The cross-item contract it inherits — the checkout session must
carry the `user_id` metadata, or a paid checkout can never be attributed — was recorded in
`billing-adapter-and-webhooks-design.md` and is honoured here: the adapter sets it from
`BillingCustomer.user_id`, and the endpoint passes the session user's id and nothing else.

### What the build actually produced

The plan's shape held. Four things changed against it, all recorded in `test-report.md` and
`review-report.md`:

1. **`frontend/lib/api/openapi.json` and `schema.ts` regenerated.** The plan named them
   under "Files to Modify"; item 2's report records the same omission causing a regression
   there, so `make client` was run in the same session rather than left for CI.
2. **Two architecture tests modified** (`test_no_direct_writes.py`,
   `test_digest_composition_separation.py`). Both assert on the set of surface files, and
   the new module changes that set. Neither guard was weakened — both now name the new
   module explicitly.
3. **The service looks the billing port up at call time** (`registry.get_billing_port()`)
   rather than binding the function at import time. Not a style choice: it is what makes
   the port boundary substitutable, and the test that substitutes it caught the mistake
   when the import was bound.
4. **The dev page honours a `next` only on this origin.** Found in review. The plan had
   the backend refusing a client-supplied URL; it had not thought about the dev page
   reading one out of a query string — which is attacker-controllable by anyone who can
   hand a developer a link. The dev page now applies the same rule.

One path the plan did not foresee: **`/settings/billing` does not exist yet.** The success,
cancel and portal-return paths all point at it, because
`frontend-account-and-billing-settings` depends on this item and will build that surface.
Until it lands, the dev checkout's "Complete" and "Cancel" links both 404 locally. The
backend's part is right — the route is the account settings surface by agreement — but the
local paid path is not fully walkable until that item lands, and it is worth saying so
rather than discovering it mid-item.

---

## Work Item: free-tier-caps-read-entitlement

*(checkpoint 1 — plan. No design doc; the decisions were taken in items 1 and 2.)*

### Approach

Two caps, one concern: **both must ask who is Pro.** They are one item because they share
the entitlement read, and splitting them would mean wiring that read twice.

#### The save gate (FR-49)

The gate does not exist. There is no constant, no check, and nothing on the save path —
so the product has no upgrade trigger at all.

**Where it goes.** `apps/personalization/services/saved_events.py`, in `save_event`. The save
already takes `user_id`, so the entitlement read and the throttle check both have what they
need.

**The order inside `save_event` is the whole design.** Three rules, in this sequence:

1. **The idempotence check comes first.** A repeat save of an already-saved event returns
   the same row and is *not* gated. This is not a convenience: `saved_events.py:119` says
   *"Saving the same event twice is idempotent: one row, not two"*, and
   `tests/e2e/test_save_race.py::test_a_save_is_idempotent_and_one_row` asserts `201` then
   `200` with one row. A gate that refused the second POST would break that contract —
   and correctly so, because nothing new is being saved. A user re-opening an event they
   already saved is not spending an allowance.
2. **Then the throttle check, and only for a save that will actually happen.** The gate is
   declared through `ThrottlePort.check(key, limit, window_seconds)`, as `EventReport`
   already does — not hand-rolled, and not a row count.
3. **Then the write.** A refused save writes nothing: no partial `SavedEvent`, no audit row,
   no conflict pair.

**The one judgement call, stated plainly.** `ThrottlePort.check` counts an attempt *by
definition* — both adapters (`INCR` in Redis, an append in memory) advance the counter
before deciding. So a refused save does advance the counter. What it does **not** do is
cost the user time: the window is anchored at the *first* attempt, so the allowance frees
up 24 hours after their first save, not 24 hours after the refusal. The refused attempt
cannot push the wait out, and it cannot shorten it. That is what *"no throttle consumed by
a save that did not happen"* has to mean given a port with exactly one operation — and the
alternative (hand-rolling a counter that only advances on success) is what the item
explicitly forbids.

**The refusal.** A new `SaveCapReached(ConflictError)` → **409**, `code = "save_cap_reached"`,
with `details = {"cap": 1, "upgrade_hint": "…"}` — the exact shape
`CalendarProviderCapReached` uses, and the item names that as the reference.

- **The status code is 409, not 429.** `ThrottledError` (429) is a *rate* limit: come back
  later. A save cap is a *tier* limit: the remedy is to upgrade, not to retry. The item
  names `CalendarProviderCapReached` as the shape reference, and that is a `ConflictError`
  → 409.
- **Its own `code` slug**, so the two 409s on this endpoint stay distinguishable: the
  endpoint already answers 409 with `SchedulingConflictError`, and the frontend branches
  on the code. `calendar_cap_reached` and `save_cap_reached` cannot be confused.
- **The sentence is `EXPERIENCE.md` §3's "Free-tier save-cap prompt" row**:
  *"You saved one event today. Save more with Pro."* §4's Browse line (*"You've used your
  1 free save today…"*) is a different surface's failure-mode copy; §3 is the canonical
  statement of this prompt, and the item cites §3 and §4 as applying unchanged.
- **No modal-shaped field.** `details` is exactly `{"cap", "upgrade_hint"}` — no `modal`, no
  `title`, no `actions`, no `dismissable`.

#### The provider cap (FR-50)

The cap becomes entitlement-chosen: **1 for Free, 3 for Pro**.

The constant `FREE_TIER_CALENDAR_PROVIDER_CAP = 1` and its stale comment (*"Every user is
Free in this intent (there is no SUBSCRIPTION entity yet)… The Pro cap of 3 is a later
intent and belongs here when it lands"*) are **replaced**, not edited around. The comment is
resolved because the `Subscription` entity now exists and this is the intent it was waiting
for.

**The reuse path still behaves.** `calendar_connections.py:403-408` decrements the
occupying count when a `needs_reconnect` row is being reused, because the reused row does
not add a slot. That arithmetic is unchanged and still correct under a cap of 3 — a reused
row occupies one slot and adds none.

**The asymmetry is preserved.** The provider cap is enforced at the *connect* step; the
save cap at the *save* step. Neither is enforced at read time. A Pro user who lapses keeps
their existing connections and their existing saves — **this item deletes nothing on
downgrade**, which the brief leaves open and the item forbids quietly answering.

#### Both caps read entitlement the one way

`is_pro(user_id=…)` from `apps.identity.services` — the published read from item 1, which
returns a bool and nothing else. `apps.personalization` may import it: the
`models-identity` contract protects `apps.identity.models` (only `apps.identity` may import
it) but says nothing about the service, and
`tests/architecture/test_import_contracts.py:226-228` plants exactly this import into
`apps/personalization/_planted.py` and asserts no contract breaks. Entitlement crosses the
database wall **by value** (a bool), which is AD-3 satisfied.

Neither cap reimplements "is Pro", and neither holds its own copy of the mapping.

### The decisions this plan settles

| Question | Decision | Why |
|---|---|---|
| Status code for a refused save | **409**, `code = "save_cap_reached"` | A tier limit, not a rate limit. 429 says "come back later"; the remedy is to upgrade. Matches the item's named shape reference. Its own slug keeps it apart from the endpoint's existing 409. |
| The `upgrade_hint` sentence | *"You saved one event today. Save more with Pro."* | `EXPERIENCE.md` §3, the Free-tier save-cap prompt row. §4's Browse line is a different surface's copy. |
| Gate placement | **After the idempotence check, before the write** | A repeat save of an already-saved event is not a new save. Keeps `test_a_save_is_idempotent_and_one_row` green, and keeps "no throttle consumed by a save that did not happen" true. |
| Counting | Through `ThrottlePort.check`, counting attempts | Required by the item. The refused attempt advances the counter but cannot move the window, so it costs the user no time. |
| The provider cap's constant | **Replaced**, comment and all | The comment was a placeholder for this item; leaving it stale is what the item forbids. |
| Where the cap value comes from | `is_pro(user_id=…)` → 1 or 3 | The single published read. The cap is a function of entitlement, so the two tiers are one rule with two values, not two rules. |

### Files to Create

| File | Purpose |
|---|---|
| `backend/tests/personalization/test_save_cap.py` | The save gate: the refusals, the payload shape, the Pro bypass, the lapse-back |
| `backend/tests/personalization/test_calendar_provider_cap.py` | The tiered provider cap: 1 for Free, 3 for Pro, and the reuse path |

### Files to Modify

| File | Change |
|---|---|
| `backend/shared/constants.py` | `FREE_TIER_SAVE_DAILY_LIMIT`, `FREE_TIER_SAVE_WINDOW_SECONDS`; the provider-cap constants and their stale comment |
| `backend/domain/errors.py` | `SaveCapReached(ConflictError)` |
| `backend/apps/personalization/services/saved_events.py` | The gate: idempotence first, then the throttle check, then the write |
| `backend/apps/personalization/services/calendar_connections.py` | The cap becomes entitlement-chosen |
| `backend/apps/personalization/api.py` | The save endpoint's response map gains the new refusal |

### Tests

**The save gate**

- A Free user's **second distinct save** in the window is refused, and the first is not.
- The refusal payload is **exactly** `{"cap": 1, "upgrade_hint": "You saved one event today.
  Save more with Pro."}` — and carries no modal-shaped field.
- **A refused save changes nothing**: no `SavedEvent`, no audit row, and the user's wait is
  not extended by the refusal.
- **A Pro user saves 10+ events in a day** with no soft wall.
- **A repeat save of an already-saved event is not gated** — the idempotence contract holds.
- A Pro user who **lapses back to Free** is refused again.

**The provider cap**

- A Free user still cannot connect a second provider; a Pro user connects a second and a
  third and is refused a fourth.
- The **reuse path** still reuses rather than adding a slot, at both caps.
- A Pro user who **lapses back to Free** is refused a second connection.

**Both**

- Each cap reads entitlement through the one `is_pro` read — asserted by the architecture
  suite, which already plants that import.

### Risks to flag early

- **The gate must not break idempotence.** This is the risk that would bite the existing e2e
  suite, and it is why the order above is idempotence-first rather than gate-first.
- **`frontend-upgrade-prompts` owns the rendering.** This item produces the payload; the
  frontend's handling of a save-cap refusal is that item's work, and it is `pending`. The
  frontend today would show a save-cap refusal as a generic failure — correct, and not
  this item's to fix.
- **The provider cap change touches a shipped path.** `CalendarProviderCapReached` and its
  exact `{"cap", "upgrade_hint"}` shape are already asserted by
  `tests/personalization/test_calendar_connect_api.py:374` and
  `tests/e2e/test_onboarding_and_calendar_proof.py:634`. Those assertions must still hold —
  for a Free user, whose cap is still 1.

### Deviations from the Design

No design doc for this item. The entitlement read it inherits — `is_pro`, returning a bool
and nothing else — was fixed by `subscription-model-and-entitlement`, and both caps use it
as-is.

---

## Work Item: frontend-pricing-page

### Approach

**One screen, two tiers, no upsell.** The page is built from `pricing-page-desktop.html`, at
`$4.99/month or $49/year`, and the copy comes from FR-48 — *"Pricing page is a single screen;
no upsell copy beyond 'fewer interruptions, more control.'"* The mockup is the authority on
layout; the PRD is the authority on copy.

**The constraint that shapes everything: there is no way to ask "is this user Pro?" over
HTTP.** `GET /api/auth/me` deliberately carries no entitlement field, and the billing router
has exactly two endpoints — `POST /api/billing/checkout` and `POST /api/billing/portal` —
both of which are *actions*. There is no read.

Yet the criterion says: *"A user who is already Pro sees their current plan and a link to the
portal, not a second buy button."* A page that renders a buy button to a Pro user and only
reveals the truth when the click is refused does not meet that. So the page needs a read, and
the smallest honest one is added here.

#### The entitlement read — `GET /api/billing/subscription`

**Why an endpoint, and why here.** The intent brief says the entitlement read is *"a single
entitlement read answers 'is this user Pro?' for every caller"* — and it exists, as
`apps.identity.services.is_pro`. It is a **service**, not an HTTP endpoint, and the frontend
cannot call a service. Something has to carry it over the wire.

The three candidates were weighed:

1. **Infer it from the checkout 409.** A Pro user's checkout is refused with
   `already_subscribed`. But discovering a user's tier by *attempting to charge them* is
   wrong on its face, and it means a Pro user is shown a buy button first — which is exactly
   what the criterion forbids.
2. **Infer it from the portal 409.** A Free user's portal request is refused with
   `no_subscription`. But `POST /api/billing/portal` **mints a portal session** — probing it
   on page load would create a real session for every Pro user who merely looked at the
   pricing page, on every visit. A read that has a side effect is not a read.
3. **Add a read-only endpoint.** `GET /api/billing/subscription` returns the caller's own
   entitlement, and nothing else.

**Option 3 is the one taken.** It is the smallest thing that satisfies the criterion, it
sits beside the two endpoints that already answer questions about the same state, and it is
read-only — no session is minted, no provider is called, nothing is written.

**It carries the minimum, and it is honest about what it does not know.** The response is
`{is_pro: bool}` — and *only* that. Not a plan, not a renewal date, not a status: this
endpoint reads entitlement, and the fuller subscription record (plan, period end, the
past-due state) belongs to `frontend-account-and-billing-settings`, whose criterion is
*"the current plan — Free, or Pro with its billing period and renewal date — read from
`Subscription`"*. That item will need a wider read and will build it there. This one answers
exactly the question the pricing page asks: **may this person buy a plan?**

**It reuses the one published read.** The endpoint calls `is_pro(user_id=...)` — the same
function the save gate and the provider cap call. It does not re-derive "is Pro" from a
status, so the pricing page and the caps cannot disagree about who is Pro.

**`is_pro` is `True` for `past_due`.** A lapsed-by-dunning user is still Pro to this
product, and the pricing page will show them Pro. That is the right answer here: their
payment failed, and the place to fix it is the portal — which `frontend-account-and-billing-settings`
will surface. A user whose subscription was actually **cancelled** has no live row, so
`is_pro` is `False`, and they are Free — which is right, and is exactly the state in which
buying a plan again is correct.

#### The three visitor states

The criterion names them, and they are three different pages sharing one layout:

| State | The Free column | The Pro column |
|---|---|---|
| **Signed out** | Both tiers shown; choosing a plan routes to sign-in | Both tiers shown; choosing a plan routes to sign-in |
| **Free** | Free column is the current plan | Pro column carries the buy button |
| **Pro** | Free column still shown, as what Free is | Pro column shows the current plan + a portal link, **no buy button** |

**A signed-out visitor can read the page and is routed to sign-in on choosing a plan** —
rather than hitting an authentication error. The page is *public*, so it must not use
`AppShell` (which is the authed frame with a sidenav). It uses the pre-auth frame: the brand
topbar, the content, and the pre-auth footer. The route reads the session to decide which of
the three states it is, but **an anonymous session is not an error** — it is the first state.

**Routing to sign-in, not to an error.** The sign-in route takes a `next` parameter — let me
verify that — and the pricing page sends the visitor there with a return path, so a signed-out
visitor who signs in lands back on the pricing page rather than at the digest home. That is
the difference between "routed to sign-in" and "hit an authentication error": the first
remembers where they were going.

#### The page's structure

The mockup's layout, in the project's tokens:

- **Hero** — the eyebrow, the headline, the lede. The mockup's lede is *"Free is plenty for
  most people. Pro adds unlimited saves, calendar sync, custom quiet hours, and your data on
  your terms. Cancel anytime."* — which is **descriptive, not upsell**, so it stays. The
  Pro tier's tagline is *"Fewer interruptions, more control."* — FR-48's own sentence.
- **Billing toggle** — Monthly / Annual, with the mockup's *"save 18%"* pill. The PRD says
  the annual price is a ~17% discount and the mockup says 18%. The **PRD wins on copy** —
  but the mockup's number is what the mockup draws. Hmm. Let me settle this in the plan: the
  annual plan is **$49/year against $4.99/month**, which is $59.88 a year — so the discount is
  **18.2%**. The mockup's "save 18%" is arithmetically right, and the PRD's "~17%" is the
  looser statement of the same fact. **"Save 18%" stays.**
- **Two tier cards** — Free and Pro, with the feature lists drawn from FR-48 (below).
- **The trust strip** — three items: cancel anytime, your data is yours, no dark patterns.
  This is the one block most at risk of reading as upsell, and it is not: it states *product
  policies* ("No urgency badges. No countdown timers."), which is the opposite of upsell
  copy — it is the product telling the visitor it will not pressure them.
- **The footer** — the mockup's "Questions? hello@eventpulse24.com" line.

#### The feature lists, from FR-48

The criterion is explicit about what each column says, and the PRD is the source:

**Free keeps:** Pulse Digest, Reminders, Personal Events, the 1-save/day cap, 1 connected
calendar provider.

**Pro adds:** unlimited saves and collections, 3 providers, per-weekday quiet hours, data
export.

**The mockup's lists are close but not the PRD's.** The mockup's Free column lists "Public
share-link sharing" and "One quiet hours window" — neither is in FR-48's Free list — and
its Pro column lists "Google Calendar sync (read-only)" and "Priority support from Brooklyn"
and "Phase 2 included: …", which FR-48 does not list. FR-48 wins on copy. The lists are
FR-48's, phrased plainly.

**The one that needs care is the cap.** FR-48 says Free retains *"the 1-save/day cap and 1
connected calendar provider"*. That is a statement about **limits**, and listing a limit
among *features* reads oddly — but it is exactly what the criterion asks the page to state,
and it is honest: the Free column that says "1 save a day" is what a Free user actually gets.
It is stated as a fact about the plan, not as a tease.

#### Choosing a plan

**The browser calls the checkout endpoint and follows the URL.** `POST /api/billing/checkout`
with `{plan: "monthly" | "yearly"}` returns `{url}` and the browser navigates to it. The
plan value is the `ProPlan` enum — `monthly` / `yearly` — and nothing else is sent.

**The refusal is handled, not swallowed.** The backend refuses a Pro user's checkout with
409 `already_subscribed` carrying `portal_path`, and a signed-out visitor's with 401. The
page's behaviour on each:

- **200** → navigate to the URL. The provider's hosted checkout takes over.
- **401** → route to sign-in with a return path.
- **409 `already_subscribed`** → the user is Pro after all (their plan arrived between the
  page's read and the click). The page swaps to the Pro state and shows the portal link,
  with a calm line saying so.
- **anything else** → a calm inline failure line. **No modal** — the same rule the cap
  prompts follow (EXPERIENCE.md §3), and the same rule the whole page follows.

**A redirect, not `fetch`.** The URL is a provider's hosted page. The browser goes there;
the API's own response is not a page.

#### Reachability from navigation

The criterion says the page must be reachable from navigation. Two places, both real:

- **The pre-auth footer** — a "Pricing" link. The footer is the conversion surface
  ("Log in", "Sign up free" live there), and the pricing page is reachable from every
  pre-auth route for free.
- **The sidenav's account row** — the account sheet gains a quiet "Pricing" link, so a
  signed-in user can find it. The account panel's own rule is *"an affordance that cannot
  work is the same lie as a link to a 404"* — `/pricing` will exist, so the affordance is
  honest.

**The sidenav does not gain a seventh row.** The rail's six routes are locked
(*"Digest / Timeline / Add / Browse / Conflicts / Settings"*), and the account sheet is
where a second destination belongs.

#### Mobile width

The two tier cards are a two-column grid at desktop and **one column at mobile** — the
cards stack, and the page is one scroll. The billing toggle stays a single row. Nothing is
hidden at small widths; the mockup's trust strip is one column of three at mobile.

### The decisions this plan settles

1. **A read-only entitlement endpoint, `GET /api/billing/subscription`, returning
   `{is_pro}`.** Chosen over inferring the tier from either action endpoint's 409, both of
   which either show a Pro user a buy button or mint a portal session on page load.
2. **The endpoint returns the minimum.** The fuller subscription record belongs to
   `frontend-account-and-billing-settings`, which owns "the current plan … with its billing
   period and renewal date".
3. **The page is public.** It uses the pre-auth frame, not `AppShell`, and an anonymous
   session is a state rather than an error.
4. **FR-48's feature lists, not the mockup's.** The mockup lists Phase 2 features, "priority
   support from Brooklyn", and share-links; FR-48 does not, and FR-48 is the authority on
   copy.
5. **"Save 18%" stays.** $49 against $4.99×12 is an 18.2% discount, so the mockup's number
   is arithmetically right and the PRD's "~17%" is the looser statement of the same fact.
6. **The Pro user's portal link comes from the same endpoint family** — `POST
   /api/billing/portal` — and is a *button*, not a buy button. Opening the portal is an
   action, so it is a POST that returns a URL to follow.
7. **The trust strip stays.** It states product policies, which is the opposite of upsell
   copy.
8. **No modal anywhere on the page.** Every refusal is an inline line.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/tests/identity/test_billing_subscription_api.py` | The entitlement endpoint's tests |
| `frontend/app/pricing/page.tsx` | The `/pricing` route — a server component that reads the session and the entitlement |
| `frontend/app/pricing/page.test.tsx` | The three visitor states, and the route's own rules |
| `frontend/components/pricing/pricing-page.tsx` | The screen — the hero, the toggle, the two tiers, the trust strip |
| `frontend/components/pricing/pricing-page.test.tsx` | The tier columns, the copy rules, and the no-upsell rule |
| `frontend/components/pricing/choose-plan-button.tsx` | The client island: the checkout call, the refusals, the redirect |
| `frontend/components/pricing/choose-plan-button.test.tsx` | The checkout call and each refusal |

### Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/identity/billing_api.py` | `GET /api/billing/subscription` |
| `backend/apps/identity/schemas.py` | `SubscriptionOut` — `{is_pro}` |
| `backend/apps/identity/services/billing.py` | `read_entitlement` — the read, over `is_pro` |
| `frontend/components/pre-auth/pre-auth-footer.tsx` | A "Pricing" link |
| `frontend/components/shell/account-menu.tsx` | A quiet "Pricing" link in the account sheet |
| `frontend/lib/api/openapi.json` | Regenerated |
| `frontend/lib/api/schema.ts` | Regenerated |

### Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/identity/test_billing_subscription_api.py` | 200 with `is_pro` true and false; 401 for an anonymous caller; no write; no provider call |
| `frontend/app/pricing/page.test.tsx` | The three visitor states; the route renders for an anonymous visitor; the Pro state has no buy button |
| `frontend/components/pricing/pricing-page.test.tsx` | The prices; the FR-48 feature lists; **no upsell copy**; the trust strip; mobile |
| `frontend/components/pricing/choose-plan-button.test.tsx` | The checkout call carries the plan; the 200 redirects; the 401 routes to sign-in; the 409 swaps to the Pro state; the failure is inline |

### Risks to flag early

1. **The entitlement endpoint is a backend change in a frontend item.** It is deliberate and
   it is the minimum — but it is a deviation from "the plan's file list", and it is recorded
   as one.
2. **`is_pro` is `True` for `past_due`.** So the pricing page shows a past-due user as Pro.
   That is right (their payment failed; the portal is where they fix it) and it is
   `frontend-account-and-billing-settings`'s job to make the *reason* visible. It is called
   out here so it is a decision rather than a surprise.
3. **The `/pricing` route and `frontend/app/settings/billing`.** Item 3 pointed the backend's
   success/cancel/portal-return paths at `/settings/billing`, which **does not exist yet** —
   it is `frontend-account-and-billing-settings`'s to build. The pricing page does not
   depend on it (it never navigates there), but a completed local checkout lands on a 404
   until that item lands. That gap is inherited, not created here.
4. **`make client` must be run**, or the OpenAPI contract test fails — the same omission
   that caused a regression in item 2.

### Deviations from the Design

(none yet — this plan has no design doc; the mockup and FR-48 are the sources)

### What this plan does not deliver

**The inline upgrade prompt at the cap.** `frontend-upgrade-prompts` owns it, and it depends
on this item. The pricing page is where that prompt's "Upgrade" link will point.

**The account settings surface.** `frontend-account-and-billing-settings` owns the current
plan, the renewal date, the past-due state, and "Download my data". This page answers one
question — *may this person buy a plan?* — and no more.

---

# Work Item: `frontend-upgrade-prompts` — the prompt at the cap

## Implementation Plan for "The prompt at the cap — calm, inline, and finally going somewhere"

### Approach

**The backend already speaks this language. The frontend does not listen yet.**

Two endpoints refuse at a cap with the *same* payload shape — `{cap, upgrade_hint}` and
nothing else:

| Source | Endpoint | `code` | `upgrade_hint` |
|---|---|---|---|
| The save cap (FR-49) | `POST /api/personal/saved-events/{id}` | `save_cap_reached` | "You saved one event today. Save more with Pro." |
| The calendar cap (FR-50) | `POST /api/personal/calendars` | `calendar_cap_reached` | "Save more with Pro." |

The payload's key set is pinned to exactly `{cap, upgrade_hint}` by three backend tests, and
the e2e test additionally asserts the **absence** of `modal`, `title`, `actions` and
`dismissable` **by name**. The backend payload was shaped to make the wrong thing hard to
build. This plan does not route around that.

**So the frontend's job is to build exactly one thing, and the backend's payload dictates its
shape: a calm inline prompt with a quiet "Upgrade" link.**

#### The three findings that shape the work

**1. `readApiError()` drops `details` entirely.** `frontend/lib/api-errors.ts:78-89` returns
`{code, message, fieldErrors}` — and `fieldErrorsFrom` reads only `details.errors`. The
`upgrade_hint` lives on `details.upgrade_hint`, so **it is currently unreachable through the
one shared error helper**. This is the "existing error-to-UI path" the work item's Technical
Notes points at, and the fix belongs *in that path*, not in a special case beside it.

**2. A half-built precedent already exists, and it renders the wrong sentence.**
`frontend/components/onboarding/calendar-step.tsx:186-190` already handles
`calendar_cap_reached`, and `:297-312` already renders an inline prompt with an "Upgrade"
link to `/pricing`. **It renders `failure.message`** — the generic error sentence ("You've
connected the calendars your plan allows.") — **not `details.upgrade_hint`**. The criterion
says the prompt renders from the server's `upgrade_hint`. So this is an extraction *and* a
correction: one component, serving both caps, reading the right field.

**3. The save cap has no render at all.** `frontend/components/detail/detail-actions.tsx:196-213`
narrows the 409 on `code`, but only handles `scheduling_conflict`; a `save_cap_reached` falls
to `else { setFailed(true) }` and shows "Couldn't save that. We'll try again on your next
change." — which is **false**: the save was not going to be tried again, and the button is
still there inviting the same refusal.

#### The Pro problem, and how it is solved

The criterion is *"A Pro user never sees it, under any state — including immediately after
upgrading, without a page reload."*

Today the frontend has **exactly one** entitlement read — `GET /api/billing/subscription`
returning `{is_pro}` — and it is used in **exactly one place**: `app/pricing/page.tsx`. There
is no client-side Pro hook, no context, no cache. The Detail Screen and the onboarding step
have **no** Pro knowledge at all, so there is nothing that could keep the prompt away from a
Pro user.

**The resolution: a Pro user is never refused a cap in the first place.** The backend's cap
check is `is_pro`-aware — `check_save_allowed` returns early for a Pro user, and
`_provider_cap` returns the tier's own cap. So a Pro user **never receives** a cap refusal.
The prompt renders *from a refusal*, and a Pro user receives no refusal, so a Pro user sees
no prompt. **The guarantee is the server's, not the frontend's** — which is the right place
for it, because only the server knows the tier at the moment of the write.

**"Immediately after upgrading, without a page reload"** is then covered by the same
argument: the upgrade changes the server's answer to the next save, so the next save is
allowed. There is no stale client-side Pro flag to go out of date — because there is no
client-side Pro flag. **This is the reason to *not* add one**: a cached Pro boolean would be
the thing that could go stale and show a Pro user a paywall.

**And the prompt is still rendered from a refusal, not from a client-side tier check.** If a
Pro user *does* somehow receive a cap refusal (a stale provider cap, a race), the component
renders it — because the server said so, and the server is the authority. Hiding it on the
client would be the frontend second-guessing the backend.

#### The decisions

**The link target is `/pricing`.** The work item's criteria say `/pricing`, and that route
exists (item 5). `EXPERIENCE.md` §4 line 382 says `/settings/plan` — a route that does not
exist and never has. **`/pricing` is the authority**; the older line predates the pricing
page.

**The link's text.** The mockup says "Upgrade →" in its states; `EXPERIENCE.md` §4 says a
`Text.Meta` "Upgrade" link. The existing `calendar-step.tsx` precedent says "Upgrade". The
component keeps "Upgrade" — quiet, one word, and matching the precedent it replaces.

**The hint is rendered verbatim.** The component takes the `upgrade_hint` string and prints
it. The frontend writes **no** sentence of its own, so a backend copy change is a backend
change. **This is asserted**, not just intended.

**It is inline, and the inline-ness is asserted.** The component renders a `<div>` with a
`<p>` and a link. It has no `role="dialog"`, no `role="alertdialog"`, no `aria-modal`, no
overlay, and it never takes focus. The tests assert the **absence** of every modal-ish
attribute, because "it is never a modal" is a criterion and a criterion wants a test.

**`role="status"`, not `role="alert"`.** The mockup's inline toast is `role="status"`
`aria-live="polite"`. The existing `calendar-step.tsx` uses `role="alert"`. A cap is not an
error condition the user must be interrupted for — it is a state the page reports — so
`role="status"` is the polite one and is the mockup's. It also does not steal focus, which
is what "does not steal focus" means in practice.

**No dismissal.** The payload carries no `dismissable` field "by design", and the criterion
says the frontend must not invent one. So there is **no dismiss button** and **no dismissal
state**. The prompt clears when the action succeeds or when the surface unmounts — and that
is the whole of its lifecycle. **A "Not now" button is not added**, even though the mockup
shows one: a dismissal that persists is a setting the payload refuses to describe, and a
dismissal that does not persist is a button that does nothing. This is called out because
the mockup shows it and this plan does not build it.

**The cap number is not rendered.** The payload carries `cap`, and the component does not
print it. The mockup's muted-footer state prints "1 of 1 free save used today", but that is
a *different* surface (the Browse card's disabled state, which has its own component and its
own item). The prompt's job is the sentence and the link. Printing the number here would be
a second statement of the cap, on a surface that already says it.

#### The shape of the change

**`frontend/lib/api-errors.ts`** — `readApiError` gains the `details` the cap needs. The
cleanest form: a **separate exported helper** beside `readApiError`, not a widening of
`ApiError`. `ApiError` is used by nine components and adding a field to it would put
`upgrade_hint` on every error the app handles — most of which have no hint. A dedicated
`readCapDetails(error)` returns `{cap, upgradeHint} | null`, reads the two fields, and
returns `null` for anything that is not a cap refusal. **`readApiError` itself does not
change**, so the nine existing call sites are untouched.

**`frontend/components/upgrade/upgrade-prompt.tsx`** — the one component. Props:
`{ hint: string }` — the server's sentence. It renders the sentence and the link. **It takes
the hint, not the whole error**, so it cannot grow a modal-shaped prop later, and so both
call sites read the same way.

**`frontend/components/onboarding/calendar-step.tsx`** — the existing inline prompt is
**replaced by the shared component**, and the hint read moves from `failure.message` to
`details.upgrade_hint`. This is the extraction.

**`frontend/components/detail/detail-actions.tsx`** — the save-cap 409 gains a branch. It
narrows on `code === "save_cap_reached"` exactly as it already narrows on
`"scheduling_conflict"`, reads the hint, and renders the shared component. **The refused
save is not silently retried** — the button returns to its idle state and stays there; no
retry is queued, and the criterion is asserted.

### Files to Create

| File | Purpose |
|---|---|
| `frontend/components/upgrade/upgrade-prompt.tsx` | The one inline upgrade prompt — the server's sentence and a quiet Upgrade link to `/pricing` |
| `frontend/components/upgrade/upgrade-prompt.test.tsx` | Its tests: the hint is verbatim, the link target, the absence of every modal attribute, no focus theft |
| `frontend/lib/cap-details.ts` | Reads `{cap, upgrade_hint}` off a refusal, or `null` |
| `frontend/lib/cap-details.test.ts` | Its tests: both cap shapes, the wrong shapes, the absence of modal-ish fields |

### Files to Modify

| File | Change |
|---|---|
| `frontend/components/onboarding/calendar-step.tsx` | The inline prompt is replaced by the shared component; the hint comes from `upgrade_hint` rather than `message` |
| `frontend/components/detail/detail-actions.tsx` | The `save_cap_reached` 409 gains a branch that renders the shared prompt; the refused save is not retried |
| `frontend/components/onboarding/calendar-step.test.tsx` | The existing cap test now asserts the server's `upgrade_hint` and the shared component's markup |
| `frontend/components/detail/detail-actions.test.tsx` | The save-cap 409 renders the prompt; the refused save is not retried; a scheduling conflict still opens the sheet |

### Tests

| Test File | Coverage |
|---|---|
| `frontend/lib/cap-details.test.ts` | Both cap payloads read correctly; a non-cap refusal reads `null`; `modal`/`title`/`actions`/`dismissable` are never read |
| `frontend/components/upgrade/upgrade-prompt.test.tsx` | The hint is rendered **verbatim**; the link points at `/pricing`; **no** `role="dialog"` / `aria-modal` / overlay; it does not take focus; it is `role="status"` |
| `frontend/components/detail/detail-actions.test.tsx` | The save cap renders the prompt; the refusal is **not retried**; the prompt is **not** a dialog; a scheduling conflict still opens the sheet (no regression) |
| `frontend/components/onboarding/calendar-step.test.tsx` | The calendar cap renders the **same** component with the server's `upgrade_hint`; no dialog |

**"One component serves both" is asserted by construction**, and the test file for the
shared component is the one both call sites' tests reach for.

### Risks to flag early

1. **The "never a modal" criterion is a test, not a promise.** The mockup has an expanded
   panel with `role="dialog"`, and the mockup's copy differs from the backend's. **The
   backend payload wins**: FR-48's criterion, the backend's pinned key set, and the work
   item's acceptance criteria all say inline. The mockup is the authority on *feel*, not on
   *mechanism*.
2. **The mockup shows a "Not now" dismissal and a muted-footer state.** Neither is built
   here, for the reasons above. **This is a deliberate divergence from the mockup** and it
   is recorded as one.
3. **`readApiError` is used in nine places.** The plan does **not** widen it — it adds a
   sibling helper — so the risk of a regression in the other nine is nil. If the review
   prefers widening `ApiError` instead, that is a legitimate alternative, but it puts an
   `upgrade_hint` on every error in the app.
4. **The Pro guarantee rests on the server.** If a later change makes the frontend decide
   "this user is Pro" from a client-side flag, this guarantee evaporates. The component
   takes no tier prop, so the frontend *cannot* make that mistake with this component — the
   prop does not exist.
5. **The save-cap branch changes an existing screen's behaviour.** `detail-actions.tsx`
   currently shows "Couldn't save that." for a capped save. Replacing that with the prompt
   is the point of the item, but it is a visible change to the Detail Screen and its
   existing test may assert the old line.

### Deviations from the Design

(none yet — this plan has no design doc; the mockup, FR-48 and the backend payload are the
sources)

### What this plan does not deliver

**The disabled Save state on Browse.** `EXPERIENCE.md` §4 describes Browse's Save buttons
rendering muted and disabled at "1 of 1 used today", with a tooltip. That is a *different*
surface — Browse's own card component — and Browse is not in this intent. The prompt here is
the refusal path: the user tried, and was refused.

**The `/pro/upgrade` route.** The mockup's expanded panel is a routable surface
(`pro-upgrade-cta-desktop.html` is a states-only showcase for a page that does not exist).
This item renders the prompt **in place**, on the surface where the refusal happened, which
is what the criteria ask for. A dedicated route is a separate thing.

---

# Work Item: `per-day-quiet-hours-domain-and-model` — seven windows instead of one

## Implementation Plan

Based on the design doc
`.specs-fire/intents/pro-tier-and-monetization/work-items/per-day-quiet-hours-domain-and-model-design.md`
(checkpoint 1 approved).

### Approach

The reshape is small on the delivery path because of one fact about the existing code:
**all seven consumers of the window forward it untouched to `shift_to_sendable`** — not one
of them reads `.start`, `.end`, `covers()` or `crosses_midnight`. So the plumbing does not
change shape; only what flows through it does.

### Files to Create

| File | Purpose |
|---|---|
| `backend/tests/domain/test_weekly_quiet_hours.py` | The weekly type, the midnight rule, DST, the week-coverage proof |
| `backend/tests/delivery/test_quiet_hours_overrides.py` | The model, the commands, the lapse, the Free user, the migration |
| `backend/apps/delivery/migrations/0008_quiethoursoverride.py` | **Schema only.** No data step. |

### Files to Modify

| File | Change |
|---|---|
| `backend/domain/quiet_hours.py` | `WeeklyQuietHours`, `Window`, `_ends_covering`, the iterating shift. `QuietHours` itself untouched. |
| `backend/apps/delivery/models.py` | `QuietHoursOverride` |
| `backend/apps/delivery/services/notification_preferences.py` | `effective_quiet_hours`, `_effective_week`, the two override commands |
| `backend/apps/delivery/services/scheduled_sends.py` | Forward `effective_quiet_hours`; annotation `QuietHours \| None` → `Window \| None` |
| `backend/apps/delivery/services/reminder_plan_read.py` | The same two changes |
| `backend/tests/architecture/test_write_ownership.py` | The new table's owner |

**Unchanged, and asserted so:** `preferences_read.py`, `schemas.py`, `preferences_api.py`,
`delivery_sweep.py`, and every existing test in `tests/domain/test_quiet_hours.py`.

### Deviations from the Design

**1. `NotificationSettings.quiet_hours` keeps its name, its type and its meaning.** The
design said it *becomes* the weekly value while also listing `schemas.py` as unchanged —
those contradict, because `schemas.py` reads `window.start` off it. Resolved by adding a
**second** field, `effective_quiet_hours: WeeklyQuietHours`, which is what the delivery path
reads, and leaving `quiet_hours` as the base window the settings API reports.

This is also the safer failure mode. Under the design as written, a consumer nobody updated
would raise `AttributeError`; under this one it keeps using the base window — today's
behaviour, which is wrong for a Pro user but cannot put a send at 3am. The seven call sites
were all updated regardless, and the API is genuinely untouched, which is what the design
intended.

**2. `has_sendable_gap` was removed before it shipped.** See the design doc's decision 3: a
fully-covered week is arithmetically impossible, so the guard could only ever return one
answer. The proof moved into `MAX_DEFERRALS`' docstring and into a brute-force test.

### Tests

| File | Coverage |
|---|---|
| `test_quiet_hours.py` (existing, **unmodified**) | 24 single-window cases still pass, which is how "a Free user's behaviour is unchanged" is proven at the arithmetic level |
| `test_weekly_quiet_hours.py` | Weeknight vs weekend; a day's window owning the next morning; Saturday's window *not* governing Saturday morning; two windows over one instant; the three-day chain; idempotence; never backwards; `every_day` ≡ the bare window over a whole week; DST both ways; the week-coverage proof |
| `test_quiet_hours_overrides.py` | A Free user's effective schedule; overrides ignored off-Pro; seven distinct windows; the lapse and the resubscribe; the refusals in Python *and* in the database; clearing; the audit rows; the migration's shape |

### Risks flagged early

1. **A send at 3am** is the failure mode this item can cause. The midnight rule is stated in
   `WeeklyQuietHours`' docstring, and each branch has a test — including the one that would
   be wrong if the rule were "ask the instant's own weekday".
2. **The entitlement read is on the delivery path.** One query per user per batch, and
   skipped entirely for a user with no override rows.
3. **A lapse moves a Pro user's delivery times.** Correct, but it is the only delivery-time
   change in this intent caused by a billing event. Item 8's API should report the
   *effective* schedule rather than the stored one.

---

# Work Item: `quiet-hours-pro-api` — seven windows over the wire

## Implementation Plan

### Approach

The work item names the real risk: **shape drift** — two parallel spellings of quiet hours
that slowly disagree. So there is no second endpoint and no second schema for "the weekly
version". There is one `PUT /api/settings/notifications`, and the weekly case is **three
fields on the body it already has**, mirroring the storage exactly:

| Field | Direction | Meaning |
|---|---|---|
| `quiet_hours` | read + write | **Unchanged.** The base window: "this window, every day". |
| `quiet_hours_overrides` | read + write | A list of `{weekday, start, end}`, at most seven. Pro only to write. |
| `effective_quiet_hours` | **read only** | Seven entries: what the delivery path will actually use. |

These are not two spellings of one thing. `quiet_hours` is still the only way to say "my
window"; an override says "…except on Thursdays". That is the same relationship the tables
have, which is why they cannot drift apart — one is derived from the other two and is
read-only.

**`effective_quiet_hours` is why a lapsed Pro user is not lied to.** It is the carried risk
from `per-day-quiet-hours-domain-and-model`'s review: a lapse silently returns a user to
their base window. With both fields on the response, a lapsed user sees their seven stored
overrides *and* sees that the effective week is their base window every day. Reporting only
the stored overrides would show seven windows that are not in force.

**Overrides go into `SettingsPatch`, not a new endpoint, and that is load-bearing.**
`apply_settings_patch` already wraps every settings write plus
`reschedule_pending_for_user` in one `transaction.atomic(using=PERSONAL)`. Putting the
overrides inside it buys three things at once: the whole week is applied in one transaction
(the acceptance criterion's "the server never observes a partially-updated week"), the
pending sends are re-timed from the new windows, and a weekday change behaves exactly like a
base-window change rather than being a second kind of settings write.

### Files to Create

| File | Purpose |
|---|---|
| `backend/tests/delivery/test_quiet_hours_pro_api.py` | The endpoint: both shapes, the refusals, the lapse, atomicity |

### Files to Modify

| File | Change |
|---|---|
| `backend/domain/errors.py` | `QuietHoursProRequired(ConflictError)` — `code = "quiet_hours_pro_required"`, `details = {cap, upgrade_hint}` |
| `backend/apps/delivery/services/notification_preferences.py` | `replace_quiet_hours_overrides` — validate every window, then apply the whole set |
| `backend/apps/delivery/services/preferences.py` | `SettingsPatch.quiet_hours_overrides` + `clear_quiet_hours_overrides`; applied inside the existing transaction |
| `backend/apps/delivery/services/preferences_read.py` | The view carries the stored overrides and the effective week |
| `backend/apps/delivery/schemas.py` | `QuietHoursOverrideIn/Out`, `EffectiveQuietHoursOut`, the three fields |
| `backend/apps/delivery/preferences_api.py` | Read the new fields from the patch; refuse a non-Pro write |
| `backend/shared/constants.py` | The upgrade sentence for this refusal |
| `frontend/lib/cap-details.ts` | `quiet_hours_pro_required` joins `CAP_CODES` |
| `frontend/lib/api/openapi.json`, `schema.ts` | Regenerated — **`make client` in this item** |

### The rules this item fixes

1. **A Free user writing overrides is refused**, with `{cap, upgrade_hint}` — the same calm
   inline shape as the save cap and the calendar cap, so the prompt built in
   `frontend-upgrade-prompts` renders it with no new component. `CAP_CODES` gains the code;
   that is the whole frontend change here, and the surface is item 9's.
2. **A lapsed Pro user can read, and cannot write.** Reading is what the acceptance
   criterion requires and what `effective_quiet_hours` makes honest. Writing is refused for
   the same reason a Free user's is — they are not Pro — and this is not a second answer to
   `per-day-quiet-hours-domain-and-model`'s rule but the same one: **the rows are the
   user's and are never deleted; the subscription governs their effect.** The *command*
   stays tier-agnostic, as that item deliberately made it; the paywall is at the API, where
   the user is.
3. **`start == end` is refused on every window, not just the first.** The whole list is
   validated before anything is written, so a bad seventh window does not leave six applied.

### Tests

| Area | Coverage |
|---|---|
| The Free shape | `GET`/`PUT` with one window is byte-identical to today; the new fields are additive |
| The Pro shape | Seven windows set in one `PUT`; read back; `effective_quiet_hours` reflects them |
| Atomicity | A list whose last window is `start == end` writes **none** of them |
| The refusal | A Free user's override write is 409 with `{cap, upgrade_hint}` and no modal field; nothing written |
| The lapse | Overrides still readable; `effective_quiet_hours` is the base window; a write is refused |
| Re-timing | Changing a weekday window re-times pending sends, as a base-window change does |
| Validation | A weekday outside 0..6; two overrides for one weekday |
| Contract | The regenerated client is in sync — **verified by the full suite**, since `test_contract.py` passes in isolation |

### Risks flagged early

1. **This item adds fields to a shared endpoint.** `NotificationSettingsOut` is read by the
   existing settings screen; the fields are additive and optional, and the Free-shape test
   asserts the old response is unchanged.
2. **`make client` must run in this item.** Item 2's regression — a stale `schema.ts`
   failing only when the contract test runs beside its siblings — is the reason it is in the
   plan rather than left to CI.
3. **The refusal's `code` is new.** Until `CAP_CODES` learns it, the shared upgrade prompt
   would silently fall back to the generic error line. Changed in the same item.
