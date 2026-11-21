---
run: run-eventpulse24-057
work_item: home-city-dropdown-catalog
intent: city-picker-and-auto-collection
generated: 2026-11-21
mode: confirm
---

# Implementation Walkthrough: The dropdown reads the catalog

## Summary

Item 4 built `GET /api/public/cities` — every place a reader may pick, as `value`/`label`
pairs, served with no session. **Nothing called it.**

The picker read the *preview's* list instead: the cities that have events right now. So a
reader in a city the catalog holds and nothing has been collected for **was not offered
their own city** — and the picker's whole purpose is to let them pick one.

**That was the last hole in the run's guarantee.** *"The stored city is the picked city"*
is only meaningful if the picker offers the picked city.

**This item closes it.** The read moves to the catalog, the options show the label and
submit the value, and the control keeps a stored city the catalog no longer offers.

## The one problem the item really was

**The options are now pairs, and a `<select>` needs one string.**

The old endpoint returned `cities: string[]` — one string per city, used as both the
label and the value. The new one returns `cities: [{value, label}]`, because **the
catalog's two forms are different strings on purpose**:

| | Portland | |
|---|---|---|
| `value` — stored, machine | `"Portland, OR"` | what `DigestPreference.city` holds; what `split_region` understands |
| `label` — shown, human | `"Portland, Oregon"` | what disambiguates Atlanta from Tbilisi |

A native `<select>` already separates them — the option's *text* is read and the
option's *value* is submitted — so **the shape the endpoint already has is the shape the
control already wants.** This item is mostly about not collapsing the two.

## The structure

```text
frontend/lib/home-city-read.ts                    MODIFIED
└── the read calls GET /api/public/cities; choices is CityChoice[]

frontend/components/settings/home-city.tsx        MODIFIED
├── choices: CityChoice[]
├── the options render the label and submit the value
├── the stored city is matched by value and kept
└── the docstring's rewrite paragraph is replaced

frontend/components/settings/place-settings.tsx   MODIFIED
└── choices: CityChoice[]

frontend/app/settings/profile/page.tsx            unchanged in behaviour
└── the type flows through it

frontend/components/settings/home-city.test.tsx   REWRITTEN (15 tests)
frontend/components/settings/place-settings.test.tsx   fixture
frontend/app/settings/profile/page.test.tsx       fixture + two assertions
frontend/tests/profile-a11y.test.tsx               fixture
frontend/tests/endpoint-coverage.test.ts           the declaration comes out
```

**No backend file changed.** The endpoint is item 4's; the storage rule is item 5's.

## The rules the surfaces hold

| Rule | Why it is a rule |
|------|------------------|
| **The picker reads the catalog, not the preview's list.** | The catalog is a map of the world; the preview's list is a mirror of what we happen to have. A reader in an uncollected city is the most important reader to offer it to. |
| **The label is read; the value is stored.** | "Atlanta, Georgia" and "Tbilisi, Georgia" differ only in the first word — a control that showed the value would offer two near-identical entries, and one that submitted the label would store a string the server refuses. |
| **The stored city is matched by its *value*.** | The stored city is `"Portland, OR"` and its label is `"Portland, Oregon"` — matching on the label would not find it, and the city would be offered twice. |
| **A stored city the catalog no longer holds shows itself.** | The catalog's disambiguating form for a city it does not hold is unknown, and inventing one would be a fabrication. |
| **The placeholder appears only when no city is set.** | "Choose a city" is not a choice this endpoint can carry out — a null city means "leave it alone". |
| **The `fallback` note is live.** | Only a *chosen* city outside the catalog is refused; a geo guess and a backfill still fall back, and their accounts still carry one. |
| **It stays a `<select>`.** | The user asked twice for a dropdown. The platform's own type-ahead *is* the type-ahead. |
| **No country control, no "cities near you".** | The country is in the label — a reader sees where a city is; a reader cannot pick a country. |

## The key decisions

**1. The read moves, and the type changes with it.**

`frontend/lib/home-city-read.ts` calls `api.GET("/api/public/cities", {})`, and `choices`
becomes `CityChoice[]` — the generated `components["schemas"]["CityChoiceOut"][]` —
rather than `string[]`.

**The type is the point (AD-19).** The generated client already knows the endpoint's
shape; a control that reaches for `option.value` on a string is a compile error rather
than `undefined` at runtime.

**2. The option renders the label and submits the value — with nothing in between.**

```tsx
<option key={choice.value} value={choice.value}>
  {choice.label}
</option>
```

**The key is the value**, not the label: the value is the identity, and it is what a
preference holds.

**3. The stored city is matched by value, and the synthesised option labels itself.**

The old line was `choices.includes(city ?? "") ? choices : [city, ...choices]`. Its
*meaning* survives; its *shape* changes, because `choices` is now pairs. So:

```tsx
const stored = city === null ? null : choices.find((choice) => choice.value === city);
const options: CityChoice[] =
  city === null || stored !== undefined ? choices : [{ value: city, label: city }, ...choices];
```

**4. The docstring's reason changed, and it says so.**

The old one said a text box would "quietly store somewhere else", because the server
replaced a city it could not serve with a fallback, silently. **That is no longer true
of a chosen city** — a city outside the catalog is now *refused* (422). So the reason is
replaced with the real one: **the catalog's size and the catalog's canonical spellings.**
166 places in a native `<select>` get the platform's own type-ahead and the mobile
picker's own wheel; a text box would offer neither and would add a second job.

**5. The declaration comes out of `DECLARED_UNCALLED`, and that is the second half of a
two-sided guard.**

Nothing else would notice the picker's *source* changed — the component would work
perfectly with fewer cities and every one of its own tests would stay green. The
coverage test notices in both directions: an endpoint with no caller and no declaration
is an orphan, and a declaration with a caller is a stale exemption.

**6. The preview's list keeps its caller.**

`preview-section.tsx` still calls `GET /api/public/preview/cities` — the Pulse Preview's
own list of cities with events right now. **A different question, with its own home.**

## What the mutation check found

**39 mutations, 39 caught, 0 survived.** Item 11's seven, all caught on the first run.

**The one worth reading twice is "the stored city is matched by its label rather than its
value".** The stored city is `"Portland, OR"` and the catalog's label for it is
`"Portland, Oregon"` — so a control that matched on the label would **not find it**, would
synthesise a second option, and would offer the reader the same city twice under two
spellings. **It is caught by one test** — *"does not offer a stored city the catalog still
holds twice"* — and that test exists because the plan's decision 3 said so before the code
was written.

**And "the picker goes back to the preview's city list"** is caught by the *coverage*
test rather than by a component test, and that is the point: the coverage test is the
only thing that notices the picker's source of truth changed.

## The rules held

| Rule | Where it is held |
|------|------------------|
| **AD-19** — the frontend reaches the backend only through the generated client | The read calls the generated client on the contract's own path; `choices` is typed by the contract, so a drift is a compile error. |
| **AD-10** — the server's answer replaces the client's guess | The control shows what the server stored, including when it stored a different city. |
| **AD-12** — the public catalog is session-free | The endpoint this item calls is session-free; the read carries a session only because it also asks for the caller's own preference. |
| **No backend file changed** | Every file touched is under `frontend/`. |
| **No API surface change** | No `make client` — item 4's contract is item 4's. |

## Verification

```bash
# backend — unchanged by this item, run to confirm
uv run --directory backend python -m pytest -q
#   → 9091 passed, 1 warning in 331.32s

# frontend
pnpm typecheck        # → clean
pnpm lint             # → 0 errors, 2 pre-existing warnings (unrelated files)
pnpm test             # → 184 files, 2957 tests passed
pnpm format:check     # → 44 files unformatted — one FEWER than the 45 the branch
                      #   started with

# the mutation check
uv run --directory backend python ../.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py
#   → All 39 mutations were caught.
```

**`pnpm format:check` reports 44 files unformatted — one *fewer* than the 45 the branch
started with**, because this item's `home-city.tsx` was in the pre-existing unformatted
set and was formatted here. The pre-existing drift is not this item's to fix.

## The risks

**The one risk worth naming** is the synthesised option's label. A reader whose stored
city the catalog no longer holds sees **one entry in the list whose spelling style
differs from every other** — "Atlantis" among "Chattogram, Bangladesh". There is no way
to fix that without knowing what the city is, and the alternative — dropping the option —
would render the select blank, which is a worse lie. **The honest answer is the plain
one.**

**The second risk is the coverage test's two-sidedness.** It is now the only thing that
notices the picker's source of truth changing, and it is easy to forget that a *stale*
declaration is as much a lie as a missing one. **Both directions are under test**, and
the removal is the half that is easy to undo by accident.

## What this unblocks

**The run. Every item is now delivered.**

The chain, end to end: a reader picks a city from the curated catalog → the pick is
stored verbatim → the city is provisioned → the sources run → the probation tells the
truth about what came back → Browse says one of four honest things → the dead end offers
a way out → and the picker itself now offers the whole world rather than a mirror of
what we happen to have.

**And the run-level `walkthrough.md`**, which is owed at run completion.
