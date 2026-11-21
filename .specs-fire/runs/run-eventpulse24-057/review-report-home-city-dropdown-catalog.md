---
run: run-eventpulse24-057
work_item: home-city-dropdown-catalog
intent: city-picker-and-auto-collection
generated: 2026-11-21
status: passed
---

# Review Report: The dropdown reads the catalog

## What this item adds

The last link in the chain. Item 4 built the catalog's choices endpoint; item 5 made the
stored city be the picked city; item 7 made a pick provision the city; item 9 gave
Browse its honest states; item 10 gave the dead end a way out.

**Nothing called item 4's endpoint.** The picker still read the preview's list of cities
that have events right now — so a reader in a city the catalog holds and nothing has been
collected for was **not offered their own city**.

| Piece | Where | What it is |
|-------|-------|-----------|
| The read | `frontend/lib/home-city-read.ts` | `GET /api/public/cities`, and `choices` is now a list of pairs |
| The control | `frontend/components/settings/home-city.tsx` | label shown, value submitted, the stored city kept |
| The declaration | `frontend/tests/endpoint-coverage.test.ts` | `GET /api/public/cities` comes out of `DECLARED_UNCALLED` |

## The findings

### 1. The picker was a mirror, not a map

The two lists answer different questions, and the picker was asking the wrong one.

| | `GET /api/public/preview/cities` | `GET /api/public/cities` |
|---|---|---|
| Question | Which cities can the Preview serve *right now*? | Which places may a reader *pick*? |
| Computed from | `EventFit` rows and upcoming events | the curated catalog, a frozen tuple |
| True while | those events are upcoming | always |
| A reader in Chittagong | **not offered Chittagong** | offered Chittagong |

**"A city is offered when the catalog has an upcoming public event with an Event Fit for
it"** — that was the old docstring's description of the picker's own source, and it is a
mirror of what we happen to have. The whole run's premise is the opposite: the catalog is
a map of the world, and **finding the events is the provisioning service's job**. A
reader in a city we have not collected for yet is the *most* important reader to offer it
to.

**And this is what made the run's guarantee hollow.** The guarantee is *"the stored city
is the picked city"* — which is only meaningful if the picker offers the picked city.
Before this item, a reader could not pick Chittagong at all, because Chittagong had no
events.

### 2. The two strings per city are the whole point

The catalog's `value` and `label` are **different strings on purpose** — `"Portland, OR"`
is stored and `"Portland, Oregon"` is read — and the endpoint already returns them as a
pair.

**A native `<select>` already does exactly what is needed**: the option's *text* is what
the reader sees and the option's *value* is what is submitted. So the control renders one
and lets the browser do the rest. **Nothing translates between them.**

This matters more than it looks. The catalog holds *"Atlanta, Georgia"* and *"Tbilisi,
Georgia"* — **two rows whose labels differ only in the first word**, and whose values are
`"Atlanta, GA"` and `"Tbilisi, GE"`. A control that showed the value would offer the
reader two nearly-identical entries; a control that submitted the label would store
`"Atlanta, Georgia"`, which the server does not hold and would refuse.

### 3. The stored city is matched by its **value**, not its label

This is the one subtle thing in the item, and the mutation check earned its keep on it.

The stored city is `"Portland, OR"`. The catalog's **label** for it is
`"Portland, Oregon"`. So a control that asked *"does some choice's label equal the stored
city?"* would **not find it** — and would synthesise a second option for it, offering the
reader the same city twice under two different spellings.

The rule is therefore: **"does some choice's *value* equal the stored city?"** — never the
label. And the plan's decision 3 said so before the code was written, which is why the
mutation was caught by a test that already existed.

### 4. A stored city the catalog no longer holds has no label — and that is honest

The synthesised option shows **the stored city as its own label**: "Atlantis" reads as
"Atlantis".

**There is nothing better to show.** The catalog's disambiguating form for a city it does
not hold is unknown — the disambiguating form *is* the catalog's data. Inventing one
would be a fabrication, and "Atlantis, Atlantis" would be noise.

**This is the one place where a value and a label coincide**, and it is exactly the case
the catalog's whole-dataset invariant excludes for *its own* rows (no two rows share
either string). So the component's rule is a table, not a formula:

| | label shown | value submitted |
|---|---|---|
| A catalog choice | `choice.label` | `choice.value` |
| The stored city, not in the catalog | the stored city itself | the stored city itself |

### 5. The docstring's reason changed, and it says so

The old docstring said the control is a select because *"the server replaces a city it
cannot serve with a fallback (FR-2), silently — so typing 'Chittagong' would appear to
work and quietly store somewhere else."*

**That is no longer true of a chosen city.** Item 5 made a chosen city outside the
catalog a **refusal** (422), not a substitution. So the stated reason for the control's
shape was false, and a docstring that explains a decision with a false reason is worse
than no docstring — it sends the next reader looking for a rewrite that no longer
happens.

**The control is still a select, for a different reason, and the docstring now says the
real one:**

- **The catalog's size.** 166 places in a native `<select>` get the platform's own
  type-ahead and the mobile picker's own wheel. **A text box would offer neither**, and
  would add a second job — resolving what the reader typed into something we hold. A
  reader who writes "chitagong" gets a refusal; a picker shows them the spelling we do
  hold.
- **The user asked twice for a dropdown and not a text box.** The work item says so, and
  a text box would be a licence to widen the scope.

### 6. The `fallback` note is not vestigial

The work item asks that `citySourceNote()` still label a `fallback` city honestly, and
the temptation is to treat the branch as dead code now that a chosen city is refused
outright.

**It is not.** Only a **`choice`** is refused when the catalog does not hold the city.
`digest_preferences.py` says:

```python
if source == SOURCE_CHOICE:
    raise _refused(city)
return PREVIEW_FALLBACK_CITY, SOURCE_FALLBACK
```

**A geo guess and a backfill still fall back** — the server chose those cities, and there
is no reader to mislead. So accounts carrying a `fallback` city still exist, and the note
still has something to say. The test asserts it.

### 7. The endpoint-coverage test is what notices the *source* changed

Nothing else would. The component would have worked perfectly with the preview's list —
it would simply have offered fewer cities, with no labels, and every one of its own tests
would have stayed green.

**The coverage test is the only thing that notices**, and it notices in both directions:

- **The picker on the catalog and the declaration still in place** → *"has no declared-
  uncalled endpoint that is in fact called"* fails. **The stale exemption is a lie in the
  same way a missing one is.**
- **The picker back on the preview and the declaration removed** → *"has no endpoint that
  is neither called nor declared"* fails. **The catalog endpoint becomes an orphan.**

So the removal of the declaration is not a cleanup — it is the second half of a
two-sided guard, and both halves are under test.

### 8. The control's shape is unchanged, and that is a decision

**It is still a `<select>`.** No combobox, no type-ahead component, no filtering, no
free text. The platform's own type-ahead *is* the type-ahead, and a native `<select>` is
what makes it work.

**And the layout is unchanged.** The control's box is sized by its CSS and a native
`<select>` **never widens its box to fit an option** — the longest option (38 characters)
is rendered by the platform's own popup. 166 options is a number the platform handles.

**The country is in the label, not in a control.** "Chittogram, Bangladesh" is one
option's text. **A reader sees where a city is; a reader cannot pick a country.** No
country dropdown, no country field, no "cities near you" — the work item forbids all
three, and none exists.

## The security and architecture notes

### AD-19 — the frontend reaches the backend only through the generated client

- The read calls `api.GET("/api/public/cities", {})` — the generated client, and the
  path is the contract's.
- **`choices` is typed by the contract** — `components["schemas"]["CityChoiceOut"]`, so
  a control reaching for `option.value` on a string is a compile error rather than
  `undefined` at runtime. **The type change is the guard.**
- **No `make client`** — the API surface did not change. Item 4's contract is item 4's.

### AD-10 — the server's answer replaces the client's guess

Unchanged, and still asserted: the control puts back what the server stored, including
when the server stored a *different* city (the `fallback` case).

### AD-12 — the public catalog is session-free

**The endpoint this item now calls is session-free, and the read is not.** The read
carries a session because it also asks `/api/personal/onboarding` — the caller's own
preference — and the two requests are `Promise.all`ed precisely so the public list does
not need one. **The auth seam is unchanged and untouched.**

### No backend file changed

**Every file this item touched is under `frontend/`.** The endpoint is item 4's; the
storage rule is item 5's; the provisioning is item 7's. **This item moves a caller and
the shape of a payload, and nothing else.**

## The findings that were *not* problems, and why

**The stored city's label is a guess.** It is not — it is the stored string itself, and
the docstring says why. There is nothing else to show.

**`preview/cities` still has a caller.** It does, and it should: the Pulse Preview's own
list of cities with events is a different question from "which places may a reader pick",
and the preview component is the right home for it.

## The deliberately-not-changed list

| Not changed | Why |
|-------------|-----|
| `backend/` — everything | No endpoint, no schema, no model, no service. Item 4 built the endpoint; item 5 owns the storage rule. |
| `frontend/lib/api/{openapi.json,schema.ts}` | The API surface did not change, so `make client` has nothing to do. |
| `frontend/components/browse/browse-hero.tsx` and `browse-states.tsx` | Both "Change city" links already point at `/settings/profile`, and both are asserted by the browse tests. |
| `frontend/app/settings/profile/page.tsx` | The type flows through it; the behaviour is unchanged and the docstring is still accurate. |
| `citySourceNote()` | Its three branches are all live. The `fallback` one especially — a geo guess and a backfill still fall back. |
| The preview's own list | A different question, with its own caller. |

## The verdict

**The item's acceptance criteria are met, and the mutation check proves the tests can
fail.**

- The picker reads the catalog, and the coverage test fails if it stops — **in both
  directions**.
- The label is read and the value is stored, and two separate mutations prove the two
  halves cannot be swapped.
- A city with no ingested events is picked and kept, and the test says so.
- The stored city stays in the options, matched by its **value**, and shows itself as its
  own label when the catalog no longer holds it.
- The docstring's false reason is gone, and a real one has replaced it.
- The control is still a `<select>`, and the option count does not break the layout.
- No country dropdown, no country field, no "cities near you".

**The one thing I would want a second pair of eyes on** is decision 4 — the synthesised
option showing the stored city as its own label. It is the honest answer, and it is the
only one available: the catalog's disambiguating form for a city it does not hold is
unknown. **But a reader with a stale city sees one entry in the list whose spelling
style differs from every other**, and there is no way to fix that without knowing what
the city is. The alternative — dropping the option — would render the select blank, which
is a worse lie.

## The files

| File | Change |
|------|--------|
| `frontend/lib/home-city-read.ts` | the read calls the catalog; `choices` is `CityChoice[]` |
| `frontend/components/settings/home-city.tsx` | the options render label over value; the stored city is kept; the docstring is rewritten |
| `frontend/components/settings/place-settings.tsx` | the prop's type |
| `frontend/app/settings/profile/page.test.tsx` | the fixture; two assertions use the catalog's strings |
| `frontend/tests/profile-a11y.test.tsx` | the fixture |
| `frontend/components/settings/home-city.test.tsx` | rewritten — 15 tests |
| `frontend/components/settings/place-settings.test.tsx` | the fixture |
| `frontend/tests/endpoint-coverage.test.ts` | the `GET /api/public/cities` declaration comes out |
