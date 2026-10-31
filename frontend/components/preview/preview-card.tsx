"use client";

/**
 * One Pulse Preview card.
 *
 * **This is deliberately the smallest card the preview needs**, so the Pulse Digest
 * intent can extend it rather than fork it. What it does *not* have is as considered as
 * what it does:
 *
 * - **No category stripe.** Must-know / Nearby / Discovery are digest categories, decided
 *   at composition time from a session. `PreviewCardOut` carries none, and cannot (AD-12)
 *   — so a stripe here would be a category invented on the client.
 * - **No Relevance Pulse.** AD-10 names two indicators that look identical on screen and
 *   forbids substituting one for the other. This page has the session-free **Event Fit**
 *   and says so in as many words.
 * - **No price.** Catalog events have no price field, so nothing here says "free".
 */

import Link from "next/link";

import type { components } from "@/lib/api/schema";
import { EVENT_FIT_MAX, clampEventFit } from "@/lib/event-fit";
import { EVENT_FIT_TOOLTIP, eventFitLabel, sourceBadge, tagLabel } from "@/lib/preview-labels";
import { cardTime } from "@/lib/detail-time";

type Card = components["schemas"]["PreviewCardOut"];

export type PreviewCardProps = {
  card: Card;
  /** What the Save button does. The soft wall belongs to the section, not the card. */
  onSave: () => void;
  /** The line under Save after it has been used, if any. */
  savedNote?: string | null;
};

export function PreviewCard({ card, onSave, savedNote = null }: PreviewCardProps) {
  const badge = sourceBadge(card.source_badge);
  const score = clampEventFit(card.score);
  const tooltipId = `fit-${card.id}`;
  const badgeTooltipId = `badge-${card.id}`;

  return (
    <article className="flex flex-col gap-3 rounded-card border border-border-subtle bg-surface-elevated px-6 py-4">
      <div className="flex items-center justify-between gap-3">
        <EventFitDots score={score} tooltipId={tooltipId} />
        <span className="group relative">
          <button
            type="button"
            aria-describedby={badgeTooltipId}
            className={[
              "rounded-control border px-2 py-1 [font:var(--type-scale-meta-sm)]",
              badge.unverified
                ? "border-signal-warn text-ink-secondary"
                : "border-border-subtle text-ink-secondary",
            ].join(" ")}
          >
            {badge.unverified ? <span aria-hidden="true">⚠ </span> : null}
            {badge.label}
          </button>
          <Tooltip id={badgeTooltipId}>
            {badge.tooltip} Source: {card.source_name}.
          </Tooltip>
        </span>
      </div>

      {/* The local start time, in the event's own zone, with the zone named: the server
          sends an instant and an IANA zone and does not guess a locale (AD-6). */}
      <p className="[font:var(--type-scale-meta-sm)] text-ink-muted">
        {cardTime(card.start_time_utc, card.start_time_tz)}
      </p>

      <h3 className="[font:var(--type-scale-headline-sm)] text-ink-primary">
        <Link href={`/events/${card.slug}`} className="underline-offset-4 hover:underline">
          {card.title}
        </Link>
      </h3>

      {card.venue_name ? (
        <p className="[font:var(--type-scale-body-sm)] text-ink-secondary">{card.venue_name}</p>
      ) : null}

      {card.tags.length > 0 ? (
        <p className="[font:var(--type-scale-microtag)] text-ink-muted">
          {card.tags.map((tag, index) => (
            <span key={tag}>
              {index > 0 ? <span aria-hidden="true"> · </span> : null}
              <span>{tagLabel(tag)}</span>
            </span>
          ))}
        </p>
      ) : null}

      <div className="mt-1 flex items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          className="rounded-control border border-border-subtle px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
        >
          Save
        </button>
        <span className="[font:var(--type-scale-body-sm)] text-ink-muted">
          {savedNote ?? "We'll hold your seat."}
        </span>
      </div>
    </article>
  );
}

/**
 * The Event Fit, as five dots and as words.
 *
 * The dots alone would carry the meaning in shape and colour only, so the label is
 * visible ("Event Fit") and the value is in the `aria-label` ("Event Fit 4 of 5") rather
 * than left to be counted.
 */
function EventFitDots({ score, tooltipId }: { score: number; tooltipId: string }) {
  return (
    <span className="group relative flex items-center gap-2">
      <button
        type="button"
        aria-label={eventFitLabel(score)}
        aria-describedby={tooltipId}
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
      {/* Inside the group, so hovering or focusing the trigger reveals it. */}
      <Tooltip id={tooltipId}>{EVENT_FIT_TOOLTIP}</Tooltip>
    </span>
  );
}

/**
 * The hand-rolled tooltip from `DESIGN.md`: a `<button>` trigger with `aria-describedby`
 * pointing at a sibling `<span role="tooltip">`. No tooltip library — "UI system: None"
 * is binding.
 *
 * **It is hidden until the trigger is hovered or focused, and it stays in the DOM.** Both
 * halves matter. Showing it always would make it a caption, and two permanent
 * explanations would crowd a card whose whole point is calm. Removing it from the DOM
 * would break the `aria-describedby` it is the target of — a description is read from the
 * element it names, hidden or not, so keeping it present is what makes the trigger's
 * label complete for a screen reader.
 *
 * Reveal is on `:focus-within` rather than `:focus-visible`: tapping a button focuses it,
 * so a touch visitor gets the tooltip on tap, which is what `DESIGN.md` asks for ("on
 * touch viewports, tooltips appear on tap"). Visibility is a swap, not an animation —
 * the product has exactly one transition and it is not this.
 */
function Tooltip({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <span
      role="tooltip"
      id={id}
      className="invisible absolute z-10 mt-1 block max-w-[260px] rounded-card bg-surface-elevated px-3 py-2 shadow-floating [font:var(--type-scale-meta-sm)] text-ink-secondary group-focus-within:visible group-hover:visible"
    >
      {children}
    </span>
  );
}
