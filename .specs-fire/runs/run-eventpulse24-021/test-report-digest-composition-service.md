---
run: run-eventpulse24-021
work_item: digest-composition-service
intent: pulse-digest-and-trust
generated: 2026-10-30
status: passing
---

# Test Report: The composition command — candidates in, one persisted Pulse Digest out (FR-5, FR-8)

The candidate reads answer "what may a Pulse Digest rank?". This item is the command
that turns that pool into a **digest a user can be shown**: three cards, each in a slot
with a meaning, each with a score, a bucket and a set of tags that explain it.

**The properties worth testing are the ones a user would notice if they broke.** A digest
with the same event in two slots is a card that appears twice. A digest whose day is the
server's day instead of the user's is a digest that arrives at the wrong hour — or two
digests in one day. A digest that quietly pads itself with an event the gates forbid is
worse than a short digest, because the padding is a lie the user cannot see.

**And one property was not a property at all until this item: the interest term.** The
Relevance Pulse's interest term is the largest weight in the formula (`0.45 ×
interest_overlap`), and it was **pinned to `0.0` for every candidate** — because the
event's half of the overlap was never produced anywhere. `domain/ranking.py` calls a
pinned term an *inert weight*: "the published formula would stay arithmetically checkable
and still produce a different number from the one on the card, which is a worse trust
failure than a reduced formula because it looks verifiable." So the item had to build
the event's half — a keyword matcher in the layer that owns the content (AD-9) — and
these tests are what prove the term is **alive** and **conservative**.

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 70 | 0 | 0 | 100% (both new modules) |
| **Total (whole backend)** | **3690** | **0** | **0** | **99.15%** |

The whole backend suite is **3690 passed, 0 failed**, with **100.00% on `domain/`** (the
AD-2 purity gate) and **100% on each of the two modules this item created**:
`digest_composition.py` and `chip_matching.py`.

### The item-scoped files, and what each is for

| File | Tests | What it proves |
|------|-------|----------------|
| `backend/tests/personalization/test_digest_composition.py` | 48 | The command: the three slots, the personal event, the opt-out, the empty state, determinism, the user's day, the city filter, the interest term, hysteresis, the saves, the conflicts, the audit, the wall |
| `backend/tests/ingestion/test_chip_matching.py` | 22 | The event's half of the overlap: the whole-word rule, the hyphen rule, the phrase rule, the ordering, the guards |

## Test Commands

```bash
# The item's own tests
cd backend
uv run pytest tests/personalization/test_digest_composition.py \
                 tests/ingestion/test_chip_matching.py -v

# The whole backend, with the coverage gates
uv run pytest --cov --cov-report=term
uv run coverage report --include='domain/*' --fail-under=100

# The other architectural gates
uv run ruff check .
uv run ruff format --check .
uv run lint-imports          # 19 contracts, 0 broken
uv run python manage.py makemigrations --check --dry-run   # No changes detected
```

## 1. The three slots

FR-5 names three slots — "must-know", "nearby", "serendipity" — and each holds a
*different kind of thing*. The tests assert the kind, not just the count.

| Test | Asserts |
|---|---|
| `test_the_slots_are_the_three_named_ones` | `must_know`, `nearby`, `serendipity` |
| `test_the_three_cards_are_three_distinct_events` | No `event_id` twice |
| `test_a_standard_day_holds_three_cards` | Three cards on an ordinary day |

**The distinctness holds by construction, not by catching an error.** Each slot draws
from what the earlier slots did not take, so a duplicate would have to be *designed* to
happen. The work item is explicit that the service "must not rely on an `IntegrityError`
to notice", and the test asserts the property rather than the absence of a crash.

**The nearby slot takes the next best, not the best.**

| Test | Asserts |
|---|---|
| `test_the_nearby_slot_takes_the_next_best_not_the_best` | Slot 2 ≠ slot 1 |
| `test_the_serendipity_slot_is_not_the_same_pick_as_the_nearby_slot` | Slot 3 ≠ slot 2 |

**And the serendipity slot inverts the interest term** — that is what makes it
"serendipity" rather than a third copy of the nearby slot. Before this item the
inverted term was `1 − 0.0`, which is *identical* to the plain score, so the slot did
not invert anything.

| Test | Asserts |
|---|---|
| `test_the_serendipity_slot_suppresses_the_chip_tags` | Slot 3's tag is `discovery`, never `matches_<chip>` |

## 2. Slot 1: the personal event

FR-5 puts "Personal Events eligible" **first**, and makes the public event conditional
on "if no Personal Event is eligible". So the personal event is not competing with the
public event for Slot 1 — it *is* Slot 1 when there is one.

| Test | Asserts |
|---|---|
| `test_slot_1_is_the_personal_event_when_there_is_one` | Slot 1 is the personal event |
| `test_the_personal_event_wins_slot_1_even_when_a_public_event_outscores_it` | Slot 1 is the personal event, even when a public event scores higher |
| `test_slot_1_falls_back_to_the_public_event_when_there_is_no_personal_event` | The fallback fires |
| `test_a_personal_event_outside_the_window_does_not_take_slot_1` | 49 hours → the public fallback |

**The third test is the one that would fail against a "highest score wins" reading of
FR-5**, and it is the reason the test exists. A personal event that scores lower than a
public event still takes Slot 1, because FR-5's structure is a fallback, not a contest.

**A personal event has no badge and no version**, because it has no source — and the
model's `digest_composition_kind_shape_ck` says so.

| Test | Asserts |
|---|---|
| `test_a_personal_event_has_no_badge_and_no_version` | Both are `None` |
| `test_a_public_composition_carries_the_badge_and_the_version` | Both are present |

## 3. The opt-out

`DigestPreference.include_personal_events` is the user's own switch, and it removes the
**personal** half of the digest — not the public half.

| Test | Asserts |
|---|---|
| `test_an_opted_out_users_digest_has_no_personal_event` | No `personal` composition at all |
| `test_an_opted_out_user_with_no_public_events_gets_the_empty_state` | The empty state fires |
| `test_an_event_the_user_opted_out_of_still_counts_as_a_public_event` | A public event still fills the digest |

The third test is the one that would catch a filter written one clause too wide. An
opt-out of *personal events* is not an opt-out of the user's own city.

## 4. The empty state

FR-8's empty digest is **a fact the user is shown**, not the absence of a digest. So the
empty state is a real row with `is_empty` set, and it has no compositions.

| Test | Asserts |
|---|---|
| `test_the_empty_state_is_a_real_digest_with_no_cards` | A `PulseDigest` row, `is_empty`, zero compositions |
| `test_the_empty_state_needs_both_halves` | A personal event alone → **not** empty |
| `test_a_user_with_public_events_is_not_in_the_empty_state` | Public events → not empty |

**The empty state needs *both* halves.** "No qualifying public event" is not enough: a
user with a personal event tomorrow and nothing else in the catalog has a card to show,
and a digest that said "nothing today" would be wrong.

## 5. Determinism and the re-run

| Test | Asserts |
|---|---|
| `test_composing_twice_returns_the_identical_rows` | The same ids, scores, buckets and tags |
| `test_the_second_call_writes_nothing` | One digest, one composition, `created is False` |
| `test_the_second_call_writes_no_second_audit_row` | Exactly one audit row |
| `test_two_users_get_different_digests_from_the_same_pool` | The composition is per user |

**The ordering is a total order** — `(-score, start_time_utc, event_id)` — so two runs
cannot disagree and the ordering never depends on the order the rows happened to come
back from the database. The `event_id` tiebreak is what makes it total: the UUIDv7 is
time-ordered and unique, so there is never a residual tie.

**The re-run is a no-op under a per-user advisory lock** (`pg_advisory_xact_lock`), not a
constraint violation. The lock makes the second worker *wait*, see the row the first one
wrote, and return it — so the caller sees the existing digest rather than an
`IntegrityError` that would reach it as a 500.

## 6. The local date, and DST

**The day is the user's day**, computed by conversion (`now.astimezone(zone).date()`) and
never by arithmetic — adding 24 hours to a UTC date would be a different day for most of
the world, and a DST transition would break it twice a year.

| Test | Asserts |
|---|---|
| `test_the_local_date_is_the_users_day_not_utc` | 16:00 UTC is the 5th in Tokyo, the 4th in Los Angeles |
| `test_two_users_in_different_zones_get_different_local_dates` | Two zones, two digests |
| `test_a_dst_fall_back_does_not_produce_two_digests_for_one_day` | The repeated hour is one day |
| `test_the_digest_records_the_zone_it_was_computed_in` | The zone is on the digest |
| `test_a_user_with_no_preference_gets_a_utc_digest` | The default zone is UTC |

**The DST test is the one that would catch date arithmetic.** In `America/New_York`,
2026-11-01 has two 01:00s; two instants an hour apart in UTC are the same local day, so
they are the same digest — and the second call writes nothing.

**An unknown zone falls back to UTC rather than failing.**

| Test | Asserts |
|---|---|
| `test_an_unknown_zone_falls_back_to_utc_rather_than_failing` | The day is the UTC day; the command did not raise |

The zone is validated at write time by the onboarding command, so an unknown name here
means hand-edited data. A composition that *raised* would leave the user with no digest
at all, which is worse than a digest whose day is computed in the fallback zone: the
failure mode is a wrong day, not a missing card.

## 7. The city filter, and the country band

The user's city filters the public pool. A user with no city is not filtered to a
fallback — they get every eligible event, which is what the serendipity slot wants.

| Test | Asserts |
|---|---|
| `test_the_pool_is_filtered_to_the_users_city` | An event in another city is not a candidate |
| `test_a_user_with_no_city_is_not_filtered_to_the_fallback` | Every eligible event is in the pool |

**The country band is `0.00`, and this is stated rather than papered over.** The
`DigestPreference` carries a city and a zone but no country, so `user_country` is empty
and the country term of the city band is zero. The trade is `0.10` of the score, and it
is documented in the design (D8) rather than hidden — a reader comparing the published
formula to the number on the card needs to know which term is carrying nothing.

## 8. The interest term is alive

This is the section the item existed for.

| Test | Asserts |
|---|---|
| `test_the_interest_term_is_alive` | The score is above what an inert term would give |
| `test_a_matching_event_outscores_a_non_matching_one` | The match changes the ranking |
| `test_a_user_with_no_chips_is_not_punished_for_it` | A chipless user still gets a ranked digest |
| `test_a_chip_the_event_does_not_match_produces_no_tag` | No `matches_<chip>` tag |

**A chipless user is not punished for it.** The interest term scores `0.0` for a user who
picked nothing, and the other three terms still rank. The design (D6) records the
alternative — scoring a chipless user as if they had picked nothing *and* ranking them
below everyone else — and rejects it.

**The matcher itself is conservative**, and its own test file says why: "a keyword that
matches too broadly is worse than no keyword: it inflates the interest term and files a
card under a category the user never asked about."

| Test | Asserts |
|---|---|
| `test_a_keyword_does_not_match_inside_a_longer_word` | "art" does not match "start" |
| `test_a_keyword_does_not_match_a_prefix_of_a_longer_word` | "market" does not match "marketing" |
| `test_a_multi_word_keyword_does_not_match_its_words_apart` | "public hearing" is a phrase, not two words |
| `test_a_multi_word_keyword_matches_across_any_run_of_whitespace` | "Craft  Fair" matches |
| `test_the_venue_is_not_matched` | The venue is where, not what |

**The hyphen rule was a real bug, and the test found it.** The module's own docstring
promised that "story-time" and "storytime" are the same word to a reader — but the
tokeniser kept the hyphen *inside* the token, so a keyword of "storytime" did not match
a title of "Story-Time". The fix normalises both sides through the same rule, so a
keyword of "story-time" and a text of "storytime" agree too.

| Test | Asserts |
|---|---|
| `test_the_whole_word_boundary_respects_apostrophes_and_hyphens` | "storytime", "Story-Time" and "Storytime's" all match |

## 9. Hysteresis

EXPERIENCE.md §4: "Across days, hysteresis resets... No persistent bucket is stored
between days."

| Test | Asserts |
|---|---|
| `test_no_bucket_is_inherited_across_days` | The same event, two days, two independent buckets |

**This is where the design met a contradiction in the work item.** The item's acceptance
criteria said the hysteresis applied "across days … reading the previous day's
composition" *and* that "across days it resets". Both cannot be true. The canonical
source — EXPERIENCE.md §4 — was taken as authoritative: the service passes
`previous_bucket=None`, so `apply_hysteresis` *is* `score_bucket`, and nothing is
inherited between days. The conflict is recorded in the design (D9) rather than papered
over.

**The test isolates the rule from the pool.** The event starts 50 hours out, so it is
eligible on *both* days; an event that started on the first day would have fallen out of
the pool by the second, and the test would be measuring the pool rather than the
hysteresis.

## 10. The saves, and the conflicts

A save is a **tag**, not a candidate pool. A saved event in another city is not "nearby",
and a save is not a statement that the event is nearby.

| Test | Asserts |
|---|---|
| `test_a_saved_event_carries_the_saved_tag` | The `saved` tag is present |
| `test_an_unsaved_event_has_no_saved_tag` | The tag is absent |

**A conflict is an indicator on a card, not an exclusion** (FR-58).

| Test | Asserts |
|---|---|
| `test_a_conflicted_event_still_appears` | The conflicted event is still composed |

## 11. The audit row

| Test | Asserts |
|---|---|
| `test_the_audit_row_records_the_composition` | `digest.composed`, the digest's id, the count |
| `test_the_audit_row_carries_no_event_content` | No title, no url, no chips |
| `test_the_command_takes_an_actor_and_writes_it_to_the_audit_row` | The actor is recorded |

**The audit row carries `{"local_date", "is_empty", "composition_count", "at"}` and
nothing else.** AD-13 forbids PII and untrusted content in logs, and the audit table is
a log. The second test asserts the *absence* of the event's content — a title or a URL
would be untrusted source content in a log.

## 12. The wall, and the transaction

| Test | Asserts |
|---|---|
| `test_the_catalog_is_read_outside_the_personal_transaction` | The catalog reads happen before the transaction opens |
| `test_the_composition_never_touches_the_catalog_for_writes` | Every write goes to `personal` |

**AD-3: no transaction spans `catalog` and `personal`.** The catalog reads happen
*before* `transaction.atomic(using=PERSONAL)` opens, so the reads are outside the
transaction by construction and the writes are inside it. The first test asserts this
from the transaction's side — that the catalog's queries are not recorded as *inside* the
personal transaction — and the second from the write side.

## 13. The command's shape

| Test | Asserts |
|---|---|
| `test_the_result_carries_the_composition_count` | The result carries the rows |
| `test_a_short_digest_is_not_padded_with_an_ineligible_event` | A two-card day is two cards |

**A short digest is not padded.** The alternative — padding to three — would publish
cards the gates forbid, and the empty state would lie about why the digest is short.
The design (D6) calls this "show what there is".

| Test | Asserts |
|---|---|
| `test_a_pool_of_one_holds_one_card` | One card |
| `test_a_pool_of_two_holds_two_cards` | Two cards |

## The bugs the tests found

Three, all real, all fixed before this report.

**1. The advisory-lock `person` was too long.** `blake2b`'s `person` parameter is capped
at 16 bytes, and `b"eventpulse-digest"` is 17. Every composition raised
`ValueError: maximum person length is 16 bytes` — the command did not work at all. The
fix uses `b"ep-digest-c"`, which is also *distinct* from every other lock namespace in
the codebase (`ep-ident`, `ep-source-run`, `eventpulse24-onb`, `eventpulse24-cal`), so a
digest lock can never collide with an ingestion or dedup lock.

**2. The slot scorers were called positionally.** `domain/ranking.py`'s `score_slot_1`,
`score_slot_2` and `score_slot_3` are keyword-only on `inputs`, and the implementation
called them as `slot_scorer(inputs)`. Every composition raised `TypeError:
score_slot_1() takes 0 positional arguments but 1 was given`. The fix calls them as
`slot_scorer(inputs=inputs)`.

**3. The hyphen rule did not hold.** `chip_matching.py`'s docstring promised that
"story-time" and "storytime" are the same word to a reader, but the tokeniser kept the
hyphen inside the token, so the two spellings did not match each other. The fix
normalises both the text's tokens and the keyword's tokens through the same rule.

## What the tests do not prove

**The composition is not the read.** This item writes the digest; the API that serves
it to a user is `digest-read-api`, and the wire shape is built there. The result object
here is plain data, and the read API is what decides how much of it reaches the client.

**The schedule is not here.** The composition runs when something asks it to. That
"something" — the daily schedule, the retry, the idempotent re-run across a restart —
is `digest-scheduling`.

**The scores are not validated against a human.** The tests prove the formula is
*applied* as published and that it is deterministic. They do not prove that a
0.72 is a good score, and no test here could: that is what a product decision looks
like, and this codebase's answer to "is the ranking good" is the trust framing in
EXPERIENCE.md, not a threshold.

**The country band is a known zero.** `user_country` is empty because the
`DigestPreference` has no country, so `0.10` of the city band is always zero. The
design (D8) says so plainly. If the preference gains a country, the band becomes
real and the D8 decision has to be revisited.

## The gate, in full

```
uv run pytest --cov
  3690 passed, 0 failed
  Total coverage: 99.15%   (gate: 80%)

uv run coverage report --include='domain/*' --fail-under=100
  TOTAL  750 stmts, 0 miss, 100%

uv run ruff check .
  All checks passed!

uv run ruff format --check .
  401 files already formatted

uv run lint-imports
  Contracts: 19 kept, 0 broken.

uv run python manage.py makemigrations --check --dry-run
  No changes detected
```
