---
run: run-eventpulse24-057
work_item: home-city-dropdown-catalog
intent: city-picker-and-auto-collection
generated: 2026-11-21
mode: confirm
---

# Plan: The dropdown reads the catalog

## Context

Run `run-eventpulse24-057`, intent `city-picker-and-auto-collection`, work item 11 of 11.

Item 4 built `GET /api/public/cities` — every city in the curated catalog, as
`value`/`label` pairs, sorted by label, served with **no session** (AD-12). Item 5 made
the stored city *be* the picked city. Item 9 gave Browse its four honest states. Item 10
gave the no-sources state a way out.

**Nothing yet calls item 4's endpoint.** The picker still reads
`GET /api/public/preview/cities` — the list derived from the events that exist. A reader in
Chittagong, a city the catalog holds and nothing has been ingested for, is **not offered
Chittagong**. The picker offers a mirror of what we happen to have rather than a map of
the world.

That is the gap. And it is the gap that makes the whole run's guarantee hollow: the
guarantee is *"the stored city is the picked city"*, and a picker that does not offer the
catalog cannot pick from the catalog.

## The one problem the item really was

**The options are now pairs, and the select needs one string.**

The old endpoint returned `cities: string[]` — one string per city, used as both the
label and the value. The new one returns `cities: [{value, label}]`, because **the
catalog's two forms are different strings on purpose**:

| | Portland | |
|---|---|---|
| `value` — stored, machine | `"Portland, OR"` | what `DigestPreference.city` holds; what `split_region` understands |
| `label` — shown, human | `"Portland, Oregon"` | what disambiguates Atlanta from Tbilisi |

The reader must **see** the label and **submit** the value. A `<select>` natively does
exactly this: `<option value={value}>{label}</option>`. So the shape the endpoint already
has is the shape the control already wants — **the option's text and the option's value
are separate attributes**, and the browser submits the value while the reader reads the
text.

**So this item is mostly about not collapsing the two.**

## The decisions

### 1. The read moves to the catalog endpoint, and the type changes with it

`frontend/lib/home-city-read.ts` calls `api.GET("/api/public/preview/cities", {})`. It
becomes `api.GET("/api/public/cities", {})`, and `choices` becomes
`CityChoice[]` — the generated `components["schemas"]["CityChoiceOut"][]` — rather than
`string[]`.

**The type is the point (AD-19).** The generated client already knows the endpoint's
shape; the read hands the component that shape, and a component that reaches for
`option.value` on a string is a compile error rather than `undefined` at runtime.

### 2. The component's prop becomes `CityChoice[]`, and it renders label-over-value

`HomeCity` takes `choices: CityChoice[]`. Each option is:

```tsx
<option key={choice.value} value={choice.value}>
  {choice.label}
</option>
```

**The key is the value, not the label** — two rows may share a label only if the catalog
allows it, and it does not (a whole-dataset invariant asserts no two rows share either
string). The value is the identity: it is what a preference holds.

### 3. The stored city stays in the options — by value

The old line was:

```ts
const options = choices.includes(city ?? "") || city === null ? choices : [city, ...choices];
```

The work item says *"Keep it; the only change is where `choices` comes from and that
options now carry a separate label."* The line's **meaning** survives, its **shape**
changes: `choices` is now pairs, so "includes" becomes "some choice's value equals the
city".

**And the stored city needs a label of its own.** A stored city the catalog no longer
offers has no `CityChoice` — and the option we synthesise for it has no label either.
**So the synthesised option shows the stored city as its own label.** "Atlantis" reads as
"Atlantis". There is nothing better to show: we do not know what it is, and inventing
"Atlantis, Atlantis" would be noise.

**This is the one place where a value and a label can coincide**, and it is exactly the
case the catalog's invariant excludes for *its own* rows. So the component's rule is:

| | label shown | value submitted |
|---|---|---|
| A catalog choice | `choice.label` | `choice.value` |
| The stored city, not in the catalog | the stored city itself | the stored city itself |

**A select whose value is absent from its options renders blank**, which would read as
"no city" to someone who has one. That is the behaviour the work item says must be
preserved *by test, not by accident* — and it is preserved by test here.

### 4. `citySourceNote()` is untouched, and the `fallback` label survives

The work item: *"`citySourceNote()` still labels a `fallback` city honestly for the
accounts that already carry one."* The function reads the stored city and its source — it
does not touch the options. **Nothing changes.** The accounts that already carry a
`fallback` city keep their honest label.

**And the fallback is still a real possibility**, because the *other* paths into the
preference (the geo guess, the backfill) still fall back — only a **`choice`** is refused
when the catalog does not hold the city (item 5's rule, in `digest_preferences.py`:
`raise _refused(city)` for `SOURCE_CHOICE`, `return PREVIEW_FALLBACK_CITY, SOURCE_FALLBACK`
for everything else). So the note's `fallback` branch is live, not vestigial.

### 5. The docstring's rewrite paragraph is replaced, not deleted

The docstring says:

> **And it is why this is a select rather than a text box.** The server replaces a city it
> cannot serve with a fallback (FR-2), silently — so typing "Chittagong" would appear to
> work and quietly store somewhere else. A picker cannot express the request that would
> be mishandled.

**This is no longer true for a picked city**, and the work item is explicit that it must
not be left standing as the stated reason for the control's shape. Item 5 made a *chosen*
city outside the catalog a **refusal** (422), not a silent substitution. So a text box
would no longer "quietly store somewhere else" — it would be refused.

**But the select is still right, for a different reason, and the docstring must say the
real one:**

- **The catalog is the set of cities we can serve.** A free-text city outside it is
  refused, and a reader typing "chitagong" (a spelling we do not hold) gets a refusal
  rather than a match — a picker shows them the spelling we do hold.
- **A select offers the whole catalog.** 165 cities in a native `<select>` get the
  platform's own type-ahead and the mobile picker's own wheel. A text box offers none of
  that and adds a second job — resolving what the reader typed into something we hold.

So the reason the control is a select is **the catalog's size and the catalog's
canonical spellings**, not a silent rewrite that no longer happens.

### 6. `preview/cities` keeps its caller

`frontend/components/preview/preview-section.tsx` calls
`api.GET("/api/public/preview/cities")` — **the Pulse Preview's own list of cities that
have events right now**. That is a different question and it stays. Only the *picker*
moves.

**This matters for `endpoint-coverage.test.ts`**: `GET /api/public/preview/cities` is
still called (so it is not an orphan), and `GET /api/public/cities` gains a caller, so its
entry in `DECLARED_UNCALLED` must come out — **the test fails if a declared-uncalled
endpoint has a caller.** The work item says exactly this: *"remove the `GET
/api/public/cities` entry from `DECLARED_UNCALLED` that item 9 added."*

### 7. The endpoint-coverage test's caller-detection must see the new call site

The coverage test walks `app/`, `components/` and `lib/`, strips comments, and looks for
the endpoint string. `home-city-read.ts` will contain `api.GET("/api/public/cities", {})` —
a plain string literal, so it is found. **But the comment-stripping matters**: the old
docstring named `/api/public/preview/cities` in prose, and the new docstring will name
`/api/public/cities` in prose. Both are stripped, so neither is a false positive.

**Careful**: the *new* docstring must not be the only mention. The actual call site is
what counts.

### 8. The headline test: a city with no ingested events is picked and kept

The work item demands it: *"A test asserts a city with no ingested events is picked and
kept — it must fail against today's rewrite."*

**Where does this test live?** The rewrite was a *backend* behaviour (item 5's
`resolve_home_city`), and the picker's own behaviour is *frontend*. The honest place is
**both**:

- **Backend** — `backend/tests/personalization/test_stored_city_is_the_picked_city.py`
  already holds 682 cases of the catalog rule. Item 5's own suite asserts a city with no
  events is stored verbatim. **If that suite already proves it, this item's job is to
  point at it** — and to add the *end-to-end* half the picker needs.
- **Frontend** — the picker's own test: a choice whose `label` differs from its `value`
  is offered, is submitted as its `value`, and comes back as the stored city.

**The frontend test is the one that "must fail against today's rewrite"** — because
today the options are strings and there is no label at all. The frontend test is the
item's own.

### 9. The control stays a `<select>`

The work item: *"It stays a `<select>`. No free text."* and *"the user asked twice for a
dropdown and not a text box."* **No combobox, no type-ahead component, no filtering.**
The platform's native `<select>` gives keyboard type-ahead for free — that is what the
AC *"keyboard type-ahead works"* means, and it is the browser's, not ours.

**And the option count does not break the layout.** 165 options in a native `<select>`
is fine; the control's width is the CSS's business and does not change.

### 10. No country dropdown, no country field, no "cities near you"

The work item forbids all three. **The catalog's `country_code` / `country_name` live in
the label** ("Chittagong, Bangladesh") — that is a *label*, not a control. **Nothing in
this item adds a country selector, a geolocation button, or a "near me" affordance.**

## The files

```text
frontend/lib/home-city-read.ts                    MODIFIED
└── the read calls GET /api/public/cities; choices is CityChoice[]

frontend/components/settings/home-city.tsx        MODIFIED
├── choices: CityChoice[]
├── the options render label, submit value
├── the stored city stays in the options, by value
└── the docstring's rewrite paragraph is replaced

frontend/components/settings/place-settings.tsx   MODIFIED
└── choices: CityChoice[]

frontend/app/settings/profile/page.tsx            MODIFIED
└── unchanged in behaviour — the type flows through

frontend/components/settings/home-city.test.tsx   MODIFIED
├── the label is shown, the value is submitted
├── the stored city stays in the options
└── a city with no events is picked and kept

frontend/tests/endpoint-coverage.test.ts           MODIFIED
└── the GET /api/public/cities entry comes out of DECLARED_UNCALLED

frontend/app/settings/profile/page.test.tsx       MODIFIED
└── the fixture carries the new shape

frontend/tests/profile-a11y.test.tsx               MODIFIED
└── the fixture carries the new shape

frontend/components/settings/place-settings.test.tsx   MODIFIED
└── the fixture carries the new shape
```

## The tests

**`frontend/components/settings/home-city.test.tsx`** — the item's own:

1. The option's **text is the label** and its **value is the catalog's value** — "Portland,
   Oregon" / `"Portland, OR"`.
2. **Picking the label's option submits the value** — the PUT body's `city` is
   `"Portland, OR"`.
3. **The stored city is shown as its own label** when the catalog no longer offers it,
   and its value is the stored city.
4. **The stored city keeps its slot** when the catalog *does* offer it — no duplicate
   option.
5. **The placeholder appears only when no city is set.**
6. `citySourceNote()` still labels a `fallback` city honestly.
7. **The headline**: a catalog city with no ingested events is picked and kept — the
   select shows it, the PUT sends its value, and the server's answer puts it back.

**`frontend/tests/endpoint-coverage.test.ts`** — the removal of the declaration; the
existing test fails if a declared-uncalled endpoint has a caller.

**Backend** — nothing changes. Item 5's suite already holds the catalog rule, and this
item changes no backend behaviour. **The endpoint's own contract** is item 4's.

## The mutation check

The run's rule is *a test must be able to fail*. This item's whole dataset is
`value`/`label` pairs and the boundary between them, so:

| Mutation | Caught by |
|---|---|
| The option shows the value instead of the label | the label test |
| The option submits the label instead of the value | the submit test |
| The stored city is dropped from the options | the stored-city test |
| The synthesised option shows an empty label | the stored-city label test |
| The placeholder is always shown | the placeholder test |
| The declaration stays in `DECLARED_UNCALLED` | the coverage test's stale-exemption check |
| The read goes back to `preview/cities` | the coverage test's orphan check |
| The catalog's `value` is submitted instead of the stored city's | the headline test |

## The risks

**The stored city's label is a guess, and it is the honest one.** When the catalog no
longer offers the stored city, we show the stored string as its own label. There is
nothing better: the catalog's disambiguating form for a city it does not hold is unknown,
and inventing one would be a fabrication. **The risk is a reader seeing "Portland, OR"
in the list where every other row reads "Portland, Oregon"** — a slight inconsistency,
visible only to someone who has a stale city, and it is the truth about that city.

**The endpoint-coverage test is the risk that bites.** It asserts *every* endpoint in the
contract is called or declared. Adding a caller to `/api/public/cities` while leaving the
declaration in place **fails the test** — that is the point. And moving the read back to
`preview/cities` without moving the declaration **also fails it** — the preview endpoint
would have two callers and the catalog none, so the catalog becomes an orphan. Both
directions are caught.

## What this unblocks

**The run's guarantee, closed.** "The stored city is the picked city" is only meaningful
if the picker offers the picked city. **It now does** — every city in the curated
catalog, whether or not anything has ever been ingested there.

**And the run-level `walkthrough.md`**, which is owed at run completion.
