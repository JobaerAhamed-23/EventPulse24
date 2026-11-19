---
run: run-eventpulse24-046
work_item: timeline-why-this-tag
intent: traceability-gap-closure
generated: 2026-11-19
mode: validate
---

# Walkthrough: The Timeline block's Why-this tag — deferred, with the reason

## What this run decided

`EXPERIENCE.md` §13 promised that a desktop Timeline event-block, on hover or focus, adds
**location and one Why-this Tag**. The location shipped in earlier runs. This run settled
the tag: **it is withdrawn**, under new **Amendment A-24**, and `TRACEABILITY.md`'s
observation **O-2 is closed**.

**Zero lines of production code changed.** `git diff HEAD -- backend frontend` is empty.

## Why it was withdrawn — and why not for the reasons on file

The work item filed on 2026-11-17 gave two reasons to defer. **Reading the code showed both
were wrong**, and the run recorded the corrections rather than inheriting them, because a
deferral resting on a false premise gets reversed the first time someone checks.

### Correction 1 — it is one extra query, not four

The work item said building the tag meant "four reads and a per-block ranking assembly".

`why_this_tags` reads **exactly one field** off `RankingInputs`: `inputs.city_match`. The
other four — `interest_overlap`, `recency`, `confidence`, `source_reliability` — are
*scoring* inputs the tag function never touches. So:

| Need | Cost |
|---|---|
| The user's city | 0 queries — a column on the `DigestPreference` row `_read_zone` already fetches |
| The event's `chip_keys` | 0 queries — `chip_keys_for(title, description)` is pure text over columns already selected |
| `venue_country_code` | 0 queries — the same joined `Venue` row |
| `user_chip_keys` | **+1 query** — `_read_interest_keys` |
| `is_saved` | free — a constant `True` here |

The Timeline's five queries would have become six.

### Correction 2 — AD-10 was not the blocker

The import-linter contract *"AD-10 personalization never reaches the Event Fit"* forbids
`apps.ingestion.event_fit`. It does **not** forbid `apps.ingestion.services.catalog_read`,
which `personalization` already imports for `get_public_events`. The chip keys a Relevance
Pulse tag needs come from `chip_keys_for` — a pure function over the event's own title and
description. **Nothing on that path touches the Event Fit.**

AD-10 remains correct and load-bearing; substituting one explanation kind for the other is
still the trust-collapse failure PRD Risk 11 calls company-ending. It simply was not what
stopped this.

### The actual reason — the tag says nothing on this surface

`RANKING_TAG_ORDER` is `discovery, nearby, tonight, tomorrow, weekend, saved`, with chip
tags appended last. §13 asks for **one** tag, so the block shows `tags[0]`. On the Timeline:

- `discovery` needs `serendipity=True`, a digest-slot decision — **never fires**.
- **Every public block is a saved event**, so `is_saved` is universally true.
- Time tags are computed against `now`, and the Timeline navigates by arbitrary week — so
  on any week but the current one, **none fire**.

Which leaves two outcomes:

1. The user has a city and the event is in it → **`nearby`, on every block, all week.** The
   same word on everything explains nothing.
2. No city (`DigestPreference.city` is nullable), an out-of-town event, or any non-current
   week → **`saved`**. On a surface that shows only saved events, "why is this here?"
   answers "because you saved it." A tautology.

The one informative tag, `matches_<chip_key>`, **sorts last** and is unreachable whenever
any fixed tag applies.

Cheap to build, and it would say nothing. That is the reason on record, and unlike a cost
argument it does not change when the query budget does.

## What changed

| File | Change |
|---|---|
| `EXPERIENCE.md` §13 line 1107 | Hover/focus Timeline row is location-only, tagged **Amendment A-24** |
| `EXPERIENCE.md` §13 anti-pattern | New `**Scope (Amendment A-24):**` paragraph (see below) |
| `EXPERIENCE.md` frontmatter | A-24 spine-update entry prepended to `updated_note`; `updated:` → 2026-11-19 |
| `TRACEABILITY.md` FR-32 row | **O-2 closed (2026-11-19)** — withdrawn by A-24, pointing at *Open items* for reasoning |
| `TRACEABILITY.md` Open items | The `timeline-why-this-tag` bullet rewritten as **DECIDED**, carrying both corrections |
| `work-items/timeline-why-this-tag.md` | frontmatter `status` → `completed` |

### Where A-24 was recorded, and why not in the Surface Coverage Map

EXPERIENCE.md records amendments in two places. The **Surface Coverage Map** (rows 1–24) is
for amendments that add or change a surface *and its mockup* — A-24 adds neither. The
**`updated_note` frontmatter** carries "Spine update" entries for as-built corrections
touching only this document, the pattern A-18 set on 2026-11-13. A-24 is the second kind.
A Surface Coverage row would have asserted a surface that does not exist.

## Two things the review caught

**1. The FR-32 matrix row was over-long and duplicated itself.** The first edit put the
whole argument into a Section C table cell — ~1,100 characters, about three times its
longest neighbour, repeating what the Open-items bullet said forty lines below. Section C is
a scannable matrix, and two copies of one argument drift apart as soon as either is edited.
The row now carries the outcome and points at *Open items*. **Auto-fixed.**

**2. §13's trust-signal anti-pattern read as contradicting A-24.** Two lines below the
amended row, §13 says adaptive density "must not hide the trust signals … at any density
mode". A reader going through §13 in order sees A-24 removing a Why-this Tag and concludes
the amendment breaks the rule.

It does not: the rule's own wording scopes it to the **Pulse Card**, whose mobile default
exposes all three signals. The **Timeline block shows none of the three at any density** —
its default is name, time, the Personal/Public label and the conflict indicator. A-24
retires a promise that was never kept; it removes no signal.

That explanation existed only in the frontmatter, ~1,100 lines away. **Raised for your
confirmation rather than auto-fixed** — editing an anti-pattern is a semantic change to a
locked constraint. You approved it, and a `**Scope (Amendment A-24):**` paragraph now sits
directly beneath the rule. The rule itself is not edited, only scoped, and it is explicitly
**unchanged and undiminished** for every surface that does expose the signals.

## Tests

| Suite | Result |
|---|---|
| Full backend suite | **7476 passed**, 3 pre-existing failures, 7 skipped (5:04) |
| Architecture + timeline suites, after the review fixes | **1113 passed** |
| Tests added | **0** — no behaviour changed; no test reads these documents |

### Three failures that are not this run's

`tests/delivery/test_preferences_api.py` fails three tests with
`ScheduledSend.DoesNotExist` — the same failure run-041 verified against base commit
`b8c6b21` in a separate worktree. This run changed zero Python, so it cannot have caused
them. **They remain open and belong to no current work item.**

### A trap worth remembering

Six tests failed on the first full run — three `test_blob.py` client-caching tests and
three `test_the_import_contracts_still_hold`. **All six were my invocation, not the code.**
Running `.venv/bin/python -m pytest` directly leaves `.venv/bin` off `PATH`, so the
subprocess call to `lint-imports` fails with "not on PATH", and the blob tests fail for the
same reason. The Makefile uses `uv run`, which sets PATH. With PATH set, all 65 pass.

If you run pytest by hand, use:

```bash
cd backend && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest -q
```

## Environment notes

- **Postgres and Redis were down** at the start; 56 DB-backed tests errored on connection
  refused. Started with `docker compose up -d postgres redis`.
- **`docker compose up` with no service named would now also start MinIO**, whose image
  cannot be pulled here (`pull access denied`). Name the services explicitly until a
  `docker login` resolves it.

## What is left in this intent

| Work item | Status |
|---|---|
| `fr22-published-formula` | **Checkpoint 1 approved**, design doc written, ready for the Builder — takes **A-25** |
| `settings-privacy-ranking-transparency` | New, pending — FR-22's transparency surface does not exist |

**One flag for the next run.** `TRACEABILITY.md`'s `fr22-published-formula` bullet — the one
directly below the bullet this run rewrote — still says the PRD "does not know it changed".
The approved design for that item establishes this is false: the PRD carries the amendment
at `prd.md:751`, and the real defect is that it reuses amendment ID **A-10**, which already
belongs to the Browse surface. Left untouched deliberately, so it is clear which run changed
what.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-046*
