# Review Report: legal-copy-draft

**Run:** run-eventpulse24-055 · **Date:** 2026-11-20 · **Verdict:** PASS

## Scope

**Created** — `frontend/lib/retention-categories.ts` (the published table),
`backend/tests/shared/test_retention_published.py` (6 tests pinning it to the registry).

**Modified** — `frontend/app/privacy/page.tsx` (10 sections),
`frontend/app/terms/page.tsx` (9 sections), `frontend/tests/legal-pages.test.tsx` (+4).

## Checks

| Check | Result |
|---|---|
| Frontend suite | 2847 tests, pass |
| Backend `tests/shared/` | 99, pass |
| Backend, full | 7666 tests, pass |
| `tsc --noEmit` | clean |
| `ruff check` | clean |
| `pnpm lint` | 5 problems, all pre-existing |

## Auto-fixes applied

- **Removed an unused `from django.apps import apps`** in the new backend test (ruff
  F401). Mechanical. Tests re-run after.

## Findings

### F-5 (fixed during the run) — the seam test's set arithmetic was wrong

`test_every_category_in_use_is_published` computed `categories_in_use() - UNIMPLEMENTED`
and **never subtracted the published rows**, so its first run reported all seven
categories missing. Fixed to subtract `published_keys()`.

**Worth recording rather than quietly correcting.** The failure was loud, so it was found
in seconds — but the same error with the operands reversed would have produced a test that
passed while asserting nothing, guarding a legal page that nobody would check by hand.
This is the argument for proving a new test fails on purpose, which was then done by
renaming a row and watching both directions catch it.

### F-6 (reported, in the user's favour) — PRD §10.2 publishes two windows for data that does not exist

- **`EMAIL_DELIVERY_EVENTS`** — §10.2 promises *"sent, opened, clicked: retained 90
  days."* No model declares the category; `apps/delivery/email_api.py:71` states the
  storage behind that metric "is not" built.
- **`ANALYTICS_AGGREGATES`** — §10.2 promises indefinite retention of anonymised
  aggregates. No model declares it, and the codebase contains **no analytics vendor**.

Omitted from the published table, with
`test_the_unimplemented_categories_are_still_unimplemented` failing the moment either
gains a model. **A privacy policy overstating collection is not a harmless error** — it is
a false statement about surveillance, made to the person being surveilled.

**Recommendation:** amend §10.2 to match, or build the stores. Not done here: this item
writes copy, and a PRD amendment is a decision with its own checkpoint.

### F-7 (open) — §10.2's training-opt-out claim is unimplemented

§10.2: *"Where the LLM provider's terms permit opt-out of training-data retention, the
system is configured to opt out at the API level."* **`adapters/llm/voyage.py` configures
nothing of the kind.**

The mitigating fact is that Voyage receives **no personal data** — `embed_event()` sends
public event title and description only — so the exposure is not what the clause guards
against. **But the PRD claims a configuration that does not exist**, and someone reading
§10.2 to answer a due-diligence questionnaire would answer wrongly.

Not repeated on the page, and a test asserts the silence.

### F-4 (still open, carried from items 1–2) — three pre-existing lint errors

Unchanged: two impure-call-during-render errors in `components/settings/email-change.tsx`,
one unused variable in `e2e/digest-opt-out.spec.ts`.

## Observations, no action

- **The table is a mirror and says so in its first line.** The risk with a generated-looking
  constant is a future editor treating it as the source and changing a window there. The
  header names the registry, names the test, and says what happens if they drift.
- **The unflattering clauses are present and testable.** `/privacy` states plainly that
  billing records survive seven years and audit logs 24 months, and a test asserts it. A
  policy that lists only what is deleted tells half a truth, and the half it omits is the
  half a regulator asks about.
- **Placeholder contact addresses are marked in the visible copy**, not only in a comment —
  `privacy@eventpulse24.example` and `legal@eventpulse24.example`, each followed by a
  `Text.Meta` line saying it is a placeholder pending legal review.
- **Reading level.** Short sentences, no defined terms, no "Section 4.2(b)" cross-references,
  and the most important clause in `/terms` — that the listings are other people's and
  cannot be vouched for — is second, not buried in a liability section at the end.

## Conclusion

Complete and green. Two PRD divergences and one unimplemented PRD claim are raised for a
human; none is absorbed into the copy.
