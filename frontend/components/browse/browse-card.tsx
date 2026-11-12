import Link from "next/link";

import { stripeColour, stripeLabel } from "@/lib/browse-labels";
import type { BrowseCard as BrowseCardOut, BrowseQuota } from "@/lib/browse-read";
import { BrowseSave } from "@/components/browse/browse-save";
import { MAX_WHY_THIS_TAGS } from "@/components/digest/pulse-card";
import { EventStateBadge } from "@/components/state/event-state-badge";
import { sourceBadge, tagLabel } from "@/lib/digest-labels";
import { cardTime } from "@/lib/detail-time";
import { cardStateFor, STATE_LABELS, type CardState } from "@/lib/event-state";

/**
 * One card on Browse — `component.card.pulse.digest`'s anatomy, at the denser Browse
 * sizing (Amendment A-12).
 *
 * **It renders the payload and decides nothing.** The card shows the server's
 * `confidence` bucket, the server's `stripe`, the server's `tags` and the server's
 * ordering. It does not score, re-bucket, re-sort, or recompute a local date (AD-10).
 *
 * **The indicator is the Relevance Pulse, and it says so.** Browse is an authed surface
 * whose first section head reads *"3 worth your attention today"* — *your* — so its
 * cards carry the personal explanation. The Event Fit is the stranger's score, computed
 * blind to who is looking, and AD-10 forbids substituting one for the other. The label
 * beside the dots is "Relevance", exactly as `PulseCard` says it, because the two
 * indicators look identical on screen and the words are the only thing keeping them
 * apart.
 *
 * **Two stripes, two colours, and no discovery.** Amendment A-12 caps the stripes at
 * slate (public) and amber (must-know) and drops the discovery stripe outright: three
 * stripe colours would be a category-colour flood, and the anti-pattern list bans it.
 *
 * **The card says no price.** The payload carries no price, so the card says nothing
 * about one — the mockup's "Free" is a persona's invention.
 *
 * **The Save button is an island, and the card stays a server component.** The button
 * holds a state machine and talks to the API, so it cannot be rendered on the server —
 * but an island can be mounted inside a server component's markup, and the card hands
 * it the payload's facts. The card decides nothing about the save: the quota is the
 * server's number, and the server's gate is the gate.
 */
export type BrowseCardProps = {
  /** The server's card. */
  card: BrowseCardOut;
  /**
   * The save allowance, as the payload states it.
   *
   * **It travels with the card because every card's Save button reads it.** A Pro
   * account's `cap` is `null` and it never sees the wall; a Free account whose
   * allowance is spent sees it on every card. The number is the server's, and the
   * server's gate is still the gate — the client renders the wall, it does not decide
   * whether a save is allowed.
   *
   * **The generated type.** `BrowseQuota` is the contract the server published, so
   * this copy of the shape cannot drift from the payload that carries it.
   */
  quota: BrowseQuota;
};

export function BrowseCard({ card, quota }: BrowseCardProps) {
  const stripe = card.stripe;
  const when = cardTime(card.start_time_utc, card.start_time_tz);
  const source = card.source_badge ? sourceBadge(card.source_badge) : null;
  const place = card.venue_name || card.venue_city || null;
  const tags = card.tags.slice(0, MAX_WHY_THIS_TAGS);
  // **The tooltip ids are the event's, not the card's shape.** A confidence bucket is
  // 1–5 and the tags come from a fixed vocabulary, so an id built from them collides
  // on every grid — `browse-badge-Official` was the same string on every official card
  // on the page. A DOM `id` must be unique, and `aria-describedby` resolves to the
  // *first* match, so a card's description was another card's element. The house
  // pattern is `pulse-card.tsx`'s, and this now matches it.
  const confidenceTooltipId = `browse-confidence-${card.event_id}`;
  const badgeTooltipId = `browse-badge-${card.event_id}`;
  // **The card's state, if it has one.** The Browse payload carries `status` but not
  // `is_sold_out`, so the sold-out branch cannot fire here — and a badge for a state
  // the payload cannot express would be a badge invented by the client.
  const state = cardStateFor(card.status, false);
  // **One clamp, three consumers.** The dots, the button's accessible name and the
  // card's accessible name all read this one value, so the card cannot say "1 of 5" in
  // one place and "0 of 5" in another.
  const confidence = Math.max(1, Math.min(5, Math.round(card.confidence)));

  return (
    <article
      className={[
        "fade-in group relative flex flex-col gap-3 rounded-card border border-border-subtle",
        "bg-surface-elevated px-[22px] py-[22px]",
        // Hover swaps the fill and the border. **No shadow is ever added** and **no
        // transition class**: `motion.fadeIn` is the product's only transition, and the
        // architecture test scans every `.tsx` for `transition-*`/`duration-*`/`ease-*`.
        "hover:border-border-strong hover:bg-surface-subtle",
        "focus-within:border-border-strong",
      ].join(" ")}
      data-browse-card
    >
      {/* The 3px left-edge stripe. It is decorative — the kicker below carries the same
          meaning in words, so colour is never the sole carrier (WCAG 1.4.1). */}
      <span
        aria-hidden="true"
        className={["absolute inset-y-0 left-0 w-[3px] rounded-l-card", stripeColour(stripe)].join(
          " ",
        )}
      />

      <div className="flex items-start justify-between gap-3">
        {/* The kicker: the stripe's other half, in words. */}
        <p className="[font:var(--type-scale-meta-sm)] text-ink-muted" data-browse-stripe-label>
          {stripeLabel(stripe)}
        </p>

        {/* The trust row: the confidence pulse and the source badge. Both are always
            present — no density state hides a trust signal.

            **`relative z-10` is load-bearing.** The stretched `<Link>` below is
            `absolute inset-0 z-0` and comes later in DOM order, so it paints over
            anything in the normal flow. Without the raise, the confidence trigger would
            be covered by the link and could never be pressed. */}
        <div className="relative z-10 flex items-center gap-2">
          <ConfidencePulse value={confidence} tags={tags} tooltipId={confidenceTooltipId} />
          {source ? <SourceBadgeBadge badge={source} tooltipId={badgeTooltipId} /> : null}
        </div>
      </div>

      {/*
        **The state badge, in its own row above the title.** Not the trust row — that
        row is at capacity with the confidence pulse and the source badge, and the
        design puts this badge in its own row for exactly that reason.
        *
        **Without it, a cancelled event lies.** The server routes cancelled and
        postponed events to the *amber* stripe, so a cancelled event renders as a
        "Must-know" card with nothing on it saying it was cancelled — for a sighted
        reader the state was invisible, and only the link's accessible name carried it.
        * `component.card.pulse.digest`'s anatomy includes this badge, and Browse
        borrows that anatomy.
        *
        **The badge is `aria-hidden`, and the link carries the state.** That is the
        design's own resolution (A-22): the badge is what makes the state legible at a
        glance and satisfies WCAG 1.4.1, and the link — the thing the reader activates
        — is what says it in words. The same fact is not announced twice.
        */}
      {state ? (
        <div className="flex items-start">
          <EventStateBadge state={state} />
        </div>
      ) : null}

      <div className="flex items-start justify-between gap-3">
        {/*
          **The headline, at Browse's 18px** — down from the digest's 22px, because a
          three-column grid gives each card less width and the smaller measure keeps the
          title legible. Amendment A-12's sizing tweak, and it is the only size in this
          card that the digest does not share.
        */}
        <h3 className="text-ink-primary [font:var(--type-scale-headline-sm)]">{card.title}</h3>
        <span
          aria-hidden="true"
          className="mt-1 shrink-0 text-ink-faint opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
        >
          ▸
        </span>
      </div>

      {/*
        **The why-tags, in the server's order.** The tags are the persisted contributing
        factors, and the order is the priority order — re-sorting them here would be a
        client-side decision (AD-10).

        **The separator is a comma, and it is real text.** The same rule `PulseCard`
        follows: a `::after` would be visible to a sighted user and invisible to a screen
        reader, which is the regression the rule forbids.
      */}
      {tags.length > 0 ? (
        <p className="[font:var(--type-scale-microtag)] text-ink-muted" data-browse-tags>
          {tags.map((tag, index) => (
            <span key={tag}>
              {index > 0 ? ", " : null}
              {tagLabel(tag)}
            </span>
          ))}
        </p>
      ) : null}

      <p className="[font:var(--type-scale-meta-md)] text-ink-secondary">
        {when ? <>{when}</> : <span className="text-ink-muted">Time to be confirmed</span>}
        {place ? <> · {place}</> : null}
        {card.tz_review_pending ? (
          <>
            {" · "}
            <span className="text-ink-muted">Time approximate</span>
          </>
        ) : null}
      </p>

      {/*
        **The Save slot.** The affordance is its own island, mounted here in the slot the
        grid work item reserved.
        *
        **The island can be mounted inside a server component's markup, and this card
        stays one.** The button holds a state machine and talks to the API, so it cannot
        be a server component — but the card can hand it the payload's facts and let it
        be the only client on the card.
        *
        **The card's facts go down, and the card decides nothing.** `event_id` is the
        **catalog** id — the path parameter the endpoint takes — and `is_saved` is the
        first paint's state, so an already-saved event never flashes "Save".
      */}
      <div className="relative z-10 flex items-start justify-end" data-browse-save-slot>
        <BrowseSave
          eventId={card.event_id}
          eventName={card.title}
          slug={card.slug}
          saved={card.is_saved}
          quota={quota}
        />
      </div>

      {/* The whole card is the tap target. The link is stretched over the card so the
          hit area is the card; the trust triggers sit above it in the stacking order and
          stay clickable. */}
      <Link
        href={`/events/${card.event_id}`}
        aria-label={accessibleName({ card, when, place, source, tags, state, confidence })}
        className="absolute inset-0 z-0 rounded-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-terracotta"
      />
    </article>
  );
}

/**
 * The confidence indicator: five positions, always.
 *
 * **No visible numeric.** The number is in the `aria-label`, where it belongs, and the
 * visible label names *which* indicator it is.
 */
function ConfidencePulse({
  value,
  tags,
  tooltipId,
}: {
  /** The **clamped** bucket. Computed once by the caller, so the dots, the button's
      accessible name and the card's accessible name cannot disagree. */
  value: number;
  tags: string[];
  /** The event's own id — a DOM id must be unique, and this one is per card. */
  tooltipId: string;
}) {
  const positions = 5;

  return (
    <span className="group/confidence relative inline-flex items-center">
      <button
        type="button"
        aria-label={`Relevance ${value} of ${positions}`}
        aria-describedby={tooltipId}
        className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center"
      >
        <span aria-hidden="true" className="flex items-center gap-1">
          {Array.from({ length: positions }, (_, index) => (
            <span
              key={index}
              className={[
                "size-[6px] rounded-full",
                index < value ? "bg-ink-primary" : "bg-ink-faint",
              ].join(" ")}
            />
          ))}
        </span>
      </button>
      {/* The label names the indicator, so the dots are never the only signal — and it
          carries no number, because the count belongs in the accessible name. */}
      <span aria-hidden="true" className="[font:var(--type-scale-meta-sm)] text-ink-muted">
        Relevance
      </span>
      <Tooltip id={tooltipId}>
        {tags.length > 0 ? (
          <>
            <span className="block font-medium">Surfaced because:</span>
            {tags.map((tag) => (
              <span key={tag} className="block">
                {tagLabel(tag)}
              </span>
            ))}
          </>
        ) : (
          <span className="block">{`Relevance ${value} of ${positions}`}</span>
        )}
      </Tooltip>
    </span>
  );
}

/**
 * The Source Badge — `DESIGN.md` `Badge.Source`.
 *
 * **The chromatic colour is on the glyph and the label is ink.** The terracotta fills
 * the icon, and the label is plain meta text — the same pattern `PulseCard` uses, for
 * the same reason: in the light theme the terracotta is 4.37:1 on paper, which is
 * under AA's 4.5:1 for text.
 *
 * **The `warn` variant keeps its warning colour.** A `crawled_html` source is
 * "Unverified", and `sourceBadge()` exposes `warn` for exactly this branch; without it
 * the ⚠ rendered in plain ink and the badge lost the one signal that separates it from
 * a merely-official source. This is `PulseCard`'s `BadgeGlyph`, unchanged.
 */
function SourceBadgeBadge({
  badge,
  tooltipId,
}: {
  badge: ReturnType<typeof sourceBadge>;
  /** The event's own id — a DOM id must be unique, and this one is per card. */
  tooltipId: string;
}) {
  const labelColour = badge.italic ? "text-ink-primary italic" : "text-ink-secondary";
  const glyphColour = badge.official
    ? "text-accent-terracotta"
    : badge.warn
      ? "text-signal-warn"
      : "text-ink-primary";

  return (
    <span className="group/badge relative inline-flex items-center">
      <button
        type="button"
        aria-describedby={tooltipId}
        className={[
          "inline-flex min-h-[44px] items-center gap-1 rounded-control px-1",
          "[font:var(--type-scale-meta-sm)]",
          labelColour,
        ].join(" ")}
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
        {badge.label}
      </button>
      <Tooltip id={tooltipId}>{badge.tooltip}</Tooltip>
    </span>
  );
}

/**
 * The hand-rolled tooltip from `DESIGN.md`: a `<button>` trigger with `aria-describedby`
 * pointing at a sibling `<span role="tooltip">`. No tooltip library — "UI system: None"
 * is binding.
 *
 * **It stays in the DOM and is revealed on hover or focus.** Removing it would break the
 * `aria-describedby` it is the target of. The reveal is a visibility swap, not an
 * animation: the product has exactly one transition and it is not this.
 */
function Tooltip({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <span
      role="tooltip"
      id={id}
      className="invisible absolute z-10 mt-1 block max-w-[260px] rounded-card bg-surface-elevated px-3 py-2 shadow-floating [font:var(--type-scale-meta-sm)] text-ink-secondary group-focus-within/confidence:visible group-hover/confidence:visible group-focus-within/badge:visible group-hover/badge:visible"
    >
      {children}
    </span>
  );
}

/**
 * The card's accessible name: the whole card, in words.
 *
 * It restates the payload's facts rather than recomputing an explanation — the same
 * rule `PulseCard` follows.
 *
 * **The indicator is named "Relevance", and the name uses the clamped value.** The
 * visible card says "Relevance" and the inner button says "Relevance N of 5"; an
 * accessible name that said "Confidence 4 of 5. Relevance." gave one indicator two
 * names, and "Confidence" appears nowhere on the visible card. The clamp is the *same*
 * one the button applies — one field, one rule, so the card cannot say 0 of 5 in one
 * place and 1 of 5 in another.
 */
function accessibleName({
  card,
  when,
  place,
  source,
  tags,
  state,
  confidence,
}: {
  card: BrowseCardOut;
  when: string | null;
  place: string | null;
  source: ReturnType<typeof sourceBadge> | null;
  tags: string[];
  state: CardState | null;
  confidence: number;
}): string {
  const parts = [
    card.title,
    stripeLabel(card.stripe),
    when,
    place,
    source ? `Source: ${source.label}` : null,
    `Relevance ${confidence} of 5`,
    tags.length > 0 ? `Why this: ${tags.map(tagLabel).join(", ")}` : null,
    // The badge is `aria-hidden`, so this is where the state is spoken.
    state ? STATE_LABELS[state] : null,
    card.is_saved ? "Saved" : null,
  ];
  return parts.filter((part): part is string => Boolean(part)).join(". ");
}
