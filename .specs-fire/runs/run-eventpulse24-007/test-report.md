---
run: run-eventpulse24-007
work_item: frontend-skeleton
intent: project-scaffold
generated: 2026-10-27
status: passed
machine: macOS 26.4.1 (Apple Silicon), Node 24.22.1, pnpm 12.15.0
---

# Test Report: Frontend Skeleton (Next.js + tokens)

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Sample test: home page (`app/page.test.tsx`) | 1 | 0 | 0 | n/a |
| Root layout: theme, lang, font classes on `<html>` (`app/layout.test.tsx`) | 2 | 0 | 0 | n/a |
| Tokens vs DESIGN.md (`styles/tokens.test.ts`) | 14 | 0 | 0 | n/a |
| Motion (`styles/motion.test.ts`) | 3 | 0 | 0 | n/a |
| Architecture: deps denylist, motion-class scan with 5 planted and 3 allowed cases, kebab-case, `lib/api` (`tests/architecture.test.ts`) | 13 | 0 | 0 | n/a |
| **Total (Vitest)** | **33** | 0 | 0 | n/a |
| `pnpm lint` (next core-web-vitals + next/typescript + typescript-eslint strict + prettier) | clean | | | |
| `pnpm typecheck` (`next typegen && tsc --noEmit`, strict) | clean | | | |
| `pnpm format:check` | clean | | | |
| `pnpm build` (production, fonts downloaded) | ✓ static `/` | | | |
| Backend suite (unchanged) | 429 | 0 | 0 | n/a |
| Mutation checks | 19/19 caught (one miss fixed, see below) | | | |
| Lockfile: one `typescript-eslint` / `@typescript-eslint/*` (8.72.0) | ✓ | | | |

## Acceptance Criteria Validation

- ✅ **`frontend/` with pnpm: Next 16.3.x, React 19.2.x, TS 5 strict, App Router, Tailwind 4.** Next 16.3.8, React 19.2.9, TypeScript 5.9.3 (`strict: true`), Tailwind 4.3.3. `packageManager: pnpm@12.15.0`; Node ≥24.15 enforced.
- ✅ **Tokens as CSS custom properties from DESIGN.md; `data-theme="dark"` on `<html>`; light is a swap, no `prefers-color-scheme`.**
  - All 21 + 21 color bullets from DESIGN.md are parsed (20 variables per mode after the alias); values match exactly.
  - Shadow and glows are mode-dependent.
  - Radius, spacing and breakpoint sets are exact.
  - Seen in a browser: dark by default; after switching to light, the body background computes to `#FAF8F4`.
- ✅ **Single `motion.fadeIn` 240ms opacity transition, `transition: none` under reduced motion.** It's the only transition or animation in any stylesheet. `@starting-style` gives the fade on first render, which the build output confirms.
- ✅ **No UI kit or animation library** (denylist test). Tailwind's animation, shadow, easing, color, radius and font defaults are reset; markup is scanned for `transition`/`duration`/`delay`/`ease`/`animate` classes.
- ✅ **ESLint + Prettier; Vitest + Testing Library with one sample test.**
- ✅ **Files `kebab-case.ts(x)`; `lib/api/` reserved with its README.**
- ✅ **`make web` runs `pnpm dev` on :3000; `pnpm lint`, `typecheck` and `test` all green.** `make web` served `/` with HTTP 200 and `<html lang="en" data-theme="dark" class="…inter… …source_serif_4… …jetbrains_mono…">`.

## Manual Verification

1. **`make web` → http://127.0.0.1:3000.** Screenshot taken with headless Chrome: near-black canvas, "EventPulse24" in Source Serif 4, the lede in Inter.
2. **Light swap:** set `data-theme="light"` in a live headless-Chrome session (Chrome DevTools Protocol). The body background computes to `rgb(250, 248, 244)` (= `#FAF8F4`), and the screenshot shows the light paper with dark ink.
3. **Built CSS** (`.next/static/chunks/*.css`):
   - both `--color-surface-paper` values are present
   - the `[data-theme=dark]{…}` block is present
   - `@starting-style{.fade-in{opacity:0}}` is present, inside `@starting-style`, so it isn't a page-hiding plain rule
   - the reduced-motion rule is present
   - no `red-500`, `animate-spin`, `--shadow-lg` or `--breakpoint-sm`
4. **`AGENTS.md` / `CLAUDE.md`:** deleted before `next dev`. Next printed "Generated AGENTS.md and CLAUDE.md for AI agents. Set `agentRules: false` in next.config to disable", and re-created both, byte-identical to the `create-next-app` versions.
5. **Node enforcement:** `make doctor` passes on 24.22.1 and fails on 20.20.2 with "nvm install 24". `pnpm install` on Node 24.14.1 fails with `ERR_PNPM_UNSUPPORTED_ENGINE … wanted >=24.15`.

## Issues Found During Execution

| Issue | Resolution |
|---|---|
| **`engine-strict=true` in `frontend/.npmrc` had no effect**: pnpm 12 installed on Node 24.14.1 | pnpm 10+ reads its settings from `pnpm-workspace.yaml`: `engineStrict: true` there; `.npmrc` removed. Verified refusal on 24.14.1. |
| `@types/react` `^19.2` resolved to 19.3.0 (newer than React 19.2) | Pinned `~19.2.18` / `@types/react-dom ~19.2.3` |
| npm marks **ESLint 9.39.5 "no longer supported"** | Kept 9 as planned: `eslint-config-next` 16.3.8's `react` / `jsx-a11y` / `import` plugins declare ESLint ≤9, and `create-next-app` 16.3.8 installs `eslint ^9`. Recorded in tech-stack; revisit when `eslint-config-next` supports 10. |
| `LayoutProps` (global) is undefined for a plain `tsc` | `typecheck` runs `next typegen && tsc --noEmit` |
| `tokens.css`'s own header comment said "No prefers-color-scheme switch" | The token test flagged it; reworded ("never follows the OS setting") rather than weakening the test |
| strict lint banned `!` assertions in tests | A small `must(map, key)` helper that fails naming the missing key |
| Mutation: an extra `--breakpoint-sm` passed | Tests now pin the **exact** set of radius, spacing and breakpoint variables |

## Mutation Checks (each reverted after)

All caught:
- dark terracotta hex changed
- an alias declared as its own variable
- shadow reset removed
- glow added in light mode
- spacing multiplier restored
- `sm` breakpoint added (after the fix)
- extra radius
- extra spacing step
- a display fallback family dropped
- `prefers-color-scheme` added
- reduced-motion rule removed
- fade at 300ms
- a second transition
- font classes moved to `<body>`
- light theme by default
- `transition-all` in markup
- `framer-motion` dependency
- DESIGN.md path wrong (clear failure message)
- a CamelCase file

## Ready for Review

- [x] All tests passing
- [x] All acceptance criteria validated
- [x] Manual verification done (macOS; Ubuntu needs Node 24 installed first)
