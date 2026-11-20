---
id: broken-links-and-legal-pages
title: The links that lead nowhere — /suggest, /terms, /privacy
status: completed
created: 2026-11-20
completed_at: 2026-11-20T11:38:08.390Z
---

# Intent: The links that lead nowhere

## Goal

**No link in EventPulse24 leads to a 404.** Three internal destinations are promised in the
UI and do not exist. Two of them sit under a sentence asking the user to agree to them.

## Users

- **Anyone whose digest is empty** — `/suggest`, reached from the one link on the empty
  Pulse Digest.
- **Every person who signs up or signs in** — `/terms` and `/privacy`, linked from the
  consent footnote on both auth screens. This is not an edge case; it is the front door.

## Problem

Reported by the user on 2026-11-20: *"some page give me 404 when no digest exist it show a
suggest event button when i click it give 404."*

That reproduced, and the scan that followed found two more.

### The three dangling destinations, verified 2026-11-20

Every static internal `href` in `frontend/` was diffed against the 28 real `page.tsx`
routes. Three do not resolve. All dynamic hrefs and the whole settings nav do resolve.

| Link | Linked from | Audience |
|---|---|---|
| `/suggest` | `components/digest/digest-empty.tsx:50` | Users with an empty digest |
| `/terms` | `components/auth/signup-form.tsx:253`, `app/signin/page.tsx:65` | **Every signup and signin** |
| `/privacy` | `components/auth/signup-form.tsx:257`, `app/signin/page.tsx:69` | **Every signup and signin** |

### `/suggest` was a deliberate choice, and it is written down

`digest-empty.tsx`'s own header comment states the position taken at build time:

> *"Suggest an event" opens `/suggest` (PRD FR-8). That route does not exist yet, and the
> link is still a **real link**: a disabled control would promise a destination the product
> cannot deliver, and a button that does nothing would be worse than either.*

The reasoning is sound as far as it goes — a dead link does beat a dead button. What it did
not account for is that the third option was never evaluated: **not making the promise.**
FR-8 requires the *link*; nothing in the PRD requires a suggestion feature, and no FR, model,
endpoint or table for one exists anywhere in the codebase.

### The legal pair is a compliance gap, not a cosmetic one

The signup copy reads *"By creating an account, you agree to our Terms and Privacy Policy."*
Both links 404. PRD §10.5's regulatory tables require a published privacy policy under
**GDPR, CCPA/CPRA, VCDPA, CPA, CTDPA, UCPA, PIPEDA, Quebec Law 25 and the Privacy Act 1988**.
`EXPERIENCE.md` §473 locks the footnote's wording but never specifies the destinations.

### Why this was not caught — corrected 2026-11-20 during run-055

**An earlier draft of this brief claimed nothing in the repo guards against dangling
links. That is wrong, and the correction matters because it changes what the fix costs.**

`frontend/tests/digest-home-boundary.test.ts:349` — *"links nowhere that does not
exist — resolved against the app directory"* — already resolves every literal internal
`href` against `app/**/page.tsx` or `route.ts`. It is a good test with real history: its
own comment records that it replaced a deny-list of one string after `/settings/billing`
sat in the dev billing panel and three backend config defaults for weeks, returning every
completed checkout to a 404 while the test stayed green.

It even names `/suggest` explicitly, in an `UNBUILT` allow-set carrying a **reverse
assertion** — `expect([...UNBUILT].filter(route => existsSync(...)))` — so that building
the route fails the test until the exception is removed. The dead link was known,
deliberate and fenced.

**What it does not cover is the rest of the app.** Its `FILES` constant lists the 15 files
*"the home surface is made of"*. `components/auth/signup-form.tsx` and `app/signin/page.tsx`
are not among them, and neither is anything else outside the digest home. That is the whole
reason `/terms` and `/privacy` went unseen: the guard exists, and its scope is one surface.

The traceability matrix is a separate miss. FR-8 is scored **`FULL` in both Section A and
Section C** of the 2026-11-17 matrix, and by FR-8's letter it is — the PRD says the empty
state shows a "Suggest an event" link, and it does. Section C checks that each component
has a real importer rooted in a route; it never follows an `href` to the other end. The
legal pages are invisible to it for a different reason again: they are required by
§10.2/§10.5, which carry no FR headings, and the matrix scores FR headings only.

## Success Criteria

- The empty Pulse Digest no longer links to `/suggest`
- The FR-8 deviation is recorded as a **PRD amendment (A-26)**, written and dated *before*
  the code lands, in the form A-24 and A-25 took
- `/terms` and `/privacy` exist and render on both auth screens' links
- Their copy is drafted from **what the product verifiably does**, and carries an explicit,
  visible notice that it is an unreviewed draft pending legal sign-off
- No static internal `href` in `frontend/` points at a non-existent route
- `EXPERIENCE.md` §5's locked empty-state copy is unchanged by the link's removal

## Constraints

- **No binding legal text is written here.** The draft describes as-built behaviour and says
  so on its face. Counsel review is out of scope and the pages must not imply it happened.
- **The draft must be true.** Every claim is checked against running code — the retention
  registry, the deletion walk, the real third parties — not against the PRD's intentions.
  A privacy policy that overstates the product's discipline is worse than none.
- **The amendment precedes the code.** Removing an FR-8 element without the written
  deviation is the PRD being amended by accident. The constitution's rule for the spine
  applies in spirit here.
- **EXPERIENCE.md §5 forbids any CTA on the empty state.** Removing the link must leave the
  locked headline and the `No qualifying events in {city}.` meta line untouched.
- **EXPERIENCE.md §473 locks the auth footnote copy.** The words do not change; only the
  destinations begin to resolve.

## What the privacy draft can be built from

This product is unusually well set up to describe itself honestly, and the draft should
exploit that rather than invent prose.

- **`backend/shared/retention.py`** — `RetentionCategory` is a machine-readable enum of
  PRD §10.2's nine categories with their windows (12 months for preference signals, 90 days
  for email delivery events, 24 months for audit logs, 7 years for billing, and so on).
  System checks `eventpulse.E003/E004` fail the build on any model without a valid category,
  and `tests/identity/test_deletion_retention_walk.py` walks the registry. **The retention
  section can be generated from the registry and be true by construction.**
- **`DELETION_GRACE_PERIOD = timedelta(days=30)`** in `shared/constants.py`, matching §10.2's
  30-day purge promise and the live cancel-within-grace flow.
- **The real third parties**, from `backend/adapters/`: Stripe (billing), SMTP (email),
  Voyage (embeddings), MinIO/S3 (blob), header-based geo, ICS fetch. That is the complete
  list of who data reaches, and it is short.
- **PRD §10.2's two absolute commitments** — *"No user-data model training"* and *"No
  third-party data sales. Not now, not ever."* — both of which the code currently honours.

## Notes

### A fourth gap, already documented, deliberately not folded in

`app/settings/privacy/page.tsx`'s own header comment records that the route owes a **data
inventory** and does not have one:

> `EXPERIENCE.md` §2 row 9 also commits this route to a data inventory, export (FR-52),
> deletion, a training opt-out, the Amendment A-14 geo-IP consent toggle, the A-13
> amendment-history timeline and a read-only mirror of Settings → Sources. **None of those
> is here.**

PRD §10.2 states it as a requirement: *"Settings → Privacy → 'What we store' displays the
categories and current retention windows in plain language."* It is unbuilt.

It shares a source with this intent's privacy draft — both render `RetentionCategory` in
plain language — so building them together would cost little more than building one. **It is
left out of this intent's work items** because the user scoped this intent to the 404s, and
because it is a pre-existing documented debt rather than part of the reported bug. It is
recorded here so the adjacency is not lost.

### The recurrence fix is cheaper than it was described as — corrected 2026-11-20

The user declined a link-resolution test when it was offered as new work. **It was offered
on a false premise.** The test already exists and is sound; what it lacks is reach. Widening
`digest-home-boundary.test.ts`'s `FILES` list — or lifting its resolving loop into a
repo-wide test over `app/**` and `components/**` — is a far smaller change than writing a
guard from scratch, and it would have caught all three of these links.

Two consequences, either way the user decides:

1. **`fr8-suggest-link-removal` must touch that test regardless.** The `UNBUILT` set, its
   reverse assertion and the paragraph of comment explaining why `/suggest` is fenced all
   describe a link that will no longer exist. Leaving them is leaving a fence around nothing.
2. The widening is **not scheduled** here, because the user scoped this intent to the 404s
   and the decision was taken on the earlier, incorrect description. It is re-offered at the
   `fr8-suggest-link-removal` checkpoint with the real cost attached.
