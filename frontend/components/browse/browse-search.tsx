"use client";

import { useMemo, useState } from "react";

import { BrowseGrid } from "@/components/browse/browse-grid";
import { BrowseMore } from "@/components/browse/browse-more";
import { BrowseSearchEmpty } from "@/components/browse/browse-states";
import { api } from "@/lib/backend-client";
import {
  filterCards,
  isEmptyQuery,
  querySummary,
  queryTerms,
  survivingTierOneCount,
  tokenize,
  type SearchQuery,
} from "@/lib/browse-search";
import type { BrowseCard as BrowseCardOut, BrowseQuota } from "@/lib/browse-read";
import { SEARCH_TAG_VOCABULARY } from "@/lib/digest-labels";

/**
 * The Browse surface's inline keyword search — Amendment A-11.
 *
 * **One input, and it is the only filter surface on this page.** There is no chip rail,
 * no date picker and no preset toggle; the city page's filter vocabulary does not
 * migrate to the authed Browse surface. The input teaches its own grammar through its
 * placeholder, and the hint line below it spells the grammar out.
 *
 * **The matching is client-side, over the loaded set, and that is a real limitation.**
 * The search sees the cards the page currently holds — the first page plus whatever the
 * reader has pulled in — so a match that sits past the current chunk does not appear
 * until that chunk loads. **This is stated here, in the component's own doc comment,
 * because a limitation that is only mentioned in a ticket is a limitation the reader
 * will rediscover the hard way.** The count line makes it visible too: the number that
 * matched is next to the server's own total, and the gap between them is the
 * chunk-bounded search.
 *
 * **No network request per keystroke.** The filter is a pure function over the cards
 * already in the browser, so typing is instant and costs nothing. A server-side search
 * would be one round trip per keystroke, and the AC forbids it.
 *
 * **The island owns the whole filterable surface — the first page *and* the appended
 * chunk.** A query typed into a client island cannot reach a server-rendered grid, and a
 * filter that reached only part of the surface would be a filter that lied about how
 * much it had narrowed. So the grid and the chunk loader are its children, and the
 * chunk's state lives here too — a chunk becomes part of the loaded set the moment it
 * lands, so the query has to reach it.
 *
 * **The grid draws every card, including the chunk's.** The island hands the grid the
 * whole loaded set; the chunk loader renders the anchor and nothing else. Rendering the
 * chunk's cards in *both* places would show every chunked event twice.
 *
 * **It filters; it does not decide.** The cards arrive ranked, tiered and ordered by the
 * server, and the search removes some of them without rearranging the rest (AD-10).
 */
export type BrowseSearchProps = {
  /** The server's first chunk of cards, in the server's order. */
  cards: BrowseCardOut[];
  /** Where the second section begins in the pool. The server's number. */
  tierTwoStartsAt: number;
  /** The pool's size. The server's number. */
  total: number;
  /** Whether the server says there is more to fetch. */
  hasMore: boolean;
  /**
   * The save allowance, as the payload states it.
   *
   * **It travels with the cards because every card's Save button reads it.** A Pro
   * account's `cap` is `null` and it never sees the wall; a Free account whose
   * allowance is spent sees it on every card. The server's gate is still the gate — the
   * client renders the wall, it does not decide whether a save is allowed.
   *
   * **The generated type.** `BrowseQuota` is the contract the server published, so
   * this copy of the shape cannot drift from the payload that carries it.
   */
  quota: BrowseQuota;
  /** Where this page's chunk began in the pool. */
  offset: number;
  /** How many cards the server sends per page. */
  limit: number;
  /** The city's name, for the grid's first-section meta. */
  city: string;
  /** The window's first instant, for the grid's first-section meta. */
  windowFrom: string;
  /** The user's zone, for the grid's first-section meta. */
  timezone: string;
};

/** The placeholder, verbatim. It teaches the grammar in place. */
const PLACEHOLDER = "Search this week — jazz, free, outdoor, tag:music";

export function BrowseSearch({
  cards,
  tierTwoStartsAt,
  total,
  hasMore,
  quota,
  offset,
  limit,
  city,
  windowFrom,
  timezone,
}: BrowseSearchProps) {
  const [raw, setRaw] = useState("");
  const [appended, setAppended] = useState<BrowseCardOut[]>([]);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const query: SearchQuery = useMemo(() => tokenize(raw), [raw]);
  const filtering = !isEmptyQuery(query);

  // **The whole loaded set, filtered once.** The first page and the appended chunks are
  // one list, because they are one loaded set — and a reader who typed a query and then
  // pulled in a chunk expects the chunk to obey the query too.
  const loaded = useMemo(() => [...cards, ...appended], [cards, appended]);
  const matches = useMemo(() => filterCards(loaded, query), [loaded, query]);

  // **The tier split is counted against the pool, not against the filtered list.**
  //
  // The server's `tier_2_starts_at` is an index into the pool it sent. A filter that
  // removes a tier-one card makes tier one *smaller* — it does not promote the next
  // card up. Counting the survivors of the pool's tier-one prefix keeps the split the
  // server's, which is the whole of AD-10's rule here.
  const tierOneCount = useMemo(() => {
    if (!filtering) return tierTwoStartsAt;
    const matchedIds = new Set(matches.map((card) => card.event_id));
    return survivingTierOneCount(loaded, matchedIds, tierTwoStartsAt);
  }, [filtering, loaded, matches, tierTwoStartsAt]);

  // **The next chunk starts where this page's cards end.** `offset` is where *this*
  // page's chunk began in the pool, and the page already holds `cards.length` of them,
  // so the next chunk starts at `offset + cards.length + appended.length`. Using
  // `offset` alone would re-request the chunk the reader is already looking at.
  const nextOffset = offset + cards.length + appended.length;

  /**
   * **The guard is inside the handler, not on the element.**
   *
   * `aria-disabled` is advisory: it tells assistive technology the control is
   * unavailable, and it does **not** stop a second click from firing. Without the
   * `busy` check below, a double-click issued two requests for the *same* offset, and
   * both responses appended — so the page showed the same events twice, under duplicate
   * React keys, and the next request skipped a chunk of the pool entirely.
   */
  async function loadMore() {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      const response = await api.GET("/api/personal/browse", {
        params: { query: { offset: nextOffset, limit } },
      });
      if (!response.data) {
        setFailed(true);
        return;
      }
      setAppended((current) => [...current, ...response.data.cards]);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  /** The reader's way out of a query that matched nothing. */
  function clearQuery() {
    setRaw("");
  }

  const terms = queryTerms(query);
  // **The matched count is the count of what is on screen.** It is the client's count of
  // the cards that survived the filter — not the server's pool size, which the count
  // line states separately.
  const matched = matches.length;

  return (
    <>
      {/*
        **The input.**
        *
        **`role="search"` on the wrapper**, so a screen reader's landmark list has a
        search landmark to jump to. The input itself carries the label, because the
        placeholder is not a label — a placeholder disappears the moment the reader
        types, and a control whose name disappears when it is used is a control whose
        name is gone exactly when it is needed.
      */}
      <div role="search" className="mt-6 max-w-[720px]">
        <div className="relative flex items-center">
          {/*
            **The magnifier.** It is 16×16, stroke-only, and sits at `left: 14px` —
            inside the field's 42px left padding, so the text starts clear of it. It is
            `aria-hidden`: the input's label says what the control is, and a decorative
            glyph beside a labelled control is decoration.

            **`suppressHydrationWarning` is here for Dark Reader**, which rewrites a
            stroke-only SVG's stroke before React hydrates — adding
            `data-darkreader-inline-stroke` and a `style` attribute. React's guard is
            one level deep, so it has to sit on the `<svg>` itself rather than on a
            wrapper. Same reason as the nav glyphs, which say so in full.
          */}
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            className="pointer-events-none absolute left-[14px] size-[16px] text-ink-muted"
            suppressHydrationWarning
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>

          <input
            type="search"
            value={raw}
            onChange={(event) => setRaw(event.target.value)}
            placeholder={PLACEHOLDER}
            aria-label="Search this week"
            className={[
              "w-full rounded-control border border-border-subtle bg-surface-paper",
              "py-3 pl-[42px] pr-[44px] text-ink-primary placeholder:text-ink-faint",
              "[font:var(--type-scale-body-md)]",
              "focus:border-accent-terracotta focus:outline-2 focus:outline-offset-1 focus:outline-accent-terracotta",
            ].join(" ")}
            data-browse-search
          />

          {/*
            **The clear button.**
            *
            **It is rendered only when there is something to clear.** A permanently
            visible ✕ on an empty input is a control that does nothing — and a control
            that does nothing is worse than no control, because it invites the click.
            *
            **It is a real `<button>`, 24×24, at the right edge.** The 44px target rule
            is about touch targets; this sits inside a field that is already a large
            target, and the design specifies 24×24.
          */}
          {raw.length > 0 ? (
            <button
              type="button"
              onClick={clearQuery}
              aria-label="Clear search"
              className="absolute right-[10px] inline-flex size-[24px] items-center justify-center rounded-full text-ink-muted hover:bg-surface-subtle hover:text-ink-primary"
              data-browse-search-clear
            >
              <span aria-hidden="true">✕</span>
            </button>
          ) : null}
        </div>

        {/*
          **The hint line.**
          *
          **It teaches the grammar when there is no query, and reports the query when
          **there is one.** The empty state teaches — the example queries and the tag
          vocabulary — and the filled state reports, in the reader's own words, what is
          being matched.
          *
          **The tag vocabulary it lists is the one that works.** It is the six friendly
          aliases that resolve to a real server tag plus the six fixed server tags. It is
          deliberately *not* the design's list of ten: four of those ten name tags the
          server has no fact for, and a grammar line that teaches four dead tags is a
          grammar line that teaches the reader to distrust the grammar.
        */}
        <p
          className="mt-[10px] text-ink-muted [font:var(--type-scale-meta-sm)]"
          data-browse-search-hint
        >
          {filtering ? (
            <>
              {querySummary(query)}
              {" · "}
              <button
                type="button"
                onClick={clearQuery}
                className="text-accent-terracotta underline underline-offset-4"
                data-browse-search-clear-hint
              >
                Clear
              </button>
            </>
          ) : (
            <>
              Try{" "}
              <code className="rounded-subtle bg-surface-subtle px-[6px] py-[2px] text-ink-secondary [font-family:var(--type-family-mono)]">
                jazz
              </code>{" "}
              or{" "}
              <code className="rounded-subtle bg-surface-subtle px-[6px] py-[2px] text-ink-secondary [font-family:var(--type-family-mono)]">
                tag:tonight
              </code>
              . Tags:{" "}
              {SEARCH_TAG_VOCABULARY.map((tag, index) => (
                <span key={tag}>
                  {index > 0 ? ", " : null}
                  <code className="rounded-subtle bg-surface-subtle px-[6px] py-[2px] text-ink-secondary [font-family:var(--type-family-mono)]">
                    {tag}
                  </code>
                </span>
              ))}
            </>
          )}
        </p>
      </div>

      {/*
        **The count line.**
        *
        **"N events matched · M of M events total · Clear filters".** The first number is
        the client's count of what survived the filter; the second is the server's pool
        size, twice, because the pool is what the reader could scroll to. **The gap
        between them is the chunk-bounded search made visible** — and it is the reader's
        clue that a match may be waiting in a chunk they have not pulled in.
        *
        **The count line is outside the grid container**, because it is about the whole
        surface rather than about the cards.
      */}
      {filtering ? (
        <p
          className="mt-8 max-w-[720px] text-ink-muted [font:var(--type-scale-meta-sm)]"
          data-browse-search-meta
        >
          <strong className="font-semibold text-ink-secondary">
            {matched === 1 ? "1 event" : `${matched} events`}
          </strong>{" "}
          matched · {total} of {total} events total ·{" "}
          <button
            type="button"
            onClick={clearQuery}
            className="text-accent-terracotta underline underline-offset-4"
            data-browse-search-clear-filters
          >
            Clear filters
          </button>
        </p>
      ) : null}

      {/*
        **The announcement.**
        *
        **The count is announced politely, not the grid.** The grid changing silently
        under a screen reader user is the worst outcome: the page sounds identical
        before and after a filter, so the reader has no way to know their query did
        anything. This region says how many cards matched.
        *
        **It is polite, not assertive.** A keystroke is not an emergency, and an
        *assertive* region would interrupt the reader on every character.
      */}
      <p className="sr-only" role="status" aria-live="polite" data-browse-search-status>
        {filtering ? `${matched === 1 ? "1 event" : `${matched} events`} matched.` : ""}
      </p>

      {/*
        **The surface.**
        *
        **The no-match state replaces the section heads and the grid**, and it renders
        **in the grid container** — full-width, so it is not a card-shaped thing in a
        card-shaped grid. The heads go because a heading over nothing is a heading that
        *lies*: "More this week" with no more in it would be a promise the page cannot
        *keep.
        *
        **The no-match state and the zero-events state are different states.** The
        *zero-events state replaces the whole page — hero and all — and says the city
        *has nothing on. This one says the *query* found nothing, and its way out is
        *the search box, not the city's settings.
      */}
      {filtering && matched === 0 ? (
        <div className="grid grid-cols-1">
          <BrowseSearchEmpty terms={terms} />
        </div>
      ) : (
        <>
          <BrowseGrid
            cards={matches}
            tierOneCount={tierOneCount}
            total={total}
            filtered={filtering}
            quota={quota}
            city={city}
            windowFrom={windowFrom}
            timezone={timezone}
          />

          <BrowseMore
            appendedCount={appended.length}
            hasMore={hasMore}
            nextOffset={nextOffset}
            busy={busy}
            failed={failed}
            onLoadMore={() => {
              void loadMore();
            }}
          />
        </>
      )}
    </>
  );
}
