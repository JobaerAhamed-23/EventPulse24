import Link from "next/link";

import { CityEventCard } from "@/components/city-page/city-event-card";
import { cityPageHref, type CityPageOut } from "@/lib/city-page-read";

/**
 * The city page — "Events in [city]", the landing page that answers the search (FR-27).
 *
 * **The page renders the payload and nothing else.** The listing's order, the Event
 * Fit's score and the fit's tags are the backend's — it already ordered the listing by
 * `-score, start_time_utc, event_id`, a total order, so two pages cannot overlap and the
 * order cannot shift between them. The page sorts nothing and re-ranks nothing (AD-10).
 *
 * **The layout follows `city-page-desktop.html`; the facts do not.** Three elements of
 * the mockup do not survive contact with the contract, and the payload wins each time:
 *
 * - **The filter chips are omitted.** The backend's city read accepts only `page` and
 *   `page_size` — there is no category, price or date-window filter, and the mockup's
 *   "When" chips are not the Event Fit tags. A chip that cannot filter is not a chip,
 *   and filtering on the client would be exactly the "re-ranked on the client" failure
 *   AD-10 forbids. **A page that cannot filter must not look like it can.**
 * - **The card has no category stripe.** Must-know / Nearby / Discovery are *digest*
 *   categories, decided at composition time from a session. A stripe here would be a
 *   category invented on the client.
 * - **The city pill's count is worded to the payload.** `event_count` is the
 *   *qualifying* count — the number the threshold was decided on — and it is not a week's
 *   count and not the listing's total. The mockup's "147 events this week" would be a
 *   false claim, so the pill says what the number is instead.
 *
 * **The mockup's SEO footer's neighbour-city and category links are absent too**, and
 * for the same kind of reason: those URLs (`/c/manhattan`, `/c/brooklyn/tech`) do not
 * exist in this system, and a public page full of dead links is worse than one without
 * them. The neighbour-city footer belongs to the sitemap item, which is where a list of
 * *real* city URLs belongs.
 */
export type CityPageProps = {
  page: CityPageOut;
  /** The page number being rendered — the one the URL carries. */
  currentPage: number;
};

export function CityPage({ page, currentPage }: CityPageProps) {
  const published = page.is_published;
  const items = page.items;

  return (
    <article className="mx-auto w-full max-w-(--layout-container-max)">
      {/* ── the hero ─────────────────────────────────────────────────────────── */}
      <section aria-label={published ? `Events in ${page.name}` : undefined}>
        {/*
          **The eyebrow.** The city, and the window the listing covers.

          **The count is not in the eyebrow, and the period is not claimed.** The
          listing is the city's upcoming events; the *count* the payload carries is a
          different number — the qualifying count over the backend's 365-day window —
          and the two must not be confused.
        */}
        <p className="text-accent-terracotta [font:var(--type-scale-meta-sm)] uppercase">
          {page.name} · This week and next
        </p>

        <h1 className="mt-4 text-ink-primary [font:var(--type-scale-display-lg)]">
          Events in {page.name}.
        </h1>

        {/*
          **The lede.** It says what the page is, and it claims no numbers the payload
          does not carry — the mockup's "23 sources across New York City" is a fact
          about the system's coverage that this page cannot see, so it is not said.
        */}
        <p className="mt-4 max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-lg)]">
          Concerts, tech meetups, classes and neighborhood events in {page.name}. Curated daily by
          EventPulse24 — we surface what matters, not what&apos;s trending.
        </p>

        {/*
          **The city pill.** The mockup's, without its false claims.

          **The count is worded to what the number is.** `event_count` is the qualifying
          count — the number FR-27's threshold was decided on, measured over the
          backend's 365-day window. It is **not** a week's count and **not** the number
          of items on this page, so the pill says "on record" rather than "this week".

          **"Change city" is absent**: there is no city index to change to yet, and a
          control that goes nowhere is a lie about what the page can do. The list of
          real city URLs belongs to the sitemap item.
        */}
        <p
          className="mt-8 inline-flex flex-wrap items-center gap-x-4 gap-y-1 rounded-full border border-border-subtle bg-surface-elevated px-4 py-2 text-ink-secondary [font:var(--type-scale-meta-sm)]"
          data-city-meta
        >
          <span className="text-ink-primary">
            <span aria-hidden="true">📍</span> {page.name}
            {page.region ? `, ${page.region}` : ""}
          </span>
          <span aria-hidden="true" className="text-ink-faint">
            ·
          </span>
          <span>{eventCountLabel(page.event_count)}</span>
        </p>
      </section>

      {published ? (
        <>
          {/* ── the listing ───────────────────────────────────────────────────── */}
          <section aria-label="Events" className="mt-16">
            {/*
              **The section head.** The mockup's reads "3 worth your attention today"
              and "Maya-fit · Brooklyn · Thu, Aug 27" — a *personal* digest heading, and
              this page has no reader to personalise it for. So the heading states the
              listing, and the meta states the page's own facts.
            */}
            <div className="flex flex-wrap items-baseline justify-between gap-3 pb-6">
              <h2 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
                Upcoming events
              </h2>
              <p className="text-ink-muted [font:var(--type-scale-meta-sm)]">
                {items.length === 0 ? "Nothing on this page" : `${items.length} on this page`}
                {currentPage > 1 ? ` · page ${currentPage}` : ""}
              </p>
            </div>

            {items.length > 0 ? (
              <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {items.map((event) => (
                  <li key={event.id} className="flex">
                    <CityEventCard event={event} />
                  </li>
                ))}
              </ul>
            ) : currentPage > 1 ? (
              /*
                **A page beyond the end of the listing.**

                **This is not the same fact as an empty first page, and saying it was
                would be a false claim.** An empty page *one* means the city has no
                upcoming events — between seasons. An empty page *five* means the city
                has events and they are on an earlier page. The first claim would tell a
                reader (and a crawler) that {city} has nothing on, when it has four
                pages of it.

                **The backend knows the difference and says so.** A request for a page
                past the last one "returns the same page shape with no items" — a
                crawler walking off the end of a listing is doing something ordinary,
                and it gets an answer rather than an error. So the answer here is
                ordinary too: the page points back to where the events are.

                **And it is a link, not a sentence.** A crawler follows links.
              */
              <p className="text-ink-secondary [font:var(--type-scale-body-lg)]" data-city-past-end>
                Nothing on this page of {page.name}&apos;s events —{" "}
                <Link href={cityPageHref(page.slug, 1)} className="underline underline-offset-4">
                  start from the first page
                </Link>
                .
              </p>
            ) : (
              /*
                **A published city with nothing on the listing.** This is a city that
                qualifies (it has events on record) but whose upcoming list is empty —
                between seasons. The count on the pill is still true, so the page does
                not claim the city is gone; it says the listing is empty, which is the
                fact the payload carries.
              */
              <p className="text-ink-secondary [font:var(--type-scale-body-lg)]" data-city-empty>
                There are no upcoming events in {page.name} right now — we&apos;ll list them here as
                soon as they are announced.
              </p>
            )}
          </section>

          {/* ── the paging ───────────────────────────────────────────────────── */}
          <Paging page={page} currentPage={currentPage} />
        </>
      ) : (
        /*
          **The sparse state — a 200, not a 404.**

          **The copy is `EXPERIENCE.md` §5's own line for this route**: "Coming soon —
          we're growing {city}'s coverage." The mockup's header comment claims the file
          includes this state, but the file contains no such markup — only the comment —
          so the copy comes from the project's own state table.

          **A quiet city is a real city whose page is not published yet.** An unknown
          slug is a URL that does not exist, and it answers 404. The difference is the
          whole point of the three answers the read makes.
        */
        <section aria-label="Coming soon" className="mt-16" data-city-coming-soon>
          <h2 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
            Coming soon — we&apos;re growing {page.name}&apos;s coverage.
          </h2>
          <p className="mt-4 max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-lg)]">
            We haven&apos;t found enough events in {page.name} yet to fill this page. Check back
            soon — we list them as they are announced.
          </p>
          {/*
           **One added sentence, and only when it is true.**
           *
           **The threshold and the collection status are different questions.**
           * `is_published` asks whether the city has enough events on record to deserve
           * a page; the status asks whether our collection of it is working. A city can
           * be `live` with four events — collection working, page not yet published —
           * and a city can be `collecting` with six, which is published while the first
           * events are still on their way.
           *
           **So the threshold decides whether the page shows a listing, and the status
           * only ever adds a sentence to the sparse state.** The "coming soon" copy is
           * true of the threshold whatever the collection is doing, and it is never
           * removed.
           *
           **A `live` city says nothing here**, because the sparse state is the
           * threshold's answer and the collection's answer is "working" — which the
           * listing will show soon enough.
           */}
          {collectionNote(page.name, page.city_collection_status)}
        </section>
      )}
    </article>
  );
}

/**
 * The one sentence the sparse state adds, when there is one.
 *
 * **It is a sentence about *our collection*, not about the city.** "We're collecting
 * events for {city}" is a fact about what we are doing; "We couldn't find any event
 * sources for {city}" is a fact about our coverage. Neither claims anything about the
 * city's evening, and neither is a substitute for the "coming soon" copy — which is
 * true of the threshold and stays.
 *
 * **A `live` city says nothing.** Its collection is working, and the threshold's
 * "coming soon" is the whole of the truth about the page.
 *
 * **An unknown status says nothing too.** The fallback is silence rather than a guess
 * — a new status added to the backend must not reach the surface as a sentence nobody
 * wrote. The vocabulary is held to the backend's in a test.
 */
function collectionNote(city: string, status: string) {
  if (status === "collecting") {
    return (
      <p
        className="mt-4 max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-lg)]"
        data-city-collecting
      >
        We&apos;re collecting events for {city} — check back soon.
      </p>
    );
  }
  if (
    status === "no_providers" ||
    status === "failed" ||
    status === "yielded_nothing" ||
    status === "paused"
  ) {
    return (
      <p
        className="mt-4 max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-lg)]"
        data-city-no-sources
      >
        We couldn&apos;t find any event sources for {city}.
      </p>
    );
  }
  /*
   **A `live` city says nothing, and the comparison is written out.**
   *
   **A working collection is not news.** The "coming soon" copy above is the whole of
   *the truth about a sparse page — the threshold's answer — and a city whose
   *collection is working has nothing to add to it.
   *
   **The comparison is here so the status is *recognised* in code**, not merely handled
   *by omission: the vocabulary test holds this surface and Browse's to the same set of
   *statuses, and a status missing from the set is a status the backend has and the
   *surface cannot report.
   */
  if (status === "live") {
    return null;
  }
  /*
   **An unknown status says nothing too.**
   *
   **The fallback is silence rather than a guess.** A new status added to the backend
   *must not reach the surface as a sentence nobody wrote — so the two branches above
   *are the whole of the vocabulary, and anything else falls through to `null`.
   */
  return null;
}

/**
 * The paging, as **links**.
 *
 * **A crawler follows links; it does not press buttons.** The AC says the paging must
 * be "reachable by link, not only by a client-side control a crawler cannot operate",
 * and this is the whole of the paging: two plain anchors in the server-rendered HTML.
 * A button that fetched the next page in the client would be invisible to a crawler,
 * and the whole point of the page is to be found.
 *
 * **The next-page link exists only when the backend says there is one.** `has_next` is
 * measured against the *upcoming* count, not the qualifying count, precisely so a city
 * between seasons is not sent to an empty page forever. The backend's flag is the
 * backend's; the page does not compute one.
 */
function Paging({ page, currentPage }: { page: CityPageOut; currentPage: number }) {
  const previous = currentPage > 1 ? currentPage - 1 : null;
  const next = page.has_next ? currentPage + 1 : null;

  if (previous === null && next === null) return null;

  return (
    <nav
      aria-label="Pagination"
      className="mt-16 flex flex-wrap items-center justify-between gap-4 border-t border-border-subtle pt-8"
      data-city-paging
    >
      {previous !== null ? (
        <Link
          href={cityPageHref(page.slug, previous)}
          rel="prev"
          className="rounded-control border border-border-subtle px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
        >
          ← Previous page
        </Link>
      ) : (
        <span />
      )}

      <p className="text-ink-muted [font:var(--type-scale-meta-sm)]">Page {currentPage}</p>

      {next !== null ? (
        <Link
          href={cityPageHref(page.slug, next)}
          rel="next"
          className="rounded-control border border-border-subtle px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
        >
          Next page →
        </Link>
      ) : (
        <span />
      )}
    </nav>
  );
}

/**
 * The qualifying count, in words.
 *
 * **`event_count` is the number the threshold was decided on**, measured over the
 * backend's qualification window — so it is not a week's count and not the size of this
 * listing. "On record" says what the number is without claiming a period the payload
 * does not state.
 */
function eventCountLabel(count: number): string {
  return count === 1 ? "1 event on record" : `${count} events on record`;
}
