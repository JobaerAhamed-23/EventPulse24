# Mockup Drift Audit — Amendment A-24 (2026-09-08)

Full sweep of `mockups/` (37 desktop + 6 mobile = 43 files) against `DESIGN.md` and
`EXPERIENCE.md` at `status: final`, `updated: 2026-09-08` (post-A-23).

Method: mechanical (grep/count) over every file, then each hit read in context to
separate real drift from sanctioned variation. Sanctioned-variation rules applied:
`Component.Sidenav.App` five-route onboarding variant, `Component.Topbar.PreAuth`
no-sidenav rule for the 8 pre-auth routes, and the sheet/modal exemptions.

**Spines win on conflict** — where a mockup diverges, the mockup is wrong, *except*
where §D below records the spine itself as the likely error.

---

## §A — Unambiguous drift (mockup is wrong, spine is right)

### A-1. Missing `/saved` route — 16 files
`Component.Sidenav.App` states the **seven-route variant is canonical going forward**
and that the six-route variant "is superseded on every authed surface; it survives
only in mockups not yet migrated to A-22." These 16 authed surfaces still render six:

| File | nav | needs |
|---|---|---|
| `account-delete-confirmation-modal-desktop.html` | 6 | + Saved |
| `browse-desktop.html` | 6 | + Saved |
| `browse-desktop-filtered.html` | 6 | + Saved |
| `browse-desktop-empty.html` | 6 | + Saved |
| `conflicts-desktop.html` | 6 | + Saved |
| `event-detail-desktop.html` | 6 | + Saved |
| `export-request-modal-desktop.html` | 6 | + Saved |
| `personal-event-create-desktop.html` | 6 | + Saved |
| `personal-event-edit-desktop.html` | 6 | + Saved |
| `pulse-digest-desktop.html` | 6 | + Saved |
| `pulse-digest-empty-state-desktop.html` | 6 | + Saved |
| `reminder-picker-desktop.html` | 6 | + Saved |
| `settings-desktop.html` | 6 | + Saved |
| `settings-quiet-hours-pro-desktop.html` | 6 | + Saved |
| `settings-sources-desktop.html` | 6 | + Saved |
| `timeline-desktop.html` | 6 | + Saved |

Only `saved-collections-desktop.html` and `event-state-change-desktop.html` (A-22/A-23)
carry the canonical seven. Fix is mechanical: insert the bookmark-glyph `nav-item`
between Browse and Conflicts, byte-identical to the A-22 implementation.

Note the four onboarding files (`onboarding-step1/2/3-desktop.html`,
`onboarding-skip-all-state-desktop.html`) render **five** routes and are **correct** —
the five-route variant is explicitly sanctioned for the onboarding funnel only.

### A-2. Untokenized violet + stripe-exclusivity breach on digest Save buttons — 2 files
`pulse-digest-desktop.html` and `onboarding-skip-all-state-desktop.html` render the
card Save affordance as a category-tinted ghost button:

- `.ghostbtn.tint-violet { color: #B59CE8; ... }` — **`#B59CE8` is not in the palette
  in either mode.** It is a fourth chromatic hue in a system whose §Color usage rules
  open with "`color.accent.terracotta` is the only chromatic accent."
- `.ghostbtn.tint-amber { color: var(--accent-amber); ... }` — uses a real token, but
  §Color usage rules reserve `color.accent.amber` "exclusively for category stripes on
  `Card.PulseDigest`. They are not used for buttons, icons, or interactive surfaces."

Note on the fix: `Component.Button.Save.Inline` (A-10) is scoped to **Browse** cards
("the quiet Save affordance on Browse cards"), so the digest card's own action row is a
different vocabulary and was *not* converted to it. The correct minimal fix is simply to
strip the unsanctioned chromatic tints and let the buttons render as the plain ink-only
`.ghostbtn` the same files already define.

### A-3. Decorative use of reserved tokens on category icons — 1 file
`pulse-digest-desktop.html` `.saved-row .cat-icon` tints:
- `tint-leaf` uses `--signal-success`, but signal colors "appear only at the moment of
  state change, never as decoration."
- `tint-book` uses `--accent-slate`, reserved exclusively for category stripes.
- `tint-pottery` uses `--warm-personal`, reserved for the Personal-event tone.

All three are decorative chips, not the sanctioned uses.

### A-4. Off-palette hover — 1 file
`signup-desktop.html:150` — `.field-error .text a:hover { color: #E8B97A; }`.
`#E8B97A` is in no palette. Nearest sanctioned value is `color.signal.warn` `#D8A86A`,
which is the token A-20 specified for this exact field-error treatment.

### A-5. Missing link reset — 9 files
`Component.Sidenav.App` locks `a { color: inherit; text-decoration: none; }` as a
"global reset prerequisite" after a real reported bug. These files carry anchors with
no reset, so browser-default underlines render:

`city-page-desktop.html` (21 anchors) · `public-event-page-desktop.html` (11) ·
`ranking-algorithm-transparency-desktop.html` (10) · `share-link-desktop.html` (5) ·
`pricing-page-desktop.html` (2) · `pro-upgrade-cta-desktop.html` (1) ·
`mobile/pulse-digest-mobile.html` (4) · `mobile/pulse-preview-mobile.html` (4) ·
`mobile/event-detail-mobile.html` (1)

### A-6. Mobile navigation has almost no coverage — 5 of 6 files
`Component.BottomTab` is the mobile nav for authed surfaces; `Component.BottomTab.MoreMenu`
(A-10, extended A-22) is the overflow affordance carrying Browse + Saved.

- Only `mobile/timeline-mobile.html` renders a bottom-tab at all.
- **No mobile file renders the `More` slot** — `Component.BottomTab.MoreMenu` has *zero*
  mockup coverage despite being specified twice (A-10, A-22).
- `mobile/pulse-digest-mobile.html` and `mobile/event-detail-mobile.html` are authed
  surfaces with no bottom-tab.

`conflict-prompt-mobile.html` (sheet), `pulse-preview-mobile.html` (pre-auth) and
`onboarding-step1-mobile.html` (onboarding funnel) correctly have none.

---

## §B — Verified clean (no action)

- **The A-8 shell is internally consistent.** All 22 shell files agree exactly:
  `--sidenav-w: 240px`, sidenav brand image 24×24, `<nav class="topbar">`. No per-file
  shell drift exists.
- **Pre-auth topbar-quiet is satisfied in all 8 pre-auth files.** Every "How it works /
  Log in / Sign up" string sits in a hero CTA cluster or a page footer — both sanctioned
  placements. No pre-auth file renders a topbar action cluster. `pulse-preview-desktop.html`
  retains a `.topright` CSS rule but **the class appears nowhere in its markup** — a dead
  rule, not a rendered violation.
- **`disabled` on `browse-desktop.html`'s quota-capped Save is correct**, not an A-23
  violation: `Component.Button.Save.Inline` explicitly specifies the capped state as
  "still visible ... but disabled" with a `title` tooltip. A-23's no-`disabled` rule is
  scoped to the sold-out Detail CTA.
- No file carries `.frame`-only legacy chrome that still renders; `event-detail-desktop.html`
  and others retain a `.container` rule but inside the A-8 shell.

---

## §C — Spine bookkeeping now stale (documentation, not pixels)

1. **`Component.Topbar.PreAuth` → "Migration status (2026-09-06)"** says "The six mockups
   remain in their prior state (some carry legacy `How it works` / `Sign in` / `Sign up`
   buttons in the topbar that violate this rule). Migration ... deferred to the next build
   batch." Per §B this is **no longer true** — the paragraph describes a backlog that is
   already clear. It should be retired or restated as satisfied.
2. **`Component.Sidenav.App` → "Global reset prerequisite"** says the sidenav "renders
   five or six `<a>` route items." A-22 made it seven.
3. **Surface Coverage Map** lists "Mobile bottom-tab nav variants beyond Timeline" as a
   pre-launch gap but does not record that the `More` slot is unmocked anywhere (§A-6).

---

## §D — Spine-vs-mockup conflicts where the spine looks like the error

These are the cases where "spines win" would mean changing 22 files to match one line,
and the weight of evidence says the line is wrong. **Decisions, not fixes.**

1. **Sidenav brand mark size.** `Component.Sidenav.App` specifies a **28×28** logo. All
   **22** shell mockups render **24×24**, byte-identically. Either the spine changes to
   24 or 22 files change to 28.
2. **Sidenav responsive width.** The spine specifies "220px on `md`, 240px on `lg+`."
   **No mockup declares the 220px `md` variant** — every one ships a single flat
   `--sidenav-w: 240px`. Either the spine drops the `md` step or 22 files gain a
   breakpoint.
3. **`<nav class="topbar">` wrapping brand only.** All 22 shell files wrap the
   brand-only topbar in a `<nav>` landmark, but the spine calls the topbar the
   "identity zone" carrying no navigation (topbar-quiet rule, ASSUM-11). A `nav`
   landmark containing zero navigation is announced as a navigation region to screen
   readers — an accessibility smell against §7. `<header>` is the fitting element.

---

## §E — Internal spine tension (noted, no mockup implication)

`Component.Button.Save.Inline` specifies a **disabled** control for the quota-capped
Save, while A-22's `Component.EmptyState.Locked` rationale argues the opposite — "a
disabled control that does nothing on tap teaches the user the product is broken,
whereas an inert illustration behind a stated gate teaches them what the tier buys."
Both are locked spine text about the same tier-gate problem. Worth reconciling before
engineering meets the contradiction.


---

## §F — Resolution log (Amendment A-24, 2026-09-08)

Scope: **desktop only** — Jobaer deferred mobile to its own amendment.

| Finding | Status | What was done |
|---|---|---|
| A-1 six-route sidenav (16 files) | **Fixed** | Saved route inserted between Browse and Conflicts in each file's own formatting (12 multi-line, 4 single-line). Verified: 18 files now at 7 routes in exact order, 4 onboarding files correctly still at 5. |
| A-2 violet + amber ghost tints (2 files) | **Fixed** | `.ghostbtn.tint-violet` / `.tint-amber` rule pairs deleted and classes stripped from markup; buttons render as the plain ink-only `.ghostbtn`. |
| A-3 decorative use of reserved tokens (1 file) | **Fixed** | Three `.saved-row .cat-icon` tint rules collapsed into one ink-only rule (`surface.inset` fill, `ink.muted` glyph). The glyph and title already carried the category, so no information was lost. |
| A-4 off-palette `#E8B97A` (1 file) | **Fixed** | → `var(--ink-primary)`, matching the ink-lift hover convention used throughout. Deliberately *not* sanctioned as a second lightened-hover hex alongside `#FF7E5E`. |
| A-5 missing anchor reset | **Fixed (5 desktop files)** | Reset added at lowest specificity after `html, body`. The 3 mobile files deferred with the rest of mobile. |
| A-6 mobile nav coverage | **Deferred** | Out of scope by decision. Recorded in the Surface Coverage Map as the largest remaining gap: `Component.BottomTab.MoreMenu` is rendered in no mockup at all. |
| C-1 stale pre-auth migration note | **Fixed** | Rewritten as CLOSED, with the reason it was wrong and a note that a migration-status claim needs re-verification before being repeated forward. |
| C-2 "five or six" route items | **Fixed** | → "five, six, or seven". |
| C-3 coverage map | **Fixed** | Counts corrected to 41 live / 4 light-archive / 3 superseded; ranking-transparency row removed from the unlisted list; full A-24 sweep table added. |
| D-1 brand 28×28 vs 24×24 | **Spine yielded** | Both spines now say 24×24, with the reasoning recorded. |
| D-2 220px `md` rail step | **Spine yielded** | `layout.sidenav.app.width.tablet` / `.desktop` collapsed into one `layout.sidenav.app.width` (240px). |
| D-3 `<nav class="topbar">` | **Fixed (30 desktop files)** | → `<header class="topbar">`. Applied first to the 22 shell files, then extended to the 8 remaining desktop files that carry a brand-only topbar (the 6 pre-auth routes, `pricing-page-desktop.html` and `less-like-this-mute-prompt-desktop.html`) so the new Do's-and-Dont's row holds across every desktop mockup rather than only the authed ones. Zero visual diff; `.topbar` selector unchanged. The 5 mobile files that carry a topbar are deferred with the rest of mobile. |
| E internal spine tension | **Open** | `Component.Button.Save.Inline` specifies a disabled tier-gated control; `Component.EmptyState.Locked` argues against exactly that. Both remain locked spine text. Not a mockup defect — left for a deliberate reconciliation. |

### Found during the sweep, not in the original audit

| Finding | Status | What was done |
|---|---|---|
| **Superseded brand asset in 39 references across 19 files** | **Fixed** | Two logo assets exist — `docs/EventPulse24-logo.png` (1282×1288) and `docs/EventPulse24-latest-logo.png` (1254×1254, copied into `mockups/`). 32 visible brand marks + 7 favicons pointed at the *superseded* one through a five-level `../../../../../docs/` path, so roughly half the mockups rendered the old logo, and 16 files rendered the old logo in the topbar beside the current one in the sidenav rail. All 39 repointed at the local canonical copy. This was invisible to the first pass because each shell file carries *two* brand images and the initial audit only inspected the sidenav one. |
| **`ranking-algorithm-transparency-desktop.html` was already self-deprecated** | **Retired** | The file carried its own `DEPRECATED 2026-09-06` banner stating its content had been inlined into Settings → Privacy, yet it was still sitting in the active `mockups/` root and still being counted as live coverage. Retired to `superseded/` with a full defect row. |
| **A dark-mode file misfiled in `light-archive/`** | **Refiled** | `light-archive/ranking-algorithm-transparency-desktop.html` was the pre-deprecation copy (254 lines vs 262) and is dark-mode (`data-theme="dark"`, `#0A0A0B`) — the same category error A-23 avoided when it declined to file the sold-out mockup there. Moved to `superseded/…predeprecation.html`. The remaining four `light-archive/` files were each verified genuinely light-mode (`#FAF8F4`, no `data-theme`), so the directory name now describes its contents. |
| **Orphan `</div>` in `onboarding-skip-all-state-desktop.html`** | **Fixed** | A stray closing tag after `</main>` left the document at div depth −1. Confirmed pre-existing at git HEAD, not introduced by this sweep. |

### Verification after all changes

- 41 mockups: **no off-palette hex** (excluding `href` anchors), **all tags balanced** (`a`, `nav`, `header`, `aside`, `main`, `section`, `button`, `div`), **CSS braces balanced**.
- 22 shell files: correct route set and order, canonical logo reference, anchor reset present.
- **Zero** `<nav class="topbar">` remaining in any of the 35 desktop mockups; 5 mobile files still carry one, deferred.
- Both spines parse as valid YAML with `status: final`. `EXPERIENCE.md`'s `updated_note` was converted from a double-quoted scalar to a folded block scalar (`>-`), the same hardening A-22 applied to `DESIGN.md` after unescaped inner quotes had silently broken that file's frontmatter for eleven amendments.
