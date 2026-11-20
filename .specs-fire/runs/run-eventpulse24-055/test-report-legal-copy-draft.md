# Test Report: legal-copy-draft

**Run:** run-eventpulse24-055 · **Date:** 2026-11-20 · **Result:** PASS

## Suite

| Scope | Tests | Result |
|---|---|---|
| Frontend, full | 2847 (177 files) | **pass** |
| `tests/legal-pages.test.tsx` | 15 (was 11) | pass |
| Backend `tests/shared/` | 99 | pass |
| Backend, full | 7666 | **pass** (877s) |

`tsc --noEmit` clean. `ruff check` clean. `pnpm lint` unchanged at 5 pre-existing problems.

## The claim-to-evidence table

Every factual claim on either page, and what it was read from. **A claim with no evidence
was cut, not softened.**

| Claim on the page | Evidence |
|---|---|
| The seven retention categories, their contents and windows | `shared/retention.py` → `lib/retention-categories.ts`, pinned by `test_retention_published.py` |
| "30 days to change your mind" | `DELETION_GRACE_PERIOD = timedelta(days=30)` |
| Profile picture restored on cancel; not removed at request time | `deletion.py` — *"Removing the object at request time makes the grace period a lie."* |
| Billing records kept 7 years; audit logs 24 months; both survive deletion | `SURVIVING_CATEGORIES`; AD-13 keeps PII out of audit |
| Audit logs "identify no one" | AD-13, cited in `deletion.py`'s own docstring |
| We do not track email opens or clicks | **No model declares `EMAIL_DELIVERY_EVENTS`**; `apps/delivery/email_api.py:71` says the storage "is not" built |
| No analytics product of any kind | No PostHog / Segment / Mixpanel / Sentry / GA anywhere in `adapters/` or `apps/` |
| Location is read from an edge header, not a geo-IP vendor | `adapters/geo/header.py` — *"does no database lookup and calls no vendor"* |
| Voyage receives public event title + description only | `embed_event()` passes `event_embedding_text(title=…, description=…)` from the public `Event`; no personal model is read |
| Six third parties, and that is the whole list | `backend/adapters/` — billing, email, llm, blob, calendar, geo |
| Password stored as a hash; calendar credentials encrypted at rest | `User` (`AbstractBaseUser`); `personalization/credentials.py` |
| Export at Settings → Account; deletion at Settings → Privacy | `data_export.py` (FR-52); danger zone per Amendment A-16 |
| Pro runs to the end of the paid period after cancelling | `plan-summary.tsx:17` — *"a subscription cancelled in the portal still reads `active`"* via `cancel_at_period_end` |
| Listings are third-party content we cannot vouch for | FR-17 source acquisition hierarchy |

## The claim that was deliberately not made

PRD §10.2: *"Where the LLM provider's terms permit opt-out of training-data retention, the
system is configured to opt out at the API level."*

**`adapters/llm/voyage.py` contains no such configuration.** The page therefore never says
it, and a test enforces the silence:

```ts
expect(container.textContent).not.toMatch(/opt(ed)?[ -]out/i);
expect(container.textContent).toMatch(/do not use your personal data to train/i);
```

**Asserting the absence of a claim is the only guard that keeps an unverified promise off
a legal page**, and it is the kind of thing that gets added later by accident.

## Divergences found between PRD §10.2 and the code

Reported, not papered over. **Both run in the user's favour.**

1. **`EMAIL_DELIVERY_EVENTS` — §10.2 publishes a 90-day window for "sent, opened,
   clicked". No model declares the category.** The product does not track opens or clicks
   at all. Publishing the window would have described more surveillance than exists.
2. **`ANALYTICS_AGGREGATES` — §10.2 promises indefinite retention of anonymised
   aggregates. No model declares it, and there is no analytics vendor.**

Both are omitted from the published table, and `test_the_unimplemented_categories_are_still_unimplemented`
**fails the moment either gains a model** — which is exactly when the policy would start
understating what is collected.

## The seam test, and the proof it fails

`backend/tests/shared/test_retention_published.py` — 6 tests. The registry is Python and
the page is TypeScript; nothing but this joins them.

**Proved by renaming one row** (`audit_log` → `audit_logs`) in the published table:

```
FAILED test_every_category_in_use_is_published
FAILED test_nothing_is_published_that_is_not_a_real_category
```

Both directions caught — the category that went missing *and* the one that was invented.
Restored, 6 pass.

**A bug in this test was found and fixed before it could pass wrongly.** Its first version
computed `categories_in_use() - UNIMPLEMENTED` and never subtracted the published rows, so
it reported all seven categories missing. Had the set arithmetic erred the other way it
would have passed while asserting nothing.

## Frontend tests added

| Test | Asserts |
|---|---|
| publishes every retention category it mirrors | each row's label reaches the DOM; row count > 5 |
| names the 30-day grace period | the figure matches `DELETION_GRACE_PERIOD` |
| explicit that billing records and audit logs survive | the unflattering half is present |
| claims no training-data opt-out | the absence guard above |

## Acceptance criteria

| Criterion | Status |
|---|---|
| Retention table matches the registry, with a test on divergence | ✔ both directions |
| Every claim traces to code; unevidenced claims cut | ✔ table above |
| 30-day grace stated, accurate about what survives | ✔ incl. avatar-in-bucket |
| Third parties: real adapters, no others | ✔ six |
| Rights described with the routes users actually use | ✔ |
| `/terms` covers service, third-party listings, use, termination, billing, disclaimers | ✔ nine sections |
| Draft status in the text, not only the banner | ✔ both contact sections |
| PRD/code gaps reported | ✔ two, above |
| Plain reading level | ✔ short sentences, no defined terms, no cross-references |
