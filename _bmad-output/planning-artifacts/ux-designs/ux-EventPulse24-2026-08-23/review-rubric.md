# Spine Pair Review — EventPulse24

_Rubric walker, run inline at Amendment A-22 Finalize (2026-09-08). **Scope: the A-22 delta only** — the `/saved` route, the five new components, and the spine sections A-22 edited. The user opted out of the full-pair subagent review; the pre-A-22 spine is not re-audited here. Three findings were fixed during the run and are recorded as resolved._

## Overall verdict

The A-22 delta is a clean, self-consistent addition: all 22 `{token}` references in the new DESIGN.md section resolve, all five new components carry both a visual and a behavioral spec, and `/saved` has full four-state coverage plus a Key Flow. Three mechanical misses were found and fixed in-run — one unresolved spacing token and two components that had a visual spec with no behavioral counterpart. The amendment also closed five pre-existing spine defects it uncovered, the most consequential being DESIGN.md frontmatter that had been unparseable YAML since Amendment A-10.

## 1. Flow coverage — adequate

Checked: does the requirement A-22 realizes have a Key Flow with a named protagonist, numbered steps, a climax beat, and failure paths.

- PRD FR-49 → **Flow 7 — Filing a save into a collection.** Named protagonist (Maya, Pro subscriber, eleven events in `Unsorted`), 5 numbered steps, an explicit climax beat, and 4 failure modes (mistaken delete, duplicate name, Free-tier deep link, failed reorder write).

### Findings

- **low** FR-49 realizes no PRD User Journey — the FR's own realizes-clause reads "the value prop of Pro" rather than naming a UJ, so Flow 7 is the first Key Flow in the spine with no upstream UJ to inherit its protagonist and beats from (`EXPERIENCE.md` §8 Flow 7). *Fix:* none required for MVP; if the PRD later adds a UJ for archival behavior, reconcile Flow 7's steps against it verbatim rather than rewriting them.

## 2. Token completeness — strong

Checked: every `{path.to.token}` reference in the new §Components → Saved surface section, against the DESIGN.md frontmatter and the scale definitions in §Colors / §Typography / §Layout & Spacing / §Shapes.

- 22 distinct token references; **all resolve.** No new colour tokens, no new CSS variables, no new spacing or radius tokens were introduced by A-22 — the surface is built entirely from the existing palette.
- `--signal-error` in the mockup is a declared palette value used for the delete affordance's label, consistent with §Color usage rules reserving `color.signal.error` for destructive actions.

### Findings

- **medium · RESOLVED IN-RUN** `{spacing.10}` was referenced for the vertical rhythm between collection sections, but the spacing scale defines `0 · 1 · 2 · 3 · 4 · 6 · 8 · 12 · 16 · 20 · 30` — there is no `spacing.10` (`DESIGN.md` §Components → Saved surface). Downstream impact would have been an engineer inventing a 40px value outside the scale. *Fix applied:* changed to `{spacing.12}` (48px), with the rationale stated inline (collections are user-owned groupings and need more separation than Browse's attention-tier heads at `{spacing.6}`), and `mockups/saved-collections-desktop.html` re-aligned from 40px to 48px so spine and mockup agree.

## 3. Component coverage — strong

Checked: every component A-22 names has a row in DESIGN.md §Components (visual spec) **and** a row in EXPERIENCE.md §4 Component Patterns (behavioral spec), each carrying real rules.

| Component | DESIGN.md visual | EXPERIENCE.md behavioral |
|---|---|---|
| `component.surface.saved` | ✓ | ✓ `Component.Surface.Saved` |
| `component.collection.header` | ✓ | ✓ `Component.Collection.Header` |
| `component.control.reorder` | ✓ | ✓ `Component.Control.Reorder` |
| `component.menu.card.collection` | ✓ | ✓ `Component.Menu.Card.Collection` |
| `component.emptystate.locked` | ✓ | ✓ `Component.EmptyState.Locked` |

### Findings

- **high · RESOLVED IN-RUN** `component.menu.card.collection` and `component.emptystate.locked` each had a DESIGN.md visual spec but **no EXPERIENCE.md Component Patterns row** — their behavior was buried inside `Component.Collection.Header` and §5 Empty Patterns respectively. A downstream consumer extracting components would have found a visual spec with no interaction contract, no keyboard model, and no accessibility floor. *Fix applied:* both promoted to full §4 entries. Writing them surfaced four decisions that had been implicit: the filing menu carries **no** "Remove from saved" row (un-saving stays the card's own toggle, so a destructive action is not duplicated into a menu); filing is one card at a time with no bulk-move mode; the locked placeholder rows are `aria-hidden` and inert rather than `disabled`, because a disabled control that does nothing on tap teaches users the product is broken; and **collections survive a Pro→Free downgrade** server-side, reappearing intact on re-subscribe.

## 4. State coverage — strong

Checked: `/saved` against the four canonical states plus the states that apply to this surface specifically.

- **default / empty / loading / error** — all four present in the §2 state-coverage table.
- **Empty variants** — three distinct patterns in §5, correctly separated: empty surface, empty single collection (header keeps its full control cluster, which is exactly when a user wants to delete it), and the Free-tier locked zone.
- **Focus** — collection controls are in natural `Tab` order; `Component.Control.Reorder` specifies focus retention across a DOM move, which is the property that makes button-based reorder usable past two collections.
- **Offline** — covered by the existing global Offline Patterns rather than a route-specific entry.

### Findings

- **low** The queued-actions contract in §5 Offline Patterns keys entries on `userId + eventId + actionType`, which fits save / dismiss / less-like-this but not A-22's three new write types — rename, reorder, and file-into-collection — none of which are event-scoped (`EXPERIENCE.md` §5 Offline Patterns). *Fix:* not blocking for MVP, since `/saved` is a read surface when offline; before implementation, either extend the queue key to admit collection-scoped actions or state explicitly that collection mutations require connectivity and fail with the inline "Couldn't save that order. Try again." message Flow 7 already specifies.

## 5. Visual reference coverage — strong

- `mockups/saved-collections-desktop.html` is linked inline from `Component.Surface.Saved` and carries a named row (21) in the Surface Coverage Map describing what it illustrates.
- "Spines win on conflict with any mockup" is stated once, in the Surface Coverage Map preamble.
- Mobile `/saved` is logged as a pending coverage gap rather than left silent.
- The mockup's states appendix is fenced in both an HTML comment and visible copy as a demonstration block, not page chrome, so it cannot be mistaken for a section to build.

### Findings

- **low** No orphans in `mockups/` after A-22: the Surface Coverage Map previously omitted 15 files that exist, and now lists them. *Fix applied during A-22.*

## Mechanical notes

- **Frontmatter.** Both spines now parse as YAML. `DESIGN.md` had been **broken since Amendment A-10** — its double-quoted `updated_note` scalar contained unescaped inner double quotes (`aria-current="page"`, `type="search"`), confirmed broken at git HEAD and therefore pre-dating A-22. Converted to a folded block scalar (`>-`) so inner quotes can never break the token contract again. `EXPERIENCE.md` parsed cleanly and was left in its quoted form.
- **Cross-reference resolution.** `/settings/plan` was referenced in **five** places across both spines but has never existed in the §2 IA (which lists `/settings/reminders`, `/settings/quiet-hours`, `/settings/sources`, `/settings/privacy`). All five now read `/settings` → Plan, matching the section-nav tab `settings-desktop.html` actually renders.
- **Name consistency.** Surface Coverage Map row 9 cited `empty-pulse-digest-desktop.html`; the real filename is `pulse-digest-empty-state-desktop.html`. Corrected. Directory counts were stale since the A-8 batch (claimed 32 files, actual 42). Recounted.
- **Duplicate entry.** `component.input.search.browse` appeared twice in DESIGN.md §Components — two near-identical A-11 paragraphs, one placing the input "below the hero" and one "above the first day divider". The A-12-correct "below the hero" version survives; the duplicate is removed.
- **Route total.** §2 IA now reads 15 routes and the count line matches the table.
- **Mockup integrity.** `saved-collections-desktop.html`: HTML tag balance verified programmatically (no unclosed or mismatched elements), CSS brace balance 0, the `a { text-decoration: none; }` sidenav prerequisite present. The one class used without a CSS rule, `brand-text`, is an unstyled hook in every canonical A-8 mockup (`browse-desktop.html`, `conflicts-desktop.html`, `timeline-desktop.html`) — consistent, not a regression.
- **Not checked.** Categories 6–8 (bloat, inheritance discipline, shape fit) and the pre-A-22 spine were out of scope for this run.

---

# Amendment A-23 — Event State Change

_Rubric walker Pass 1, run inline 2026-09-08. **Scope: the A-23 delta only.**_

## Overall verdict

Clean. All 13 `{token}` references in the new DESIGN.md material resolve, both new components carry a visual and a behavioral spec, all four FR-54 states appear in the §5 pattern table, and the mockup is linked inline from both component entries. No new findings — the three defects A-23 addressed were pre-existing ones in the mockup it retired, not misses in the new work. One A-22 defect was found and fixed while reading §Colors for this amendment.

## 1. Flow coverage — strong

- PRD FR-54 → **Flow 8 — A saved event is cancelled.** Named protagonist, 5 numbered steps, an explicit climax beat, 4 failure modes (overlapping personal event, three simultaneous changes, source re-listing, user never opens the digest).

## 2. Token completeness — strong

- 13 distinct references across the generalised badge, the new banner and the new text-decoration entry; **all resolve.** No new colour tokens, no new CSS variables. `type.decoration.superseded` is a new *token*, defined in the §Typography → Text decoration section that introduces it.
- Mockup hex audit: 16 values, every one drawn from the existing palette.

### Findings

- **medium · RESOLVED IN-RUN (Amendment A-22 regression)** `mockups/saved-collections-desktop.html` declared `--signal-error: #C4614A`, but `color.signal.error` is `#C66A5C` in dark mode — confirmed against both §Colors and `pulse-digest-desktop.html`'s own declaration. A-22's memlog entry had claimed no new hex values were introduced, which was false. *Fix applied:* corrected to `#C66A5C` and the destructive-hover `rgba()` re-derived from it. The token's *use* remains sanctioned — §Colors reserves it for destructive actions, and deleting a collection qualifies.

## 3. Component coverage — strong

| Component | DESIGN.md visual | EXPERIENCE.md behavioral |
|---|---|---|
| `component.badge.eventstate` | ✓ (generalises A-15) | ✓ `Component.Badge.EventState` |
| `component.banner.statechange` | ✓ | ✓ `Component.Banner.StateChange` |
| `type.decoration.superseded` | ✓ (§Typography) | n/a — a type token, not a component |

- The A-15 `Component.Badge.SoldOut` entry was retained rather than deleted, re-headed as generalised-by-A-23, and now reads as the `sold_out` variant's specification. This keeps every inbound reference to it valid.

## 4. State coverage — strong

- All four FR-54 states present in the §5 State-Change Patterns table, each with a banner headline, card treatment, reminder consequence and card lifecycle.
- The `cancelled` lifecycle resolves a live contradiction between FR-54 (badge required) and FR-55 (event removed from digest) via deferred removal.
- State reversion is explicitly ruled out: a re-listed event is ingested with a new id.

## 5. Visual reference coverage — strong

- `mockups/event-state-change-desktop.html` linked inline from both new component entries and carrying coverage-map row 22.
- `mockups/superseded/` introduced with a README tabulating why its one occupant is wrong. This is deliberately **not** `light-archive/`, which holds light-mode variants of current surfaces — filing a superseded dark-mode mockup there would have made the directory name misdescribe its contents.
- Mockup integrity: HTML tag balance clean, CSS brace balance 0, link reset present, **zero `disabled` attributes** (all five textual occurrences are comments stating that `disabled` is forbidden), **zero uses of `signal.success`** beyond an annotated palette declaration.

## Mechanical notes

- FR-54 removed from the coverage map's unmocked-FR queue; the queue preamble now records that A-23 closed it.
- Directory counts re-stated: 36 in `mockups/`, 6 in `mockups/mobile/`, 5 in `light-archive/` (excluded), 1 in `superseded/` (excluded).
- The one remaining body reference to `sold-out-card-state-desktop.html` is coverage-map row 22, which names it as superseded on purpose.
- **Not checked.** Categories 6–8 and the pre-A-23 spine remain out of scope, consistent with the A-22 run.
