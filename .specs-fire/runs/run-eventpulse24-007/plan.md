---
run: run-eventpulse24-007
work_item: frontend-skeleton
intent: project-scaffold
mode: confirm
checkpoint: plan
revision: 3 (plan reviews: 5 points + 8 smaller; font classes on <html>)
approved_at: 2026-10-27
---

# Implementation Plan: Frontend Skeleton (Next.js + tokens)

## Approach

Create `frontend/` with `create-next-app@16.3.8` (App Router, TypeScript, Tailwind 4, ESLint, pnpm), then strip its boilerplate:
- the Geist fonts and demo page
- the SVGs in `public/`
- the `prefers-color-scheme` block in `globals.css`, which DESIGN.md forbids

Then add the token layer, Prettier, Vitest + Testing Library, and the checks that keep "UI system: None" true.

**Node 24 LTS on both machines** (user decision, this session). Node 20 is end of life (April 2026), and the current test tools need ≥22 (jsdom 30 needs ≥24.15 on the 24 line). This Mac now has Node 24.22.1 via nvm as the default.
- A root **`.nvmrc`** (`24`) means `nvm use` picks it.
- `frontend/package.json` sets **`engines.node: ">=24.15"`** and **`packageManager: "pnpm@12.15.0"`** *(review: the field must be set explicitly)*.
- `frontend/.npmrc` sets **`engine-strict=true`**, so pnpm refuses to install on an older Node.
- `make doctor` requires Node 24.15+.

### Versions (verified on npm today)

| Package | Version | Note |
|---|---|---|
| `next` / `eslint-config-next` | **16.3.8** | The work item pins 16.3.x; 16.4 exists but isn't adopted here |
| `react` / `react-dom` | **19.2.9** (latest 19.2 patch; create-next-app pins 19.2.8) | 19.3 exists, not adopted |
| `typescript` | **5.9.3** | TS 7 exists; the work item says TS 5 |
| `tailwindcss` / `@tailwindcss/postcss` | 4.3.3 | |
| `eslint` | **9.39.x** | ESLint 10 exists, but `eslint-plugin-react`, `jsx-a11y` and `import` (pulled in by `eslint-config-next`) only declare up to ESLint 9 |
| `typescript-eslint` | in `^8.46` (the range `eslint-config-next` declares) | **Exactly one copy in the lockfile**: two copies make ESLint fail with "Cannot redefine plugin @typescript-eslint" *(review)*. Checked with `pnpm why typescript-eslint` / `@typescript-eslint/eslint-plugin`. |
| `prettier` + `eslint-config-prettier` | 3.9.x / latest | |
| `vitest` | 5.0.5 | Needs Node ≥22.12 |
| `@vitejs/plugin-react` | 6.1.2 | |
| `jsdom` | 30.1.x | Needs Node ≥24.15 |
| `@testing-library/react` / `dom` / `jest-dom` | 16.3.3 / 10.4.2 / 7.0.1 | |

### 1. Token layer (`frontend/styles/tokens.css`), sourced from DESIGN.md

**Names** follow the Token Implementation Contract: the kebab-case form of each path, e.g. `color.accent.terracotta` → `--color-accent-terracotta`. Path aliases are **not** declared separately (`color.ink.meta` → `--color-ink-muted`; `color.cool.public` → `--color-accent-slate`).

**Tailwind wiring, settled now** *(review 5)*. I checked this in a scratch Tailwind 4.3.3 build before writing it here.

- **Light values go directly in `@theme static`.**
  - `@theme` emits them on `:root`, which is the contract's light default.
  - `static` makes Tailwind output **every** token, even ones no component uses yet. In the probe, an unused color was still emitted.
- **Dark overrides go in a plain `[data-theme="dark"]` block.**
  - Tailwind's classes read the variables (`.bg-surface-paper { background-color: var(--color-surface-paper) }`), so they switch automatically when the theme changes. The probe confirmed this.
  - The names match DESIGN.md exactly, nothing is declared twice, and nothing refers to itself.
- **Colors, radius, spacing and the shadow** already use Tailwind's own name prefixes (`--color-*`, `--radius-*`, `--spacing-*`, `--shadow-*`), so they need no mapping.
- **Type tokens** need a one-line mapping each, in `@theme inline`: `--font-display: var(--type-family-display)`, `--font-body: …`, `--font-mono: …`.
- **Every other token** (type scale, layout, stroke, glow, motion) goes in `@theme static` too, so it's emitted on `:root` beside the rest. Tailwind doesn't create classes for them.

**Tailwind defaults are reset in the same `@theme static` block**, so only DESIGN.md tokens exist as classes *(review 4 + breakpoints)*:

| Reset | Effect (seen in the probe) |
|---|---|
| `--color-*: initial` | No `bg-red-500` etc. Terracotta stays the only chromatic accent. |
| `--radius-*: initial` | No `rounded-lg`; only `rounded-card`, `rounded-subtle`, … |
| `--shadow-*: initial` | No `shadow-lg`. Only the single floating shadow (`shadow-floating`) exists. |
| `--animate-*: initial` | No `animate-spin` / `animate-pulse` |
| `--ease-*: initial` | No `ease-in-out` |
| `--font-*: initial` | Only `font-display` / `font-body` / `font-mono` |
| `--spacing: initial` | Tailwind's 4px multiplier is gone, so off-scale classes like `p-5` aren't generated. `p-4` uses `var(--spacing-4)`, as DESIGN.md defines it. |
| `--breakpoint-*: initial`, then `md: 768px`, `lg: 1024px` | Only DESIGN.md's tablet and desktop breakpoints. `sm` / `xl` / `2xl` don't exist. |

**What a theme reset can't remove:** `transition-*`, `duration-*` and `delay-*` classes aren't driven by the theme, and the probe still generated them. A test scans the `.tsx` files instead (see Tests).

**Mode-dependent vs mode-independent tokens** *(review 1)*:

| Token | `:root` (light, in `@theme static`) | `[data-theme="dark"]` |
|---|---|---|
| All `color.*` | DESIGN.md light hex | DESIGN.md dark hex |
| `shadow.floating` | `0 8px 24px rgba(0,0,0,0.08)` | `0 8px 24px rgba(0,0,0,0.40)` |
| `glow.today` (Indicator.Today dot) | `none` (light has no glow) | `0 0 12px rgba(255,106,71,0.55)` |
| `glow.brandmark` (the CSS dot fallback for the brand mark) | `none` | `0 0 14px rgba(255,106,71,0.55)` |
| type families, type scale (desktop + mobile), spacing `0…30`, layout, radius, stroke widths, `motion.fadeIn` 240ms | same in both modes | (not overridden) |

The glow names (`--glow-today`, `--glow-brandmark`) are new CSS variable names. DESIGN.md describes the two glows but gives them no token path, so this is noted as a naming decision.

**`styles/globals.css`:**
- `@import "tailwindcss"`, then `tokens.css`
- **Base styles:**
  - `body` on surface paper / ink primary in the body family
  - the link reset DESIGN.md requires (`a { color: inherit; text-decoration: none; }`)
  - the **focus ring**: 2px solid terracotta, 2px offset, on `:focus-visible`
- **`motion.fadeIn`:** `.fade-in { transition: opacity 240ms ease-out; }`, and `@media (prefers-reduced-motion: reduce) { .fade-in { transition: none; } }`. It's the only transition, and there's no animation library.
- **No `prefers-color-scheme` anywhere.** Light is a swap-out: set `data-theme="light"`. A Settings toggle comes later.

### 2. App shell

- **`app/layout.tsx`:** `<html lang="en" data-theme="dark">`, fonts loaded with **`next/font/google`** (decision below), metadata title "EventPulse24".
- **`app/page.tsx`:** a minimal placeholder home. The brand name in the display serif and one line of body copy, using `.fade-in`. No marketing content, no components.
- **`lib/api/README.md`:** "Generated from the backend's OpenAPI schema (AD-19). Never hand-edited." The generator arrives in `health-round-trip`.

**Fonts** *(review, smaller point)*:
- **Inter** (body): `style: ["normal", "italic"]`, because `type.scale.microtag` is italic in the body family. Weights 400 / 500 / 600 / 700 are all used.
- **Source Serif 4** (display): 400 / 600 / 700.
- **JetBrains Mono** (mono): 400 / 500 / 600.
- All three are variable fonts on Google Fonts. Where `next/font` accepts the whole weight range, I use that; otherwise I list the weights explicitly.
- `next/font` provides each font as a CSS variable, so the family tokens become, for example, `--type-family-display: var(--font-source-serif), Fraunces, Georgia, serif`. DESIGN.md's named fallbacks stay after the variable. The token test allows this form: the first entry is a `var(--font-…)`, followed by the documented fallbacks.
- **The font classes (`inter.variable`, `sourceSerif.variable`, `jetbrainsMono.variable`) go on `<html>`, never `<body>`** *(review)*.
  - `next/font` defines each `--font-…` variable on whichever element gets its class.
  - The family tokens live on `:root`, which is `<html>`, and read those variables there.
  - If the class were on `<body>`, the variable wouldn't exist where `:root` reads it. The token would quietly break, and headings would fall back to the default font with no error.
  - `create-next-app` 16.3.8's own template already puts them on `<html>`. The rule is enforced anyway, because it's an easy slip in later edits.

**Decision to note: fonts via `next/font/google`.** DESIGN.md names Source Serif 4, Inter and JetBrains Mono, all open source (OFL). ASSUM-2 leaves "font hosting/loading" to engineering. `next/font` downloads them **at build time and serves them from our own site**, so visitors' browsers never contact Google.
- **Cost:** `next dev` / `next build` need internet the first time; GitHub Actions has it.
- **Fallback:** system fallbacks only, with the serif as Georgia until real fonts are added.

**`frontend/AGENTS.md` and `CLAUDE.md`** *(review)*: these are instructions AI agents follow when they work in `frontend/`. `create-next-app` 16.3.8 generates them.
- **Content as generated:** "This is NOT the Next.js you know … Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices." The block itself says `next dev` re-adds it (`next/dist/server/lib/generate-agent-files.js`). `CLAUDE.md` is just `@AGENTS.md`.
- **They're not committed until you've approved the content.** After the first `next dev`, I check whether they really are re-created (delete them, run, look), and report what I see.

### 3. Tooling and scripts (`frontend/package.json`)

- `dev`, `build`, `start`
- **`lint`:** `eslint .` with `next/core-web-vitals`, `next/typescript`, `typescript-eslint` `strict`, and `eslint-config-prettier` last
- **`typecheck`:** `tsc --noEmit`, with `strict: true`
- **`test`:** `vitest run` (jsdom, `@testing-library/jest-dom` matchers, `@/` alias)
- **`format` / `format:check`:** Prettier with print width 100, double quotes, trailing commas (per coding-standards)

### 4. Make and docs

- **`make web`:** `pnpm --dir frontend dev --port $(WEB_PORT)` (default 3000)
- `make web-install` (`pnpm install --frozen-lockfile`), `make lint-web` (lint + typecheck + format check), `make test-web`
- **`make doctor`:** Node ≥24.15
- **Setup guides and README:** Node 24 (`nvm install 24`), the frontend commands, and how to try light mode
- **`tech-stack.md`:** versions and the Node requirement
- **`coding-standards.md`:** Tailwind is limited to the tokens (with the reset list); motion only through `.fade-in`; the fonts decision
- **`ci-pipeline` work item hand-off:** Node 24 from `.nvmrc`; pnpm from `packageManager`; `make lint-web` / `make test-web`; fonts need network at build time

## Files to Create

| File | Purpose |
|------|---------|
| `.nvmrc` | `24` |
| `frontend/package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `.npmrc` | pnpm project: pinned versions, `packageManager`, `engines`, `engine-strict` |
| `frontend/next.config.ts`, `tsconfig.json`, `next-env.d.ts`, `postcss.config.mjs` | Next 16 + Tailwind 4 |
| `frontend/eslint.config.mjs`, `.prettierrc`, `.prettierignore` | Lint and format |
| `frontend/vitest.config.mts`, `vitest.setup.ts` | Tests |
| `frontend/styles/tokens.css`, `styles/globals.css` | Tokens (`@theme static` + dark overrides), resets, base, focus ring, `.fade-in` |
| `frontend/app/layout.tsx`, `app/page.tsx`, `app/favicon.ico` | Shell |
| `frontend/lib/api/README.md` | Reserved for the generated client |
| `frontend/README.md` | Frontend commands, tokens, light-mode swap |
| `frontend/AGENTS.md`, `CLAUDE.md` | Next's agent notes; **committed only after the user approves the content** |
| Tests | see below |

## Files to Modify

| File | Changes |
|------|---------|
| `Makefile` | `web`, `web-install`, `lint-web`, `test-web` |
| `scripts/doctor.sh` | Node ≥24.15 |
| `README.md`, `docs/setup/{macos,ubuntu}.md` | Node 24, frontend commands |
| `.specs-fire/standards/{tech-stack,coding-standards}.md` | Versions, Node 24, Tailwind token lock, motion rule, fonts |
| `.specs-fire/intents/project-scaffold/work-items/ci-pipeline.md` | Hand-off (above) |
| DESIGN.md ASSUM-1 status | **Only if the user accepts the current dark values** (see the open question) |

## Tests

| Test File | Coverage |
|-----------|----------|
| `frontend/app/page.test.tsx` | **The sample test:** the home renders the brand heading and uses `.fade-in` |
| `frontend/app/layout.test.tsx` | **Calls `RootLayout({ children })` directly** and checks the returned element's props: `data-theme="dark"` and `lang="en"`. `next/font` is mocked, each font returning a distinct `variable` class. This avoids rendering `<html>` inside a `<div>` *(review)*. **Asserts all three font variable classes are in `<html>`'s `className` and that `<body>` has none of them** *(review: font classes on `<html>`)*. |
| `frontend/styles/tokens.test.ts` | Parses DESIGN.md and `tokens.css` (details below) |
| `frontend/styles/motion.test.ts` | `.fade-in` is a 240ms opacity transition with `ease-out`, and `transition: none` under `prefers-reduced-motion: reduce`. No other `transition` / `animation` / `@keyframes` in any stylesheet (the skeleton pulse is added to the allowlist when it arrives). |
| `frontend/tests/architecture.test.ts` | Details below |

**`tokens.test.ts`, hardened** *(review 3)*:
- **One constant** holds the DESIGN.md path (`_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md`). If the file is missing, the test fails with a message naming that constant, rather than skipping.
- **The parser must find exactly the expected counts.** A trial parse of DESIGN.md today finds **21 color bullets in each mode**, with the same 21 names. After mapping the `color.cool.public` alias, that leaves **20 CSS variables per mode**. The test pins these counts and the full name list. If someone rewords or reformats the list and the parser finds fewer, the test fails instead of passing on an empty set.
- **`color.cool.public`** has its own hex in both lists, though it's an alias. The parser **deliberately maps it to `--color-accent-slate`** and asserts that the two hex values are equal in each mode. If design ever makes them differ, the test fails and says why.
- `color.ink.meta` is likewise asserted to be undeclared.
- Every color must equal the doc's value: light in `@theme static`, dark under `[data-theme="dark"]`.
- **Mode-dependent shadow and glows:** checked per the table above. Both glows are `none` in light.
- **Radius and spacing values** match §Shapes and §Spacing.
- **Family tokens:** start with a `var(--font-…)` and keep the documented fallbacks.
- **No `prefers-color-scheme`** in any stylesheet.

**`architecture.test.ts`:**
- **No UI kit or animation library** in `package.json`. Denylist: MUI, Chakra, Radix, Headless UI, Mantine, NextUI/HeroUI, Ant Design, Bootstrap, daisyUI, Flowbite, PrimeReact, Ark, shadcn helpers (`class-variance-authority` + `tailwind-merge` as a pair is allowed only if added deliberately later), framer-motion/motion, react-spring, GSAP, anime.js, Lottie, auto-animate, react-transition-group, tailwindcss-animate, tw-animate-css.
- **No motion classes in markup** *(review 4)*: scans every `.tsx` under `app/` and `components/` for `animate-`, `transition`, `transition-*`, `duration-*`, `delay-*` and `ease-*` class names. The probe showed these still exist, so motion must go through `.fade-in`. Planted cases prove the scan catches each form.
- **Source files are `kebab-case`** (`app/`, `components/`, `lib/`, `styles/`, `tests/`). Next's special files (`page.tsx`, `layout.tsx`) already are.
- `lib/api/README.md` exists.

**Gates:** `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm format:check` and `pnpm build`, all green, plus one `typescript-eslint` in the lockfile.

**Manual check:** `make web`, then http://localhost:3000. The page is dark, with the brand in the serif. Setting `data-theme="light"` in devtools swaps to light.

## Decided before approval

1. **ASSUM-1: accept the current dark values** *(review 2, user decision 2026-10-27)*. Implemented as written in DESIGN.md.
   - Recorded in this run's decisions.
   - In DESIGN.md, ASSUM-1's status changes from OPEN to **RESOLVED (2026-10-27): current values accepted as shipped by the project owner; revisit with sampled values (Linear / Vercel / Arc dark) when design has them**. The status lines are edited, nothing else in DESIGN.md.
   - Changing a color later is a one-place edit, and `tokens.test.ts` makes the CSS follow.
2. **Run 006 committed separately** *(review, user decision)*: `a0bf35e`. `.specs-fire/state.yaml` is left out of that commit because it already records run 007 as in progress; it's committed with 007.

## Not in this item

- **Components** (cards, sidenav, buttons): feature work
- **The generated API client** and a lint rule that blocks hand-written `fetch` to backend routes (AD-19): `health-round-trip`
- **Playwright + axe-core:** a later intent, with the first real surfaces
- **A theme toggle:** Settings → Appearance, later

---
*`approved_at` is set when the user approves at the checkpoint; until then this plan is a draft.*
