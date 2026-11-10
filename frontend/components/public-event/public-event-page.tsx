import Link from "next/link";

import { cardTime } from "@/lib/detail-time";
import { SOLD_OUT_LINE, statusLineFor } from "@/lib/event-state";
import type { PublicEventPageOut } from "@/lib/public-event-read";

/**
 * The public event page — the front door, open to a stranger (FR-26, AD-12).
 *
 * **The page renders the payload and nothing else.** Every fact on it — the title, the
 * description, the time, the venue, the source, the sold-out state — came from the
 * backend's public read, and the JSON-LD is the *same payload's* `schema_org` object,
 * embedded verbatim. The page scores nothing, sorts nothing, invents nothing and fills
 * no gap (AD-10, ASSUMPTION-9).
 *
 * **The layout follows `public-event-page-desktop.html`; the facts do not.** The mockup
 * carries `offers.price`, an `organizer`, a `streetAddress` and an
 * `eventAttendanceMode` — none of which the backend's projection sends, because a value
 * that was not measured is not shown (ASSUMPTION-9). So the mockup is a layout and tone
 * reference and the payload is the data source, and where they disagree the payload
 * wins.
 *
 * **The time is the event's own time, in the event's own zone.** `cardTime` formats in
 * `start_time_tz`, which is the same helper the Pulse cards use and for the same reason:
 * this page renders on the server and hydrates in the browser, and formatting in the
 * browser's zone would print a different string on each side. The Detail Screen's
 * `detailTimes` is the one that adds the viewer's own clock, and a statically generated
 * page has no viewer to add one for.
 *
 * **The CTA is a soft wall.** The visitor reads the whole event first; "Save to Pulse"
 * invites an account and does not gate the content. It is a plain `<Link>` to `/signup`,
 * not a client island — the page must be a complete document with no JavaScript
 * required, because a crawler that does not execute JavaScript is a first-class reader
 * of this surface.
 */
export function PublicEventPage({ page }: { page: PublicEventPageOut }) {
  const when = cardTime(page.start_time_utc, page.start_time_tz);
  const where = [page.venue_name, page.venue_address].filter(Boolean).join(", ");
  const soldOut = page.is_sold_out;
  const statusLine = statusLineFor(page.status);

  return (
    <>
      {/*
        **The JSON-LD is the payload's own object, verbatim.**
        **It is in the server-rendered markup**, not injected by a client script: a
        crawler that does not execute JavaScript sees nothing otherwise, which defeats
        the entire FR. And it is the *same* object the backend projected — the page
        does not build a second one, so the page and the structured data cannot
        disagree about the event.
      */}
      <script
        type="application/ld+json"
        // **The payload's object, as the server rendered it.** The `dangerouslySetInnerHTML`
        // is unavoidable — this is a JSON-LD block, and it is *data*, not markup — but the
        // content is the backend's own projection, and the closing script tag is escaped
        // so the object cannot break out of the element.
        dangerouslySetInnerHTML={{
          __html: serializeJsonLd(page.schema_org),
        }}
      />

      <article className="mx-auto w-full max-w-(--layout-container-max)">
        {/*
          **The crumb.** The city is shown as **text, not as a link.** The city's slug is
          minted by the backend and can be `brooklyn`, `brooklyn-ny` or `brooklyn-ny-us`
          depending on what uniqueness required (`domain/cities.mint_city_slug`), and the
          public payload carries only the display name — so the frontend cannot know
          which form this city's URL has. A link built from the display name would be
          right for one city and broken for another, and a broken link on a public page
          is worse than no link. The city page arrives with the next work item, and it
          will bring the slug with it.

          **The slug is printed as this system's own path.** The mockup writes `/e/…`,
          which is *its* URL scheme and not this one's — this system's event page is
          `/events/<slug>` (`domain/revalidation.EVENT_PATH_PREFIX`). A page that printed
          the mockup's path would show a reader a URL that does not exist here.
        */}
        <p className="mb-8 [font:var(--type-scale-meta-sm)] text-ink-muted">
          {page.venue_city ? (
            <>
              <span>Events in {page.venue_city}</span>
              <span aria-hidden="true"> · </span>
            </>
          ) : null}
          <span>/events/{page.slug}</span>{" "}
          {/*
            **The structured-data badge.** The mockup carries one, and it is *true
            here*: this page emits the payload's own Schema.org `Event` object, so the
            claim is a fact about the document rather than a decoration. It says so in
            the vocabulary the standard uses.
          */}
          <span className="ml-1 text-ink-faint">schema.org/Event</span>
        </p>

        <section aria-label="Event">
          {/*
            **The eyebrow.** It states the one fact about this event that a stranger
            cannot get anywhere else: that it is public, and where it is.
          */}
          <p className="text-accent-slate [font:var(--type-scale-meta-sm)] uppercase">
            Public event{page.venue_city ? ` · ${page.venue_city}` : ""}
          </p>

          <h1 className="mt-4 text-ink-primary [font:var(--type-scale-display-lg)]">
            {page.title}
          </h1>

          {/*
            **The meta row: when, where, and whether it is still on.**
            **Each fact is omitted when the payload does not carry it** — there is no
            "Time to be confirmed" invented for a missing time, and no "Location to be
            announced" for a missing venue. A missing fact is simply not shown.
          */}
          <div className="mt-6 flex flex-wrap gap-x-8 gap-y-3 text-ink-secondary [font:var(--type-scale-body-md)]">
            {when ? (
              <span>
                <span className="mr-2 text-ink-muted [font:var(--type-scale-meta-sm)] uppercase">
                  When
                </span>
                {when}
              </span>
            ) : null}
            {where ? (
              <span>
                <span className="mr-2 text-ink-muted [font:var(--type-scale-meta-sm)] uppercase">
                  Where
                </span>
                {where}
              </span>
            ) : null}
          </div>

          {/*
            **The source bar.** The source's name is a fact the payload carries, so it is
            shown. **The reliability score the mockup draws is not** — the projection has
            no such field, and inventing one would be a number no one measured. The
            canonical URL is the listing this event was read from, and it is a plain
            external anchor.
          */}
          <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-card bg-surface-subtle px-4 py-3 [font:var(--type-scale-body-sm)] text-ink-secondary">
            <span className="text-ink-primary">{page.source_name}</span>
            {page.canonical_url ? (
              <a
                href={page.canonical_url}
                rel="noopener noreferrer nofollow"
                target="_blank"
                className="text-accent-terracotta underline underline-offset-4"
              >
                Open the listing
              </a>
            ) : null}
          </div>

          {/*
            **The time-zone review is a fact about the event's own times, and it is not
            hidden.** The payload says the zone has not been reviewed; a reader whose
            clock differs from the venue's deserves to know why. It is one calm line,
            not an error.
          */}
          {page.tz_review_pending ? (
            <p className="mt-4 text-ink-muted [font:var(--type-scale-meta-md)]">
              The start time has not been checked against the venue&apos;s clock.
            </p>
          ) : null}

          {/*
            **The lifecycle state is one line, and it is not an error.** The payload's
            `status` is the event's own lifecycle — `scheduled`, `postponed` or
            `cancelled` (`Event.Status`). A postponed or cancelled event still has a
            page, and the reader who came to that page needs to know it is not going to
            happen as advertised. **The server states the fact and the page renders it**
            (AD-10) — and the payload's `schema_org` already carries the same fact as
            `eventStatus`, so the visible line and the structured data cannot disagree.

            **A status this system does not recognise shows nothing.** The vocabulary is
            the backend's, and a page that rendered an unknown status as "unknown" would
            be inventing a fact about the world (ASSUMPTION-9).
          */}
          {statusLine ? (
            <p
              className="mt-6 text-ink-secondary [font:var(--type-scale-body-md)]"
              data-public-status
            >
              {statusLine}
            </p>
          ) : null}

          {/*
            **The sold-out state is one line, and it is not an error.** The event exists;
            it is simply gone — and the page says so where the reader will see it.
          */}
          {soldOut ? (
            <p
              className="mt-6 text-ink-secondary [font:var(--type-scale-body-md)]"
              data-public-sold-out
            >
              {SOLD_OUT_LINE}
            </p>
          ) : null}

          {/*
            **The soft wall.** The visitor has now read everything the page knows; this
            is where the invitation goes. It does not hide a fact and it does not
            interrupt the reading — it sits after the description, where the reader has
            already decided they care.
          */}
          <div
            className="mt-12 flex flex-col gap-4 rounded-card border border-accent-terracotta/25 bg-surface-subtle px-6 py-6 md:flex-row md:items-center md:justify-between"
            data-public-save-cta
          >
            <div>
              <h2 className="text-ink-primary [font:var(--type-scale-headline-sm)]">
                Save to your Pulse Digest
              </h2>
              <p className="mt-1 max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-sm)]">
                Free, no card. We&apos;ll surface it in your morning brief with 1-day and 1-hour
                reminders, or pick your own.
              </p>
            </div>
            <Link
              href="/signup"
              className="shrink-0 rounded-control bg-accent-terracotta px-6 py-3 text-center [font:var(--type-scale-meta-md)] text-ink-inverse"
            >
              Save to Pulse →
            </Link>
          </div>

          {page.description ? (
            <>
              <h2 className="mt-12 text-ink-primary [font:var(--type-scale-headline-md)]">
                About this event
              </h2>
              <div className="mt-4 max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-lg)]">
                {page.description}
              </div>
            </>
          ) : null}

          {where ? (
            <>
              <h2 className="mt-12 text-ink-primary [font:var(--type-scale-headline-md)]">Where</h2>
              <p className="mt-4 max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-lg)]">
                {where}
                {page.venue_city ? `, ${page.venue_city}` : ""}
                {page.venue_country_code ? `, ${page.venue_country_code}` : ""}
              </p>
            </>
          ) : null}
        </section>

        {/*
          **The closing invitation.** The mockup's footer CTA: the product's own promise,
          once, at the end of the page. It is the same promise the Pulse Preview makes,
          because it is the same promise.
        */}
        <section className="mt-16 rounded-card bg-surface-elevated px-8 py-12 text-center">
          <h2 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
            Three things matter. We show you exactly those.
          </h2>
          <p className="mx-auto mt-3 max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
            EventPulse24 is the calm intelligence layer above all event sources. One daily brief. No
            feeds. No infinite scroll.
          </p>
          <Link
            href="/signup"
            className="mt-6 inline-block rounded-control bg-accent-terracotta px-6 py-3 [font:var(--type-scale-meta-md)] text-ink-inverse"
          >
            Get my first brief →
          </Link>
        </section>
      </article>
    </>
  );
}

/**
 * The event's lifecycle, as one line a reader can act on.
 *
 * **The vocabulary is the backend's** — `Event.Status` is `scheduled`, `postponed` or
 * `cancelled` — and it is the same vocabulary the backend's `schema_org` projection
 * maps to Schema.org's `eventStatus`. So the visible line and the structured data are
 * two renderings of one fact.
 *
 * **`scheduled` says nothing.** A scheduled event is the ordinary case, and a line
 * reading "Scheduled" tells a reader nothing they did not already assume. Only the
 * two states that change what a reader should do get a line.
 *
 * **An unrecognised status shows nothing.** A status this system has never heard of is
 * a fact the frontend cannot put into words, and a page that rendered one as
 * "unknown" would be inventing a claim about the world (ASSUMPTION-9).
 *
 * **The table itself now lives in `lib/event-state.ts`.** It used to sit here, and the
 * Pulse Card needed the same two sentences — so the words moved to a module every
 * surface can read, and this page imports them. One table, one sentence, one place to
 * change it.
 */

/**
 * The payload's Schema.org object, as a JSON-LD block's text.
 *
 * **It is serialised once, here, and nowhere else.** The alternative — writing the
 * object into the markup with a template expression — would produce JavaScript, not
 * JSON: a `<` would be written unescaped, and a `</script>` inside a string would close
 * the block early. `JSON.stringify` plus the escapes below is what makes the block safe
 * to inline.
 *
 * **The `<` escape is the important one.** JSON-LD blocks are parsed as HTML, so the
 * only sequence that can break out of the element is `</script`. Replacing `<` with
 * `\u003c` keeps the JSON valid — JSON parsers accept the escape — and makes the
 * sequence inert.
 *
 * **The line-separator escapes are the cheap insurance.** U+2028 and U+2029 are legal
 * in a JSON string but are line terminators in JavaScript, so a block that were ever
 * parsed as a script would break on them. This block is `application/ld+json` and is
 * parsed as JSON, so it is not an injection today — but escaping them costs nothing and
 * removes the question.
 */
function serializeJsonLd(schemaOrg: Record<string, unknown>): string {
  return JSON.stringify(schemaOrg)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}
