/**
 * The **reliability legend** — the three readings the mockup puts in the page head.
 *
 * **Why it exists.** "trust · 3" on a row is an uninterpretable number unless the screen
 * says what a number means. The mockup ships a legend for exactly this reason
 * (`mockups/settings-sources-desktop.html:224-227`), and the design's own risk table names
 * the failure: *"a trust surface that overstates its own evidence is worse than no trust
 * surface."* A dot row without a legend is exactly that.
 *
 * **What the three readings mean.**
 *
 * - **5 = trusted** — the source has enough observations to be believed.
 * - **3 = ok** — the ordinary case: enough to use, not enough to lean on.
 * - **1 = low coverage** — the source has barely been seen, so its score is mostly prior.
 *
 * The wording is the mockup's own, and it is deliberately *not* a score out of five, a
 * percentage, or a claim about individual events. It describes how much evidence a
 * *source* has behind it.
 *
 * **The dots are the same dots the rows use.** The legend draws the same five-dot row with
 * the same two ink tokens (`--ink-primary` on, `--ink-faint` off), so the eye reads the
 * legend and the rows with one vocabulary. No new tokens, and no terracotta — the
 * terracotta is the Confidence Pulse's, and borrowing it here would make the two
 * different things look like the same thing.
 *
 * **The dots are decorative; the words carry the meaning.** Each item is a `<span>` with
 * visible text, so a screen reader reads "5 = trusted" without needing the dots announced.
 */
export type SourceTrustLegendProps = {
  /** Nothing — the legend is fixed. It is a reading aid, not a control. */
  className?: string;
};

const MAX_DOTS = 5;

/** The three readings, from most to least evidence. */
const READINGS: { band: number; label: string }[] = [
  { band: 5, label: "5 = trusted" },
  { band: 3, label: "3 = ok" },
  { band: 1, label: "1 = low coverage" },
];

export function SourceTrustLegend({ className }: SourceTrustLegendProps) {
  return (
    <ul
      className={`flex flex-wrap items-center gap-4 text-ink-muted [font:var(--type-scale-body-sm)] ${className ?? ""}`}
      aria-label="Reliability legend"
      data-trust-legend
    >
      {READINGS.map((reading) => (
        <li key={reading.band} className="flex items-center gap-2">
          <span className="inline-flex gap-[3px]" aria-hidden="true">
            {Array.from({ length: MAX_DOTS }, (_, index) => (
              <span
                key={index}
                className={
                  index < reading.band
                    ? "block size-[6px] rounded-full bg-ink-primary"
                    : "block size-[6px] rounded-full bg-ink-faint"
                }
              />
            ))}
          </span>
          <span>{reading.label}</span>
        </li>
      ))}
    </ul>
  );
}
