---
run: run-eventpulse24-057
work_item: home-city-dropdown-catalog
intent: city-picker-and-auto-collection
generated: 2026-11-21
status: passed
---

# Test Report: The dropdown reads the catalog

## Summary

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| `components/settings/home-city.test.tsx` (rewritten) | 15 | 0 | 0 |
| `components/settings/place-settings.test.tsx` (fixture) | 4 | 0 | 0 |
| `app/settings/profile/page.test.tsx` (fixture) | 30 | 0 | 0 |
| `tests/profile-a11y.test.tsx` (fixture) | — | 0 | 0 |
| `tests/endpoint-coverage.test.ts` (declaration removed) | 11 | 0 | 0 |
| Frontend suite (full) | 2957 | 0 | 0 |
| Backend suite (full) | 9091 | 0 | 0 |

**The mutation probe: 39 mutations, 39 caught, 0 survived** — item 11's seven, all caught
on the first run.

**No backend file changed.** The endpoint is item 4's; the storage rule is item 5's. This
item moves a caller and the shape of a payload.

## Acceptance Criteria Validation

### The control reads the catalog choices endpoint

- ✅ **`/settings/profile`'s city control reads the catalog choices endpoint** —
  `frontend/lib/home-city-read.ts` calls `api.GET("/api/public/cities", {})`. **The
  mutation "the picker goes back to the preview's city list"** rewrites that call to
  `/api/public/preview/cities` and **the endpoint-coverage test fails** — the catalog
  endpoint becomes an orphan with no caller and no declaration, and the test says so by
  name.
- ✅ **The preview's own list keeps its caller** — `preview-section.tsx` still calls
  `GET /api/public/preview/cities`. **That is a different question** ("which cities can
  the Pulse Preview serve *right now*?"), and it is not the picker's question.

### The options render the label and submit the value

- ✅ **The option's text is the `label`** — `home-city.test.tsx` → *"shows the label, not
  the value, for a city whose two forms differ"*: the option named "Portland, Oregon" has
  value `"Portland, OR"`. **The mutation "the option shows the value instead of the
  label"** fails 3 tests.
- ✅ **The option submits the catalog `value`** — *"saves the chosen city's value, not
  its label"*: the PUT body's `city` is `"Portland, OR"`. **The mutation "the option
  submits the label instead of the value"** fails 8 tests.
- ✅ **A reader sees "Portland, Oregon" and the server stores "Portland, OR"** — the two
  are the same test seen from both sides, and the two mutations above are the two ways to
  break it.

### Picking a city stores that city, and the control shows it afterwards

- ✅ **A city with no ingested events is picked and kept** —
  `home-city.test.tsx` → *"picks a city the catalog holds and nothing has been collected
  for, and keeps it"*. The control offers "Portland, Oregon" to a reader with no city;
  the PUT carries `"Portland, OR"`; and the server's answer puts it back in the select.
  **This test would fail against today's control** — the options were the preview's list
  of cities *with events*, so "Portland, Oregon" would not have been offered at all, and
  there was no label to render.
- ✅ **The server's answer replaces the client's guess** (AD-10) — *"takes the server's
  city over the one it sent"*, unchanged from before.
- ✅ **A refusal puts the old city back** — *"puts the old city back when the save is
  refused"*, unchanged.
- ✅ **A request that never lands puts the old city back** — *"puts the old city back when
  the request never lands"*, unchanged.
- ✅ **The schedule rides along unchanged** — *"sends the schedule back unchanged"*, and
  `place-settings.test.tsx`'s four tests still hold, because the city's request body is
  the only place the zone-coupling bug could show itself.

### The stored city remains in the options

- ✅ **The stored city stays in the options even when the catalog no longer offers it** —
  *"keeps showing a stored city the catalog no longer offers"*: the select's value is
  "Atlantis" and the option "Atlantis" is present. **A select whose value is absent from
  its options renders blank**, which would read as "no city" to someone who has one.
- ✅ **Preserved by test, not by accident** — the behaviour was already in the code and
  is now asserted.
- ✅ **The synthesised option shows the stored city as its own label** — *"shows a stored
  city the catalog no longer offers as its own label"*. **The mutation "the synthesised
  option shows an empty label"** fails 2 tests.
- ✅ **And it is not offered twice when the catalog does hold it** — *"does not offer a
  stored city the catalog still holds twice"*. **The mutation "the stored city is matched
  by its label rather than its value"** fails 1 test: matching on the label would fail
  to find "Portland, OR" (the label is "Portland, Oregon"), so the synthesised option
  would be prepended and the city would appear twice.

### `citySourceNote()` still labels a `fallback` city honestly

- ✅ **The fallback branch is live and asserted** — *"still labels a fallback city
  honestly"*: `citySourceNote("Fixtureville", "fallback")` matches
  /We don't have your city yet/.
- ✅ **And it is not vestigial** — only a *chosen* city outside the catalog is refused
  (item 5's rule in `digest_preferences.py`: `raise _refused(city)` for `SOURCE_CHOICE`,
  `PREVIEW_FALLBACK_CITY` for everything else). **A geo guess and a backfill still fall
  back**, and their accounts still carry one.
- ✅ **The `geo` and `choice` notes are unchanged** — *"says when the city was guessed
  rather than chosen"*.

### The placeholder appears only when no city is set

- ✅ **The placeholder is offered when there is no city** — *"offers a placeholder when
  the user has no city, and never submits it"`.
- ✅ **And it is offered *only* then** — **the mutation "the placeholder is always
  offered"** fails 1 test. Leaving it in the list once a city is set would offer "Choose
  a city" as a choice this endpoint cannot carry out.

### The docstring is rewritten

- ✅ **The "silently replaces a city with a fallback" paragraph is gone** — the
  component's docstring now says, under *"And it is still a select rather than a text
  box"*:

  > **The reason changed, and the docstring had to change with it.** The old one said a
  > text box would "quietly store somewhere else", because the server replaced a city it
  > could not serve with a fallback, silently. **That is no longer true of a chosen
  > city**: a city outside the catalog is now *refused* (422), not quietly substituted.
  >
  > **So the real reason is the catalog's size and the catalog's canonical spellings.**

- ✅ **And it gives a real reason** — a hundred and sixty-odd pickable places in a native
  `<select>` get the platform's own type-ahead and the mobile picker's own wheel; a text
  box would offer neither and would add a second job (resolving what the reader typed
  into something we hold).
- ✅ **The same correction in `home-city-read.ts`** — the module docstring's
  `preview/cities` paragraph is replaced with the catalog's, and says why the preview's
  list is a different question.

### The list is long enough to need it, and the control is usable at that length

- ✅ **166 cities** in the catalog (`domain.city_catalog.choices()`), and the longest
  label is 38 characters.
- ✅ **Keyboard type-ahead works** — it is the **browser's**, not ours: a native
  `<select>` gives the platform's own type-ahead, and the control is still a `<select>`
  (the work item: *"It stays a `<select>`. No free text."*; *"the user asked twice for a
  dropdown and not a text box"*).
- ✅ **The option count does not break the layout** — the control's box is sized by its
  CSS (`min-h-[44px]`, `px-3`, inside a flex row), and a native `<select>` **never
  widens its box to fit an option** — the longest option is rendered by the platform's
  own popup. The element's own width is unchanged from before this item.

### Browse's "Change city" links still land on this control

- ✅ **Both links already point at `/settings/profile`** — `browse-hero.tsx` and
  `browse-states.tsx`. **Neither changed**; `browse-states.test.tsx` and
  `browse-rendering.test.tsx` assert the href and still pass.

### No country dropdown, no country field, no "cities near you"

- ✅ **None of the three exists** — the item's three touched files contain no `country`
  control, no country field, and no geolocation or "near me" affordance.
- ✅ **The country is in the *label*, not in a control** — "Chattogram, Bangladesh" is
  one option's text, computed by `domain.city_catalog`'s `CityChoice.label` and stored
  nowhere. **A reader sees where a city is; a reader cannot pick a country.**

### The API surface

- ✅ **Unchanged** — no endpoint added, none removed, no schema touched.
  `make client` is therefore **not needed** for this item, and `backend/tests/api/
  test_contract.py` is unaffected.

## The mutation check

**39 mutations, 39 caught, 0 survived.** Item 11's seven, all caught on the first run:

| # | Mutation | Caught by | Result |
|---|----------|-----------|--------|
| 1 | The option shows the value instead of the label | the label test | 3 failed |
| 2 | The option submits the label instead of the value | the submit test | 8 failed |
| 3 | The stored city is dropped from the options | the stored-city tests | 3 failed |
| 4 | The synthesised option shows an empty label | the stored-city label test | 2 failed |
| 5 | The stored city is matched by its label rather than its value | the duplicate test | 1 failed |
| 6 | The placeholder is always offered | the placeholder test | 1 failed |
| 7 | The picker goes back to the preview's city list | the coverage test's orphan check | 1 failed |

**The other 32 are items 1–10's mutations, all still caught.**

### What the mutation check found — nothing survived, and the two that had to be *written*

**This item's mutations all died on the first run, and two of them earned their place
by being mutations of a mistake the item nearly made.**

**"The stored city is matched by its label rather than its value"** is the interesting
one. The stored city is `"Portland, OR"` and the catalog's label for it is
`"Portland, Oregon"` — so a control that matched on the label would **not find the
stored city in the catalog**, would synthesise a second option for it, and would offer
the reader the same city twice under two different spellings. **The mutation is caught by
one test** — *"does not offer a stored city the catalog still holds twice"* — and that test
exists because the plan's decision 3 spelled out that the match is on the *value*.

**"The picker goes back to the preview's city list"** is caught by the *endpoint-coverage*
test rather than by a component test, and that is the point. The component would still
have worked perfectly — it would have been offered fewer cities, with no labels. **The
coverage test is the only thing that notices the picker's *source* of truth changed**,
and it notices it in both directions: an endpoint with no caller and no declaration is an
orphan, and a declaration with a caller is a stale exemption.

**So the declaration had to come out**, and it is the *removal* that is now under test:
the file's second test ("has no declared-uncalled endpoint that is in fact called")
fails if the entry is put back.

## The commands

```bash
# backend — unchanged by this item, run to confirm
uv run --directory backend python -m pytest -q
#   → 9091 passed, 1 warning in 331.32s

# frontend
pnpm typecheck        # → clean
pnpm lint             # → 0 errors, 2 pre-existing warnings (unrelated files)
pnpm test             # → 184 files, 2957 tests passed
pnpm format:check     # → 44 files unformatted — one FEWER than the 45 the branch
                      #   started with, because home-city.tsx was in the pre-existing
                      #   unformatted set and was formatted here

# the mutation check
uv run --directory backend python ../.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py
#   → All 39 mutations were caught.
```

**No `make client`** — the API surface did not change.

**`pnpm format:check` reports 44 files unformatted — one *fewer* than the 45 the branch
started with.** This item's `home-city.tsx` was in the pre-existing unformatted set and
was formatted here. The remaining pre-existing drift is not this item's to fix.
