"use client";

/**
 * `Card.PulseDigest` — the signature card of the product.
 *
 * **It is a projection, and it decides nothing.** Everything it shows was decided by the
 * composition service and persisted (AD-10). The card renders `DigestCardOut`: it does
 * not re-bucket the score, re-sort the tags, recompute the local date, or choose the
 * category. That is why the API sends the *bucket* and not the raw score — a client that
 * re-bucketed would be recomputing a persisted fact at render, which is the failure
 * AD-10 exists to prevent.
 *
 * **The explanation source is a required prop.** The Relevance Pulse (per-user, AD-10)
 * and the Event Fit (session-free, AD-12) look identical on screen and mean different
 * things, and AD-10 forbids substituting one for the other. So the caller must say which
 * it is, and the card names it — visibly and in the `aria-label`. A defaulted prop would
 * be exactly how one quietly became the other.
 *
 * **The trust signals never hide.** There is no density state, no `compact` variant and
 * no media-query branch that drops a signal. `EXPERIENCE.md` §13 is a locked
 * anti-pattern: "Adaptive density must not hide the trust signals … hover/focus/long-press
 * *add* detail but never *remove* the trust signals." Hover and focus add — the
 * tooltips appear, the `▸` appears — and nothing is removed.
 */

import Link from "next/link";

import type { components } from "@/lib/api/schema";
import { sourceBadge, tagLabel } from "@/lib/digest-labels";
import { cardTime } from "@/lib/detail-time";

type DigestCard = components["schemas"]["DigestCardOut"];

/**
 * Which explanation the card is carrying.
 *
 * **Required, and a union, not an optional flag.** The two indicators are rendered
 * identically — five dots — so the *words* are the only thing keeping them apart.
 */
export type Explanation =
  { kind: "relevance"; value: number } | { kind: "event_fit"; value: number };

export type PulseCardProps = {
  /** The persisted card row. The card renders it and decides nothing about it. */
  card: DigestCard;
  /** Which explanation the card carries. The caller must say. */
  explanation: Explanation;
};

/** The confidence indicator's five positions, always (`DESIGN.md` `component.indicator.confidence`). */
const CONFIDENCE_POSITIONS = 5;

/** The most Why-this Tags a card shows (`EXPERIENCE.md` §4: "up to 3 Why-this Tags"). */
export const MAX_WHY_THIS_TAGS = 3;

/**
 * The card's category, from the server's `slot` and `event_kind`.
 *
 * **The personal check comes first.** A personal event fills Slot 1 (`must_know`) when it
 * is eligible — the backend's own rule — so a slot-first mapping would give every
 * personal event the must-know amber stripe and the label "Must-know". The warm-personal
 * tone is the tone of the *kind*, not of the slot (FR-19).
 *
 * **`nearby` → the plain public stripe; `serendipity` → the discovery treatment.**
 * `DESIGN.md` names `color.accent.slate` as "the serendipity / discovery card category
 * stripe", and the PRD says Slot 3's tag reads `discovery` — so Slot 3 is the 0.85
 * opacity variant and `nearby` is the full-opacity one.
 */
export type Category = {
  /** The visible kicker label. Never the stripe alone (WCAG 1.4.1). */
  label: string;
  /** The stripe's Tailwind colour utility. */
  stripe: string;
  /** Whether the stripe is the discovery treatment (slate at 0.85). */
  discovery: boolean;
};

export function categoryFor(card: DigestCard): Category {
  if (card.event_kind === "personal") {
    return { label: "Personal", stripe: "bg-warm-personal", discovery: false };
  }
  if (card.slot === "must_know") {
    return { label: "Must-know", stripe: "bg-accent-amber", discovery: false };
  }
  if (card.slot === "serendipity") {
    return { label: "Public event", stripe: "bg-accent-slate", discovery: true };
  }
  return { label: "Public event", stripe: "bg-accent-slate", discovery: false };
}

export function PulseCard({ card, explanation }: PulseCardProps) {
  const category = categoryFor(card);
  const tags = card.tags.slice(0, MAX_WHY_THIS_TAGS);

  const title = card.title ?? "Event details unavailable";
  const place = card.venue_name || card.location || card.venue_city || null;
  const source = card.source_badge ? sourceBadge(card.source_badge) : null;

  const time = cardTime(card.start_time_utc, card.start_time_tz);
  const tooltipId = `confidence-${card.event_id}`;
  const badgeTooltipId = `badge-${card.event_id}`;

  return (
    <article
      className={[
        "fade-in group relative flex flex-col gap-3 rounded-card border border-border-subtle",
        "bg-surface-elevated p-4 md:p-6",
        // Hover swaps the fill and the border. **No shadow is ever added** (`DESIGN.md`
        // `component.surface.card`), and no transition class: `motion.fadeIn` is the
        // product's only transition.
        "hover:border-border-strong hover:bg-surface-subtle",
        "focus-within:border-border-strong",
      ].join(" ")}
    >
      {/* The 3px left-edge category stripe. It is decorative — the kicker below carries
          the same meaning in words, so colour is never the sole carrier (WCAG 1.4.1). */}
      <span
        aria-hidden="true"
        className={[
          "absolute inset-y-0 left-0 w-[3px] rounded-l-card",
          category.stripe,
          category.discovery ? "opacity-85" : "",
        ].join(" ")}
      />

      <div className="flex items-start justify-between gap-3">
        {/* The kicker: the category label, in `type.scale.meta.sm` and `color.ink.muted`.
            It is the stripe's other half. */}
        <p className="[font:var(--type-scale-meta-sm)] text-ink-muted">{category.label}</p>

        {/* The trust row: the conflict indicator, the confidence pulse and the source
            badge. All three are always present — none of them hides at any density.

            **`relative z-10` is load-bearing.** The stretched `<Link>` below is
            `absolute inset-0 z-0` and comes later in DOM order, so it paints *over*
            anything in the normal flow. Without this, the confidence and badge
            `<button>`s would be covered by the link and could never be pressed — the
            tooltips would be unreachable and the trust signals would be inert. Raising
            the row above the link is what makes the triggers clickable. */}
        <div className="relative z-10 flex items-center gap-2">
          {card.conflict ? <ConflictIndicator /> : null}
          <ConfidencePulse explanation={explanation} tags={tags} tooltipId={tooltipId} />
          {source ? <SourceBadgeBadge badge={source} tooltipId={badgeTooltipId} /> : null}
        </div>
      </div>

      <div className="flex items-start justify-between gap-3">
        <h3 className="text-ink-primary [font:var(--type-scale-headline-md)]">{title}</h3>
        {/* The `▸` is decorative information about tappability, not a click target of its
            own — the whole card is the tap target (`EXPERIENCE.md` §4). It is revealed on
            hover *and* on focus, so the desktop cue has a mobile equivalent and there
            are no hover-only affordances on small viewports. */}
        <span
          aria-hidden="true"
          className="mt-1 shrink-0 text-ink-faint opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
        >
          ▸
        </span>
      </div>

      {tags.length > 0 ? (
        <p className="[font:var(--type-scale-microtag)] text-ink-muted">
          {/*
            The separator is a **comma**, and it is real text in the DOM rather than a
            CSS pseudo-element. `EXPERIENCE.md` §7 says the tags are announced as
            comma-separated text, and §8 says visible helper text must be in the DOM —
            a `::after` would be visible to a sighted user and invisible to a screen
            reader, which is the regression the rule forbids. The middle dot the mockup
            uses would make the announcement "nearby dot tonight", so the mockup is the
            thing that changes.
          */}
          {tags.map((tag, index) => (
            <span key={tag}>
              {index > 0 ? ", " : null}
              {tagLabel(tag)}
            </span>
          ))}
        </p>
      ) : null}

      <p className="[font:var(--type-scale-meta-md)] text-ink-secondary">
        {time ? <>{time}</> : <span className="text-ink-muted">Time to be confirmed</span>}
        {place ? <> · {place}</> : null}
        {card.tz_review_pending ? (
          <>
            {" · "}
            <span className="text-ink-muted">Time approximate</span>
          </>
        ) : null}
      </p>

      {card.catalog_event_missing ? (
        <p className="[font:var(--type-scale-body-sm)] text-ink-muted">
          The source listing has changed, so some details are missing.
        </p>
      ) : null}

      {/* The whole card is the tap target. The link is stretched over the card so the hit
          area is the card; the tooltip triggers sit above it in the stacking order and
          stay clickable. */}
      <Link
        href={`/events/${card.event_id}`}
        aria-label={accessibleName({ card, category, tags, time, place, source, explanation })}
        className="absolute inset-0 z-0 rounded-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-terracotta"
      />
    </article>
  );
}

/**
 * The conflict indicator (`DESIGN.md` `component.indicator.conflict`).
 *
 * **6px, `color.warn.amber`, never red** — ASSUM-13 locks the size and `DESIGN.md` says
 * "Never red". It never collapses at any density (`EXPERIENCE.md` §13).
 *
 * **The ring is what distinguishes it from an unfilled confidence dot.** The confidence
 * dots are 6px circles too, and `DESIGN.md` requires the conflict mark to be "distinct in
 * shape and position". A ring in `color.ink.faint` — the dimmest ink, not a chromatic one
 * — does that without breaking the locked size and without inventing a colour.
 */
function ConflictIndicator() {
  return (
    <span
      role="img"
      aria-label="Schedule conflict"
      className="inline-flex h-6 w-6 items-center justify-center"
    >
      <span className="size-[6px] rounded-full bg-warn-amber ring-1 ring-ink-faint" />
    </span>
  );
}

/**
 * The confidence indicator: five positions, always.
 *
 * **No visible numeric.** `DESIGN.md` renders the count beside the dots and
 * `EXPERIENCE.md` says "Dots only. No numeric label visible." The number is in the
 * `aria-label`, where it belongs — and the visible label names *which* indicator it is,
 * because the Relevance Pulse and the Event Fit look identical on screen and AD-10
 * forbids substituting one for the other.
 *
 * **The tooltip's factors are the persisted tags.** AD-10 says an explanation is never
 * generated at view time, and the card cannot compute "strong match on your top three
 * interests" — that text was never persisted. The tags *are* the persisted contributing
 * factors; the full prose breakdown is the Detail Screen's job.
 */
function ConfidencePulse({
  explanation,
  tags,
  tooltipId,
}: {
  explanation: Explanation;
  tags: string[];
  tooltipId: string;
}) {
  const value = Math.max(1, Math.min(CONFIDENCE_POSITIONS, Math.round(explanation.value)));
  const name = explanation.kind === "relevance" ? "Relevance" : "Event Fit";

  return (
    <span className="group/confidence relative inline-flex items-center">
      <button
        type="button"
        aria-label={`${name} ${value} of ${CONFIDENCE_POSITIONS}`}
        aria-describedby={tooltipId}
        className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center"
      >
        <span aria-hidden="true" className="flex items-center gap-1">
          {Array.from({ length: CONFIDENCE_POSITIONS }, (_, index) => (
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
          carries no number, because the count belongs in the accessible name and not on
          the card. */}
      <span aria-hidden="true" className="[font:var(--type-scale-meta-sm)] text-ink-muted">
        {name}
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
          <span className="block">{`${name} ${value} of ${CONFIDENCE_POSITIONS}`}</span>
        )}
      </Tooltip>
    </span>
  );
}

/**
 * The Source Badge (`EXPERIENCE.md` §4 `Badge.Source`).
 *
 * **Always inline, never behind a tap**, and every variant has a **visible inline text
 * label** — never icon-only (WCAG 1.1.1).
 *
 * **The chromatic colour is on the glyph, and the label is ink.** `EXPERIENCE.md` §4
 * `Badge.Source` is the canonical list, and it says: *"`official_site`:
 * `color.accent.terracotta`-**filled checkmark icon**. Inline label "Official" in
 * `Text.Meta`."* — the terracotta fills the **icon**, and the label is plain meta text.
 * `DESIGN.md` §"Badges and indicators" says "terracotta label", which contradicts the
 * canonical list it cites; the canonical list wins, and it agrees with the design's own
 * `soldout-badge` precedent (`DESIGN.md`): a chromatic **glyph** paired with the label
 * in `color.ink.secondary`.
 *
 * **And it has to be that way, because the chromatic colours do not survive as text.**
 * In the light theme `color.accent.terracotta` is `#C4502B`, which is **4.37:1** against
 * `color.surface.paper` — below AA's 4.5:1 for text, though comfortably above the 3:1
 * that a meaningful **graphic** needs. `color.signal.warn` is worse: **2.96:1** on paper,
 * which fails even the non-text threshold. So the colours stay on the glyphs, where the
 * design put them and where they are legible, and the text goes back to ink.
 *
 * **This is the pattern `DESIGN.md` already uses** for the sold-out badge: *"a leading
 * `●` glyph in `{color.signal.warn}` … + label "Sold out" in `{type.scale.meta.sm}`
 * `{color.ink.secondary}`"*. The badge and the sold-out pill now read the same way.
 */
function SourceBadgeBadge({
  badge,
  tooltipId,
}: {
  badge: ReturnType<typeof sourceBadge>;
  tooltipId: string;
}) {
  const labelColour = badge.italic ? "text-ink-primary italic" : "text-ink-secondary";

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
        <BadgeGlyph glyph={badge.glyph} official={badge.official} warn={badge.warn} />
        {badge.label}
      </button>
      <Tooltip id={tooltipId}>{badge.tooltip}</Tooltip>
    </span>
  );
}

/** The badge's glyph. Each variant's shape is distinct from the others. */
function BadgeGlyph({
  glyph,
  official,
  warn,
}: {
  glyph: "check" | "chain" | "inbox" | "warning";
  official: boolean;
  warn: boolean;
}) {
  const colour = official
    ? "text-accent-terracotta"
    : warn
      ? "text-signal-warn"
      : "text-ink-primary";
  const shape = {
    check: "✓",
    chain: "⚭",
    inbox: "⌸",
    warning: "⚠",
  }[glyph];

  return (
    <span aria-hidden="true" className={colour}>
      {shape}
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
 * element it names, hidden or not.
 *
 * Reveal is on `:focus-within` rather than `:focus-visible`: tapping a button focuses it,
 * so a touch visitor gets the tooltip on tap, which is what `DESIGN.md` asks for.
 * Visibility is a swap, not an animation — the product has exactly one transition and it
 * is not this.
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
 * `EXPERIENCE.md` §4: "`aria-label` reads the full card content." It is assembled by one
 * function so the visible card and the announced card cannot drift — and it restates the
 * persisted facts rather than recomputing an explanation.
 */
function accessibleName({
  card,
  category,
  tags,
  time,
  place,
  source,
  explanation,
}: {
  card: DigestCard;
  category: Category;
  tags: string[];
  time: string | null;
  place: string | null;
  source: ReturnType<typeof sourceBadge> | null;
  explanation: Explanation;
}): string {
  const name = explanation.kind === "relevance" ? "Relevance" : "Event Fit";
  const parts = [
    card.title ?? "Event details unavailable",
    category.label,
    time,
    place,
    source ? `Source: ${source.label}` : null,
    `Confidence ${explanation.value} of ${CONFIDENCE_POSITIONS}`,
    name,
    tags.length > 0 ? `Why this: ${tags.map(tagLabel).join(", ")}` : null,
    card.conflict ? "Schedule conflict" : null,
  ];
  return parts.filter((part): part is string => Boolean(part)).join(". ");
}
