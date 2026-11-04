---
work_item: share-control
intent: public-pages-and-seo
created: 2026-11-04
mode: validate
checkpoint_1: approved
---

# Design: Handing it to a friend — the share affordance

## Summary

FR-28's sender side: a **share control** on the Pulse Card and on the Detail Screen that
produces the public `/events/{slug}` URL — the same URL FR-26's page already serves, with
no second link shape, no token and no new route.

**The Detail Screen already has a Share button, and it is wrong.** It shares
`window.location.href`, which on the Detail Screen is `/events/{uuid}` — the signed-in
personal URL. A friend who opens that link gets a sign-in wall instead of the event. So
this item is not "add a share button"; it is "make the existing one share the *public*
page, and give the Pulse Card one too".

**Two things the work item did not know it needed**, both found by reading the code:

1. **The Pulse Card cannot build a public URL today.** `DigestCardOut` carries no slug.
   The card links to `/events/{event_id}` — the personal URL — because the slug has never
   been on the wire. The catalog's read already has it (`PublicEvent.slug`), so the fix is
   a **new field on the card**, not a new endpoint.
2. **`in_review` is invisible to the client.** It is filtered at the read boundary, so no
   payload carries a publication-status flag — but the *absence* of the public facts is
   exactly the signal, and it is already on the wire as `catalog_event_missing`. The
   server can state shareability outright rather than leaving the client to infer it.

**This item contradicts one sentence of `EXPERIENCE.md` §13**, and the design says so
plainly rather than quietly breaking it: *"No description, no image, no map, no price, no
attendee count, no share button."* FR-28 is a PRD requirement and the card is where FR-28
says the affordance lives. The amendment is one small action row; everything else §13
forbids stays forbidden, and §13's anti-pattern — progressive disclosure that **hides**
trust signals — is not violated, because this **adds**.

## Scope

**In Scope:**
- A shared share control (one component, one behaviour) used by the Pulse Card and the
  Detail Screen.
- Web Share API where it exists, clipboard copy where it does not, and a confirmation
  that is both shown and announced.
- A new `public_slug` field on the digest card, so the server states shareability.
- The Detail Screen's Share button fixed to share the public page.
- The share affordance on the Pulse Card, with its placement decided (OQ-B).
- The attribution question answered (the mockup's "Shared by" banner).

**Out of Scope:**
- **A share control on the public event page.** FR-26's page already carries the Open
  Graph metadata that makes an unfurl rich; a Share button there is a third surface, not
  a requirement of this item's AC.
- **A share control on the Pulse Preview's cards.** `/preview` is the anonymous gateway
  and its card is deliberately the smallest card in the product; it already links to
  `/events/{slug}`.
- **Any change to the public page's metadata, its OG image or its schema.org block** —
  those are `frontend-public-event-page`'s, and this item relies on them for the unfurl.
- **A server-side share endpoint, a share token, a share record, or a referral
  attribution.** One URL, read by the public page, is the whole scope.
- **Attribution in the shared URL.** Decided below, and it is *no*.
- **The long-press quick-actions sheet** (`EXPERIENCE.md` §13's mobile affordance). It
  does not exist in this codebase, it is not keyboard-reachable, and FR-28 says the
  affordance is reachable from the card.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **OQ-B — what the sender-side control is** | **A visible-label text button — "Share" — never an icon-only control, never a menu item, never a long-press.** | **Icon-only fails WCAG 1.1.1 as this repo reads it**: `pulse-card.tsx`'s own Source Badge docstring says *"every variant has a visible inline text label — never icon-only (WCAG 1.1.1)"*, and the boundary test's terracotta rule shows how deliberate that is. There is also **no icon library** — `DESIGN.md` says "UI system: None" and `components/shell/nav-glyphs.tsx` hand-draws 16×16 SVGs; inventing a `ShareGlyph` would add a glyph for one button. **A menu item needs a menu**, and there is no menu component in the product. **A long-press is unreachable by keyboard** and undiscoverable on desktop, and the AC demands keyboard reachability. A text button needs nothing new and reads in the screenshot the design already shows. |
| **OQ-B — where it sits on the Pulse Card** | **In a new card action row at the card's foot — the mockup's own `.card-actions` position — right-aligned, inside a `relative z-10` container.** | **The trust row is at capacity.** It already holds the conflict indicator, the five-dot confidence pulse *with* its visible "Relevance" label, and the Source Badge *with* its visible label ("Community source"), beside the category kicker — and it is `flex items-center gap-2` with no wrap. A fourth control with a visible label would overflow a 360px viewport. Putting it in the **title row** puts an action beside the event name and competes with the decorative `▸`; putting it in the **meta row** puts a button inside a sentence. The mockup's own answer is a footer: `.card-footer` → `.card-actions` → `.ghostbtn` ("Why this?", "Save") — the card's actions live at its foot. **The `relative z-10` is load-bearing and not optional**: the stretched `<Link>` is `absolute inset-0 z-0` and comes later in DOM order, so it paints over anything in the normal flow — `pulse-card.tsx` says so in the trust row's own comment, and without the raise the confidence and badge buttons are inert. A new row must carry the same raise or the Share button is unpressable. |
| **Does the Pulse Card's Share survive `EXPERIENCE.md` §13's "no share button"?** | **No — the sentence is amended, deliberately and explicitly.** | §13's sentence enumerates the **mobile default of `Card.PulseDigest`**, and FR-28 puts the share affordance *on the card*. A PRD requirement outranks a UX-spine's density note, and the alternative — a share control only on the Detail Screen — would not satisfy FR-28's *"from any Pulse Card **or** Detail Screen"*. **What §13 forbids besides the share button stays forbidden**: this adds one action row and nothing else — no description, no image, no map, no price, no attendee count. **And §13's own anti-pattern is not triggered**: the anti-pattern is disclosure that *hides* trust signals; this *adds* a control and leaves the Why-this Tags, the Confidence Pulse, the Source Badge and the conflict indicator exactly where they are. The existing test `pulse-card.test.tsx` — *"shows no attendee count, no share button and no description"* — is **rewritten**, and the rewrite says why in a comment. |
| **Attribution: does the shared link carry "shared by"?** | **Dropped. The shared URL is exactly `/events/{slug}` — no query parameter, no fragment, no token.** | Three reasons, in order of weight. **(1) It would be a second URL shape for one document**, which this intent has already ruled out twice: the sitemap item made "one URL, one canonical" a property of the site, and the public page sets `alternates.canonical: /events/{slug}` — a `?shared_by=` variant is a second URL the page does not canonicalise to, and a crawler that fetches it records two documents. **(2) The public page must be session-free and cacheable** (AD-12: "Public event pages render fully without a session and are statically generated or ISR'd"). A "Shared by Sara" banner is per-referrer state; to render it the page would have to read a session or a cookie, which makes its content depend on who is asking and takes it out of the cache. **(3) FR-28 itself does not ask for it**: the PRD says the share-link is *"already in the form of FR-26) with pre-filled metadata"* — **the event's** metadata — and its stated consequence is *"A share-link opens the public Event URL with a 'Save to Pulse' CTA."* No attribution appears anywhere in FR-28. `share-link-desktop.html`'s "Shared by Sara · 2 days ago" banner is the **recipient's** landing (tagged UJ-5) and is *not* the public page's design; `TRACEABILITY.md` records FR-28 as *"PARTIAL (inferred only) — open gap"* for exactly this reason. **Consequence, accepted:** the mockup's banner is not implemented, and this design says so rather than leaving a reader to wonder. |
| **How the client learns an event is shareable** | **A new server field, `public_slug: str \| None`, on the digest card. `None` means "not publicly shareable".** | The client must not *infer* shareability (AD-10's shape: the server states the fact, the client renders it). Today it could not even try: `DigestCardOut` has no slug, and `in_review` is invisible — it is filtered at the read boundary, so no payload carries a publication-status flag. **`get_public_events` already answers exactly this question**: it returns published, non-superseded events and *"an id that is not public is simply absent from the result"*. So `public_slug` is `public.slug` when the event is public and `None` when it is not — and an `in_review` event is absent, so it is `None`, so **the control is not offered**. The same field is `None` for a **personal** card, because a personal event has no public page at all. **One field, one meaning.** |
| **The Detail Screen's slug** | **Already on the wire — `EventDetailFactsOut.slug` — so the Detail Screen needs no backend change.** | The detail read only ever answers for a public event (`get_public_event_detail` 404s for an unpublished, `in_review`, superseded or started event), so the Detail Screen's event is **always** shareable and the Share control is always offered there. The existing `DetailActions` Share button was simply never given the slug — it shared `window.location.href` instead. |
| **What URL is copied** | **An absolute URL: the site's configured public origin + `/events/{slug}`, with the browser's own origin as the fallback.** | A relative `/events/slug` pasted into a chat is a broken link. **The configured origin is `PUBLIC_SITE_URL`**, read server-side by `lib/site-url.ts` — the same origin Next resolves `metadataBase`, the canonical and the `og:url` against, so the shared URL and the page's own canonical cannot disagree. `siteUrl()` **returns `undefined` in production when the origin is unset** (an unset origin is a deployment mistake and Next warns about it), so the client falls back to `window.location.origin` — the origin the user is actually looking at, which is never wrong for the person receiving the link. `PUBLIC_SITE_URL` has **no `NEXT_PUBLIC_` prefix**, so it is unreadable from a client component: **the server resolves it and passes it down.** |
| **The share payload** | **`navigator.share({ title, url })` — the event's title and the public URL.** | `EXPERIENCE.md` §964 names the Web Share API as the platform capability for FR-28. **The title is the event's own**, not a generic "Event on EventPulse24" — the current button's constant title is part of what is being fixed. The rich unfurl (description, image) is the **page's** Open Graph metadata, delivered by `frontend-public-event-page`; the share payload does not re-implement it. |
| **The clipboard fallback, and what "confirmation" means** | **`navigator.clipboard.writeText(url)`; on success a visible, announced confirmation. A cancelled share sheet is not a failure and says nothing.** | The AC asks for the Web Share path *and* a copy-to-clipboard fallback *everywhere else*, with **visible confirmation that the copy happened** — so the confirmation belongs to the **copy**. On the native path the user has already chosen a target; the control says the share happened and stops. A share sheet the user dismissed throws `AbortError`: reporting that as an error would be a lie about the user's own action, and the existing code already says so (*"A cancelled share sheet is not a failure, and there is nothing to say about it"*). |
| **How the confirmation is announced** | **A bare `aria-live="polite"` region, next to the control — never a second `role="status"`.** | **One `role="status"` per surface** is the rule the codebase already follows and states: the digest page's status region is `app/page.tsx`'s *"Pulse Digest ready, 3 events for today"*, and `components/add-event-button.tsx` therefore uses a **bare** `aria-live="polite"` with the comment *"A live region without `role="status"`. The digest's own 'ready' line is the page's `role="status"`, and it stays the only one there is — two status regions on a page would make 'which one is the page talking?' a question the DOM cannot answer."* The Detail Screen's action row already owns a `role="status"` (the conflict-resolution failure line), so **both** surfaces use the bare live region. The confirmation is **shown and announced** — the AC asks for both. |
| **One control or two?** | **One component — `components/share/share-control.tsx` — with two *weights*, and the weight is a property of the surface, not of the behaviour.** | "Sits consistently on both surfaces" is best guaranteed structurally: the same component, the same token vocabulary, the same behaviour, the same messages. **The weights differ because the design says they differ**: `EXPERIENCE.md` §4 puts the Detail Screen's three buttons in *`Button.Secondary` weight* (`DESIGN.md`: surface.subtle fill, 1px border.subtle stroke, spacing.3 × spacing.6), while the mockup's card actions are the small bordered ghost button (`.ghostbtn`: 7px × 14px, 13px, ink.secondary) — the card's own density. **The Detail Screen's existing Share styling is preserved exactly**; the card gets the mockup's treatment. Same tokens, same affordance, each at its surface's specified weight. |
| **Where the share lives on the Detail Screen for a sold-out event** | **The Share control stays; the Save button and the reminder link do not.** | The sold-out branch of `app/events/[id]/page.tsx` currently **replaces** the action row wholesale — but a sold-out event is still published, still public, and still has a public page. **The two surfaces must agree**: the Pulse Card offers a share for a sold-out event (it is public), so the Detail Screen must too. Offering it in one place and not the other is the inconsistency the AC names. So the row is *narrowed*, not removed: sold out → the notice plus Share; otherwise → Save, Share, Reminder. |
| **Personal events are never shareable** | **No share control on a personal card, ever.** | A personal event is **the user's own agenda row** — their dinner, their anniversary, their location. It has no catalog event and no public page. A share control on one would produce a link to `/events/{personal_event_uuid}`, which the public page 404s — and if it did not, it would publish a stranger's private calendar. `public_slug` is `None` for a personal card, and the control is therefore not rendered. |

## Data Models Affected

### Creates

- **None.** No new table, no new model, no migration.

### Modifies

- **`DigestCard`** (`backend/apps/personalization/services/digest_read.py`) — adds
  `public_slug: str | None`. **The event's public page slug, or `None`.** `None` means
  *not publicly shareable*, and there are three reasons it can be `None`, all of them
  facts rather than guesses: the card is a **personal** event; the catalog does not
  currently hold the event publicly (`_public_display_facts` found no `PublicEvent`) —
  which covers `in_review`, unpublished and superseded alike; or the card's event has no
  slug at all. **The field is the server's statement, and it is the same statement the
  public catalog already makes** — `get_public_events` returns published, non-superseded
  events and *"an id that is not public is simply absent from the result"*. Nothing is
  computed on the client to fill it.
- **`DigestCardOut`** (`backend/apps/personalization/schemas.py`) — adds
  `public_slug: str | None = None`, with the same meaning and the same reason. The wire
  shape is regenerated (`make client`), so the frontend's `DigestCardOut` type carries it
  and **cannot drift** (AD-19).
- **`DigestCardOut(...)`** (`backend/apps/personalization/api.py:508`) — the mapping
  carries `public_slug=card.public_slug`.

## Technical Approach

### Architecture

```
  SENDER'S SIDE                                     RECIPIENT'S SIDE
  ───────────                                       ───────────────

  Pulse Card (signed in)          Detail Screen (signed in)
   card.public_slug  ─┐            event.slug ─┐
                      │                        │
  app/page.tsx ───────┤  (server)              │  (server)
   siteUrl() ─────────┤                        │  siteUrl()
                      ▼                        ▼
        shareOrigin (string | null)   shareOrigin + slug
                      │                        │
                      └────────┬───────────────┘
                               ▼
                 components/share/share-control.tsx
                    (one component, one behaviour)
                               │
               click ──────────┴──────────────
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
     navigator.share({title,url})     navigator.clipboard.writeText(url)
     (Web Share API present)          (everywhere else)
                │                             │
                └──────────────┬──────────────┘
                               ▼
              visible + announced confirmation
                    (aria-live="polite")

  ── one URL, no token, no second shape ──────────────────────────

        {origin}/events/{slug}      ──►     FR-26 public event page
                                             (OG metadata → rich unfurl)
                                             "Save to Pulse →" CTA
                                             (sign-up, for a recipient
                                              with no account)
```

**The two data paths, side by side:**

| | Pulse Card | Detail Screen |
|---|---|---|
| Slug source | **new** `DigestCard.public_slug` (from `PublicEvent.slug`) | `EventDetailFactsOut.slug` (already there) |
| Shareable? | `public_slug is not null` | always — the detail read 404s for anything non-public |
| Origin | `siteUrl()` on `app/page.tsx` → prop | `siteUrl()` on `app/events/[id]/page.tsx` → prop |
| Weight | ghost (the card's density) | secondary (`EXPERIENCE.md` §4) |
| Confirmation | bare `aria-live` (the digest owns the page's `role="status"`) | bare `aria-live` (the action row owns a `role="status"` for the conflict failure) |

### API Changes

- `GET /api/personal/digest` — **the response's card gains `public_slug: string | null`.**
  No new endpoint, no new route, no change to any other field. `null` means the event is
  not publicly shareable.
- `GET /api/events/{event_id}` — **no change.** `EventDetailFactsOut.slug` already
  carries what the share needs.

### Database Changes

None. No migration is created or required.

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/personalization/services/digest_read.py` | modify | `DigestCard.public_slug`, populated from `PublicEvent.slug`. |
| `backend/apps/personalization/schemas.py` | modify | `DigestCardOut.public_slug`. |
| `backend/apps/personalization/api.py` | modify | The digest endpoint's card mapping. |
| `backend/tests/personalization/test_digest_api.py` | modify | The card's `public_slug`, per card kind. |
| `frontend/lib/share-link.ts` | create | The one place a public event URL is built: `publicEventUrl(slug, origin)`. Pure — no env, no `window`. |
| `frontend/lib/share-link.test.ts` | create | The URL builder's tests. |
| `frontend/components/share/share-control.tsx` | create | The shared control: Web Share, clipboard fallback, confirmation, keyboard. |
| `frontend/components/share/share-control.test.tsx` | create | The control's own tests. |
| `frontend/components/digest/pulse-card.tsx` | modify | The card's action row and the Share control. |
| `frontend/components/digest/pulse-card.test.tsx` | modify | The *"no share button"* test, rewritten. |
| `frontend/components/detail/detail-actions.tsx` | modify | The Share button, fixed and shared; `soldOut`. |
| `frontend/components/detail/detail-actions.test.tsx` | modify | The share path on the Detail Screen. |
| `frontend/app/page.tsx` | modify | Resolve the origin on the server and pass it down. |
| `frontend/app/events/[id]/page.tsx` | modify | Pass the slug and the origin; narrow the sold-out branch. |
| `frontend/app/events/[id]/page.test.tsx` | modify | The sold-out row and the Share control. |
| `frontend/lib/api/openapi.json` | modify | Regenerated (`make openapi`). |
| `frontend/lib/api/schema.ts` | modify | Regenerated (`make client`). |
| `frontend/tests/pulse-card-boundary.test.ts` | modify | The card's structural rules, extended to the new control. |

## Security Considerations

- **A personal event is never shared.** `public_slug` is `None` for a personal card, so no
  control is rendered. A personal event is the user's own agenda row — their dinner,
  their location — and it has no public page. This is the one case where an
  over-eager share control would leak something real, so it is a server-side fact and not
  a client-side check.
- **An `in_review` event is never shared.** It is absent from `get_public_events`, so
  `public_slug` is `None` and the control is not offered — **rather than producing a link
  that 404s for the recipient**, which is the AC's own wording.
- **The shared URL carries no token, no identifier of the sender and no referral code.**
  It is a public page's URL and nothing else, so it leaks nothing about who sent it and
  creates no capability.
- **Nothing is written.** The share action is a read of the URL the client already holds;
  no endpoint is called, no row is written and no audit entry is made. A share is not a
  decision (AD-5, AD-13).

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| FR-26 public event page (`/events/{slug}`) | HTTP link | The shared URL's destination, with its OG metadata and its "Save to Pulse →" CTA. |
| Web Share API | Browser platform | The primary share path, where it exists. |
| Clipboard API | Browser platform | The fallback path, everywhere else. |
| `siteUrl()` / `PUBLIC_SITE_URL` | Environment | The site's public origin — the same one the canonical and the OG URL resolve against. |
| `navigator.clipboard` | Browser platform | The copy. Not available on insecure origins; the failure is reported, not swallowed. |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **The share button is unpressable, because the stretched link covers it** | **Severe** — a control that looks real and does nothing is worse than no control. The card's own comment records that the trust row's buttons were inert without `relative z-10`. | The new action row carries **`relative z-10`**, like the trust row. A source-text assertion in `tests/pulse-card-boundary.test.ts` requires the row that holds the share control to be raised above the link, so the rule cannot be lost in a later edit. |
| **The shared URL is the *personal* URL** — `/events/{uuid}` — and the recipient gets a sign-in wall | **Severe** — the feature would appear to work and share the wrong thing. **This is the bug that exists today.** | The control is given a **slug**, never a uuid, and the slug is the server's `public_slug` / `event.slug`. A test asserts the shared URL's path is `/events/{slug}` and **not** `/events/{uuid}`, on both surfaces. The card's own stretched link still points at the personal URL — that is correct, and the test distinguishes the two. |
| **`in_review` (or any non-public) event gets a link that 404s for the recipient** | High — a broken promise made to the sender. | `public_slug` is `None` for anything the public catalog does not hold, and **the control is not rendered at all**. A backend test covers a saved-and-then-unpublished event; a frontend test covers a card with `public_slug: null`. |
| **The card's density is broken by the new row** | Medium — the card is the product's signature surface. | The row holds **one** small ghost button and nothing else. §13's other exclusions (description, image, map, price, attendee count) stay excluded, and **no trust signal moves**. The amendment to §13's sentence is stated in this design, in the work item's acceptance criteria, and in the rewritten test's comment — so the change is recorded rather than smuggled. |
| **A second URL shape appears** (a `?shared_by=` parameter, a token, a share route) | High — the intent's own central rule. | **No query parameter, no fragment, no token, no route.** The shared URL is exactly `{origin}/events/{slug}`, which is the page's canonical URL. A test asserts the URL has no query and no fragment. |
| **The public page becomes per-referrer** (to carry the "Shared by" banner) | High — it would break AD-12's session-free, cacheable public surface. | **Attribution is dropped.** The public page reads no session and no referrer, and this item changes nothing about it. |
| **The origin is unset in production** (`PUBLIC_SITE_URL` missing) | Medium — the shared link would name the wrong host, or none. | `siteUrl()` returns `undefined` in production when unset, and the control **falls back to `window.location.origin`** — the origin the user is actually at. The fallback is explicit in the code and asserted by a test. |
| **`navigator.share` rejects for a reason other than cancellation** (permissions, a hostile iframe) | Medium — the user presses Share and nothing happens. | A non-cancellation rejection **falls through to the clipboard copy**, and only a clipboard failure reports *"Couldn't copy the link."* A cancelled sheet (`AbortError`) says nothing at all — reporting a cancellation as an error would be a lie about the user's own action. |
| **The clipboard is unavailable** (insecure origin, permissions) | Low — the share simply did not happen. | The control says so plainly and **does not claim a copy it did not make**. The AC's "visible confirmation that the copy happened" is a claim about a real copy. |
| **Two live regions on one surface** | Medium — "which one is the page talking?" becomes a question the DOM cannot answer. | **Neither surface adds a `role="status"`.** Both use a bare `aria-live="polite"`, following `components/add-event-button.tsx`'s precedent and its comment. The digest's `role="status"` and the Detail Screen's conflict-failure `role="status"` are untouched. |
| **The regenerated OpenAPI contract drifts** | Medium — AD-19. | `make openapi && make client` are run, and `backend/tests/api/test_contract.py` — which fails when the committed schema does not match the served one — is part of the gate. |
| **The card's existing test asserts the *absence* of a share button** | Low — but it would fail the build for the right reason | It is **rewritten**, not deleted: the new test asserts a Share control for a shareable card and **no** control for an unshareable one, and its comment names the FR-28 amendment. |

## Implementation Checklist

**Backend**
- [ ] `DigestCard.public_slug: str | None`, set from `PublicEvent.slug` in
      `_card_for_public`, `None` in the missing-facts branch and in **both**
      `_card_for_personal` branches
- [ ] `DigestCardOut.public_slug: str | None = None`, documented
- [ ] `api.py` maps `public_slug=card.public_slug`
- [ ] **Test: a published public card carries its slug**
- [ ] **Test: a personal card carries `None`**
- [ ] **Test: an event the public catalog no longer holds carries `None`** (the
      `in_review` / unpublished case)
- [ ] `make openapi && make client`; `backend/tests/api/test_contract.py` green

**Frontend — the shared control**
- [ ] `lib/share-link.ts` — `publicEventUrl(slug, origin)`, pure; **no query, no
      fragment, no token**
- [ ] `lib/share-link.test.ts` — the path is `/events/{slug}`; the origin is the
      configured one; the fallback is the browser's
- [ ] `components/share/share-control.tsx` — Web Share path, clipboard fallback,
      visible **and** announced confirmation, `AbortError` says nothing, a real failure
      says so
- [ ] `components/share/share-control.test.tsx` — the Web Share path, the clipboard
      path, the confirmation, the cancelled sheet, the failure, and keyboard operation
- [ ] The control is a real `<button type="button">` with a **visible** label — never
      icon-only

**Frontend — the Pulse Card**
- [ ] The card renders the control **only** when `card.public_slug` is set
- [ ] A **personal** card renders no control
- [ ] The control sits in the card's action row, inside **`relative z-10`**
- [ ] The shared URL is `/events/{slug}`, **not** `/events/{event_id}`
- [ ] The card's stretched link still points at `/events/{event_id}`
- [ ] The confirmation is a bare `aria-live="polite"`; the digest keeps its single
      `role="status"`
- [ ] **Rewrite** the *"shows no attendee count, no share button and no description"*
      test, with the FR-28 amendment in a comment
- [ ] `tests/pulse-card-boundary.test.ts` — the share control's row must be raised
      above the stretched link; the token, motion and terracotta rules still hold

**Frontend — the Detail Screen**
- [ ] `DetailActions` receives the slug and the origin
- [ ] The Share button shares `/events/{slug}` — **not** `window.location.href`
- [ ] The Web Share payload's title is **the event's title**, not a constant string
- [ ] The existing secondary-button styling is preserved
- [ ] A **sold-out** event keeps the Share control and loses Save and Reminder
- [ ] The confirmation is a bare `aria-live="polite"`; the row's existing
      `role="status"` is untouched
- [ ] `app/events/[id]/page.tsx` resolves the origin on the server and passes it down

**Gate**
- [ ] Frontend suite green (`vitest`), `tsc` clean, `eslint` clean, `prettier --check`
      clean
- [ ] Backend suite green, `ruff` clean, `lint-imports` clean
- [ ] `test-report.md` written; code review run; `review-report.md` written

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-04*
