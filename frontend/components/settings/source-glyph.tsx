/**
 * `Component.Source.Glyph` — the monogram tile `settings-sources-desktop.html` puts in
 * front of every source.
 *
 * ## What it is for
 *
 * The Sources screen is a long list of names in a single column, and a long list of names
 * is the hardest thing to scan: every row looks like every other row until it is read.
 * The mockup's answer is a small tile carrying the source's initials, tinted by its badge
 * group — so a row is recognisable by its shape and colour before it is read, and the
 * groups stay visually distinct as the user scrolls past their headings.
 *
 * ## The initials are derived, never stored
 *
 * `SourceOut` carries a name and nothing shorter, so the monogram is computed here: the
 * first letter of each of the first two words ("Barbican Centre" → "Bc"), or the first
 * two letters when a source has a single-word name ("Songkick" → "So").
 *
 * **The mockup's own glyphs do not follow a rule** — it draws "Bb" for Barbican Centre
 * and "Mo" for MoMA PS1, which are hand-picked rather than derived. Hand-picking is not
 * available to a registry that grows server-side, so the rule above is the one applied,
 * and it is applied to every source alike.
 *
 * **It is decorative, and marked so.** The source's name is right beside it, in text. A
 * screen reader that announced "Bb" before "Barbican Centre" would be reading an
 * abbreviation of the next thing it is about to read — so the tile is `aria-hidden` and
 * carries no label of its own.
 *
 * ## The colour is the badge's, and it is a tint rather than a fill
 *
 * The four badges map to the four colours the mockup names. They are **tints** — a
 * six-percent wash with a thirty-percent border — not solid fills: a column of saturated
 * tiles would compete with the Digest's own cards for the eye, and the accent is the
 * product's scarcest resource. An unknown badge falls back to muted ink rather than
 * guessing a colour, because a new badge type should look unfamiliar rather than
 * miscoloured.
 */
import type { ReactNode } from "react";

/**
 * The four badges, as the mockup tints them.
 *
 * Tailwind cannot see a class name that is assembled at runtime, so each entry is a
 * complete, literal class string. That is also why the colours are written as arbitrary
 * values: these are the mockup's exact tints, and they exist nowhere else in the system.
 */
const BADGE_TINT: Record<string, string> = {
  official:
    "text-accent-terracotta border-[color:rgba(196,80,43,0.30)] bg-[color:rgba(196,80,43,0.06)]",
  community:
    "text-[color:var(--color-cool-public)] border-[color:rgba(110,126,146,0.30)] bg-[color:rgba(110,126,146,0.06)]",
  aggregator:
    "text-[color:var(--color-warm-personal)] border-[color:rgba(200,150,122,0.30)] bg-[color:rgba(200,150,122,0.06)]",
  crawled: "text-ink-muted border-border-subtle bg-surface-subtle",
};

/** The fallback for a badge this component has never heard of. */
const UNKNOWN_TINT = "text-ink-muted border-border-subtle bg-surface-subtle";

/**
 * A source's two-letter monogram.
 *
 * Exported because the test asserts the rule directly: a naming rule that can only be
 * checked by rendering is a rule whose edge cases go untested.
 */
export function monogram(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) {
    const word = words[0];
    // One word: its first two letters, capitalised as "Xy".
    return (word[0] ?? "").toUpperCase() + (word[1] ?? "").toLowerCase();
  }
  return (words[0][0] ?? "").toUpperCase() + (words[1][0] ?? "").toLowerCase();
}

export type SourceGlyphProps = {
  /** The source's name. The monogram is derived from it. */
  name: string;
  /** The source's badge — `official`, `community`, `aggregator`, `crawled`. */
  badge: string;
};

export function SourceGlyph({ name, badge }: SourceGlyphProps): ReactNode {
  return (
    <span
      // **Decorative.** The name follows it in text; announcing the initials first would
      // be reading an abbreviation of the next thing.
      aria-hidden="true"
      data-source-glyph={badge}
      className={[
        "flex size-8 shrink-0 items-center justify-center rounded-subtle border",
        "[font:var(--type-scale-meta-sm)] font-semibold",
        BADGE_TINT[badge] ?? UNKNOWN_TINT,
      ].join(" ")}
    >
      {monogram(name)}
    </span>
  );
}
