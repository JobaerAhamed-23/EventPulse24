---
run: run-eventpulse24-057
work_item: city-provisioning-service
intent: city-picker-and-auto-collection
mode: validate
checkpoint: plan-approval
status: approved
approved_at: 2026-11-20
---

# Implementation Plan: Provisioning a city on first pick

## What this item is

The service that turns a pick into collection. A reader picks Chittagong; this mints the
`City` row, walks the provider templates from item 6, registers a `Source` per spec, and
records what happened so the surface can tell the truth about it.

After this, the existing scheduler does the rest for free — a source with
`last_attempted_at IS NULL` is due immediately, so `claim_due_sources` takes it on the next
60-second tick. **Nothing here fetches anything.**

## The shape of the flow

```text
reader picks a city
        │
        ▼
set_home_city()  ──personal──►  DigestPreference.city = "Chittagong"
        │
        │ transaction.on_commit(using=PERSONAL)
        ▼
provision_city_on_commit()  ──catalog──►  CityProvisioning row
                                            ├─ City row minted (resolve_city)
                                            ├─ for each spec from city_providers.resolve():
                                            │     register_source(...)  ← the only writer
                                            └─ status: collecting | live | no_providers | ...
```

## The design constraint that shapes everything: two databases

`personalization` writes the `personal` schema; `ingestion` writes the `catalog` schema.
The trigger is registered on the **personal** transaction, and the work is done in the
**catalog** transaction.

**So the work happens after the personal transaction commits, in its own transaction.**
That is the right shape for three separate reasons, and each is a requirement rather than a
preference:

1. **The AC says so**: *"Provisioning is triggered on commit of a successful home-city set,
   never inline in the request's critical path — a slow registry write must not fail the
   user's save."*
2. **A cross-schema transaction is not atomic in Django.** Django will not enlist two
   databases in one `atomic()` block, so a single transaction spanning both would be a
   lie about what is atomic.
3. **`on_commit` is the only honest seam.** The row the worker reads must be committed
   before the worker reads it.

**Which means the trigger is a function call, not a Celery task.** `digest_enqueue` sends
a task through the broker because composing a digest is worker work (AD-11: "a request
handler's job is to validate, enqueue, and return"). Provisioning is different: it is
**ingestion's own service**, calling ingestion's own `register_source`, writing ingestion's
own tables. It does not need the worker runtime, and `personalization` may not import
`worker` or `config` (the layers contract) — but it *may* import
`apps.ingestion.services.*`, which is the established crossing (there are sixteen such
imports in `apps/personalization` today).

**So: `transaction.on_commit(partial(provision_city, ...), using=PERSONAL, robust=True)`.**

### `robust=True`, and what that means here

The digest enqueue uses `robust=True` so "a broker that is down logs the failure and lets
the transaction stand". The same reasoning applies here, for the same reason: **a failure
to provision must not roll back the stored city** (an AC). The pick is kept; the status
reflects the failure.

But `robust=True` in Django swallows the exception and logs it. So the failure must be
**recorded on the row**, not merely logged — otherwise a city that failed to provision
looks exactly like a city that was never provisioned. The status vocabulary has a place
for that.

## The status vocabulary

The AC names five: `collecting` | `live` | `no_providers` | `yielded_nothing` | `paused`.

Reading them against the code:

| Status | Means | When |
|---|---|---|
| `collecting` | Sources registered, we are waiting for events | The normal case right after provisioning |
| `live` | The city has published events | Set by a later item, when the city's first event lands |
| `no_providers` | **No template covers this city** | `city_providers.resolve()` returned an empty tuple |
| `yielded_nothing` | Providers exist, but their events produced nothing | A later item, after an ingest cycle |
| `paused` | Provisioning stopped for this city | The probation item (item 8) |

**`no_providers` is a normal outcome, not an error** — the AC says so, and item 6's
walkthrough says the same: a city outside Ticketmaster's 19 countries resolves to no
sources today, because the Eventbrite template is disabled.

**`collecting` is the honest word for "we registered sources and are waiting".** It is not
`live`: the city has no events until the scheduler has run and a source has answered. The
distinction matters because a reader who picks a brand-new city should be told "we're
collecting" rather than "here are your events".

**`live` and `yielded_nothing` are not this item's to set.** They describe what happens
*after* the first ingest cycle, and this item provisions — it does not ingest. **So they
are in the vocabulary (the AC names them) but this item never writes them.** A test asserts
that, so the vocabulary is not a promise the code does not keep.

## The model: `CityProvisioning`

**It lives in `ingestion`** — the AC says so, and it must: it holds a foreign key to
`City`, and `City` is an `ingestion` model. AD-16 says `ingestion` is the sole writer of
`Source` and `City`; a provisioning record beside them belongs beside them.

```python
class CityProvisioning(UUIDv7Model):
    """What we did about a city, so the surface can tell the truth about it."""
    city = models.OneToOneField(City, ...)   # keyed uniquely on the city
    status = models.CharField(max_length=16, choices=Status.choices)
    source_count = models.PositiveIntegerField(default=0)
    last_error_code = models.CharField(max_length=64, blank=True)
```

**Keyed uniquely on the city.** The AC says "keyed uniquely on the city", and a
`OneToOneField` gives that at the database level — which is what makes idempotency
checkable rather than hoped for.

**`last_error_code` is the same shape `Source` uses** (`last_error_code`, blank when
none), so a reader of the row reads one vocabulary. A provisioning failure is a fact about
the provisioning, and it belongs in a column rather than only in a log line.

**The city name is not in the row.** AD-13: the city is weak location data about a real
person. The row carries the `City` foreign key — which identifies the city without
restating it — and nothing else. The AC says the same: *"AD-13: the city name stays out
of
`details`."*

## The service: `provision_city`

**Where it lives.** `apps/ingestion/services/city_provisioning.py`.

**It may not import `apps.personalization`** — the layers contract points inward, and
`ingestion` is not above `personalization`. So the trigger direction is:
`personalization` → `ingestion`, never the reverse.

```python
def provision_city(*, city_name: str, country_code: str, tz: str, actor: Actor) -> ProvisioningOutcome
```

**The parameters are plain data, not the catalog's `CityChoice`.** `ingestion` may import
`domain.city_catalog` (it is a `domain` module), so it *could* take a `CityChoice`. But
the trigger site is in `personalization`, which holds the stored string `"Chittagong"` —
not a `CityChoice`. So the service takes the plain values and looks the catalog row up
itself. That keeps one source of truth for the city.

Hmm — actually, wait. Let me reconsider: `personalization` *also* may import
`domain.city_catalog`. So the trigger could look the row up and pass the `CityChoice`.

**But the trigger runs in the `personal` transaction's `on_commit`, and the catalog lookup
is cheap and pure.** Either works. The question is which is the better seam.

**Decision: the service takes the plain values and does the lookup itself.** The reason is
that the service is **also** callable from the management command and from a retry, and
those callers hold a city *string* too. A service whose signature demands a `CityChoice`
pushes the lookup onto every caller, and the lookups would drift — one would pass the
stored name, another the display label, another a slug. The service taking a string and
resolving it means there is **one** place that turns a city name into a city, and it is
the same place `resolve_city` already is.

## The five sources of truth in one function

`provision_city` has to line up five things, and each is a fact from somewhere else:

| Fact | From | Why it matters |
|---|---|---|
| The city's canonical row | `resolve_city(city=..., country_code=...)` | So the city has a slug and an FR-27 page before any event arrives |
| The provider specs | `city_providers.resolve(catalog_row)` | Item 6's registry |
| The city's zone | `domain.city_catalog.lookup(name).tz` | Item 2 put `Source.city_tz` on the row for exactly this |
| The source's other fields | The `SourceSpec` | Item 6's `SourceSpec` is the registry's own field names |
| Whether the API key exists | `settings.TICKETMASTER_API_KEY` | **Item 7 owns this** — the handoff says so |

### The API key: refusing to provision an `api` source without one

The handoff is explicit: *"Item 7 owns refusing to provision an `api` source when
`TICKETMASTER_API_KEY` is empty and populating `Source.city_tz` from the catalog."*

**Why refuse rather than register a source that will 401.** `provider_keys.authorized_url`
already handles an empty key gracefully — it returns the URL untouched and `False`, so the
fetch happens without a key and takes the provider's 401. That is deliberate: *"a source
that cannot authenticate is a source whose `last_error_code` should say so."*

So the graceful path exists. But **provisioning a source we know cannot work** is a
different act from **fetching a source and watching it fail**. A source registered with no
key will be picked up by the scheduler within 60 seconds, fail, and burn a slot in the
reliability score and the review queue — for a source that was never going to work. And
the surface would show the city as "collecting" while it collected nothing.

**So: a template whose method is `api` is skipped when the key is not configured**, and
the reason is recorded on the provisioning row. The spec is not registered.

**But `domain` cannot read `settings`.** The template is in `domain/city_providers.py`,
and `domain` is stdlib-only. So the *decision* cannot live in the template. Two options:

- (a) The template asks a callback: `build(city, api_key=...)`. That pushes a
  configuration question into a pure function, and every template would have to handle it.
- (b) **The provisioning service decides, after `resolve()`.** It filters out the specs
  whose method needs a credential that is not configured, using its own knowledge of
  `PROVIDER_KEYS`.

**(b) is right.** The template stays pure — "here is what a Ticketmaster source for
Chittagong looks like" — and the *deployment* decides whether this deployment can use it.
That is the same separation the whole registry rests on: a template describes a provider;
the service describes this installation.

And the filter is driven by `provider_keys.PROVIDER_KEYS`, which already maps
`app.ticketmaster.com → ("apikey", "TICKETMASTER_API_KEY")` — **exact hosts, never
suffixes**, the same rule the parser and the key injector use. So the service asks: *does
this spec's host need a key, and is that key configured?* And the answer is derived from
one table, not a second list of providers that need keys.

**If every spec is filtered out this way, the city records `no_providers`** — because from
this deployment's point of view, no provider can serve it. That is honest, and it is the
same status a country Ticketmaster does not serve gets.

## The AC's guard: "a source is only registered for a method that has a registered parser"

The AC says: *"Registering a method `parse()` would answer `unsupported_method` for is a
defect, and a test asserts it cannot happen."*

Item 6's registry already guarantees this — every method the registry can emit has a
registered parser, asserted over the whole cross-product. **So the guarantee is inherited,
and the service re-checks it at the point of registration**, because that is where the
defect would bite. The service refuses to register a spec whose method is not in
`PARSERS`, and records why.

## The concurrency discipline

The AC: *"Provisioning is concurrency-safe: two users picking the same city at the same
moment produce one set of sources, not two. Use the same advisory-lock discipline
`digest_preferences` already uses rather than relying on the unique constraint to raise."*

**The lock key is the city, not the user.** `digest_preferences` locks on
`blake2b(user_id, person=b"eventpulse24-onb")` — one user's rows. Provisioning locks on
the **city**, because the city is what two users might be provisioning at once.

**A separate lock key space.** `digest_preferences`'s `_LOCK_PERSON` is
`b"eventpulse24-onb"`. Provisioning needs its own — `b"eventpulse24-cty"` — because the
key spaces must not collide: a user id and a city id are both UUIDs, and a hash of one
must never be mistaken for a hash of the other.

**The lock is transaction-scoped** (`pg_advisory_xact_lock`), so a crashed worker cannot
leave a city wedged. Same reasoning, same mechanism.

**The lock is taken in the `catalog` transaction**, because that is the transaction doing
the writing.

**And the lock is not the only guard.** The `CityProvisioning` row is a `OneToOneField`
on the city, so two concurrent provisioners would race on the unique constraint. The
advisory lock makes that race impossible in the normal case; the constraint is the backstop.
But the AC says **not** to rely on the constraint to raise — so the service **re-reads the
row under the lock** and returns early if the city is already provisioned. The lock orders
the writers; the re-read is what makes the second one a no-op rather than an exception.

## Idempotency

The AC: *"Provisioning is idempotent: a second pick of an already-provisioned city
registers nothing further and leaves its status untouched."*

**"Leaves its status untouched"** is the important half. A second pick must not reset a
`live` city to `collecting`. So the re-read under the lock returns the existing row
**unchanged** — no status write, no `updated_at` write, no source write.

**What "already provisioned" means.** The `CityProvisioning` row exists. Not "the status
is `collecting`" — a city whose provisioning *failed* and is recorded as such is still
provisioned, and re-provisioning it should be a deliberate retry, not something a second
reader's pick triggers.

Hmm — that raises a question: **should a failed provisioning be retried by a later pick?**
The AC says "A failure to provision does not roll back the stored city. The pick is kept;
the status reflects the failure." It does not say a later pick retries.

**Decision: a second pick does not retry a failed provisioning.** The reason is that the
pick is not a retry request — the reader did not know anything failed, and the retry would
be invisible to them. A retry belongs to a person or to the scheduler (item 8's
probation). So the row's existence means "provisioned", whatever the status says.

## The trigger site

In `set_home_city`, next to `enqueue_digest_composition_on_commit(user_id)` — **the same
`on_commit` discipline, for the same reason**: the row must be committed before the work
reads it.

**But there is a subtlety the AC implies.** `set_home_city` may be called with a city of
`None` (which *clears* the stored city), or with a `geo` source, or with a `seed` source.

**Should a geo-sourced city be provisioned?** A geo city is an edge's guess — but it is
still a city someone is in. Hmm. And the geo path may store `PREVIEW_FALLBACK_CITY`, which
is a city that is **not in the catalog**.

**So the trigger must fire only for a city the catalog holds.** The service does the
lookup and, if the city is not in the catalog, records nothing at all — there is no
`City` row to key the provisioning on, and `resolve_city` would mint one for "New York
City" that no reader picked.

**Decision: the trigger fires for every city the catalog holds, whatever the source.**
A `geo` guess of "Portland, OR" is a real city a real reader is in, and provisioning it
is right. A geo guess of "Springfield" (not in the catalog) is not, and nothing happens.

**What about `SOURCE_SEED`?** The local dev seed writes "Fixtureville", which is not in
the catalog — so nothing happens. And "Montgomery" *is* in the catalog, so seeding it
would provision it, which is correct and useful for local development.

## What the AC says about the audit rows

*"Audit rows are written for the provisioning and for each registered source. AD-13: the
city name stays out of `details`."*

`register_source` already writes an audit row per source — inside
`transaction.atomic(using=CATALOG)`, with the actor. So "for each registered source" is
**already satisfied** by using `register_source` rather than writing `Source` rows
directly. That is the AC's own instruction: *"through the existing
`source_registry.register_source()` — not by direct ORM writes, so FR-13's audit and
FR-17's guards both apply."*

**And the city name in `register_source`'s details?** The audit details are
`{"fields": fields}`, and `fields` includes `"city"`. **So the city *is* in the audit row**
— and it should be.

### Two different cities, two different rules

The codebase already draws this line, and the AC's phrase "the city name stays out of
`details`" has to be read against it:

| City | Whose | In audit `details`? | Why |
|---|---|---|---|
| **A source's / a venue's city** | a **place** | **Yes** — `register_source` and `register_venue` both write `{"fields": fields}` including the city | It is a public fact about a place. AD-13 is about **PII**: email addresses, OAuth tokens, personal event content. "Chittagong" is none of those |
| **A reader's home city** | a **person** | **No** — `_write_city_audit` writes `{"has_city": bool}`, never the value | It is weak location data about a real person, and the audit log crosses into `catalog` |

So **the AC's rule applies to the provisioning's own audit row** — the one this item writes
about the *reader's* city — and not to the source rows.

**The consequence for this item:** the provisioning audit row records the **city id**, not
the city name. `{"city_id": "...", "status": "...", "sources": 2}` — the id identifies the
city without restating where the reader lives, and it is exactly what an audit reader
needs. The `Source` rows' own audit rows carry the source's city, which is a fact about
the place and belongs there.

**That reading is also the only one that can satisfy both rules at once.** If the city
name had to stay out of *every* audit row, `register_source` would have to change — and
`register_source`'s audit row is FR-13's, about the **source registry**, where a city's
name is public information and the registry's own readers need it. Changing that would be
a change to another item's contract, on this item's say-so.

So: **this item does not touch `register_source`.** It writes its own audit row, with the
city id and never the name.

## The open calls for the checkpoint

**All five confirmed at the checkpoint.**

1. **A city outside the catalog provisions nothing** — the service does the catalog lookup
   and, finding no row, records nothing at all. ✅ confirmed
2. **A failed provisioning is not retried by a later pick** — the row's existence means
   "provisioned", whatever its status. ✅ confirmed
3. **`live` and `yielded_nothing` are in the vocabulary but never written by this item** —
   they describe what happens after the first ingest cycle. ✅ confirmed
4. **The lock is on the city, in its own key space** (`b"eventpulse24-cty"`), not the
   user's. ✅ confirmed
5. **The provisioning's own audit row carries the city id, not the city name** — the
   source rows' audit rows keep the city, because a source's city is a public fact about
   a place and `register_source` is FR-13's, not this item's to change. ✅ confirmed
