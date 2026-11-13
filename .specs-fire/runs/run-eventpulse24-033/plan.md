---
run: run-eventpulse24-033
work_item: settings-sources-surface
intent: source-transparency-and-mute
mode: validate
checkpoint: plan
approved_at: pending
---

# Implementation Plan: Settings → Sources

## Approach

Build the screen the mockup specifies and the endpoints it needs, in the order the
dependencies actually run: the data layer first (the `SourceMute` row and the
`source_id` the mute keys on), then the service that owns the row, then the two reads
that must honour it, then the endpoints, then the screen.

**Four things the codebase decides for us, and the plan follows them rather than
re-deriving them.**

1. **The four groups are FR-23's Source Badge types, already implemented.**
   `apps/ingestion/services/source_badges.py:35-52` maps a source to exactly
   `official_site` / `community` / `aggregator` / `crawled_html`, server-side, and two
   reads already use it. The screen groups by the badge. No new taxonomy, and no second
   mapping from `SourceType`/`AcquisitionMethod`.

2. **The mute row lives in `personal`, keyed by value.**
   `personalization.SourceMute` with `user_id` + `source_id` as plain `UUIDField`s, a
   `UniqueConstraint` on the pair, and `retention_category = PREFERENCE_SIGNALS`. This
   is the `EventNoticeMute` shape (`apps/delivery/models.py:598-640`) and the
   `EventDetailOpen` shape (`apps/personalization/models.py:710-790`). AD-3 forbids the
   FK; the ORM enforces the wall, so the relation is by value.

3. **`default` is the absence of a row, not a third state.**
   Only `show_less` and `mute` are stored. Setting `default` **deletes** the row. That
   makes "Restore all defaults" a single bulk delete and makes the row honest — a row
   saying "default" says nothing.

4. **The registry read crosses the wall through a published service, not a model.**
   `personalization` may not import `apps.ingestion.models` (the `models-ingestion`
   import contract). So the source list is read by a **new `ingestion` service**
   (`services/source_registry_read.py`) that returns plain data — the same shape
   `catalog_read` returns — and `personalization` calls it.

**The one genuinely open design point: how "Show less" deprioritises without touching
the published FR-22 formula.**

`domain/ranking.py:316-338` computes `relevance_score()` as exactly five weighted terms
summing to 1.00, and `backend/tests/shared/test_constants.py:147-153` pins those five
weights in CI against `ADR-0025`. A "show less" penalty **cannot** be a sixth term —
that would change a published, CI-pinned formula and require a new ADR to authorise it.

So the penalty is applied **outside** the formula, as a post-score adjustment applied to
the computed score *before* ordering. The seam is `_Scored.score` in
`digest_composition.py` and the `(score, ...)` tuple in `browse_read.py:295`. The
adjustment subtracts a fixed amount from a `show_less` source's score, so the event
still competes — it simply competes lower. This keeps the FR-22 formula byte-identical,
keeps the CI weight pin green, and satisfies the acceptance criterion ("the setting
changes what the user is shown") without hiding events the user only asked to see
*less* of.

The penalty magnitude is a named constant in `shared/constants.py`
(`SOURCE_SHOW_LESS_PENALTY = Decimal("0.10")`), documented as a post-score
deprioritisation, not a scoring term. It is deliberately *smaller* than the smallest
published weight (0.10) so that a single "show less" cannot by itself invert a
slot's intent, but large enough to reorder within a slot.

**Where each filter is applied — the acceptance criterion demands proof, not a written
row.**

| Setting | Effect | Applied at |
|---|---|---|
| `mute` | The source's events are **absent** from the candidate set | Before scoring, in `compose_digest` and `read_browse_page` |
| `show_less` | The source's events **are present** but score lower | After scoring, before ordering, in the same two paths |

Both are applied to the **candidate set**, which is the seam
`digest_composition.py:652-665` already uses for user-shaped filters
(`include_personal_events`, `user_city`). Not in `domain/ranking.py` (stdlib-only, no
DB) and not in `catalog_read` (not user-scoped; it must not learn about preferences).

**Digest and Browse must agree.** A source muted in Settings must not reappear in
Browse, and a "show less" must order lower in both. Both read paths call the same
service helper, so they cannot drift.

**The screen's most prominent element differentiates nothing at launch.** The registry
holds ~3 sources (`config/local_feeds.fixtures.json` has 3, `config/local_feeds.json`
has 2, `seed_browse_catalog` adds 1), all with `reliability_score = NULL`, which reads as
the 0.50 prior. The plan therefore makes the **empty and near-empty states
first-class** and does **not** fabricate sources to fill the screen. A screen that
invents sources would be asserting a registry that does not exist.

**What this plan does not do.** It does not touch `TRACEABILITY.md` or the mockup
header (FR-16's `PARTIAL` score is a citation problem, and editing a document to
improve a score in the same pass that measures it is how a matrix stops being
trustworthy). It does not couple to FR-25 — that mockup reverses at `Settings → Taste`
(`less-like-this-mute-prompt-desktop.html:122`, `:149`), which is a **category** mute,
not a source mute, and it gets its own route in the sibling intent.

### The reliability band

FR-16's score is a posterior in [0, 1]. The mockup wants **1–5 dots** with a legend
reading "5 = trusted, 3 = ok, 1 = low coverage". `domain/ranking.py:341-364` has a
`score_bucket()` for the Confidence Pulse, but its boundaries are **FR-22's** (≥0.85 →
5, ≥0.65 → 4, …) and it is the Confidence Pulse's bucket, not the source's trust.

The screen therefore uses **its own banding**, declared in
`shared/constants.py` next to the reliability constants:

```
SOURCE_TRUST_BAND_5 = Decimal("0.80")
SOURCE_TRUST_BAND_4 = Decimal("0.65")
SOURCE_TRUST_BAND_3 = Decimal("0.50")
SOURCE_TRUST_BAND_2 = Decimal("0.35")
```

`0.50` is band 3 — "ok" — which is exactly right for the 0.50 prior every un-scored
source reads as, and it means the dots are meaningful before a source has 30
observations. The band count is the **stored** `source.reliability_score` (or the prior
when null), never a week-over-week delta: `domain/reliability.py:47-60` proves a 3x
drop is impossible, and a screen that rendered one would assert something the domain
says cannot happen.

**The dots are ink-primary, not terracotta.** The mockup's own header says so
(`settings-sources-desktop.html:23`, `:145-153`): 1–5 dots, `--ink-primary` for on and
`--ink-faint` for off, reusing the existing `--ink-faint` / `--ink-primary` tokens. **No
new tokens.**

### Endpoints

Three, on the existing `/settings` router (`backend/config/api.py:72` mounts
`settings_router` at `/api/settings`):

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/api/settings/sources` | The grouped source list with each source's trust band and the user's current mute state |
| `PUT` | `/api/settings/sources/{source_id}` | Set `mute` / `show_less` / `default` for one source |
| `POST` | `/api/settings/sources/restore-defaults` | Bulk reset — **confirmed by the client before it is called** (§10.4) |

**Where the endpoints live.** The design doc proposed `delivery/preferences_api.py` or a
sibling router. A *new* `*_api.py` file is a **surface file** under AD-5, and
`backend/tests/architecture/test_no_direct_writes.py:47` asserts
`len(names) == 23` — adding one breaks that test and would need the count changed.

The cleanest home is a **new `apps/personalization/source_mutes_api.py`**, because the
row it writes (`personalization_sourcemute`) is `personalization`'s and the
personalization app already owns `/api/personal/*`. That means updating the count
23 → 24 in the architecture test — a one-line change to a test that is *designed* to
fail when a surface file is added. The alternative, adding the endpoints to
`delivery/preferences_api.py`, would put `personalization`'s commands behind `delivery`'s
router, which is the ownership blur AD-16 exists to prevent.

**Decision: new `apps/personalization/source_mutes_api.py`, and update the architecture
test's surface-file count from 23 to 24.**

The API layer is thin, like every other: resolve the user from the session, call the
published service, project the service's plain data onto the wire shape. It never
imports `apps.personalization.models` and never touches the ORM — the AD-5 architecture
test enforces that.

### The screen

`/settings/sources`, on the five-step house pattern documented at
`frontend/app/settings/page.tsx:26-41`, with `frontend/app/settings/calendars/page.tsx`
as the canonical implementation. **And** a row in `SETTINGS_SECTIONS`
(`frontend/lib/settings-sections.ts`) — `frontend/tests/settings-routes.test.ts:53-62`
fails on a settings route that is not listed, so this is required, not optional.

The mockup's section nav lists "Sources" as a peer of Appearance / Notifications /
Quiet hours / Calendar sync / Account / Plan / Privacy, and the built sub-nav is
`SettingsNav`, which renders `SETTINGS_SECTIONS`. The screen therefore gets a row in
`SETTINGS_SECTIONS` labelled "Sources", with a description matching the page's own
subheading.

**The 3-state control.** The mockup's markup is a `role="group"` with an
`aria-label="Mute controls for <source>"`, three buttons, and `aria-pressed="true"` on
the selected one. This plan follows that exactly — a radio group is the semantically
right control, and `aria-pressed` on three buttons in a labelled group is the pattern
the mockup already specifies.

**"Restore all defaults"** is the footer ghost button. The mockup's note says: *"We ask
once before applying."* The confirmation dialog is the **frontend's** job — the endpoint
is a single idempotent bulk delete, and the client confirms before it calls it. That is
§10.4's bulk-action safeguard satisfied: the destructive action is confirmed before it
completes.

### Client generation (AD-19)

`make client` regenerates `frontend/lib/api/schema.ts` from the OpenAPI schema, and CI
does `git diff --exit-code frontend/lib/api/`. The generated output **must be
committed** in this change.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/personalization/models.py` | (modify — see below) `SourceMute` |
| `backend/apps/personalization/migrations/0016_sourcemute.py` | Forward-only migration for `SourceMute`, with the AD-15 retention declaration |
| `backend/apps/personalization/services/source_mutes.py` | The commands: `set_source_mute`, `restore_source_defaults`, and the read helpers `muted_source_ids` / `show_less_source_ids` |
| `backend/apps/personalization/source_mutes_api.py` | The three endpoints (a surface file — thin, no ORM, no model imports) |
| `backend/apps/ingestion/services/source_registry_read.py` | The source-registry read that crosses the wall: grouped by badge, with each source's reliability and the fields the screen shows |
| `backend/tests/personalization/test_source_mutes.py` | The command tests: set / unset / bulk reset / the state vocabulary |
| `backend/tests/personalization/test_source_mute_composition.py` | The proof that the mute **changes what is shown** — in Digest and in Browse |
| `backend/tests/ingestion/test_source_registry_read.py` | The registry read: grouping by badge, the trust band, the prior for an un-scored source |
| `frontend/lib/source-mutes-read.ts` | The server-side read helper (`readSources`), mirroring `calendars-read.ts` |
| `frontend/app/settings/sources/page.tsx` | The screen |
| `frontend/app/settings/sources/loading.tsx` | The sibling loading state |
| `frontend/components/settings/source-mute-control.tsx` | The 3-state control (`role="group"`, `aria-pressed`) |
| `frontend/components/settings/source-trust-dots.tsx` | The 1–5 ink-primary dots with `aria-label="N of 5 reliability"` |
| `frontend/components/settings/source-list.tsx` | The grouped list, the empty state, and the "Restore all defaults" footer with its confirmation |
| `frontend/tests/settings-sources.test.tsx` | The screen's tests |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/personalization/models.py` | Add `SourceMute` — `user_id`, `source_id` (both by value), `state`, timestamps; `UniqueConstraint(["user_id","source_id"])`; `Index(["user_id"])`; `retention_category = PREFERENCE_SIGNALS` |
| `backend/apps/ingestion/services/catalog_read.py` | Add `source_id: UUID` to `PublicEventCandidate` and populate it in `_to_public_candidate` from the already-`select_related`'d `event.source_id` — **no extra query** |
| `backend/apps/personalization/services/digest_composition.py` | Apply the mute filter and the show-less penalty to the candidate set, before and after scoring respectively |
| `backend/apps/personalization/services/browse_read.py` | The same two adjustments, so Browse and Digest agree |
| `backend/apps/personalization/schemas.py` | The wire shapes: `SourceMuteState`, `SourceTrustOut`, `SourceOut`, `SourceGroupOut`, `SourceListOut`, `SourceMuteSetIn` |
| `backend/apps/personalization/api.py` | Import and re-export nothing — the new router is mounted separately in `config/api.py` |
| `backend/config/api.py` | Mount `source_mutes_router` under `/settings` (it is the same `/api/settings` prefix the notifications router already uses) |
| `backend/shared/constants.py` | The trust-band boundaries and the show-less penalty, with their rationale |
| `backend/tests/architecture/test_write_ownership.py` | Add `personalization_sourcemute: personalization` to `TABLE_OWNERS` — a table with no declared owner fails the test |
| `backend/tests/architecture/test_no_direct_writes.py` | The surface-file count 23 → 24, because a new `*_api.py` is a surface file |
| `frontend/lib/settings-sections.ts` | Add the "Sources" row |
| `frontend/lib/api/schema.ts` | **Regenerated** by `make client` and committed (AD-19) |
| `frontend/lib/api/openapi.json` | **Regenerated** by `make client` and committed |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/personalization/test_source_mutes.py` | `set_source_mute` writes a row for `mute` and `show_less`; `default` **deletes** the row rather than writing one; the unique constraint holds; `restore_source_defaults` clears every row for the user and nothing else; the state vocabulary rejects anything else |
| `backend/tests/personalization/test_source_mute_composition.py` | **The acceptance criterion.** A muted source's events are **absent** from the composed digest's candidates and from Browse's page; a show-less source's events are **present** but ordered **lower** than an otherwise-identical event from an un-muted source; a source with no mute row is unaffected |
| `backend/tests/ingestion/test_source_registry_read.py` | The four badge groups; the trust band at each boundary; the 0.50 prior for a source with no stored score; an empty registry returns empty groups, not fabricated sources |
| `backend/tests/api/test_source_mutes_api.py` | The three endpoints: the list's shape, the PUT's three states, the bulk reset; and that the user id comes from the session and never from the payload |
| `frontend/tests/settings-sources.test.tsx` | The grouped rendering, the 3-state control, the dots' `aria-label`, the empty state, and that "Restore all defaults" **asks before it calls** |

**Every test gets a mutation probe** — a one-line change that makes it fail — per the
testing standards. The probes for this item are: flip `mute` to a no-op in the filter;
delete the row instead of writing it in `set_source_mute`; make the penalty a no-op;
remove the `source_id` from the candidate; invert the trust band boundaries.

## Technical Details

### The model

```sql
CREATE TABLE personal.personalization_sourcemute (
    id          uuid        PRIMARY KEY,
    user_id     uuid        NOT NULL,
    source_id   uuid        NOT NULL,
    state       varchar(16) NOT NULL,
    created_at  timestamptz NOT NULL,
    updated_at  timestamptz NOT NULL,
    CONSTRAINT source_mute_state_ck CHECK (state IN ('show_less', 'mute')),
    CONSTRAINT source_mute_user_source_uq UNIQUE (user_id, source_id)
);
CREATE INDEX source_mute_user_idx
    ON personal.personalization_sourcemute (user_id);
```

`state` holds **only** the two non-default states. The check constraint is what makes
the vocabulary enforceable in the database rather than only in Python.

The state vocabulary lives in the model as `TextChoices`, exactly as `Source.Status`
does, so the schema and the service cannot disagree.

### The commands (AD-5 — one mutation path per entity)

`apps/personalization/services/source_mutes.py`:

| Function | Behaviour |
|---|---|
| `set_source_mute(*, actor, user_id, source_id, state)` | `mute`/`show_less` → `get_or_create` then update, inside `transaction.atomic(using=PERSONAL)`, with a `write_audit` row. `default` → **delete** the row if it exists, and write the audit row |
| `restore_source_defaults(*, actor, user_id)` | Bulk delete every row for the user, in one transaction, with one audit row |
| `muted_source_ids(*, user_id)` | The set of source ids to exclude, read in one query |
| `show_less_source_ids(*, user_id)` | The set of source ids to deprioritise, read in one query |

Both read helpers are one query each. They are read together on the hot path, so
`compose_digest` and `read_browse_page` call **one** helper that returns both sets —
a single query for the user's mutes, not two.

`write_audit` must run inside `transaction.atomic(using=PERSONAL)` — the helper raises
`AuditOutsidePersonalTransaction` otherwise
(`apps/personalization/services/audit.py:40-43`).

### Applying the filter and the penalty

In `compose_digest` (`digest_composition.py`), the candidate set is built around
`:652-665`. The mute filter drops candidates whose `source_id` is in the muted set,
**before** the slot scorers run. The show-less penalty is applied to `_Scored.score`
after `_score_public` has computed it and before `_assign_slots` orders by
`order_key()`.

`_Scored.order_key()` (`digest_composition.py:344-352`) is `(-score, start_time_utc,
event_id)` — a total order, so lowering the score lowers the event's position without
perturbing the tie-breaks.

In `browse_read.py`, the equivalent seam is the `(relevance_score(inputs), ...)` tuple
built at `:295` and sorted at `:302` by `(-score, start, id)`. The same two
adjustments are applied there, from the same service helper.

**`show_less` does not hide anything.** A test asserts that a show-less source's
events are still **present** in the page, and ordered lower. A "show less" that hid
events would be a lie to the user — and it would be indistinguishable from `mute` on
the wire.

### The trust band

`shared/constants.py`, next to the reliability constants:

```python
#: The source trust bands — the 1–5 dots on Settings → Sources.
SOURCE_TRUST_BAND_5 = Decimal("0.80")
SOURCE_TRUST_BAND_4 = Decimal("0.65")
SOURCE_TRUST_BAND_3 = Decimal("0.50")
SOURCE_TRUST_BAND_2 = Decimal("0.35")
SOURCE_TRUST_BANDS = (0.80, 0.65, 0.50, 0.35)
```

A function `source_trust_band(score) -> int` returning 1–5, with **0.50 → 3**, so a
never-scored source (the prior) reads as "ok" rather than as "low coverage". This is
the source's *trust*, which is not the Confidence Pulse's bucket — so it does not reuse
`domain/ranking.py:341`'s `score_bucket`, whose boundaries are FR-22's and whose
docstring's `≥` is implemented as `>`.

The band is computed on the **catalog side**, in the `ingestion` read service, so the
number the client renders is the server's statement — the same rule the Source Badge
follows ("the server names the type, the client owns the label").

### The registry read

`apps/ingestion/services/source_registry_read.py` returns plain dataclasses — no
model escapes the app. It reads `Source` rows with their `reliability_score`, resolves
each one's badge via `source_badge_for_type`, computes the trust band, and groups by
badge in the fixed order **Official → Community → Aggregator → Crawled**.

**Which sources appear.** `Source.status` is `active` or `paused`, and a paused source
is still in the registry. The screen shows **every** source in the registry — including
paused ones — because the screen's job is transparency ("who is informing your
timeline"), and hiding a paused source would hide a source that is still on record.
A paused source is marked paused.

**An empty registry returns empty groups.** No group is fabricated, and the client
renders `component.emptystate.quiet` — which the mockup already provides for.

### The wire shapes

`apps/personalization/schemas.py`, following the existing conventions (a
`Literal`-constrained alias for the state, `from_view` classmethods):

```python
SourceMuteState = Literal["show_less", "mute"]
```

The **client** constrains the state to the two storable values; `default` is expressed
by the client as a DELETE-like call to the PUT endpoint with `"default"`, which the
service turns into a delete. The schema's `Literal` deliberately includes `"default"`
so the endpoint can accept the three-state vocabulary the mockup shows.

### The frontend

`frontend/lib/source-mutes-read.ts` mirrors `calendars-read.ts`: a server-side read
that carries the session cookies, and a `found` / `unavailable` distinction — because
"unavailable" and "you have no sources" look identical on screen and mean opposite
things.

`frontend/app/settings/sources/page.tsx` follows the five steps:
`force-dynamic` → `homeRoute(session)` redirect → the signed-out branch with
`SettingsStates` → the `unavailable` branch with `SettingsStates` → the page.

`frontend/components/settings/source-trust-dots.tsx` renders five dots,
`--ink-primary` for on and `--ink-faint` for off, with
`aria-label="N of 5 reliability"` on the group — the mockup's own markup. The label
reads `trust · N` in the mono face. **No new tokens, and no terracotta.**

`frontend/components/settings/source-mute-control.tsx` renders the three buttons with
`aria-pressed` on the selected one, inside a `role="group"` with
`aria-label="Mute controls for <source>"`.

`frontend/components/settings/source-list.tsx` renders the four groups, the empty
state, and the footer. **"Restore all defaults" opens a confirmation before it calls
the endpoint** — the button is a ghost button, and the confirmation is a dialog that
names what is about to happen ("this clears custom mutes across the board"), matching
the mockup's note.

### The `SETTINGS_SECTIONS` row

```ts
{
  href: "/settings/sources",
  label: "Sources",
  description: "Where your events come from, and how much of each you want to see.",
},
```

The label matches the page's `<h1>`, and the description matches the page's
subheading — the two rules `settings-sections.ts` states for itself.

## Based on Design Doc

Reference: `.specs-fire/intents/source-transparency-and-mute/work-items/settings-sources-surface-design.md`

---
*Plan approved at checkpoint. Execution follows.*
