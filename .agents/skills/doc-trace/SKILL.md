---
name: doc-trace
description: Build and check a traceability matrix across the PRD, Architecture Spine, and UX Design/Experience docs for this project (FR-N <-> AD-N/Capability, and FR-N <-> named design element), flagging coverage gaps and Amendment tags that didn't propagate everywhere they should. Only runs when explicitly invoked (e.g. "/doc-trace", "run the traceability check", "check doc alignment").
disable-model-invocation: true
---

# Doc Traceability Check

**Goal:** Confirm the PRD is still the actual source of truth — every requirement it defines is traceable into Architecture and into Design, and every change made downstream (or upstream) is tagged consistently everywhere it touches. Produce a persisted matrix so this is checkable at a glance, not something anyone has to hold in their head.

The report has **three separate alignment sections** (PRD↔Design, PRD↔Architecture, then PRD↔Implementation) — never merge them into one combined table. Each section runs its own independent FR-by-FR pass with its own evidence rules, because "does this FR have a UI design" and "does this FR have an architectural home" are different questions with different answers for the same FR (e.g. a backend-only FR is N/A for Design but must be FULL for Architecture; a pure-narrative FR could be the reverse).

## The Amendment convention (read this first — it's the rule, not just the report)

This project tags any change to an `FR-N`, an `AD-N`, or a UX section with a shared `Amendment A-N` ID, written inline at the point of change (e.g. `#### FR-5: Pulse Digest Composition (revised by Amendment A-2)` followed by a short `**Amendment A-2 (date):** ...` note). This convention already exists in `prd.md`, `DESIGN.md`, and `EXPERIENCE.md` — this skill does not invent it, it enforces it: **whenever a change gets an Amendment ID, that same ID must appear in every doc the change actually touches**. Run this skill after any such edit to confirm that happened. If it finds an Amendment in one doc that's absent from another doc the change clearly affects, that's a defect to fix, not a stylistic nit.

## Step 1 — Locate the source docs

Resolve each from the project root (glob, then pick the most recently modified match if more than one exists):

- PRD: `_bmad-output/planning-artifacts/prds/*/prd.md`
- Architecture Spine: `_bmad-output/planning-artifacts/architecture/*/ARCHITECTURE-SPINE.md`
- UX Design (component/visual system): `_bmad-output/planning-artifacts/ux-designs/*/DESIGN.md`
- UX Experience (flows/journeys): `_bmad-output/planning-artifacts/ux-designs/*/EXPERIENCE.md`
- UX Mockups (individual screens): `_bmad-output/planning-artifacts/ux-designs/*/mockups/**/*.html` — **read each mockup's own header comment**, not just its filename. A mockup's header comment is the strongest evidence a design exists for an FR (e.g. `<!-- FR-59 / Amendment A-4. Tapped from "Report this event" link... -->`). Do not skip this and rely on DESIGN.md/EXPERIENCE.md prose alone — a mockup can be the *only* place an FR is actually designed, and DESIGN.md/EXPERIENCE.md's own summary tables of "which mockups exist" have been found stale before (they can undercount the real files in the directory). Always cross-check the mockup count they claim against `ls` of the actual directory.
- Epics/Stories (may not exist yet): glob broadly, e.g. `_bmad-output/planning-artifacts/epics*/**/*.md` and `_bmad-output/planning-artifacts/**/epic*.md` or `**/story*.md`. If nothing matches, that's expected pre-epics — proceed without one, don't treat it as an error.

If the PRD or Architecture Spine is missing entirely, stop and tell the user which one and where you looked — don't guess at a matrix with a required doc missing. If DESIGN.md, EXPERIENCE.md, or the mockups directory is missing, note it and mark every FR's Design status as `MISSING (no design docs found)` rather than halting — Design coverage absence is itself a valid, reportable finding.

## Step 2 — Extract every FR from the PRD

Every `#### FR-N: Title` heading, plus any `(revised by Amendment A-N)` / `(added by Amendment A-N)` / `(lifted by Amendment A-N)` tag on that heading. This list must be exhaustive — never group, sample, or silently skip an FR, including Pro-tier, internal-only, and backend-only ones. Note each FR's MVP/Phase status (MVP vs. deferred) since deferred FRs are reported separately and not scored.

## Step 3 — Section A: PRD ↔ Design Alignment

For **every MVP FR**, answer one question: *does a design element exist for this requirement, described in enough detail that an engineer could build the UI from it?* Check evidence in this order of strength:

1. **A mockup file self-tagged with this FR-N** in its own header comment (or, failing that, a filename that unambiguously matches). Strongest evidence — this alone is sufficient for **FULL**.
2. **A named, explicit section/component/flow in DESIGN.md or EXPERIENCE.md** that names the FR-N directly (e.g. `Component.Badge.SoldOut ... "Closes PRD FR-53 / FR-54"`). Sufficient for **FULL** on its own even with no matching mockup.
3. **Only inferable via adjacency** — a plausible-but-unnamed component, or coverage guessed from a neighboring feature's UI, with no direct FR tag anywhere. This is **PARTIAL (inferred only)** — never FULL. List it as an open gap.
4. **Nothing found** for a requirement that describes a user-facing flow, screen, or interaction. This is **MISSING** — flag it plainly; don't soften it into PARTIAL.
5. **The FR has no UI surface by nature** — a backend pipeline, an internal admin tool, a data/timing policy, a notification-channel-only mechanism with no in-app screen, etc. This is **N/A (no design needed)** — state briefly why (e.g. "backend caching policy, no user-facing surface").

Marketing/pricing copy that *sells* a feature (e.g. a pricing-page bullet) does not, by itself, count as design for that feature — it's advertising the entitlement, not designing the screen that fulfills it. Check for an actual interaction/screen separately from the sales copy.

Build the table:

| FR-ID | Title | Design element found (source: mockup / DESIGN.md / EXPERIENCE.md) | Status | Note |
|---|---|---|---|---|

Status is one of: `FULL`, `PARTIAL (inferred only)`, `MISSING`, `N/A (no design needed)`.

## Step 4 — Section B: PRD ↔ Architecture Alignment

For **every MVP FR**, answer: *does the Architecture Spine's `Capability → Architecture Map` (or equivalent) have an explicit row naming this FR (or a range covering it), with a module and at least one `AD-N`?*

- **FULL** — an explicit Capability-Map row covers this exact FR (ranges like `FR-13–17` count as covering each FR in the range).
- **PARTIAL** — the FR is covered by inference/adjacency to a module's general responsibility, but no row names it directly.
- **MISSING** — no row, no module, nothing — including the specific case of an FR the PRD itself says is in MVP scope (check Amendment tags like "lifted to MVP") but that Architecture still treats as absent.
- **N/A** — genuinely rare for Architecture (almost every FR needs *some* system to implement it); use only for a pure-narrative/vision FR with no independent build surface of its own (state why).

Build the table:

| FR-ID | Title | Architecture (module · AD-N) | Status | Note |
|---|---|---|---|---|

## Step 4b — Section C: PRD ↔ Implementation

For **every MVP FR**, answer: *can a user reach this, in the running product, today?*

**This section exists because Sections A and B cannot see the difference between designed
and built.** FR-18 carried `FULL` in both while its delete control did not exist — scored
on a mockup that draws a danger zone nobody implemented. FR-20, FR-24, FR-49 and FR-50
carried `FULL` on the same terms while four endpoints had no caller at all. A morning's
manual audit found eight such gaps across twelve intents; nothing in the matrix had ever
asked the question.

**Evidence rules — and they are deliberately harsher than Section A's.**

- **FULL** — a user-reachable path exists in the code: a route, a mounted component, or a
  control on a surface that renders. Cite the file and line. A mockup is Section A's
  evidence and **must never be reused here**; an architecture row is Section B's.
- **PARTIAL** — the machinery exists and the surface is incomplete: an endpoint with a
  caller that only covers part of the FR, or a control reachable from one surface where
  the FR implies several.
- **MISSING** — no user-reachable path. **Including the case where the backend is complete
  and tested**: a preference the product stores, audits and honours but cannot be set is
  MISSING here, however green its tests are.
- **N/A** — no user surface by nature (an internal policy, a retention rule).
- **UNASSESSED** — not yet checked against the code. **Honest and preferred over a guessed
  FULL.** Say so in the row rather than inferring from Section A.

**Two traps, both of which have already caught this project:**

1. **A called endpoint is not a reachable feature.** `SavedEventsSection` called
   `GET /api/personal/saved-events` from a component nothing rendered, and
   `PersonalEventsPanel`'s list branch was the same shape — tested, green, unreachable.
   `frontend/tests/endpoint-coverage.test.ts` cannot see this and says so in its own
   docstring. **Check the mount, not just the call.**
2. **A passing test is not a reachable feature**, for the same reason: both dead surfaces
   had full test coverage, which is exactly why nobody noticed.

## Step 5 — Build the Amendment Ledger

Cross-cutting across all docs (PRD, Architecture, Design, Experience, mockups). One row per distinct `Amendment A-N` found anywhere:

| Amendment | Found in | Consistent? |
|---|---|---|

`Consistent?` = No with a one-line reason when an Amendment appears in one doc but is plausibly relevant to another doc that doesn't mention it (e.g. "Amendment A-8 appears in EXPERIENCE.md but prd.md has no matching tag on the FR it changes").

## Step 6 — Write the persisted record

- Ensure `_bmad-output/planning-artifacts/traceability/` exists.
- Write `_bmad-output/planning-artifacts/traceability/TRACEABILITY.md`, overwriting any previous version, in this order:
  1. Dated header (`Generated: YYYY-MM-DD`) + sources scanned (resolved paths, including EXPERIENCE.md and the mockups directory with its file count).
  2. **Section A: PRD ↔ Design Alignment** (table from Step 3) + a short list of every non-FULL/non-N/A row as an open gap.
  3. **Section B: PRD ↔ Architecture Alignment** (table from Step 4) + a short list of every non-FULL/non-N/A row as an open gap.
  3b. **Section C: PRD ↔ Implementation** (table from Step 4b) + a short list of every non-FULL/non-N/A row as an open gap. Each row cites running code, never a mockup.
  4. Amendment Ledger (Step 5).
  5. Deferred/out-of-MVP FRs, listed but not scored.
  6. Epic/Story coverage (`— not yet created` when no epics doc exists — don't treat that as MISSING/PARTIAL).
- Append one line to `_bmad-output/planning-artifacts/traceability/.memlog.md` (create it with a one-line header if it doesn't exist yet): `- YYYY-MM-DD: scanned <docs>; Design N missing/M partial; Architecture N missing/M partial; Implementation N missing/M partial/U unassessed; K inconsistent amendment(s)`.

## Step 7 — Report to the user

In the chat, give a short summary (not the whole matrix): total FR count, Design section counts by status, Architecture section counts by status, Implementation section counts by status, the specific MISSING rows in each section, the specific inconsistent Amendments, and the path to `TRACEABILITY.md` for the full detail. If everything is FULL/N/A/Consistent, say so plainly — don't manufacture findings to seem thorough.
