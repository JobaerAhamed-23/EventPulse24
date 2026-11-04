import Link from "next/link";

import type { components } from "@/lib/api/schema";
import { cardTime } from "@/lib/detail-time";
import { EVENT_FIT_MAX, clampEventFit } from "@/lib/event-fit";
import { EVENT_FIT_TOOLTIP, eventFitLabel, tagLabel } from "@/lib/preview-labels";

/**
 * One event on a city page.
 *
 * **This is the Pulse card's presentation, without the Pulse card.** The work item says
 * to reuse the public event card presentation rather than build a second one — the two
 * pages show the same noun and should not drift. So the *shape* is the same: the Event
 * Fit dots, the event's own time, the venue, the tags, the title linked to
 * `/events/{slug}` — and the shared helpers (`clampEventFit`, `cardTime`, `tagLabel`,
 * `eventFitLabel`) do the work rather than copied logic.
 *
 * **`PreviewCard` cannot be reused as-is, and the reasons are load-bearing.**
 *
 * - **It is `"use client"`, and it carries a Save button.** A Save button is a
 *   session-bound control: it cannot be rendered on a page that has no session (AD-12),
 *   and a page whose content depends on who is asking cannot be cached for everyone.
 * - **It carries a source badge, and `CityPageEventOut` has no `source_name`.** The
 *   badge would be a fact invented on the client (ASSUMPTION-9).
 *
 * **What is deliberately absent, and why:**
 *
 * - **No category stripe.** Must-know / Nearby / Discovery are *digest* categories,
 *   decided at composition time from a session. `PreviewCard`'s own docstring says a
 *   stripe on a session-free surface "would be a category invented on the client", and
 *   Amendment A-12 caps stripes at two and drops the discovery stripe.
 * - **No price.** The payload carries no price, so nothing here says "free".
 * - **No Save.** The page is a public document; the invitation to an account lives on
 *   the event's own page, once, where the event has been read in full.
 *
 * **The score and the tags are rendered as served** (AD-10). The backend computed them
 * when the Event Fit row was written; this card computes nothing and re-ranks nothing.
 */
export type CityEventCardProps = {
  event: components["schemas"]["CityPageEventOut"];
};

export function CityEventCard({ event }: CityEventCardProps) {
  const score = clampEventFit(event.score);
  const when = cardTime(event.start_time_utc, event.start_time_tz);

  return (
    <article
      className="flex flex-col gap-3 rounded-card border border-border-subtle bg-surface-elevated px-6 py-4"
      data-city-event
    >
      {/*
        **The Event Fit, as five dots and as words.**

        **The same control the Pulse card uses** — a trigger with an `aria-label` that
        names the value ("Event Fit 4 of 5") and a tooltip that explains what the number
        is. The dots alone would carry the meaning in shape and colour only.

        **It is a `<button>` here for the same reason it is there:** it is the trigger for
        the tooltip, and a tooltip needs a focusable trigger. It does nothing when
        pressed, and it is not a control that changes anything.
      */}
      <span className="group relative flex items-center gap-2">
        <button
          type="button"
          aria-label={eventFitLabel(score)}
          aria-describedby={`city-fit-${event.id}`}
          className="flex items-center gap-1"
        >
          {Array.from({ length: EVENT_FIT_MAX }, (_, index) => (
            <span
              key={index}
              aria-hidden="true"
              className={[
                "size-[6px] rounded-full",
                index < score ? "bg-ink-primary" : "bg-ink-faint",
              ].join(" ")}
            />
          ))}
        </button>
        <span aria-hidden="true" className="[font:var(--type-scale-meta-sm)] text-ink-muted">
          Event Fit
        </span>
        <span
          role="tooltip"
          id={`city-fit-${event.id}`}
          className="invisible absolute z-10 mt-1 block max-w-[260px] rounded-card bg-surface-elevated px-3 py-2 shadow-floating [font:var(--type-scale-meta-sm)] text-ink-secondary group-focus-within:visible group-hover:visible"
        >
          {EVENT_FIT_TOOLTIP}
        </span>
      </span>

      {/* The local start time, in the event's own zone, with the zone named: the server
          sends an instant and an IANA zone and does not guess a locale (AD-6). */}
      {when ? <p className="[font:var(--type-scale-meta-sm)] text-ink-muted">{when}</p> : null}

      <h3 className="[font:var(--type-scale-headline-sm)] text-ink-primary">
        <Link href={`/events/${event.slug}`} className="underline-offset-4 hover:underline">
          {event.title}
        </Link>
      </h3>

      {event.venue_name ? (
        <p className="[font:var(--type-scale-body-sm)] text-ink-secondary">{event.venue_name}</p>
      ) : null}

      {/*
        **The tags, as served.** The backend's tag keys are rendered through the shared
        `tagLabel`, so a tag the frontend has never seen still appears — this is a
        translation, not a filter.
      */}
      {event.tags.length > 0 ? (
        <p className="[font:var(--type-scale-microtag)] text-ink-muted">
          {event.tags.map((tag, index) => (
            <span key={tag}>
              {index > 0 ? <span aria-hidden="true"> · </span> : null}
              <span>{tagLabel(tag)}</span>
            </span>
          ))}
        </p>
      ) : null}

      {event.is_sold_out ? (
        <p className="[font:var(--type-scale-body-sm)] text-ink-secondary" data-city-sold-out>
          Sold out — tickets no longer available.
        </p>
      ) : null}
    </article>
  );
}
