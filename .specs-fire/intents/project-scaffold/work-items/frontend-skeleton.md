---
id: frontend-skeleton
title: Frontend Skeleton (Next.js + tokens)
intent: project-scaffold
complexity: medium
mode: confirm
status: pending
depends_on: []
created: 2026-10-27
---

# Work Item: Frontend Skeleton (Next.js + tokens)

## Description

Create the Next.js client under `frontend/` with the design-token layer and no component kit, per the UX spine's binding 'UI system: None'.

## Acceptance Criteria

- [ ] `frontend/` created with pnpm: Next.js 16.3.x, React 19.2.x, TypeScript 5 strict, App Router, Tailwind CSS 4
- [ ] `styles/` holds design tokens as CSS custom properties sourced from the UX DESIGN.md token contract; `data-theme="dark"` is set on `<html>`; light theme is a swap-out, no `prefers-color-scheme` auto-switch
- [ ] Single `motion.fadeIn` 240ms opacity transition, collapsing to `transition: none` under `prefers-reduced-motion`
- [ ] No UI kit, no animation library in `package.json`
- [ ] ESLint (`eslint-config-next`, TS strict) + Prettier; Vitest + Testing Library with one sample test
- [ ] Files are `kebab-case.ts(x)`; `lib/api/` reserved (README note: generated, never hand-edited)
- [ ] `make web` runs `pnpm dev` on :3000; `pnpm lint`, `pnpm typecheck`, `pnpm test` all green

## Technical Notes

- Token values come from `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md`.

## Dependencies

(none)
