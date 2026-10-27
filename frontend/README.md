# EventPulse24 frontend

Next.js 16 (App Router), React 19.2, TypeScript 5 (strict) and Tailwind CSS 4 over the design-token
layer from DESIGN.md. **UI system: None**: no component kit, no animation library.

Needs **Node 24 LTS** (≥ 24.15; `nvm use` reads the repo's `.nvmrc`) and pnpm via corepack.

## Commands

From the repository root:

```bash
make web-install   # pnpm install --frozen-lockfile
make web           # dev server on http://127.0.0.1:3000
make test-web      # Vitest
make lint-web      # ESLint, typecheck (next typegen + tsc), Prettier check
```

Or inside `frontend/`: `pnpm dev`, `pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm format`,
`pnpm build`.

## Layout

| Path                 | What                                                                          |
| -------------------- | ----------------------------------------------------------------------------- |
| `app/`               | App Router routes. `layout.tsx` sets `<html data-theme="dark">` and the fonts |
| `styles/tokens.css`  | Design tokens (DESIGN.md §Token Implementation Contract)                      |
| `styles/globals.css` | Tailwind, base styles, focus ring, `.fade-in`                                 |
| `lib/api/`           | **Generated** API client: never edited by hand (AD-19)                        |
| `tests/`             | Structural tests (no UI kit, no motion classes, kebab-case files)             |

## Design tokens

- Token `color.accent.terracotta` is the CSS variable `--color-accent-terracotta`. Aliases aren't
  declared: `color.ink.meta` is `--color-ink-muted`, `color.cool.public` is `--color-accent-slate`.
- **Dark is the default.** Light is a swap: `data-theme="light"` on `<html>`. The theme never
  follows the OS setting.
- **Tailwind only knows the tokens.** Its own colors, radii, shadows, animations, easings, fonts,
  spacing multiplier and `sm` / `xl` / `2xl` breakpoints are reset. Use `bg-surface-paper`,
  `text-ink-muted`, `border-border-subtle`, `rounded-card`, `shadow-floating`, `p-4`
  (= `spacing.4`, 16px), `font-display`, `md:`, `lg:`. Type sizes are `font` shorthands:
  `[font:var(--type-scale-body-md)]`.
- **Motion:** only `.fade-in` (240ms opacity, off under reduced motion). Tailwind's
  `transition-*` / `duration-*` / `animate-*` classes are rejected by a test.
- `styles/tokens.test.ts` reads DESIGN.md itself: change a color there and the test fails until
  `tokens.css` matches.

## Fonts

Source Serif 4 (display), Inter (body, with italic for micro-tags) and JetBrains Mono load through
`next/font/google`. They're downloaded at build time and served from the app, so browsers never
contact Google; the first `dev` / `build` needs internet. Their CSS variable classes must stay on
`<html>`: the `--type-family-*` tokens on `:root` read them.

## Agent notes

`AGENTS.md` / `CLAUDE.md` are written by `next dev` (it re-creates them if deleted; set
`agentRules: false` in `next.config.ts` to stop that). They tell AI agents to read the bundled
Next.js docs in `node_modules/next/dist/docs/` before writing code.
