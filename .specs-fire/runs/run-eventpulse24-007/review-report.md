# Code Review Report

**Run**: run-eventpulse24-007
**Intent**: project-scaffold
**Reviewed**: 2026-10-27
**Files Reviewed**: 27 (21 created, 9 modified incl. docs; generated `pnpm-lock.yaml` spot-checked)

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 1 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 0 | 1 |
| Testing | 0 | 0 | 1 |
| **Total** | **1** | **0** | **2** |

**Tests Status**: Passing (Vitest 33; lint, typecheck, format check and build clean; backend 429 unchanged)

---

## Files Reviewed

- `frontend/app/{layout,page}.tsx`, `app/{layout,page}.test.tsx`
- `frontend/styles/{tokens,globals}.css`, `styles/{tokens,motion}.test.ts`, `frontend/tests/architecture.test.ts`
- `frontend/{package.json,pnpm-workspace.yaml,next.config.ts,tsconfig.json,postcss.config.mjs,eslint.config.mjs,vitest.config.mts,vitest.setup.ts,.prettierrc,.prettierignore,.gitignore,README.md}`, `lib/api/README.md`, `AGENTS.md`, `CLAUDE.md`
- `.nvmrc`, `Makefile`, `scripts/doctor.sh`, `README.md`, `docs/setup/{macos,ubuntu}.md`, standards, `ci-pipeline.md`, DESIGN.md (ASSUM-1 status lines only)

ESLint (strict), `tsc` (strict) and Prettier were clean before review.

---

## Auto-Fixed Issues

### 1. [Code Quality] Template placeholder in `next.config.ts`

- **File**: `frontend/next.config.ts`
- **Fix**: Prettier had left `create-next-app`'s placeholder comment as `{/* config options here */}`; replaced with an empty config object. No behavior change; checks re-run clean.

---

## Skipped (recorded)

- [Testing] **The motion-class scan reads `className="…"`, `` className={`…`} `` and `className={"…"}` only.** Classes built with a helper (`clsx(…)`, `cn(…)`) or passed through props aren't scanned. No such helper exists yet: none is a dependency, and the architecture test would show it once added. When one arrives, extend `classStrings()` to read its string arguments.
- [Architecture] **ESLint 9 is marked "no longer supported" by npm.** It stays until `eslint-config-next` supports ESLint 10, because its bundled `react` / `jsx-a11y` / `import` plugins declare ≤9. Recorded in tech-stack. Dev-only tool, no runtime exposure.

---

## Notes

- **Security:**
  - Fonts are self-hosted at build time, so there are no runtime requests to Google.
  - There are no environment reads in the frontend yet; the API base URL arrives with `health-round-trip`.
  - The page has no user input.
- **Lockfile:** exactly one `typescript-eslint` and one `@typescript-eslint/eslint-plugin` / `parser` (8.72.0), so the "Cannot redefine plugin" failure can't occur. `pnpm-workspace.yaml` keeps `create-next-app`'s `allowBuilds` (no install scripts for `sharp` / `unrs-resolver`) and adds `engineStrict: true`.
- **Where custom properties resolve:**
  - `--stroke-*`, `--type-scale-*` and `--type-family-*` use `var()` on `:root`, and the theme and font classes sit on that same element (`<html>`), so they resolve with the active theme and the loaded fonts.
  - Putting `data-theme` on a sub-element instead of `<html>` would not re-theme those composite tokens. That isn't supported today (the toggle will set it on `<html>`).
