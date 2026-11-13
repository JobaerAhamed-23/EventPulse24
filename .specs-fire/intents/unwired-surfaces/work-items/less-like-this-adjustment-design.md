---
id: less-like-this-adjustment-design
work_item: less-like-this-adjustment
intent: unwired-surfaces
run_id: run-eventpulse24-031
status: approved
decision: split-into-own-intent
created: 2026-11-13
---

# Design: FR-25 "Less like this" — and why it leaves this intent

## The checkpoint's question

The work item and the brief both said this design checkpoint decides one thing before any
code: **does FR-25 belong in `unwired-surfaces`, or in an intent of its own?**

> If either design checkpoint shows the work is larger than the rest of this intent
> combined, it should be split out rather than forced through. — `brief.md`, Notes

## The finding: the foundation does not exist

`less-like-this-mute-prompt-desktop.html` specifies the behaviour precisely:

> FR-25. Triggered after **3 clustered dismissals (embedding cosine ≥0.7)**. Calm copy.
> Reversible from settings. No dark-pattern nag.

Four checks against the code, all negative:

| Check | Result |
|---|---|
| A model storing a dismissal | **none** |
| A persisted embedding, anywhere | **none** — `grep "embedding" backend/apps/*/models.py` returns nothing |
| A migration creating a vector column or enabling pgvector | **none** |
| A production caller of `EmbeddingPort` | **none** — only `FakeEmbeddingAdapter` and the port registry |

The port is declared and wired into the registry; nothing in the product has ever embedded
anything. `pgvector/pgvector:0.8.6-pg18` is the database image, and no migration uses it.

And AD-4 constrains what embeddings may do: *"embeddings only route editorial review
candidates; they never decide identity."* Using them to drive what a user is shown is a
**new** use, which means amending the Architecture Spine — the constitution's rule is that
deviating from an AD *"requires amending the spine first"*.

## What FR-25 actually needs

1. A dismissal model, with the never-delete constraint applied to it
2. Per-event embeddings: a vector column, a migration enabling pgvector, a backfill, and a
   production caller of `EmbeddingPort` with its AD-8 cost accounting
3. A clustering rule over those vectors — cosine ≥0.7 across three dismissals
4. A mute model, and its effect on composition or ranking
5. An endpoint, and the generated client regenerated
6. A swipe on the Pulse Card, plus the prompt
7. A reversal surface in settings, which depends on `settings-sources-surface`
8. An AD amendment, or a documented decision that this use is within AD-4

That is more backend infrastructure than the six completed items of this run **combined**,
and it is the only item in the intent that needs a spine amendment.

## Decision

**Split into its own intent: `relevance-feedback-loop`.**

This is not a deferral and not a scope cut. The brief authorised exactly this outcome at
exactly this checkpoint, and the evidence is unambiguous: `unwired-surfaces` is about
endpoints that exist and have no caller. FR-25 has **no endpoint, no model, no column and
no production use of the port it would need**. It is a different kind of work and
measuring it as "a gap in wiring" would misdescribe it to whoever picks it up.

The new intent carries the full finding so nothing is re-derived.

## What this intent keeps

Nothing from FR-25 is built here. `detail-actions.tsx:7` already states the position
correctly and needs no change:

> there is **no dismissal endpoint** in this codebase — a "Dismiss" button here would be a
> control that silently does nothing

That comment remains true and remains the right behaviour until the new intent lands.
