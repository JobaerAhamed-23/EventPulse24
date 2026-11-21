import Image from "next/image";

/**
 * The brand mark, as an image.
 *
 * **It is the one place the logo lives.** Every surface that shows the brand — the
 * pre-auth topbar, the authed topbar, the sidenav rail, the pre-auth footer — renders
 * this component, so the mark cannot drift from one surface to another.
 *
 * **It used to drift.** The pre-auth topbar drew the brand from a PNG, while the
 * authed topbar and the sidenav rail drew a `◉` glyph and the pre-auth footer drew a
 * terracotta dot. Three surfaces, three marks, one product. The glyph was not a
 * rendering of the logo — it was a different picture of the same idea — so no amount
 * of CSS would have reconciled them. Only one source could.
 *
 * **The source of truth is the PNG at `/brand/eventpulse24-logo-ecg.png`**, which is a
 * copy of `docs/EventPulse24-logo.png` in the repository root. `public/` is what the
 * browser can fetch, so that is where the file has to live; the `docs/` copy is the
 * canonical original and the two are kept byte-identical.
 *
 * **The filename carries `-ecg` for a reason, and it is not decoration.** The file
 * used to be served at `/brand/eventpulse24-logo.png`, and it used to hold a
 * *different* picture — the old "P"-in-circle mark. Replacing a file's bytes while
 * keeping its URL is invisible to anyone who had already loaded that URL: the
 * browser holds the old mark under the old name and never asks again. A reader
 * would have been looking at the previous logo while the source said otherwise,
 * which is exactly the drift this component exists to end. **A new filename is the
 * only honest way to say "this is a different image".**
 *
 * **The mark is decorative wherever the wordmark sits beside it.** The wordmark
 * already spells "EventPulse24", so an `alt` of "EventPulse24" would make a screen
 * reader say the name twice. The default `alt` is therefore the empty string — the
 * mark carries the picture, the text carries the name — and `alt` stays overridable
 * for the rare surface that shows the logo *without* a wordmark next to it.
 */
export function BrandMark({
  size = 36,
  alt = "",
  priority = false,
  className,
}: {
  /** The rendered edge length in pixels. The mark is square. */
  size?: number;
  /**
   * The alternative text. Empty by default, because the mark sits beside the wordmark
   * and the name is already there.
   */
  alt?: string;
  /** Set on the mark that sits above the fold, so it is not lazy-loaded. */
  priority?: boolean;
  /** Extra classes, for positioning only. */
  className?: string;
}) {
  return (
    <Image
      src="/brand/eventpulse24-logo-ecg.png"
      alt={alt}
      width={size}
      height={size}
      priority={priority}
      className={className ?? `size-[${size}px]`}
      /**
       * Dark Reader (and similar extensions) rewrite the DOM before React hydrates:
       * they inject `--darkreader-inline-color` into the inline style and a
       * `data-darkreader-inline-color` attribute onto the element. React then finds
       * markup that differs from what it rendered on the server and reports a
       * hydration mismatch.
       *
       * The mismatch is in the extension's injected attributes, not in this
       * component's own markup, and React would only strip them at the cost of a
       * client re-render of the logo — a visible flash on a surface that is meant to
       * hold the brand and nothing else.
       *
       * `suppressHydrationWarning` is scoped to this element's attributes and
       * text content; it does not silence hydration warnings from its children.
       */
      suppressHydrationWarning
    />
  );
}
