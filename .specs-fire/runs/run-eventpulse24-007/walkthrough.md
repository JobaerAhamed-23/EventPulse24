---
run: run-eventpulse24-007
work_item: frontend-skeleton
intent: project-scaffold
generated: 2026-10-27
mode: confirm
---

# Implementation Walkthrough: Frontend Skeleton (Next.js + tokens)

## Summary

`frontend/` is a Next.js 16.3.8 / React 19.2.9 / TypeScript 5.9 (strict) / Tailwind 4.3.3 app. Its only styling vocabulary is DESIGN.md's token layer: Tailwind's own colors, radii, shadows, animations, easings, fonts, spacing multiplier and extra breakpoints are switched off, and the single 240ms fade is the only motion. Dark is the default theme and light is a swap of one attribute. The tests read DESIGN.md itself, so the CSS can't drift from the design doc.

Node 24 LTS is now required on both machines and enforced in three places: `make doctor`, pnpm's `engineStrict`, and `.nvmrc`. On this Mac, all gates pass and the page renders in both themes. 19/19 mutations were caught.

## Structure Overview

```text
DESIGN.md (§Colors, §Shapes, §Spacing, §Type families) ──read by──► styles/tokens.test.ts
        │ transcribed into
        ▼
styles/tokens.css
  @theme static { resets (--color-*, --radius-*, --shadow-*, --animate-*, --ease-*, --font-*,
                  --spacing, --breakpoint-*) · light colors · shadow/glows (light) · type · spacing ·
                  layout · radius · stroke · motion }               ← emitted on :root
  @theme inline { --font-display/body/mono → --type-family-* }      ← Tailwind font utilities
  [data-theme="dark"] { dark colors · dark shadow · both glows }
        │ imported by
        ▼
styles/globals.css: @import "tailwindcss" · base · link reset · :focus-visible ring · .fade-in
        │ imported by
        ▼
app/layout.tsx: <html lang="en" data-theme="dark" class="{inter} {sourceSerif} {jetbrainsMono}">
                  (next/font defines --font-inter / --font-source-serif / --font-jetbrains-mono here,
                   on the same element whose :root tokens read them)
```

- **Utilities resolve through the variables,** e.g. `.bg-surface-paper { background-color: var(--color-surface-paper) }`. Switching `data-theme` on `<html>` re-themes everything.
- **Type sizes** are `font` shorthands (`[font:var(--type-scale-headline-md)]`), because the DESIGN.md tokens bundle size, line height, weight and family.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `.nvmrc` | `24` |
| `frontend/package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml` | Pinned deps; `packageManager`; `engines` ≥24.15; `engineStrict` |
| `frontend/styles/tokens.css`, `globals.css` | Token layer and base |
| `frontend/app/layout.tsx`, `page.tsx` | Root layout and placeholder home |
| `frontend/lib/api/README.md` | Reserved for the generated client (AD-19) |
| `frontend/{eslint.config.mjs, vitest.config.mts, vitest.setup.ts, .prettierrc, .prettierignore}` | Tooling |
| `frontend/README.md` | Commands, tokens, fonts, agent notes |
| `frontend/AGENTS.md`, `CLAUDE.md` | Next 16's agent notes. **Commit pending your approval of the content.** |
| Tests | `app/page.test.tsx`, `app/layout.test.tsx`, `styles/tokens.test.ts`, `styles/motion.test.ts`, `tests/architecture.test.ts` |

### Modified

| File | Changes |
|------|---------|
| `Makefile` | `web`, `web-install`, `lint-web`, `test-web` |
| `scripts/doctor.sh` | Node ≥24.15 |
| `README.md`, `docs/setup/{macos,ubuntu}.md` | Node 24 via nvm; frontend section (fonts need internet once, light-mode swap, token-only Tailwind) |
| `.specs-fire/standards/{tech-stack,coding-standards}.md` | Versions and the ESLint 9 note; Tailwind token lock, motion rule, theme and fonts on `<html>` |
| `ci-pipeline.md` | Frontend CI hand-off |
| DESIGN.md | **ASSUM-1 status line only**: RESOLVED, current values accepted as shipped |

## Key Implementation Details

### 1. Tokens that can't drift

`tokens.test.ts`:
- parses DESIGN.md through **one path constant**, and fails clearly if the file has moved
- must find **exactly** the 21 named color bullets per mode
- maps the `color.cool.public` alias to `--color-accent-slate` deliberately, and checks the two values are equal
- checks every value in both modes, the mode-dependent shadow and glows, and the **exact** sets of radius, spacing and breakpoint variables
- checks the family fallbacks after each `var(--font-…)`
- checks there's no `prefers-color-scheme`

### 2. "UI system: None" as tests, not intentions

- A dependency denylist covers kits and animation libraries.
- Tailwind's theme-driven motion and shadow classes are reset.
- The classes the theme can't remove (`transition*`, `duration-*`, `delay-*`, `ease-*`, `animate-*`) are caught by a markup scan, with planted and allowed cases.

### 3. The fade

`.fade-in { transition: var(--motion-fade-in) }` (`opacity 240ms ease-out`), plus `@starting-style { opacity: 0 }`, so it fades in on first render without JavaScript. Under `prefers-reduced-motion: reduce` it's `transition: none`. The built CSS confirms `opacity:0` sits inside `@starting-style`, not as a plain rule.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Node | 24 LTS (≥24.15), both machines (user) | Node 20 EOL; Vitest 5 / jsdom 30 |
| ASSUM-1 | Accept current dark values; status RESOLVED (user) | The test keeps the CSS in sync if design changes them |
| Commit of run 006 | Separate commit `a0bf35e` (user) | One commit per work item |
| Tailwind wiring | `@theme static` light + `[data-theme="dark"]` overrides; defaults reset (plan review) | Names identical to DESIGN.md; no self-reference; only token classes exist |
| Fonts | `next/font/google`, classes on `<html>` (plan review) | Self-hosted; the `:root` tokens read the variables there |
| Versions | Next 16.3.8, React 19.2.9, TS 5.9.3, ESLint 9.39 | Spine's lines; ESLint 10 not yet supported by Next's lint plugins |
| Glow and shadow names | `--glow-today`, `--glow-brandmark`, `--shadow-floating` | DESIGN.md describes them but gives no token path |
| Type-scale tokens | `font` shorthands | One variable per DESIGN.md path |

## Deviations from Plan

- **`engine-strict`** moved from `frontend/.npmrc` to `engineStrict: true` in `pnpm-workspace.yaml`. pnpm 12 ignored the `.npmrc` setting (it installed on Node 24.14.1); the workspace setting refuses, as verified.
- **`@types/react` / `@types/react-dom`** pinned to `~19.2` (`^19.2` had pulled 19.3).
- **`typecheck` runs `next typegen` first**, because `LayoutProps` is a generated global.
- **`.fade-in` uses `@starting-style`**, so the single fade actually plays on first render. The plan only defined the class.
- **Token tests pin exact name sets** for radius, spacing and breakpoints, added after the mutation run showed an extra breakpoint would pass.
- **A home page lede line** ("What's actually worth your attention right now.") comes from DESIGN.md §Brand & Style.

## Dependencies Added

`next` 16.3.8, `react` / `react-dom` 19.2.9; dev:
- `@tailwindcss/postcss` + `tailwindcss` 4.3.3
- `typescript` 5.9.3
- `eslint` 9.39.5, `eslint-config-next` 16.3.8, `typescript-eslint` 8.72.0, `eslint-config-prettier` 10.1.8
- `prettier` 3.9.10
- `vitest` 5.0.5, `@vitejs/plugin-react` 6.1.2, `jsdom` 30.1.3
- `@testing-library/react` 16.3.3, `/dom` 10.4.2, `/jest-dom` 7.0.1
- `@types/node` 24, `@types/react` 19.2.18, `@types/react-dom` 19.2.7

## How to Verify

1. **Node:** `node -v` must be ≥ v24.15. If not: `nvm install 24`, or `nvm use` in the repo.
2. **Install and run**
   ```bash
   make web-install
   make web
   ```
   Open <http://127.0.0.1:3000>. Expected: a near-black page, "EventPulse24" in a serif and the line below in Inter.
3. **Light mode:** in devtools, change `<html data-theme="dark">` to `"light"`. Expected: warm off-white paper (`#FAF8F4`) with dark ink.
4. **Gates**
   ```bash
   make test-web    # 33 passed
   make lint-web    # eslint, typecheck, prettier: clean
   ```
5. **Guard check:** add `className="animate-spin"` to `app/page.tsx` and run `make test-web`. Expected: the architecture test fails. Revert it.

## Test Coverage

- Tests added: 33 (Vitest)
- Coverage: not measured (`ci-pipeline` sets up coverage reporting)
- Status: all passing; backend unchanged at 429

## Developer Notes

- **pnpm 10+ ignores pnpm settings in `.npmrc`.** Put them in `pnpm-workspace.yaml` (`engineStrict`, `allowBuilds`, …).
- **`next dev` re-creates `AGENTS.md` / `CLAUDE.md`** if they're deleted. `agentRules: false` in `next.config.ts` stops it.
- **Tailwind 4 `@theme` names are CSS variables.** Because DESIGN.md's paths already use `color-` / `radius-` / `spacing-` prefixes, the tokens *are* the theme. Don't re-declare them in `@theme inline` with `var(--same-name)`: that would refer to itself.
- **A theme reset doesn't remove every Tailwind class:** `transition*`, `duration-*`, `delay-*` and the `p-px` literal still exist. The markup scan is the guard for motion.
- **Testing the layout:** call `RootLayout()` and inspect the element. Rendering `<html>` with Testing Library nests it in a `<div>`.
- **Checking the light theme visually:** a saved copy of the dev page opened from disk loses its CSS, because the dev server delivers CSS through JavaScript. Switch `data-theme` on the live page instead.
- **The first `pnpm install` took about 6 minutes** on this network, with supply-chain verification. Later installs are instant from the store.

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing (33; backend 429)
- [x] No critical issues (1 auto-fix; 2 low items recorded)
- [x] Documentation updated
- [x] Developer notes captured
- [ ] `frontend/AGENTS.md` and `CLAUDE.md` content approved by you, before they're committed

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-007*
