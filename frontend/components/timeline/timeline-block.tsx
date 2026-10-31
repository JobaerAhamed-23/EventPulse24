import Link from "next/link";

import { cardTime } from "@/lib/detail-time";
import type { TimelineBlock as TimelineBlockData } from "@/lib/timeline-read";

/**
 * `component.timeline.event-block` — one event on one day of the Timeline
 * (`DESIGN.md` §Timeline, `EXPERIENCE.md` §4 `Surface.Timeline`).
 *
 * **The stripe and the label always come together.** The 2px left stripe is
 * `color.warm.personal` for a personal event and `color.cool.public` for a public one,
 * and the block also carries the visible text label "Personal" / "Public event" in its
 * top-right corner. **Colour is never the sole carrier of meaning** (WCAG 1.4.1) — the
 * design says so twice, and the pairing is what makes the two kinds of block tellable
 * without colour vision.
 *
 * **The conflict indicator is a 6px filled amber circle**, `aria-label="Schedule
 * conflict"`, at the **top-left** — so it never covers the category label at the
 * top-right. The API has already decided whether it is there; the block draws it and
 * decides nothing.
 *
 * **The time is the event's own zone.** The week is cut in the *user's* zone, but the
 * block's time belongs to the event — a public event in Berlin shown to a user in Los
 * Angeles is on a different Los Angeles day than its own clock suggests, and rendering
 * it in the user's zone would contradict the cell it sits in. `cardTime` renders it in
 * `start_time_tz` on the server, so the server and the browser print the same string.
 */
export function TimelineBlockView({
  block,
  onEditPersonal,
}: {
  block: TimelineBlockData;
  /**
   * Opens the **Edit personal event** sheet for this block.
   *
   * **Only a personal block has one.** A public block routes to `/events/:id` instead —
   * a saved public event is edited there, not in the personal sheet.
   */
  onEditPersonal?: (block: TimelineBlockData) => void;
}) {
  const personal = block.kind === "personal";
  const name = block.name ?? "Event no longer available";
  const time = blockTime(block);

  // The accessible name is name + time + kind, and the indicator is named too. The
  // visible label ("Personal" / "Public event") is inside the name, so a screen reader
  // hears the same three things the sighted reader sees.
  const accessibleName = [name, time, personal ? "Personal" : "Public event"]
    .filter(Boolean)
    .join(", ");

  const body = (
    <>
      {/*
        The stripe. `aria-hidden` because the label beside it says what it is — the
        stripe is the second signal, never the only one.
      */}
      <span
        aria-hidden="true"
        className={[
          "absolute inset-y-0 left-0 w-[2px] rounded-l-subtle",
          personal ? "bg-warm-personal" : "bg-accent-slate",
        ].join(" ")}
      />

      {/*
        The conflict indicator, top-left, so the category label at the top-right stays
        readable. It is a `<span>` with a label of its own, and the visible dot is
        `aria-hidden` — the label is what a screen reader reads.
      */}
      {block.conflict ? (
        <span
          role="img"
          aria-label="Schedule conflict"
          className="absolute top-1 left-1 size-[6px] rounded-full bg-warn-amber"
        />
      ) : null}

      {/*
        The name. A single line, ellipsised on overflow — the timeline is denser than
        the digest, and a wrapped name would break the column's rhythm.
      */}
      <span
        className={[
          "block truncate [font:var(--type-scale-meta-md)] text-ink-primary",
          // The indicator's gutter, so a flagged block's name does not sit under it.
          block.conflict ? "pl-3" : "",
        ].join(" ")}
      >
        {name}
      </span>

      {time ? (
        <span className="block [font:var(--type-scale-meta-sm)] text-ink-muted">{time}</span>
      ) : null}

      {/*
        The category label, top-right. The one place the block says what kind of thing
        it is, in words.
      */}
      <span className="absolute top-1 right-1 [font:var(--type-scale-meta-sm)] text-ink-muted">
        {personal ? "Personal" : "Public event"}
      </span>
    </>
  );

  const className = [
    "relative block w-full rounded-subtle border border-border-subtle bg-surface-subtle",
    "px-3 py-2 pl-4 text-left",
    // **Hover swaps the fill** — the affordance is the fill, not a chevron. The
    // timeline is denser than the digest, and a chevron on every block would be noise.
    "hover:bg-surface-inset",
  ].join(" ");

  if (personal) {
    return (
      <button
        type="button"
        onClick={() => onEditPersonal?.(block)}
        aria-label={accessibleName}
        className={className}
      >
        {body}
      </button>
    );
  }

  return (
    <Link href={`/events/${block.id}`} aria-label={accessibleName} className={className}>
      {body}
    </Link>
  );
}

/**
 * A block's time line: "9:00 AM – 9:30 AM PDT".
 *
 * **The range when there is an end, the start alone when there is not.** `end_time_utc`
 * is nullable — an open-ended event has no end — and an open-ended event shows its
 * start, not a dash.
 *
 * **The zone's short name appears once, at the end.** `cardTime` prints the start in
 * the event's own zone with that zone's name; the end is printed in the same zone
 * without repeating it.
 */
export function blockTime(block: TimelineBlockData): string | null {
  const start = cardTime(block.start_time_utc, block.start_time_tz);
  if (!start) return null;

  if (!block.end_time_utc) return start;

  const end = cardTime(block.end_time_utc, block.start_time_tz);
  if (!end) return start;

  // `cardTime` prints "Tue, Nov 3 · 9:30 AM PST". The range wants the same clock and
  // the same zone, and **the zone's name once** — so both ends' inline zones come off
  // and one goes on at the end.
  //
  // **The zone is stripped by length, not by pattern.** A zone's short name is a
  // rendered string — it can be anything the platform's `Intl` says — so a regex
  // built from it would have to escape it, and a zone name carrying a metacharacter
  // would either throw or silently strip the wrong text. Counting the characters off
  // the end cannot go wrong.
  const zone = start.slice(start.lastIndexOf(" ") + 1);

  // The start's date and clock, without its trailing zone.
  const startClock = start.slice(start.indexOf(" · ") + 3);
  const startTime = startClock.endsWith(` ${zone}`)
    ? startClock.slice(0, startClock.length - zone.length - 1)
    : startClock;

  // The end's clock, without its trailing zone and without the date — the range
  // reads as one moment to another, so the date is named once, at the front.
  const endClock = end.slice(end.indexOf(" · ") + 3);
  const endTime = endClock.endsWith(` ${zone}`)
    ? endClock.slice(0, endClock.length - zone.length - 1)
    : endClock;

  // The start's date, without its clock.
  const startDate = start.slice(0, start.indexOf(" · "));

  return `${startDate} · ${startTime} – ${endTime} ${zone}`;
}
