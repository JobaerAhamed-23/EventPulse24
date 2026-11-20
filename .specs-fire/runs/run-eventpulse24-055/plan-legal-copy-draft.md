# Plan: legal-copy-draft

**Run:** run-eventpulse24-055 · **Mode:** confirm · **Complexity:** medium
**Depends on:** legal-page-routes (done) · **Checkpoint:** plan approval

## The research is done, and it changes what the policy may say

Every claim below was read out of running code, not out of the PRD.

### The retention registry — 7 categories in use, not 9

`retention_registry()` maps 41 models. Grouped:

| Category | Models | Window (PRD §10.2) |
|---|---|---|
| `ACCOUNT_CONTENT` | 12 — `PersonalEvent`, `SavedEvent`, `SavedCollection`, `SavedCollectionItem`, `ConflictPair`, `ReminderPlan`, `ScheduledSend`, `PulseDigest`, `DigestComposition`, `StateChangeNotice`, `EventReport`, `DataExport` | while active; purged ≤30 days after deletion |
| `PREFERENCE_SIGNALS` | 10 — `Interest`, `DigestPreference`, `EventDismissal`, `EventDetailOpen`, `CategoryMute`, `SourceMute`, `EventNoticeMute`, `NotificationPreference`, `QuietHoursOverride`, `OnboardingProgress` | 12 months rolling |
| `ACCOUNT_IDENTITY` | 5 — `User`, `CalendarConnection`, `PendingEmailChange`, `PasswordResetToken`, + `sessions.session` | while active; purged on disconnect or deletion |
| `AUDIT_LOG` | 4 + `admin.logentry` | 24 months |
| `SOURCE_REGISTRY` | 11 — the public catalog | event range + 12 months |
| `BILLING_RECORDS` | 1 — `Subscription` | 7 years |
| `TOS_REVIEW_RECORDS` | 1 | 7 years |

**Two categories PRD §10.2 publishes have no models at all.**

- **`EMAIL_DELIVERY_EVENTS`** — §10.2 promises *"sent, opened, clicked: retained 90 days."*
  **No model declares it.** `apps/delivery/email_api.py:71` says so outright: *"SM-2 is a
  success metric measured in analytics, and the storage that would feed it is not"* built.
  The product does not record opens or clicks.
- **`ANALYTICS_AGGREGATES`** — no model. There is also **no analytics vendor** anywhere:
  no PostHog, Segment, Mixpanel, Sentry or Google Analytics in `adapters/` or `apps/`.

**The policy must not publish those two windows.** Publishing a 90-day retention period
for open-and-click tracking that does not happen would describe a product that collects
more than this one does. This is the divergence the work item predicted, and it runs in
the user's favour.

### Who the data actually reaches — shorter than expected

| Adapter | Third party | What it receives |
|---|---|---|
| `billing/stripe.py` | **Stripe** | payment and subscription data |
| `email/smtp.py` | **SMTP provider** | address + message, to send it |
| `llm/voyage.py` | **Voyage AI** | **public event title + description only** |
| `blob/s3.py` | **S3/MinIO** | avatar images |
| `calendar/ics.py` | the user's own calendar host | fetches the URL the user supplied |
| `geo/header.py` | **nobody** | reads an edge header |

**Two of these are worth stating plainly because most products cannot.**

- **Voyage never receives personal data.** `embed_event()` embeds
  `event_embedding_text(title=..., description=...)` from the public `Event` row. Nothing
  reads a `PersonalEvent`, a `SavedEvent` or a preference signal into an embedding.
- **Geo-location calls no vendor.** `adapters/geo/header.py`'s own docstring: *"This
  adapter does no database lookup and calls no vendor… asking a geo-IP service would mean
  sending the caller's address to a third party on every page load."*

### Deletion — what dies, what survives, and why

`PURGED_CATEGORIES` = `ACCOUNT_CONTENT`, `PREFERENCE_SIGNALS`, `EMAIL_DELIVERY_EVENTS`,
`ACCOUNT_IDENTITY`. `SURVIVING_CATEGORIES` = `AUDIT_LOG` (24 months; safe to keep because
**AD-13 keeps PII out of it**) and `BILLING_RECORDS` (7 years, tax and legal).
`UNTOUCHED_CATEGORIES` = the catalog, the operator's own ToS paperwork, and anonymised
aggregates that carry no user id.

`DELETION_GRACE_PERIOD = 30 days`, and the avatar deliberately survives in the bucket for
that window — `deletion.py`: *"Removing the object at request time makes the grace period
a lie."* **The policy says this**, because a reader who cancels within the grace period
needs their picture back.

## What gets written

**`/privacy`** — what we collect (by the seven live categories, in plain language), how
long, who it reaches, what we never do, your rights and where to exercise them, deletion
and the grace period, children, changes to the policy, contact.

**`/terms`** — what the service is, that **public listings are other people's data and we
cannot guarantee them** (FR-17), acceptable use, accounts and termination, Pro billing and
cancellation as `adapters/billing/stripe.py` implements them, liability limits in plain
terms, changes, contact.

## The test that keeps it true

`tests/legal-retention-table.test.ts` — the published retention table's categories must
match the live registry. A new `RetentionCategory`, or a window changed in
`shared/retention.py`, fails the page.

**The registry is Python and the page is TypeScript**, so the seam needs a source of
truth. Plan: a committed `frontend/lib/retention-categories.ts` holding the table, plus a
**backend** test (`backend/tests/shared/test_retention_published.py`) asserting the TS
file's categories equal `PRD_CATEGORIES` minus the two unimplemented ones. The backend
owns the fact; the test fails on either side drifting.

## Steps

1. `frontend/lib/retention-categories.ts` — the table, with each category's plain-language
   name, window and what it holds.
2. Backend test pinning that file to `retention_registry()`.
3. `/privacy` body — nine sections, built on the table.
4. `/terms` body — eight sections.
5. Extend `tests/legal-pages.test.tsx` for the new sections and the table.
6. Full suite, `tsc`, lint.

## Constraints held

- **No claim about the LLM provider's training-retention opt-out.** §10.2 says *"where the
  provider's terms permit opt-out… the system is configured to opt out."* **`voyage.py`
  contains no such configuration.** The policy will say only what is true: we do not train
  on your data, and the embedding provider receives no personal data.
- The draft banner stays. Nothing implies legal review.
- Divergences are reported in the run, not papered over.

## Decision asked for

**A contact address.** Both documents need one — a privacy policy with no way to reach
anyone fails the "right to know" it describes. There is no support address anywhere in the
repo. Options: a real address you supply, a placeholder clearly marked, or a sentence
pointing at in-product settings with no email at all.
