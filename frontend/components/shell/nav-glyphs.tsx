/**
 * The shell's glyphs — hand-drawn, stroke-only, 16×16.
 *
 * **There is no icon library.** The stack is "UI system: None" (`DESIGN.md`), and adding
 * one for six 16-pixel marks would be a heavier dependency than the marks themselves.
 * So each glyph is an inline SVG path: `fill="none"`, `stroke="currentColor"`,
 * `stroke-width="1.6"`.
 *
 * **Never filled chromatic.** The spec says so twice — "16×16 stroke-only SVG, never
 * filled chromatic" — and the reason is that a filled chromatic glyph on a nav item
 * spends a colour that is rationed. `currentColor` means the glyph takes the label's
 * ink, so the resting, active and hover states all follow the text automatically.
 *
 * **Each glyph is `aria-hidden`.** The label beside it is the name; a screen reader
 * announcing "graphic" before every nav item is noise.
 */

/** The shared wrapper: the 16×16 box, the stroke, and the hiding. */
function Glyph({ children }: { children: React.ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

/** Digest — a pulse wave. The product's own name, drawn as its shape. */
export function DigestGlyph() {
  return (
    <Glyph>
      <path d="M1 8h2.5l1.5-4 2.5 8 2-6 1.5 2H15" />
    </Glyph>
  );
}

/** Timeline — a week grid: two rows of three days, the first one marked. */
export function TimelineGlyph() {
  return (
    <Glyph>
      <rect x="1.5" y="2.5" width="4" height="4" rx="1" />
      <rect x="6" y="2.5" width="4" height="4" rx="1" />
      <rect x="10.5" y="2.5" width="4" height="4" rx="1" />
      <rect x="1.5" y="8" width="4" height="4" rx="1" />
      <rect x="6" y="8" width="4" height="4" rx="1" />
      <rect x="10.5" y="8" width="4" height="4" rx="1" />
    </Glyph>
  );
}

/** Add — a plus. The spec names this one exactly. */
export function AddGlyph() {
  return (
    <Glyph>
      <path d="M8 3v10M3 8h10" />
    </Glyph>
  );
}

/** Browse — a compass. The spec names this one exactly. */
export function BrowseGlyph() {
  return (
    <Glyph>
      <circle cx="8" cy="8" r="6" />
      <path d="M10.5 5.5 7.8 9.2 5.5 10.5l2.7-3.2z" />
    </Glyph>
  );
}

/** Conflicts — two overlapping arcs: two events that collide. */
export function ConflictsGlyph() {
  return (
    <Glyph>
      <circle cx="6" cy="8" r="4.5" />
      <circle cx="10" cy="8" r="4.5" />
    </Glyph>
  );
}

/** Settings — a slider: two rules and two knobs. */
export function SettingsGlyph() {
  return (
    <Glyph>
      <path d="M2 5h12M2 11h12" />
      <circle cx="6" cy="5" r="1.75" />
      <circle cx="10" cy="11" r="1.75" />
    </Glyph>
  );
}

/** Search — a magnifier. */
export function SearchGlyph() {
  return (
    <Glyph>
      <circle cx="7" cy="7" r="4.5" />
      <path d="m10.5 10.5 3 3" />
    </Glyph>
  );
}

/** More — three stacked dots. The spec sanctions this over a 3×3 grid. */
export function MoreGlyph() {
  return (
    <Glyph>
      <circle cx="8" cy="3" r="1.25" />
      <circle cx="8" cy="8" r="1.25" />
      <circle cx="8" cy="13" r="1.25" />
    </Glyph>
  );
}
