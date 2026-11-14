---
id: run-eventpulse24-034
scope: single
work_items:
  - id: less-like-this-adjustment
    intent: relevance-feedback-loop
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-11-13T17:03:56.431Z
completed: 2026-11-14T07:34:11.000Z
---

# Run: run-eventpulse24-034

## Scope
single (1 work item)

## Work Items
1. **less-like-this-adjustment** (validate) — completed

## Current Item
(all completed)

## Files Created

**Backend — adapters**
- `backend/adapters/llm/voyage.py` — the real embedding adapter: the REST call, the dimension request, the vector pairing, the cost row
- `backend/adapters/llm/costs.py` — the AD-8 cost-row writer, and the refusal to write outside a catalog transaction
- `backend/adapters/llm/models.py` — `AICostRow`, routed to the `catalog` schema
- `backend/adapters/llm/fake.py` — the fake embedding adapter, the test double at the port boundary

**Backend — services**
- `backend/apps/ingestion/services/embedding.py` — the embed command
- `backend/apps/ingestion/services/embedding_backfill.py` — the resumable backfill
- `backend/apps/ingestion/services/event_embeddings.py` — the published read port for the vectors
- `backend/apps/personalization/services/dismissals.py` — the dismissal, the guard, the cluster, the decay, the prompt
- `backend/apps/personalization/services/taste_mutes.py` — the category-mute commands

**Backend — surfaces, models, migrations**
- `backend/apps/personalization/taste_mutes_api.py` — the three `/api/settings/taste` endpoints
- `backend/config/management/commands/backfill_embeddings.py` — the resumable backfill's entry point
- `backend/apps/ingestion/migrations/0013_event_embedding.py` — `Event.embedding`, `public.vector(256)`
- `backend/apps/personalization/migrations/0017_dismissal_mute_cost.py` — `EventDismissal`, `CategoryMute`

**Backend — tests**
- `backend/tests/adapters/test_voyage_embedding.py` — 19 tests
- `backend/tests/personalization/mutation_probe_fr25.py` — 35 probes, one per rule

**Frontend**
- `frontend/components/digest/swipe-dismiss.tsx` — the gesture and the keyboard-reachable button, one `dismiss()` between them
- `frontend/components/digest/mute-prompt.tsx` — the bottom-anchored sheet
- `frontend/components/digest/digest-card-list.tsx` — the client state the loop needs
- `frontend/components/settings/taste-mute-list.tsx` — the reversal surface's list
- `frontend/app/settings/taste/page.tsx` — `/settings/taste`
- `frontend/app/settings/taste/loading.tsx` — the sibling loading skeleton
- `frontend/lib/dismissal-write.ts` — the one client write path for a dismissal
- `frontend/lib/taste-mute-write.ts` — the client write paths for a category mute
- `frontend/lib/taste-mutes-read.ts` — the server read for the reversal surface

## Files Modified

- `backend/shared/constants.py` — the FR-25 thresholds (AD-8)
- `backend/apps/ingestion/models.py` — `Event.embedding`
- `backend/apps/ingestion/services/catalog_read.py` — the chip keys the mute filters on
- `backend/apps/personalization/models.py` — `EventDismissal`, `CategoryMute`
- `backend/apps/personalization/schemas.py` — the wire shapes, and the `Literal` that is the published duration contract
- `backend/apps/personalization/api.py` — `POST /api/personal/dismissals`
- `backend/apps/personalization/services/digest_composition.py` — the category filter
- `backend/apps/personalization/services/browse_read.py` — the same filter, so the two surfaces agree
- `backend/config/api.py` — the router mounts
- `backend/config/adapters.py` — the embedding adapter registered; the `:49-51` comment corrected
- `backend/config/settings.py`, `backend/config/env.py`, `.env.example` — the Voyage settings
- `backend/pyproject.toml` — the `pgvector` dependency
- `frontend/components/digest/pulse-card.tsx` — the swipe wrapper and the button
- `frontend/app/page.tsx` — the digest delegates to `DigestCardList`
- `frontend/lib/settings-sections.ts` — the "Taste" row
- `frontend/e2e/settings-navigation.spec.ts` — the "Taste" row, and the missing "Sources" row
- `frontend/lib/api/` (generated) — the OpenAPI client (AD-19)

## Decisions

1. **The prompt is a bottom-anchored sheet, not a modal.** The mockup says so in as many
   words; the inherited implementation blacked out the digest and centred the panel. The
   container is `pointer-events-none`, the backdrop is transparent (it catches the click,
   it does not dim the page), and the digest stays readable behind it.
2. **The prompt's copy is server-computed and never built from an event's title.** A
   scraped title is untrusted source content (AD-9) and must never reach a user's screen.
3. **The cost row is written inside the caller's transaction (AD-8).** The adapter does not
   open a transaction of its own — it would commit a cost row describing a result that
   later rolled back. It *raises* if no catalog transaction is open.
4. **The category mute is a filter on the candidate set, in both surfaces.** Applied in
   `compose_digest` **and** in `browse_read`; a filter present in one and absent in the other
   is the quietest bug in this feature.
5. **The AD-4 question is a finding, not an amendment.** The spine binds *identity*
   ("Embedding cosine similarity is never an identity signal"); FR-25 clusters
   *preference* — a different decision, on the other side of the wall.
6. **Slot-3 immunity is enforced at the dismissal, not at the candidate.** The candidate
   carries no slot, so the immunity reads the user's own composition to find the slot the
   card came from.
7. **The two 422s are different on purpose.** A bad *shape* is `invalid_request` (Ninja,
   before the handler runs); a bad *value* is `invalid_input` (the command, refusing the
   value). The test asserts both codes.
8. **`ADAPTER_MODE=real` still refuses to boot.** The Voyage adapter exists now; the `llm`
   and `email` adapters do not, and building them is out of this item's scope.

## Summary

- Work items completed: 1
- Files created: 30
- Files modified: 22
- Tests added: 200 (139 backend, 61 frontend)
- Coverage: 98.35% across the new modules (8 of them at 100%)
- Completed: 2026-11-14T07:34:11.000Z
