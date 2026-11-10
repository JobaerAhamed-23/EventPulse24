---
run: run-eventpulse24-025
work_item: notice-and-mute-api
intent: event-state-sync
generated: 2026-11-10
mode: confirm
---

# Implementation Walkthrough: The strip needs something to read and the mute needs somewhere to write

## Summary

FR-54's in-app half is a **dismissible strip** on the digest home and a **banner** on the
Detail Screen. FR-55's **per-event mute** needs a write, from the Detail Screen. Both need
a **read**, and the Detail Screen needs **both facts in one round trip** — the banner and
the mute control render from one response, and two snapshots could disagree.

The previous work item built the notice row and the email but deliberately stopped at the
surface boundary: `list_undismissed_notices` was **unbounded**, `dismiss_notice` and
`mute_event_notices` existed but nothing called them over HTTP, and the Detail read knew
nothing about notices or mutes.

**This item is the API slice.** Four endpoints, one combined read, two new Detail fields,
and the regenerated contract.

### The three decisions this item actually turns on

**1. The strip is keyed on `dismissed_at`, not `seen_at`.** The work item's criterion 1 said
"unseen" and criterion 2 said a dismiss "marks a notice seen" — and the two pull in
different directions. The service's own rule is explicit (*"the strip is a queue, and
closing an item should empty it"*), and criterion 2's own wording says dismissal is what
makes FR-54's "one-time, never repeats" true.

**So `mark_seen` is not called by this API at all.** A `GET` that writes `seen_at` is
exactly the shape `apps/personalization/detail_api.py` refuses (*"a `GET` that writes is the
shape CSRF exists to stop"*), and the strip's read is asserted to be **one query**. `seen_at`
is still on the wire — it is a fact about the row — but it does not gate the strip.

**2. The banner reports the newest notice whatever its dismissal state.** Criterion 4 said
"an undismissed notice"; the service's own rule says the opposite — the banner is about
*this* event, which the user navigated to on purpose, so dismissing the strip on the digest
home must not hide *"this event was cancelled"* from the event's own page. `dismissed_at`
rides on the wire so the client can tell the two states apart.

**3. The dismiss 404 and the dismiss idempotence are the same endpoint.** `dismiss_notice`
returns a `bool` that collapses three cases: not yours, does not exist, already dismissed.
Criterion 6 wants the third to answer success; criterion 5 wants the first two refused.

The resolution keeps the common path free:

| case | `dismiss_notice` | the scoped check | result |
|---|---|---|---|
| yours, open | `True` | *not called* | **200** `changed: true` |
| yours, already dismissed | `False` | `True` | **200** `changed: false` |
| another user's | `False` | `False` | **404** |
| no such notice | `False` | `False` | **404** |

The two 404s are **byte-identical** — a 403 would confirm that the record exists, so the
endpoint could be used to probe for other users' notice ids. And the extra query runs
**only** on the `changed == False` path, so the common case costs **zero** extra queries.

## Structure Overview

```text
┌──────────────────────────────────────────────────────────────┐
│  apps/delivery/notices_api.py           (the surface)         │
│                                                              │
│  GET    /api/notices                     → the strip's read    │
│  POST   /api/notices/{id}/dismiss        → close one          │
│  PUT    /api/notices/events/{id}/mute    → silence it         │
│  DELETE /api/notices/events/{id}/mute    → let it through     │
│                                                              │
│  auth=current_user — the id comes from the session,          │
│  never from a payload                                      │
└────────────────────────────┬─────────────────────────────────┘
                             │ calls a published service
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  apps/delivery/services/notice_state.py   (the read)          │
│                                                              │
│  NoticeSummary          plain data, not a model instance     │
│  EventNoticeState       the notice and the mute, together    │
│  summarize_notice()     the projection                      │
│  read_event_notice_state()  TWO queries, both user-scoped   │
│                                                              │
│  owns the "newest notice" rule — and the tiebreaker          │
└────────────────────────────┬─────────────────────────────────┘
                             │ plain data crosses the boundary
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  apps/personalization/services/detail_read.py                │
│                                                              │
│  read_event_notice_state() is called AFTER the              │
│  `user_id is None` early return — the leak floor             │
└──────────────────────────────────────────────────────────────┘
```

## Architecture

### The wall (AD-2)

`apps.personalization` never imports `apps.delivery.models` — directly or transitively. It
imports two things from `delivery`'s **service** layer: `NoticeSummary` and
`read_event_notice_state`. Both are plain frozen dataclasses.

**`notice_state.py` reads the two models directly** rather than going through
`services.state_notices` and `services.mutes`, and the reason is the **model boundary**:
`state_notices` publishes reads that return `StateChangeNotice` *model instances*, and
handing one to `personalization` would put a reference to `apps.delivery.models` in another
app's hands. The projection happens **inside the owning app**.

> **A note on what this is *not*.** An earlier draft justified the direct model read by
> claiming an import cycle: `personalization → notice_state → state_notices →
> scheduled_sends → personalization`. The code review checked that against the real import
> graph and it is **false** — `scheduled_sends` imports only
> `apps.personalization.services.digest_preferences`, which reaches none of `detail_read`,
> `personalization.schemas`, `detail_conflict` or `neighbor_count`. Adding the edge leaves
> `lint-imports` at 19 kept, 0 broken. The docstring now names the reason that **does**
> hold, and says plainly that there is no cycle to avoid.

### The leak floor (AD-12)

`read_event_notice_state` is called in `read_event_detail` **strictly after** the
`user_id is None` early return. An anonymous `GET /api/events/{id}` issues **zero** personal
queries — and the test that says so is restated under this change's name, so the property
cannot be lost with it.

### The wall (AD-3)

Neither read crosses to `catalog`. The `event_id` names a row in another schema, and a
notice for an event that has since gone still reads and still dismisses.

### The guards

`checkers.py::surface_files()` used to glob `apps/*/api.py`, which matches only files named
exactly `api.py` — so **four** surface files were **exempt from AD-5**: nothing would have
caught `apps/catalog/preview_api.py`, `apps/delivery/email_api.py`,
`apps/delivery/preferences_api.py` or `apps/personalization/detail_api.py` writing through
the ORM.

The discovery is now **by shape** (`admin.py`, `api.py`, `*_api.py`), the same rule the AD-11
guard already used. The count goes **13 → 18 → 19** (the last step is `config/health.py`,
which defines its own `Router` and is mounted at `/health`, and is included by name because
the shape rule does not match it). The four previously-unchecked files were **checked for
the first time** — all four pass.

**One discovery, two rules.** `api_modules()` (routers only, for AD-11) and
`surface_files()` (admins + routers, for AD-5) live side by side in `checkers.py`, so the
two guards can never disagree about what a request handler is.

## Files Changed

| File | What changed |
|---|---|
| `backend/apps/delivery/notices_api.py` | **new** — the router and the four handlers |
| `backend/apps/delivery/services/notice_state.py` | **new** — the leaf combined read; `NoticeSummary`, `EventNoticeState`, `summarize_notice`, `read_event_notice_state` |
| `backend/apps/delivery/services/state_notices.py` | `list_undismissed_notices` gains a required keyword-only `limit` and a tiebreaker; `notice_belongs_to_user` added; `latest_notice_for_event` **deleted** as dead code |
| `backend/apps/delivery/schemas.py` | `NoticeOut`, `NoticeListOut`, `NoticeDismissOut`, `EventMuteOut` |
| `backend/apps/personalization/schemas.py` | `DetailNoticeOut`; `DetailPersonalOut` gains `muted` and `notice` |
| `backend/apps/personalization/services/detail_read.py` | `DetailPersonal` gains the two facts; the read is placed after the anonymous early return |
| `backend/apps/personalization/detail_api.py` | the two fields projected onto the wire |
| `backend/shared/constants.py` | `NOTICE_STRIP_LIMIT = 5` |
| `backend/config/api.py` | the router mounted at `/api/notices` |
| `backend/tests/architecture/checkers.py` | `api_modules()` split out; `surface_files()` discovered by shape; `config/health.py` included |
| `backend/tests/architecture/test_no_direct_writes.py` | the surface count 13 → 18 → 19 |
| `backend/tests/architecture/test_digest_composition_separation.py` | uses the shared `api_modules()` discovery; `REQUEST_MODULES` gains the notices router and `config/health.py` |
| `backend/tests/delivery/test_notices_api.py` | **new** — 38 tests |
| `backend/tests/delivery/test_notice_state.py` | **new** — 13 tests |
| `backend/tests/delivery/test_state_notices.py` | `limit=` added; two bound tests; the banner tests moved to `test_notice_state.py` |
| `backend/tests/personalization/test_event_detail_api.py` | 12 new Detail tests; the pinned `personal` shape widened; the query bounds split by path |
| `frontend/lib/api/openapi.json` | **regenerated** |
| `frontend/lib/api/schema.ts` | **regenerated** |

## Domain Model

No new model, no new column, **no migration**. `makemigrations --check` reports no changes
detected.

The two tables this item reads — `StateChangeNotice` and `EventNoticeMute` — were built by
`state-change-notice-model`. The one thing this item *adds* is a rule, and the rule is not
a column: **which notice is the newest one**, and how a tie is broken.

## Key Implementation Details

### The tiebreaker, and why it was needed

Both "newest notice" reads order by `("-created_at", "-id")`. The `-id` is not decoration.

`created_at` is `auto_now_add` with microsecond resolution, and
`ingestion.event_writes` appends **one `EVENT_STATE_CHANGE` per kind within a single poll**
— so a source update that moves an event's time *and* marks it sold out produces two
notices seconds apart, and two notices can genuinely share a `created_at`.

Without a secondary sort key the database is free to return either row from an unordered
tie, and it is free to make a **different choice each time**. The strip's read and the
banner's read are two separate queries — so the strip could show one notice and the banner
could name a different one, for the same event, at the same moment.

**`-id` is the natural tiebreak** because the primary key is a **UUIDv7**, which is
time-ordered by construction: of two notices raised in the same instant, the later one has
the larger id.

### The two queries

`read_event_notice_state` issues **exactly two**: the mute is an `EXISTS` and the notice is
the newest row for the pair. They are **not** merged, because there is no honest way to: a
cross-table join would answer "is there a notice" only for events that also have a mute
row, and an `EXISTS` against a join is the kind of thing that is subtly wrong in exactly
the case nobody tests.

The count is **constant** — verified at 0, 1 and 50 notices, and 150 neighbours.

### The bound is at the service, not the surface

`list_undismissed_notices(*, user_id, limit)` — the `limit` is **keyword-only, required,
and has no default**. A default would leave the unbounded read reachable, and "somebody
forgot to pass a limit" is exactly the failure the bound exists to prevent. The slice is
applied by the database, through the slice on the ordered queryset, so a busy day costs one
query and one index range.

The API takes **no `?limit=` parameter**: the bound is a product decision (FR-54's "one calm
correction"), so it belongs in the server, not in the client's hands.

### The two paths of the Detail read

The Detail read's query count is **path-dependent**, because the conflict read is gated on
the caller having saved the event:

| path | queries | |
|---|---|---|
| unsaved user | **6** | composition, save row, 2 signal aggregates, mute `EXISTS`, notice `LIMIT 1` |
| **saved user** | **8** | the above **+ 2** conflict-pair reads |

The bounds are **named constants** — `UNSAVED_READ_QUERIES = 6`,
`CONFLICT_READ_QUERIES = 2`, `SAVED_READ_QUERIES = 8` — and the saved path is asserted
**relatively**: `saved == unsaved + 2`. That form survives the next read anyone adds to the
surface, while still catching the regression the test is for: a per-save or per-conflict
loop.

**The saved path is the path most users are on** — a user who saved the event is the one
reading the Detail Screen at all.

### Why the router declares `401` and `403`

No sibling router declares either. `401` is the anonymous refusal and `403` is the CSRF
refusal (`csrf_failed`), and both are reachable on every endpoint here — `identity`'s
`current_user` resolver answers the first with a 401 and raises the second.
`apps/identity/api.py` declares `403: ErrorOut` on its own endpoints for exactly this
reason.

The other app routers declare neither, which means their generated clients **cannot type a
response the server actually gives**. Declaring them here is deliberate: the frontend needs
to branch on "sign in" (a 401) against "fetch a fresh token and retry" (a `csrf_failed`
403), and it can only do that if the contract says both are possible.

### Why a router of its own

The mount path is public contract (AD-19): `frontend/lib/api/openapi.json` and
`frontend/lib/api/schema.ts` are generated from it and committed, and
`tests/api/test_contract.py` fails on any drift. So a path has to name the thing it
serves.

`/api/reminders` names **Reminder Plans** — a plan has slots, and its path shape is
`/{target_kind}/{target_id}`. A state-change notice is not a plan, and an FR-55 mute is not
a plan either; hanging them off that router would make `/api/reminders/<uuid>` mean two
different things depending on which handler matched.

### Two routes that are not the same verb

**The mute is a state, so it is `PUT` and `DELETE`.** Setting a state is `PUT`; clearing it
is `DELETE`; there is **no request body at all**, so the client cannot encode "clear this"
as a field that could be confused with "leave it alone".

**The dismiss is a `POST`, not a `DELETE`.** The notice row is **not** deleted — FR-54's
"never repeats" and the daily cap both depend on the row surviving — and `dismiss_notice`
sets `dismissed_at` rather than deleting. A `DELETE` that does not delete is a lie in the
method, so the path names the act.

## Security Considerations

- **The user id comes from the session, never from a payload.** `auth=current_user` is on
  the **router**, and no endpoint accepts a user id as an input. Tested as an authorization
  case, not assumed from the router.
- **The dismiss write is scoped by `user_id` in the `UPDATE` itself** —
  `filter(user_id=..., pk=..., dismissed_at__isnull=True)` — so another user's notice
  **cannot** be dismissed. The scoping is in the write, not only in the check after it.
- **The two 404s are byte-identical**, so the endpoint is not an existence oracle over
  notice ids.
- **No PII on the wire.** The change's *content* — the before/after values — is source
  payload and is deliberately absent. `change_kind` is the vocabulary
  `domain.lifecycle.ChangeKind` defines, carried through unchanged. No title, no venue.
- **`state_change_id` is not on the wire.** It is the notice's internal uniqueness key and
  no client acts on it.
- **The writes refuse a request without a CSRF token**, with `403` / `csrf_failed` — and
  the row does not change. Tested, because the whole suite otherwise uses a client that
  always sends a token.

## Performance Considerations

- **The strip's read is one query**, bounded by the database, and it does not grow with the
  number of notices.
- **The combined read is two queries**, and the count does not grow with notices, saves or
  neighbours.
- **The Detail read's count is a constant per path** — 6 unsaved, 8 saved — and neither
  grows with the number of neighbours.
- **The strip's bound drops the tail rather than paging it.** Unlike `SAVERS_PAGE` — a page,
  because propagation must reach *every* saver — the sixth notice loses nothing here: the
  user who needs it opens the sixth event.

## Decisions Made

| Decision | Reasoning |
|---|---|
| **Should the strip be keyed on `seen_at` or `dismissed_at`?** | `dismissed_at`. The strip is a queue, and closing an item should empty it; being *shown* something is not the same as acting on it. And a `GET` that marks notices seen is the shape CSRF exists to stop |
| **Should the banner report only undismissed notices?** | No — the **newest notice, whatever its dismissal state**. The banner is about *this* event, and the user navigated here on purpose. `dismissed_at` rides on the wire so the client can tell the two apart |
| **Should the dismiss 404 or 200 for an already-dismissed notice?** | **200, with `changed: false`.** "Already closed" is a success, not an error — and `changed: false` is what makes the idempotent write honest: a client that redrew on `changed` would redraw a control that did not move |
| **Should "not yours" and "no such notice" be different answers?** | No — the **same 404**, byte for byte. A 403 would confirm the record exists, and the endpoint could be used to probe for other users' notice ids |
| **Should the mute be `PUT`/`DELETE` or one `POST` with a body flag?** | `PUT`/`DELETE`, with **no body at all**. A mute is a state with two values, and a body field could be confused with "leave it alone" |
| **Should the dismiss be `DELETE`?** | No. The row survives — the cap and the never-repeat rule depend on it — and a `DELETE` that does not delete is a lie in the method |
| **Should the limit have a default?** | No — **required and keyword-only**. A default leaves the unbounded read reachable, and "somebody forgot to pass a limit" is exactly the failure the bound exists to prevent |
| **Should the API take a `?limit=` parameter?** | No. The bound is a product decision (FR-54's "one calm correction"), so it belongs in the server |
| **Should `notice_state` go through `state_notices`?** | It would have been fine — there is no cycle. But it would hand `personalization` a **model instance**, which is the AD-2/AD-16 leak. The direct model read is right for the model-boundary reason |
| **What breaks a `created_at` tie?** | `-id`. The primary key is a UUIDv7, which is time-ordered by construction, so of two notices raised in the same instant the later one has the larger id. A second timestamp would need a column, and a column is a migration |
| **Should the query bound be one absolute number or two?** | Two, and **named**. The conflict read is gated on the save, so the two paths differ by exactly two — and the relative assertion survives the next change |
| **Should `mark_seen` be called by the strip's read?** | No. It would make the strip's `GET` a write, and the strip's read is asserted to be **one query** |
| **Should the router declare `401`/`403` when no sibling does?** | Yes — deliberately, and documented. The frontend must branch on "sign in" against "fetch a fresh token" |

## Deviations from Plan

Four, all forced by the code review, all recorded in the review report:

1. **The plan's stated reason for the module's shape was false.** The import cycle it
   claimed does not exist. The docstring now names the reason that does hold — the model
   boundary — and says plainly that there is no cycle to avoid.
2. **`state_notices.latest_notice_for_event` was deleted.** It had no production caller
   once the combined read arrived, and its query was duplicated verbatim in
   `notice_state`. The rule moved to the module that actually reads it, and the strip's
   read now uses the **same ordering**, with a **tiebreaker** the plan had not thought
   about.
3. **The query bound was wrong on the path nobody tested.** The plan widened `4 → 6` by
   adding two to the number it had, without asking which path that number described. The
   saved path is **8**. The bounds are now named constants and the saved path is asserted
   relatively.
4. **`config/health.py` was outside the discovery.** It is a router, mounted at `/health`,
   and the shape rule missed it. The surface count goes 18 → 19.

## Dependencies Added

None. No new package, no new service, no new model, no migration.

## How to Verify

```bash
cd backend

# The four endpoints' contract.
uv run pytest tests/delivery/test_notices_api.py -q
# 38 passed

# The combined read.
uv run pytest tests/delivery/test_notice_state.py -q
# 13 passed

# The Detail Screen's two new facts.
uv run pytest tests/personalization/test_event_detail_api.py -q
# 65 passed

# The architecture guards — the discovery, the counts, AD-11.
uv run pytest tests/architecture/ -q
# 859 passed

# The contract, the linters, and the migration check.
uv run lint-imports
# Contracts: 19 kept, 0 broken.
uv run ruff check .
# All checks passed!
uv run ruff format --check .
# 534 files already formatted
uv run python manage.py makemigrations --check --dry-run
# No changes detected
```

The full suite is **5637 passed, 16 failed**. All 16 are pre-existing date-expired fixtures,
verified against a clean `git worktree` at `HEAD` — see the test report.

### The end-to-end path

```bash
# Sign in and read the strip.
GET /api/notices
# → 200 {"items": [...]}   (at most NOTICE_STRIP_LIMIT items, newest first)

# Close one.
POST /api/notices/{notice_id}/dismiss
# → 200 {"id": ..., "dismissed": true, "changed": true}

# It has left the strip.
GET /api/notices
# → 200 {"items": [...]}   (that notice is gone)

# Silence the event.
PUT /api/notices/events/{event_id}/mute
# → 200 {"event_id": ..., "muted": true, "changed": true}

# The Detail Screen now knows both facts, from one response.
GET /api/events/{event_id}
# → 200 {"personal": {..., "muted": true, "notice": {...}}}
```

## Test Coverage

**67 tests added.** The baseline at `HEAD` is **5438 passed, 16 failed** on a clean
worktree — the same sixteen. **Zero new failures.**

| Suite | Result |
|---|---|
| `tests/delivery/test_notices_api.py` (new) | **38 passed** |
| `tests/delivery/test_notice_state.py` (new) | **13 passed** |
| `tests/delivery/test_state_notices.py` | **48 passed** (44 pre-existing + 4 new) |
| `tests/personalization/test_event_detail_api.py` | **65 passed** (53 pre-existing + 12 new) |
| `tests/architecture/` | **859 passed** |
| `tests/api/` + `tests/e2e/test_delivery_contract.py` | **10 passed** |
| **Full backend suite** | **5637 passed, 16 failed** — all 16 pre-existing |

### The mutations

Eight, each applied to the source, the suite run, and the source restored.

| # | Mutation | Caught by |
|---|---|---|
| 1 | The route is `"/"` instead of `""` | every strip test — a trailing-slash **301** |
| 2 | `limit` is dropped from the slice | `test_the_strip_is_bounded` |
| 3 | The slice keeps the **oldest** notices | `test_the_strip_keeps_the_newest_when_it_is_bounded` |
| 4 | `notice_belongs_to_user` is not user-scoped | `test_dismissing_another_users_notice_is_a_404` |
| 5 | The dismiss 404 is raised for an already-dismissed notice | `test_dismissing_an_already_dismissed_notice_is_a_success` |
| 6 | `read_event_notice_state` is hoisted above the anonymous early return | `test_the_anonymous_path_still_never_queries_the_personal_schema` |
| 7 | The read loops over the notices | `test_the_read_is_two_queries` |
| 8 | The Detail reports only an **undismissed** notice | `test_the_detail_reports_a_dismissed_notice_too` |

**Mutation 6 is the one that matters most.** `read_event_notice_state` is one line above the
place it belongs, and moving it one line up would be invisible to every other test — the
notice would still be reported, the mute would still be reported, and the response would be
identical for a signed-in user. The **only** thing that would change is that an anonymous
caller's request would touch the `personal` schema, which is the leak AD-12 forbids.

## Ready for Review

The change is complete, verified, and reviewed.

- **67 new tests**, all passing; **zero new failures** against a clean-`HEAD` baseline.
- **19 import contracts kept, 0 broken.** Ruff clean, formatted, and **no migration**.
- The contract is **regenerated** and committed; `tests/api/test_contract.py` is green.
- **The code review found three real defects and five coverage gaps — all fixed**, each
  pinned by a test that was proven to fail against the defect.
- The two ambiguities the acceptance criteria left open are **resolved and recorded**, and
  the criteria themselves were **amended in place** with the reason.

### What this item does not do

- **The strip and the banner are not rendered yet.** This item builds the API they read;
  `frontend-digest-strip-and-detail-banner` renders them.
- **The Pulse Card's state fields come from the catalog, not from a notice.** A notice is
  about a *change*; a card field is about the event's *current* state. Two different facts,
  and `detail-overlap-notice` has to say which one the Detail Screen shows when both exist.
- **The mute is still not reachable from the mail.** The notice body links to the Detail
  Screen; the mute lives there, and this item gives the Detail Screen the button's write.
