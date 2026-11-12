/**
 * The "More events below" anchor — the soft cap's way through.
 *
 * **No pagination chrome.** The criterion is explicit: no page numbers, no "Load more"
 * button, no pager. The surface loads the next chunk *in place*, and this anchor is the
 * only affordance that says so.
 *
 * **It decides nothing.** The chunk comes already ranked, already tiered and already in
 * order, and the client renders it as it came. It re-ranks nothing, re-sorts nothing
 * and re-buckets nothing (AD-10).
 *
 * **The chunk's state lives in the search island, not here.** Amendment A-11's search
 * narrows "the loaded set", and a chunk becomes part of the loaded set the moment it
 * lands — so the query has to reach it. The island therefore owns the chunk's cards.
 *
 * **And the grid draws them, not this component.** The island hands the *whole loaded
 * set* — the first page plus the chunks — to the grid, which is the one place cards
 * are rendered. This component used to render the chunk's cards itself, in a list of
 * its own below the grid; when the state moved into the island, that list became a
 * **second** rendering of the same cards, and every chunked event appeared twice on
 * the page. The chunk's cards belong to the second section of the grid — the server's
 * tier formula puts every card past the first section in tier two — so the grid is
 * where they belong, and this component is left with the anchor.
 */
export type BrowseMoreProps = {
  /** How many cards the chunk that arrived carried, for the announcement. */
  appendedCount: number;
  /** Whether the server says there is more to fetch. */
  hasMore: boolean;
  /** Where the next chunk starts in the pool. */
  nextOffset: number;
  /** Whether a chunk is in flight. */
  busy: boolean;
  /** Whether the last chunk load failed. */
  failed: boolean;
  /** Loads the next chunk. */
  onLoadMore: () => void;
};

export function BrowseMore({
  appendedCount,
  hasMore,
  nextOffset,
  busy,
  failed,
  onLoadMore,
}: BrowseMoreProps) {
  // **The server says whether there is more.** `has_more` is on the payload, so the
  // anchor's visibility is the server's statement rather than the client's arithmetic
  // on `total`. A pool whose `total` disagrees with its card count — a stale count, a
  // filter that dropped rows after the count was taken — would otherwise strand the
  // reader on an anchor that leads nowhere, or hide a chunk that is really there.
  //
  // **A chunk that has arrived keeps the anchor alive only while more remains.** The
  // cards it fetched stay on the page either way — in the grid, where every card is.
  const remaining = hasMore;

  return (
    <>
      {/*
       **The anchor.**
       *
       **It appears only while there is more to reach.** `hasMore` is the server's
       * statement, and the anchor goes once the last chunk has arrived — but the cards
       * it fetched stay.
       */}
      {remaining ? (
        <div className="mt-8 flex flex-col items-center gap-2" data-browse-more>
          {/*
           **The anchor.** Its `href` names the next chunk, so the affordance is a real
           * navigation even though the click is intercepted to load in place.
           *
           **`role="button"` because it acts as one.** The click is intercepted and a
           * chunk is fetched in place; no navigation happens. An element that behaves
           * as a button but announces as a link lies about what activating it does —
           * a screen reader user would be told to expect a page load, and would wait
           * for one that never comes. The `href` stays, because the chunk's real URL
           * is the anchor's `href` and a reader with JavaScript off still needs it.
           */}
          <a
            href={`/browse?offset=${nextOffset}`}
            role="button"
            onClick={(event) => {
              event.preventDefault();
              onLoadMore();
            }}
            aria-disabled={busy}
            className="[font-family:var(--type-family-mono)] text-ink-muted underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
          >
            {busy ? "Loading…" : "More events below"}
          </a>

          {failed ? (
            <p className="text-ink-muted [font:var(--type-scale-meta-sm)]" role="status">
              Couldn&apos;t load more. Try again.
            </p>
          ) : null}

          {/*
           **The success announcement.** The chunk arrives silently: the cards appear
           *below* the reader, outside the focus, and nothing has changed where they
           * were. A screen reader user who triggered the load gets no signal that it
           * worked, and no signal where the new cards are. This live region says how
           * many arrived.
           *
           **It is polite, not assertive.** The load succeeded; it is not an emergency,
           * and an assertive region would interrupt whatever the reader was doing.
           */}
          <p className="sr-only" role="status" aria-live="polite" data-browse-more-status>
            {appendedCount > 0
              ? `Loaded ${appendedCount} more ${appendedCount === 1 ? "event" : "events"}.`
              : ""}
          </p>
        </div>
      ) : null}
    </>
  );
}
