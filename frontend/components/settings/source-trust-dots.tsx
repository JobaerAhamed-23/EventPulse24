/**
 * A source's **trust** — the 1–5 dots on `Settings → Sources`.
 *
 * **These are the reliability dots, and they are not the terracotta confidence pulse.**
 * The mockup says so in its own header, and it is worth repeating here because the two
 * look similar and mean different things: the **Confidence Pulse** is a card's own
 * confidence in one event, and the **trust dots** are how much we trust a *source*. They
 * are drawn in ink — `--ink-primary` for on, `--ink-faint` for off — because a
 * five-dot row is a reading of a quantity, and a colour would make it a mood.
 *
 * **No new tokens.** The dots reuse the two ink tokens the mockup names, and the label
 * reuses the mono face and the muted ink.
 *
 * **The band is the server's number.** `band` arrives in the response; the client draws
 * `band` filled dots and `5 - band` empty ones. It does not recompute the band from the
 * score — the boundaries are the server's rule, and a client that recomputed them would
 * be a second opinion about what a score means.
 *
 * **The dots are decorative; the group carries the name.** The dots are `aria-hidden`, and
 * the reading is on the group's `aria-label` — "N of 5 reliability" — so a screen reader
 * hears one sentence instead of five identical elements.
 */
export type SourceTrustDotsProps = {
  /** The trust band, 1–5. The server's number. */
  band: number;
};

const MAX_DOTS = 5;

export function SourceTrustDots({ band }: SourceTrustDotsProps) {
  // **Clamped, so a stray value cannot draw a broken row.** The server sends 1–5; a
  // value outside that is a bug, and rendering nine dots would be a worse answer than
  // rendering five.
  const filled = Math.max(0, Math.min(MAX_DOTS, Math.round(band)));

  return (
    <span
      className="inline-flex items-center gap-1"
      role="img"
      aria-label={`${filled} of ${MAX_DOTS} reliability`}
      data-trust-dots
    >
      <span className="inline-flex gap-[3px]" aria-hidden="true">
        {Array.from({ length: MAX_DOTS }, (_, index) => (
          <span
            key={index}
            className={
              index < filled
                ? "block size-[7px] rounded-full bg-ink-primary"
                : "block size-[7px] rounded-full bg-ink-faint"
            }
          />
        ))}
      </span>
      <span className="text-ink-muted [font:var(--type-family-mono)] text-[10px] tracking-[0.04em]">
        trust · {filled}
      </span>
    </span>
  );
}
