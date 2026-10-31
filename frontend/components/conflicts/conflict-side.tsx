import { cardTime } from "@/lib/detail-time";
import type { ConflictSide as ConflictSideData } from "@/lib/conflict-wording";

/**
 * One side of a conflict pair.
 *
 * **The stripe and the label always come together.** The 2px left stripe is
 * `color.warm.personal` for a personal event and `color.accent.slate` for a saved
 * public one, and the side also carries the visible text label "Personal" / "Public
 * event" in its top-right corner. **Colour is never the sole carrier of meaning**
 * (WCAG 1.4.1) — the same rule the Timeline's blocks follow, and the reason the label
 * is text and not a swatch.
 *
 * **The time is the side's own zone.** The conflict list carries each side's display
 * zone (`start_time_tz` — the personal event's own zone, or the catalog event's zone for
 * a saved side), so the time is rendered the way the event itself is rendered. A pair
 * whose two sides live in two different zones shows two different clocks, and both are
 * true.
 *
 * **An unavailable side says so.** `available: false` means the side's record cannot be
 * read — its row is gone, or the catalog no longer publishes the event. There is no
 * title to show, so the side says "Event no longer available" rather than rendering a
 * blank name. The state is explicit instead of looking like an event with no title.
 */
export function ConflictSideView({ side }: { side: ConflictSideData }) {
  const personal = side.kind === "personal_event";
  const name = side.available
    ? (side.name ?? "Event no longer available")
    : "Event no longer available";

  // **The zone is the side's display zone**, and it is absent for an unavailable side —
  // the snapshot is UTC and the display zone is then genuinely unknown. `cardTime`
  // falls back to UTC rather than showing a zone it was never told.
  const time = cardTime(side.start_time_utc, side.start_time_tz);

  return (
    <div
      className={[
        "relative rounded-timeline-cell border border-border-subtle bg-surface-subtle",
        "px-4 py-3 pl-4",
      ].join(" ")}
    >
      {/*
        The stripe. `aria-hidden` because the label beside it says what it is — the
        stripe is the second signal, never the only one.
      */}
      <span
        aria-hidden="true"
        className={[
          "absolute inset-y-0 left-0 w-[2px] rounded-l-timeline-cell",
          personal ? "bg-warm-personal" : "bg-accent-slate",
        ].join(" ")}
      />

      {/*
        The category label, top-right. The one place the side says what kind of thing it
        is, in words.
      */}
      <span className="absolute top-3 right-3 [font:var(--type-scale-meta-sm)] text-ink-muted">
        {personal ? "Personal" : "Public event"}
      </span>

      <span className="block pr-20 [font:var(--type-scale-headline-sm)] text-ink-primary">
        {name}
      </span>

      {time ? (
        <span className="mt-1 block [font:var(--type-scale-meta-sm)] text-ink-muted">{time}</span>
      ) : null}
    </div>
  );
}
