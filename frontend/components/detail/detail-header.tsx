/**
 * The Detail Screen's header: the trust row, the event's name, and when · where.
 *
 * **This is the top of the locked element order** (`EXPERIENCE.md` §12):
 *
 *   1. Source Badge
 *   2. Confidence Pulse
 *   3. Event name
 *   4. When · Where
 *
 * **The Source Badge comes before the Confidence Pulse**, even though the card renders
 * them in the other order (confidence, then badge). The order here is the locked one and
 * the screen follows it; the card's own order is the card's.
 *
 * **The confidence pulse is absent when there is no composition.** The pulse's value is
 * the persisted Relevance Pulse bucket — `why_this.bucket` — and there is no other
 * source for it on this screen. The Event Fit's bucket belongs to the anonymous preview
 * (AD-12), and reaching for it here would be exactly the substitution AD-10 calls
 * "company-ending": an authenticated surface falling back to the Event Fit to fill a
 * missing Relevance Pulse. So an anonymous visitor, and a signed-in user who was never
 * shown this event, see **no five-dot indicator at all**.
 */
import { TriggerTip } from "@/components/detail/trigger-tip";
import { sourceBadge } from "@/lib/digest-labels";
import type { DetailTimes } from "@/lib/detail-time";

/** The confidence indicator's five positions, always (`DESIGN.md` `component.indicator.confidence`). */
const CONFIDENCE_POSITIONS = 5;

export type DetailHeaderProps = {
  /** The event's title. */
  title: string;
  /** The venue's name, if there is one. */
  venueName: string | null;
  /** The venue's city, if there is one. */
  venueCity: string | null;
  /** The times, already resolved into the user's and (maybe) the venue's zones. */
  times: DetailTimes | null;
  /** Whether the source's time is under review. */
  approximate: boolean;
  /** The persisted Source Badge variant key, or `null` for a personal event. */
  sourceBadgeKey: string | null;
  /** The persisted Relevance Pulse bucket, or `null` when there is no composition. */
  confidence: number | null;
  /** The breakdown's factor lines, shown in the confidence tooltip. */
  factors: string[];
};

export function DetailHeader({
  title,
  venueName,
  venueCity,
  times,
  approximate,
  sourceBadgeKey,
  confidence,
  factors,
}: DetailHeaderProps) {
  const badge = sourceBadgeKey ? sourceBadge(sourceBadgeKey) : null;
  const place = venueName || venueCity || null;

  return (
    <header>
      {/* The trust row: the Source Badge and the Confidence Pulse, in the locked order.
          The badge is first because "where did this come from" is the first question a
          sceptical reader has. */}
      <div className="flex flex-wrap items-center gap-3">
        {badge ? <SourceBadgeView badge={badge} /> : null}
        {confidence !== null ? <ConfidenceView value={confidence} factors={factors} /> : null}
      </div>

      <h1 className="mt-4 text-ink-primary [font:var(--type-scale-display-md)]">{title}</h1>

      <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
        {times ? (
          <>
            {times.date} · {times.time}
            {times.venueTime ? (
              <>
                {" "}
                <span className="text-ink-muted">
                  ({times.venueTime} {times.venueZone})
                </span>
              </>
            ) : (
              <span className="text-ink-muted"> ({times.zone})</span>
            )}
          </>
        ) : (
          <span className="text-ink-muted">Time to be confirmed</span>
        )}
        {place ? <> · {place}</> : null}
        {approximate ? (
          <>
            {" · "}
            <span className="text-ink-muted">Time approximate</span>
          </>
        ) : null}
      </p>
    </header>
  );
}

/**
 * The Source Badge (`EXPERIENCE.md` §4 `Badge.Source`).
 *
 * **Every variant has a visible inline text label** — never icon-only (WCAG 1.1.1).
 *
 * **The chromatic colour is on the glyph; the label is ink.** `EXPERIENCE.md` §4
 * `Badge.Source` is the canonical list: *"`official_site`:
 * `color.accent.terracotta`-**filled checkmark icon**. Inline label "Official" in
 * `Text.Meta`."* The terracotta fills the **icon**; the label is plain meta text.
 *
 * **On this screen that distinction is load-bearing.** The Detail Screen's badge sits
 * directly on `color.surface.paper`, and in the light theme `color.accent.terracotta`
 * (`#C4502B`) is **4.37:1** on paper — under AA's 4.5:1 for text, over the 3:1 a
 * meaningful graphic needs. `color.signal.warn` (`#B8893A`) is **2.96:1** on paper, which
 * clears neither. So the colours live on the glyphs, where `EXPERIENCE.md` put them and
 * where they are legible, and the labels go back to ink. This is the same pattern the
 * design already uses for the sold-out badge (`DESIGN.md`: a `●` glyph in
 * `{color.signal.warn}` with the label in `{color.ink.secondary}`).
 */
function SourceBadgeView({ badge }: { badge: ReturnType<typeof sourceBadge> }) {
  const labelColour = badge.italic ? "text-ink-primary italic" : "text-ink-secondary";
  const glyphColour = badge.official
    ? "text-accent-terracotta"
    : badge.warn
      ? "text-signal-warn"
      : "text-ink-primary";

  return (
    <TriggerTip
      label={badge.label}
      tip={badge.tooltip}
      className={`gap-1 px-1 [font:var(--type-scale-meta-sm)] ${labelColour}`}
    >
      <span aria-hidden="true" className={glyphColour}>
        {badge.glyph === "check"
          ? "✓"
          : badge.glyph === "chain"
            ? "⚭"
            : badge.glyph === "inbox"
              ? "⌸"
              : "⚠"}
      </span>
      <span>{badge.label}</span>
    </TriggerTip>
  );
}

/**
 * The Confidence Pulse: five positions, always.
 *
 * **No visible numeric.** `EXPERIENCE.md` §4 says "Dots only. No numeric label visible."
 * The count is in the accessible name, where it belongs.
 *
 * **The tooltip carries the persisted factors, not an invented explanation.** The
 * `Indicator.Confidence` pattern's example text ("Strong match on your top three
 * interests. Within 2 km. Source reliability 0.92.") is the mockup's prose and it is
 * drift — none of those strings was persisted, and two of them are things this codebase
 * cannot compute at all (FR-16 is unbuilt; there are no coordinates). The factors shown
 * here are the same lines the breakdown shows, so the two cannot drift.
 */
function ConfidenceView({ value, factors }: { value: number; factors: string[] }) {
  const dots = Math.max(1, Math.min(CONFIDENCE_POSITIONS, Math.round(value)));

  return (
    <TriggerTip
      label={`Relevance ${dots} of ${CONFIDENCE_POSITIONS}`}
      tip={
        factors.length > 0 ? (
          <>
            <span className="block font-medium">Surfaced because:</span>
            {factors.map((factor) => (
              <span key={factor} className="block">
                {factor}
              </span>
            ))}
          </>
        ) : (
          <span className="block">{`Relevance ${dots} of ${CONFIDENCE_POSITIONS}`}</span>
        )
      }
      className="gap-1 px-1"
    >
      <span aria-hidden="true" className="flex items-center gap-1">
        {Array.from({ length: CONFIDENCE_POSITIONS }, (_, index) => (
          <span
            key={index}
            className={[
              "h-1.5 w-1.5 rounded-full",
              index < dots ? "bg-ink-primary" : "bg-ink-faint",
            ].join(" ")}
          />
        ))}
      </span>
      <span aria-hidden="true" className="[font:var(--type-scale-meta-sm)] text-ink-muted">
        Relevance
      </span>
    </TriggerTip>
  );
}
