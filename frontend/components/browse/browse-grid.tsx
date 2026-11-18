import { BrowseCard } from "@/components/browse/browse-card";
import { eventCountLabel, windowDateLabel } from "@/lib/browse-labels";
import type { BrowseCard as BrowseCardOut, BrowseQuota } from "@/lib/browse-read";

/**
 * The Browse grid: two attention-tier sections, three columns.
 *
 * **The split is the server's.** `tier_2_starts_at` is where the second section begins
 * in the pool, and the server names it so the rule cannot drift from the Digest's idea
 * of "worth your attention" (AD-10). The client does not re-tier, does not re-sort, and
 * does not re-rank — it slices at the index the server gave.
 *
 * **It takes the cards to render, not the payload.** Amendment A-11's search filters
 * the loaded set, and a filter that reached only part of the surface would be a filter
 * that lied about how much it had narrowed. So the grid is given the cards it should
 * draw, and it draws them in the order they arrive — which is the server's order.
 *
 * **The split is a count of the pool's tier-one survivors, not a re-slice of the
 * server's index.** This is the one place the filter could quietly re-tier, and it is
 * the reason the grid takes `tierOneCount` rather than `tier_2_starts_at`: the server's
 * number is an index into the *pool*, and slicing the *filtered* list at it would
 * promote a tier-two card into tier one the moment the filter removed the pool's
 * tier-one cards. A filter makes tier one smaller; it never makes it longer.
 *
 * **One `<ul>` per section, not one `<ul>` with headings inside it.** A list whose
 * children are headings and `<li>`s is not a list, and the `list` axe rule is *serious* —
 * a screen reader would announce the cards as ungrouped text and the count of the
 * city's events would be lost with them. The city page's own a11y test has a mutation
 * probe for exactly that mistake.
 *
 * **The grid gains a column at each step, and the steps now reach past `lg`.**
 * Amendment A-12 asks for three columns at ≥1280px and two at 1024-1279px, and
 * `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` still serves that range unchanged.
 *
 * **Above `lg` it used to serve nothing, and that is what made the cards look wrong.**
 * `lg` was the last breakpoint the token file declared, so three columns was also the
 * answer at 1920px and at 2560px — the grid kept the column *count* and stretched each
 * column instead, to 739px at 2560px against the same card's 312px at 1280px. The card
 * never changed; there was simply no rule above it. `xl: 1440px` and `2xl: 2048px` are
 * now declared, and this grid uses them to add a fourth and a fifth column, so a card
 * stays a card at every width instead of growing into the space.
 */
export type BrowseGridProps = {
  /** The cards to render, in the server's order. */
  cards: BrowseCardOut[];
  /**
   * How many of these cards belong to the first section.
   *
   * **This is the count of the pool's tier-one cards that survived the filter, not the
   * server's raw split index.** The server's `tier_2_starts_at` is an index into the
   * pool it sent; when a search narrows the pool, the first section holds however many
   * of the pool's tier-one cards are left. A filter that removes a tier-one card makes
   * tier one smaller — it does not promote the next card up.
   */
  tierOneCount: number;
  /** The pool's size, for the second section's count. */
  total: number;
  /**
   * Whether a search is narrowing the pool.
   *
   * **The second section's count is the pool's tier-two size, and that changes under a
   * filter.** Unfiltered, the meta reads "144 events" — the pool's tier-two size, which
   * is what the mockup shows. Filtered, that number would head a grid of two cards
   * while the count line above said "2 events matched", and the page would contradict
   * itself twice over. Under a filter the meta counts what the section holds.
   */
  filtered: boolean;
  /**
   * The save allowance, as the payload states it.
   *
   * **It travels with the cards because every card's Save button reads it.** A Pro
   * account's `cap` is `null` and it never sees the wall; a Free account whose
   * allowance is spent sees it on every card. The number is the server's, and the
   * server's gate is still the gate.
   *
   * **The generated type.** `BrowseQuota` is the contract the server published, so
   * this copy of the shape cannot drift from the payload that carries it.
   */
  quota: BrowseQuota;
  /** The city's name, for the first section's meta. */
  city: string;
  /** The window's first instant, for the first section's meta. */
  windowFrom: string;
  /** The user's zone, for the first section's meta. */
  timezone: string;
};

export function BrowseGrid({
  cards,
  tierOneCount,
  total,
  filtered,
  quota,
  city,
  windowFrom,
  timezone,
}: BrowseGridProps) {
  // **The split is the count, not a re-slice of the server's index.** The grid draws
  // the first `tierOneCount` cards in the first section and the rest in the second, and
  // the count is the server's tiering filtered by the reader's query — never the
  // client's own opinion about which cards deserve the top section.
  const split = Math.max(0, Math.min(tierOneCount, cards.length));
  const first = cards.slice(0, split);
  const rest = cards.slice(split);

  const dateLabel = windowDateLabel(windowFrom, timezone);
  // **The section's own count, not the not-yet-loaded remainder.** The mockup settles
  // it: the hero pill says "147 events this week" and the second section's meta says
  // "144 events" — and 147 − 3 (the first section's cards) is 144. So N is the number
  // of events *in the second section*, which is the pool's tier-2 size.
  //
  // Reading it as "what is still to come" would announce "16 events" above a grid of 21
  // cards — a heading that contradicts the thing it heads.
  //
  // **Under a filter, the pool's tier-two size is the wrong number.** The section holds
  // the *matching* cards, so the meta counts those — the same number the count line
  // above it reports, which is what makes the two agree.
  const tierTwoTotal = filtered ? rest.length : Math.max(0, total - tierOneCount);

  return (
    <>
      {/*
        **Section 1 — "3 worth your attention today".**

        **The count is not in the heading.** The heading names a *section*, and the server
        decided how many cards it holds; a heading that said "5 worth your attention"
        would be a number that changes with the pool. The mono meta carries the city's
        own facts instead.

        **The section head exists only when there is a section 1.** The same rule section
        2 follows: a heading over an empty list is a heading that lies. A later chunk
        has no tier 1 at all — the server's split is `max(0, min(3 - offset, len(cards)))`,
        so every card past the first three is tier 2 — and an empty "3 worth your
        attention today" over nothing would be the loudest lie on the page.
      */}
      {first.length > 0 ? (
        <section aria-labelledby="browse-tier-1" data-browse-section="tier-1">
          <div className="flex flex-wrap items-baseline justify-between gap-3 pb-6 pt-8">
            <h2
              id="browse-tier-1"
              className="text-ink-primary [font:var(--type-scale-headline-lg)]"
            >
              3 worth your attention today
            </h2>
            <p className="[font-family:var(--type-family-mono)] text-ink-muted [font:var(--type-scale-meta-sm)]">
              {[city, dateLabel].filter(Boolean).join(" · ")}
            </p>
          </div>

          <ul className="grid grid-cols-1 gap-[20px] md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {first.map((card) => (
              <li key={card.event_id} className="flex">
                <BrowseCard card={card} quota={quota} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/*
        **Section 2 — "More this week".**

        **The section head exists only when there is a section 2.** A heading over nothing
        is a heading that lies: "More this week" with no more in it would be a promise
        the page cannot keep.

        **The meta counts the section's own events** — "N events · scroll for more" —
        where N is the pool's tier-2 size, which is what the mockup shows ("147 events
        this week" in the pill, "144 events" here, and 147 − 3 = 144). The
        "scroll for more" half is the affordance, and it only appears while there is
        more to scroll to.
      */}
      {rest.length > 0 || tierTwoTotal > 0 ? (
        <section aria-labelledby="browse-tier-2" data-browse-section="tier-2">
          <div className="flex flex-wrap items-baseline justify-between gap-3 pb-6 pt-12">
            <h2
              id="browse-tier-2"
              className="text-ink-primary [font:var(--type-scale-headline-lg)]"
            >
              More this week
            </h2>
            <p className="[font-family:var(--type-family-mono)] text-ink-muted [font:var(--type-scale-meta-sm)]">
              {tierTwoTotal > rest.length
                ? `${eventCountLabel(tierTwoTotal)} · scroll for more`
                : `${eventCountLabel(rest.length)}`}
            </p>
          </div>

          <ul className="grid grid-cols-1 gap-[20px] md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {rest.map((card) => (
              <li key={card.event_id} className="flex">
                <BrowseCard card={card} quota={quota} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
