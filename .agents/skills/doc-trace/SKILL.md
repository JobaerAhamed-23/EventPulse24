---
name: doc-trace
description: Build and check a traceability matrix across the PRD, Architecture Spine, and UX Design docs for this project (FR-N <-> AD-N/Capability <-> UX section <-> Epic), flagging coverage gaps and Amendment tags that didn't propagate everywhere they should. Only runs when explicitly invoked (e.g. "/doc-trace", "run the traceability check", "check doc alignment").
disable-model-invocation: true
---

# Doc Traceability Check

**Goal:** Confirm the PRD is still the actual source of truth — every requirement it defines is traceable into Architecture and UX, and every change made downstream (or upstream) is tagged consistently everywhere it touches. Produce a persisted matrix so this is checkable at a glance, not something anyone has to hold in their head.

## The Amendment convention (read this first — it's the rule, not just the report)

This project tags any change to an `FR-N`, an `AD-N`, or a UX section with a shared `Amendment A-N` ID, written inline at the point of change (e.g. `#### FR-5: Pulse Digest Composition (revised by Amendment A-2)` followed by a short `**Amendment A-2 (date):** ...` note). This convention already exists in `prd.md` and `DESIGN.md` — this skill does not invent it, it enforces it: **whenever a change gets an Amendment ID, that same ID must appear in every doc the change actually touches** (PRD, Architecture Spine, UX Design, and later Epics). Run this skill after any such edit to confirm that happened. If it finds an Amendment in one doc that's absent from another doc the change clearly affects, that's a defect to fix, not a stylistic nit.

## Step 1 — Locate the source docs

Resolve each from the project root (glob, then pick the most recently modified match if more than one exists):

- PRD: `_bmad-output/planning-artifacts/prds/*/prd.md`
- Architecture Spine: `_bmad-output/planning-artifacts/architecture/*/ARCHITECTURE-SPINE.md`
- UX Design: `_bmad-output/planning-artifacts/ux-designs/*/DESIGN.md`
- Epics/Stories (may not exist yet): glob broadly, e.g. `_bmad-output/planning-artifacts/epics*/**/*.md` and `_bmad-output/planning-artifacts/**/epic*.md` or `**/story*.md`. If nothing matches, that's expected pre-epics — proceed without one, don't treat it as an error.

If any of PRD/Architecture/UX is missing entirely, stop and tell the user which one and where you looked — don't guess at a matrix with a doc missing.

## Step 2 — Extract IDs from each doc

1. **PRD**: every `#### FR-N: Title` heading, plus any `(revised by Amendment A-N)` / `(added by Amendment A-N)` / `(lifted by Amendment A-N)` tag on that heading.
2. **Architecture Spine**: the `## Capability → Architecture Map` table — each row maps one or more `FR-N` (often a range like `FR-13–17`) to a module and a list of `AD-N` IDs. Expand ranges to individual FR-Ns. Also scan for any `Amendment A-N` mentions elsewhere in the doc (there may be none today — that's itself worth noting, see Step 4).
3. **UX Design**: section headings or inline notes tagged `(Amendment A-N ...)`. For each, use the section title/content to judge which FR(s) it implements (match against PRD feature titles and user journeys) — this is a judgment call, not a string match; note it as inferred if not explicit.
4. **Epics (if present)**: whatever ID scheme they use to reference `FR-N` — extract epic/story ID ↔ FR-N pairs.

## Step 3 — Build the matrix

One row per `FR-N` found in the PRD:

| FR-ID | Title | PRD Amendment(s) | Architecture (module + AD-N) | UX section(s) / Amendment | Epic/Story | Status |
|---|---|---|---|---|---|---|

Status rules:
- **FULL** — has an Architecture Capability-Map row AND (a UX section if the FR is user-facing, or explicitly none needed for a backend-only FR).
- **PARTIAL** — covered in some expected docs but not all.
- **MISSING** — a user-facing FR with no Architecture row and/or no UX section.
- **ORPHAN** — an `Amendment A-N` or `FR-N` reference found in Architecture or UX that does not exist in the PRD.

For Epic/Story, write `— not yet created` when no epics doc was found (do not treat this as MISSING/PARTIAL — epics are intentionally out of scope until that phase starts).

## Step 4 — Build the Amendment Ledger

Second table: one row per distinct `Amendment A-N` found anywhere across the three (or four) docs.

| Amendment | Found in | Consistent? |
|---|---|---|

`Consistent?` = No with a one-line reason when an Amendment appears in one doc but is plausibly relevant to another doc that doesn't mention it (e.g. "Amendment A-8 appears in DESIGN.md but prd.md has no matching tag on the FR it changes").

## Step 5 — Write the persisted record

- Ensure `_bmad-output/planning-artifacts/traceability/` exists.
- Write `_bmad-output/planning-artifacts/traceability/TRACEABILITY.md`, overwriting any previous version: a dated header (`Generated: YYYY-MM-DD`), the sources scanned (with their resolved paths), the FR matrix, the Amendment Ledger, and a short **Findings** list of every non-FULL / non-Consistent row.
- Append one line to `_bmad-output/planning-artifacts/traceability/.memlog.md` (create it with a one-line header if it doesn't exist yet): `- YYYY-MM-DD: scanned <docs>; N drift item(s): <ids, or "none">`.

## Step 6 — Report to the user

In the chat, give a short summary (not the whole matrix): total FR count, counts by status, the specific ORPHAN/MISSING rows, the specific inconsistent Amendments, and the path to `TRACEABILITY.md` for the full detail. If everything is FULL/Consistent, say so plainly — don't manufacture findings to seem thorough.
