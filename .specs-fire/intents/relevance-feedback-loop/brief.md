---
id: relevance-feedback-loop
title: The Relevance Feedback Loop — FR-25's Dismissal, Clustering and Mute
status: pending
created: 2026-11-13
split_from: unwired-surfaces
---

# Intent: The Relevance Feedback Loop

## Goal

Build FR-25 — *"Less like this"* — which is MVP scope and exists nowhere: no endpoint, no
model, no column, no UI.

## Why it is its own intent

Split out of `unwired-surfaces` at its design checkpoint (2026-11-13,
`run-eventpulse24-031`), which that intent's brief authorised in advance. The full finding
is in `unwired-surfaces/work-items/less-like-this-adjustment-design.md`.

`unwired-surfaces` is about **endpoints that exist and have no caller**. FR-25 has no
endpoint to call. Measuring it as a wiring gap would misdescribe it.

## The state of the world, verified 2026-11-13

| Piece | State |
|---|---|
| `less-like-this-mute-prompt-desktop.html` | **designed** — *"Triggered after 3 clustered dismissals (embedding cosine ≥0.7). Calm copy. Reversible from settings. No dark-pattern nag."* |
| A dismissal model | **none** |
| A persisted embedding anywhere | **none** — no model field, no migration, no vector column |
| A production caller of `EmbeddingPort` | **none** — only `FakeEmbeddingAdapter` and the registry |
| pgvector enabled by a migration | **no** — the image is `pgvector/pgvector:0.8.6-pg18`; nothing uses it |
| A mute model, or any effect on composition | **none** |
| A dismissal affordance (the swipe FR-25 specifies) | **none** — `components/digest/` has the card and four states |

`detail-actions.tsx:7` states the current position correctly and should stay until this
intent lands: *"there is no dismissal endpoint in this codebase — a 'Dismiss' button here
would be a control that silently does nothing."*

## The architectural question this intent must answer first

**AD-4 says embeddings *"only route editorial review candidates; they never decide
identity."*** Using them to decide what a user is shown is a new use of the port.

The constitution: *"Its ADs (AD-1..AD-21) are invariants, not suggestions; deviating
requires amending the spine first."*

So the first work item is not code. It is a decision, with the Architecture Spine amended
or a written finding that this use is already within AD-4.

## Rough shape

1. The AD question, settled in writing
2. A dismissal model, under the never-delete constraint
3. Per-event embeddings — vector column, pgvector migration, backfill, a production
   `EmbeddingPort` caller with AD-8 cost accounting
4. The clustering rule — cosine ≥0.7 across three dismissals
5. A mute model and its effect on composition or ranking
6. The endpoint, and `make client` regenerated
7. The swipe on the Pulse Card, and the prompt
8. The reversal surface — **depends on `unwired-surfaces/settings-sources-surface`**, whose
   3-state mute control may be the same control

## Constraints

- **Decide the AD question before writing a migration.** A vector column added on the way
  past is the spine being amended by accident.
- **No dark-pattern nag** — the mockup's own constraint, and the reason the prompt fires
  once rather than on every dismissal.
- **Calm copy**, and the prompt is **reversible from settings**.
- **AD-8 cost accounting** applies to every embed call, as it does to every LLM call.
- The generated client is the contract (AD-19).

## Not decomposed yet

This brief is the capture. Decomposition into work items is the planner's next pass, and
should start from the AD question rather than from the UI.
