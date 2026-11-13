---
id: detail-open-signal
title: The Open Signal — Half of FR-24's Neighbour Rule, Never Fired
intent: unwired-surfaces
complexity: medium
mode: confirm
status: pending
depends_on: []
created: 2026-11-13
---

# Work Item: The Open Signal — Half of FR-24's Neighbour Rule, Never Fired

## Description

FR-24 counts a neighbour as a user who **saved _or_ opened** an event.
`neighbor_count.py:157-169` implements exactly that — a set union of `SavedEvent` user ids
and `EventDetailOpen` user ids, deduplicated so a user who did both counts once.

`EventDetailOpen` has exactly one writer: `record_detail_open`
(`services/detail_opens.py:45`), reached only through
`POST /api/events/{event_id}/opened` (`detail_api.py:159`). **The frontend has never called
it.** So the union's second half contributes zero rows, and every neighbour count in the
product is the saver count — silently, with no error and no visible symptom.

This is a deferral that was recorded and then lost. `frontend-event-detail.md:48`:

> **The `opened` signal is not fired.** The API has `POST /api/events/{id}/opened`… Firing
> it means a client-side POST on mount, with CSRF, that must not block the render and must
> not fire for anonymous visitors. That belongs to the delivery intent.

The delivery intent never took it. `tests/ad19-endpoint-coverage.test.ts:225` records the
state of affairs rather than hiding it: *"The endpoint's presence is asserted; the caller is
not asserted to exist, because it does not."*

## Acceptance Criteria

- [ ] Opening the signed-in Detail Screen records the open through
      `POST /api/events/{event_id}/opened`
- [ ] The write is **fire-and-forget** — the render never waits on it, and a failed or slow
      write changes nothing the user sees
- [ ] **No write for an anonymous visitor.** The endpoint answers 401; the UI must not call it
- [ ] **No write on the public event page.** `/events/{slug}` is the anonymous surface
      (AD-12) and is a different page from the signed-in Detail Screen, even though they
      share a route
- [ ] The signal fires **once per screen view**, not once per render — a re-render from any
      state change does not fire a second write
- [ ] `tests/ad19-endpoint-coverage.test.ts` is updated: the caller now exists, so the split
      that documented its absence is replaced by a real call-site assertion
- [ ] Tests cover: the write fires for a signed-in view, does not fire for an anonymous one,
      does not fire on the public page, fires once across re-renders, and a rejected write
      leaves the screen unchanged
- [ ] Every test is verified by a mutation probe that makes it fail

## Technical Notes

- **The route branches, and the branch decides.** `app/events/[id]/page.tsx` renders the
  public page for a minted slug and the signed-in Detail Screen for everything else, via
  `isDetailEvent`. The signal belongs to the second branch only.
- **The write is a client-side POST with CSRF**, so it belongs in a client island, not in
  the server component. `lib/backend-client.ts` handles the CSRF token; use it rather than
  a hand-written `fetch` (AD-19).
- **"Once per view" is the hard part.** A `useEffect` with an empty dependency array fires
  once per mount, which is right — but React Strict Mode double-invokes effects in
  development. Decide how that is handled and say so; the endpoint is idempotent per
  `(user, event)` (`detail_api.py:165`: "opening the screen again refreshes the timestamp
  rather than adding a row"), so a double fire is harmless but still wrong to ship.
- **The idempotency is why this is `confirm` and not `validate`** — the write cannot corrupt
  anything, and the blast radius of getting it wrong is a refreshed timestamp.
- **Do not backfill.** The neighbour bucket counts behaviour from before this item as
  saves-only, and that is correct: the count is other people's behaviour, and we have no
  record of opens that were never recorded.

## Dependencies

- (none)
