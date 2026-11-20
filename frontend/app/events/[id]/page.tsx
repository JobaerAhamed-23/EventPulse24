import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { Suspense } from "react";

import { DetailActions } from "@/components/detail/detail-actions";
import { RecordDetailOpen } from "@/components/detail/record-detail-open";
import { DetailBreakdown, DetailTags } from "@/components/detail/detail-breakdown";
import { DetailHeader } from "@/components/detail/detail-header";
import { DetailNeighbors } from "@/components/detail/detail-neighbors";
import { DetailReminderLink } from "@/components/detail/detail-reminder-link";
import { DetailError, DetailRemoved, DetailSkeleton } from "@/components/detail/detail-states";
import { BrandTopbar } from "@/components/brand-topbar";
import { PreAuthFooter } from "@/components/pre-auth/pre-auth-footer";
import { PublicEventPage } from "@/components/public-event/public-event-page";
import { AppShell } from "@/components/shell/app-shell";
import { DetailNoticeBanner } from "@/components/state/detail-notice-banner";
import { factorLine } from "@/lib/detail-labels";
import { browserTimeZone, detailTimes } from "@/lib/detail-time";
import { displayName } from "@/lib/display-name";
import { readEventDetail } from "@/lib/event-detail-read";
import { SOLD_OUT_LINE, statusLineFor } from "@/lib/event-state";
import { isDetailEvent } from "@/lib/event-identifier";
import { readPublicEvent } from "@/lib/public-event-read";
import { getSession } from "@/lib/session";
import { siteUrl } from "@/lib/site-url";

/**
 * `/events/:id` — the Detail Screen, **and** `/events/:slug` — the public event page.
 *
 * **One route, two surfaces, and the parameter decides which.** Next.js allows exactly
 * one `page.tsx` per URL, and two different dynamic names at one level (`[id]` and
 * `[slug]`) is a build error. So the route branches: a **minted slug** renders the
 * public event page, and **everything else** is the signed-in Detail Screen. The rule
 * is `isDetailEvent` — a shared, tested predicate, not a regex written at the call
 * site.
 *
 * **The two surfaces are different kinds of page, and the difference reaches all the way
 * down.**
 *
 * The Detail Screen is the trust-signal elevation surface (`EXPERIENCE.md` §12), where
 * AD-10's durability rule becomes visible: an event this user was never shown gets **no
 * explanation at all**, rather than a plausible one generated on the spot. It is read on
 * the server, per request — the payload is per-user and neither it nor the 404 can be
 * baked into a build.
 *
 * The public page is the opposite. AD-12: "Public event pages render fully without a
 * session and are statically generated or ISR'd." So it reads **no cookies**, makes **no
 * session call**, and shows the event's **own** time in the event's **own** zone — a
 * statically generated page has no browser, and `browserTimeZone()` on the server
 * returns the *server's* zone, which would print a different clock on each side.
 */

/**
 * **`"force-dynamic"`, and this is not a default — it is a finding.**
 *
 * **One segment cannot hold two rendering modes.** The route segment serves both
 * surfaces, and a segment's rendering mode is a property of the segment: a prerendered
 * segment cannot run the detail branch's `cookies()`, and a dynamic segment's page is
 * never in the Full Route Cache. The two surfaces want opposite things — the public
 * page wants to be cached, the personal page must never be — and the segment can only be
 * one of them.
 *
 * **The choice is made by the safety asymmetry, not by the caching preference.**
 *
 * The branch was tried as a prerendered segment (`dynamic = "auto"` with an empty
 * `generateStaticParams`). It **500s in production**, and the reason is in Next's own
 * runtime (`app-page-runtime.js`): a route registered in the prerender manifest may not
 * bail to dynamic at request time, so it throws *"Page changed from static to dynamic at
 * runtime"*. The detail branch bails (it reads cookies) and the public branch bails
 * too (its read is uncached), so **both** paths 500 — and no unit test can see it,
 * because the unit tests call the page function directly.
 *
 * **So the segment is dynamic, and the public page's caching moves down a level.** The
 * public branch is cached by the *data* cache rather than the *page* cache
 * (`unstable_cache` in `lib/public-event-read.ts`), and `revalidatePath("/events/{slug}")`
 * — which the backend already delivers, naming `/events/` as the event page's prefix in
 * `domain/revalidation.py` — invalidates it.
 *
 * **The properties this preserves:**
 *
 * - **The personal page is never cached.** A dynamic route's page is never in the Full
 *   Route Cache, so there is no way for one visitor's page to be served to another.
 * - **The public page's facts are cached, and the cache holds nothing personal.** The
 *   public read carries no cookie header, so a cached copy cannot contain a session.
 * - **A cached public page is still a fresh answer to "does this event exist?"** A
 *   cached *not-found* is a problem, so the not-found answer is **not** cached — it is
 *   always re-read. Only a *found* answer is cached.
 */
export const dynamic = "force-dynamic";
export const dynamicParams = true;

/**
 * **There is nothing to prerender at build time.**
 *
 * The slugs are minted by the ingest pipeline (`apps/ingestion/services/slugs.py`), so
 * they are runtime facts and a build machine cannot know them.
 *
 * **`dynamicParams` stays `true`** (the default). An unknown slug has to reach the page
 * so the page can answer a real 404; if only prerendered slugs resolved, every newly
 * published event would 404 until the next build.
 */

/**
 * The page's metadata — the **shareable** half of the public page (FR-28).
 *
 * **Only the public branch has one.** A signed-in user's Detail Screen is not a share
 * artefact, and its metadata is the route's static title.
 *
 * **This runs for both branches, and it must not read cookies.** `generateMetadata` is
 * called before the page renders, and a Request-time API there would opt the **whole
 * route** out of static generation — undoing the design above for the public page. So
 * the metadata read is a plain public read: no `sessionHeaders()`, no `getSession()`.
 *
 * **The metadata is built from the same payload the page renders.** The title, the
 * description and the canonical URL are the event's own, so what a reader sees when they
 * paste the link is what the page says.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;

  // **The signed-in surface has no share metadata.** Nothing here reads a session, so
  // this cannot distinguish a signed-in reader from a stranger — and it does not need
  // to: a personal page's metadata is the same for everyone who sees it.
  //
  // **The same discriminator as the page itself**, so the two can never disagree about
  // which surface a parameter names.
  //
  // **And it is `noindex`, and that is the point.** The Detail Screen is the authed
  // branch of a path that also holds the public event pages — one route, two pages — so
  // robots.txt cannot exclude it without excluding the public pages too (robots.txt has
  // no path regular expression; the only wildcards are `*` and `$`). **The document
  // itself has to say so**, and a crawler reads that instruction on the page it
  // fetched. A crawler that indexed this branch would record a sign-in redirect as the
  // page's content.
  //
  // **`follow: false` as well as `index: false`.** The Detail Screen's links point at
  // the reader's own personal surfaces — the timeline, the conflicts, the saved events —
  // and a crawler that followed them would spend its budget on pages it may not keep.
  if (isDetailEvent(id)) {
    return {
      title: "Event · EventPulse24",
      robots: { index: false, follow: false },
    };
  }

  const read = await readPublicEvent(id);

  // **No event, no share metadata.** The page answers 404; the metadata answers with
  // the route's title rather than a promise of a title the page does not have.
  if (read.kind !== "found") {
    return { title: "Event · EventPulse24" };
  }

  const page = read.page;
  const description = page.description
    ? page.description.slice(0, 200)
    : `${page.title} — ${page.source_name}`;

  return {
    title: page.title,
    description,
    alternates: { canonical: `/events/${page.slug}` },
    openGraph: {
      type: "article",
      title: page.title,
      description,
      url: `/events/${page.slug}`,
      images: [BRANDED_IMAGE],
    },
    twitter: {
      card: "summary_large_image",
      title: page.title,
      description,
      images: [BRANDED_IMAGE],
    },
  };
}

/**
 * The branded share image (FR-28).
 *
 * **It is static, and it is the same for every event.** FR-28's image was held static by
 * decision — a per-event rendered OG image would mean a render per share, on a
 * deployment whose public surface is meant to be a static document. The image is the
 * brand's mark, and the *event's* title and description carry the specificity.
 */
const BRANDED_IMAGE = {
  url: "/brand/eventpulse24-logo.png",
  width: 1200,
  height: 630,
  alt: "EventPulse24",
};

export default async function EventDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  // **The branch.** A **minted slug** is the public event page; everything else is the
  // signed-in Detail Screen.
  //
  // **Why the rule is stated that way round.** A slug's shape is *knowable* — the
  // backend mints one format and never changes it — while an event id's shape is only
  // *guessable*: the real ids are UUIDv7s, but the detail endpoint's parameter is typed
  // `UUID`, so the route has to keep working for every id that is actually linked
  // into it. Naming the thing that can be named, and routing everything else to the
  // detail screen, is also the safe direction: the backend refuses a non-UUID
  // parameter with a 422, so a stray token can never render a personal page.
  //
  // **The branches are awaited, not rendered as elements.** An `<AsyncComponent />`
  // element in the returned tree is a *promise of an element* that React's renderer
  // resolves on its own schedule — which is fine in Next.js and is not fine for a test
  // that calls the page function directly. Awaiting the branch's content here makes the
  // page's return value fully resolved, so `await EventDetailPage(…)` gives the
  // finished tree and nothing else.
  //
  // **The detail branch is the only one under a Suspense boundary, and that is load-
  // bearing.** Next.js's rule for a real 404 is exact: "To return a real `404` status,
  // the resource has to be checked before the response streams." A Suspense boundary
  // *above* the page (which is what a segment-level `loading.tsx` is) streams the
  // fallback first, and then the status can no longer be set — the public branch's
  // `notFound()` would answer **200**, a soft 404, and a crawler would record a page
  // that does not exist. This was measured against a running production server: with a
  // segment `loading.tsx`, the unknown slug answered **200**; without one, it answers
  // **404**.
  //
  // **So the Detail Screen's skeleton lives inside the page, not above it.** The
  // boundary is below the public branch's `notFound()` call site, so the public branch
  // is never inside a pending subtree, and the Detail Screen still shows its skeleton
  // (`EXPERIENCE.md` §12: "Detail skeleton: header + meta row + 3 Why-this chips")
  // while the personal read is in flight.
  //
  // **The detail branch is awaited before it goes into the boundary, so the boundary's
  // fallback is never what a direct caller sees.** A `<Suspense>` whose child is an
  // already-resolved element renders that element immediately; the fallback is for the
  // case where the child is still a promise. `await DetailBranch(id)` resolves the
  // read here, in the render path, so the page's return value is a finished tree —
  // which is what the existing detail-route tests assert on, and what makes the
  // skeleton's presence a *client-navigation* affordance rather than a server-render
  // one.
  if (isDetailEvent(id)) {
    return <Suspense fallback={<DetailLoading />}>{await DetailBranch(id)}</Suspense>;
  }

  return await PublicEventBranch(id);
}

/**
 * The public event page — the front door (FR-26, AD-12).
 *
 * **This branch reads no session, ever.** No `cookies()`, no `sessionHeaders()`, no
 * `getSession()`. The read is `readPublicEvent`, which calls the catalog's public
 * endpoint without a cookie header. A session call here would make the page's content
 * depend on who is asking, and the first requester would bake their session into the
 * cache for everyone.
 *
 * **`notFound()` is called in the render path, before any `<Suspense>` boundary.**
 * Next 16's rule is exact: "To return a real `404` status, the resource has to be
 * checked before the response streams." The route's `not-found.tsx` renders the
 * document, and because nothing has streamed, the response status is **404** rather
 * than a soft 404's 200.
 */
async function PublicEventBranch(slug: string) {
  const read = await readPublicEvent(slug);

  if (read.kind === "not-found") {
    // **A superseded event sends the reader forward, and only a superseded one.**
    // The backend carries the successor's slug in the 404's `details`, and the
    // successor is a *live, published* event — `supersede_event` creates it published,
    // and the read refuses an unpublished successor — so the destination is a page
    // that exists. The redirect is **308**, not 302: the old URL is permanently
    // wrong, and a crawler is better served by being told so than by being handed a
    // 404 for a link it can follow. This is the backend's own intent — "the link a
    // crawler already holds resolves forward rather than dying" — made real.
    //
    // **Everything else is a real 404.** An unknown slug and an unpublished event
    // read as not found — that is the backend's own statement, and the page does not
    // soften it. Note that the backend's code is `"not_found"` for *every* absent
    // event; the *reason* is carried in `details`, and only the successor's slug is a
    // reason we can act on.
    if (read.supersededBySlug) {
      permanentRedirect(`/events/${read.supersededBySlug}`);
    }
    notFound();
  }

  if (read.kind === "unavailable") {
    // **A failure to answer is not an answer.** Telling a crawler an event does not
    // exist because we could not reach the API would put a wrong fact into an index
    // that is hard to correct. The server error says "not now"; the page says the same.
    return (
      <PublicShell>
        <PublicEventUnavailable />
      </PublicShell>
    );
  }

  return (
    <PublicShell>
      <PublicEventPage page={read.page} />
    </PublicShell>
  );
}

/**
 * The Detail Screen — the signed-in surface, read on the server, per request.
 *
 * **This branch is unchanged in every particular that matters.** It reads the event
 * with the visitor's cookies, renders the four answers it has always rendered, and
 * **never** touches the public endpoint. The two branches share a file and nothing else.
 *
 * **It is an awaited function, not an async component.** The page awaits it and puts
 * the resolved element inside the `<Suspense>` boundary, so the boundary's fallback is
 * the skeleton's *client-navigation* affordance and never the server-rendered answer.
 */
async function DetailBranch(id: string) {
  const read = await readEventDetail(id);

  // **The two failures share no chrome.** The removed and error states are plain
  // documents: there is no app shell around them, because there is no event to be in
  // the app about.
  if (read.kind === "removed") {
    return (
      <PublicShell>
        <DetailRemoved />
      </PublicShell>
    );
  }

  if (read.kind === "unavailable") {
    return (
      <PublicShell>
        <DetailError />
      </PublicShell>
    );
  }

  const event = read.detail.event;
  const personal = read.detail.personal ?? null;
  const why = personal?.why_this ?? null;

  // **The tags, the bucket and the badge all come from the same persisted
  // composition.** When there is no composition there are no tags and no confidence
  // pulse — and no breakdown section either. The screen is not a template with holes in
  // it; the explanation is *absent*, which is a different thing.
  const tags = why?.tags ?? [];
  const factors = tags.map(factorLine);

  const times = detailTimes(event.start_time_utc, event.start_time_tz, browserTimeZone());

  /**
   * **The event's lifecycle line, if it has one.**
   *
   * **The same table the public page reads.** `statusLineFor` is the shared copy, and
   * the public page and the Detail screen asking it the same question is what keeps
   * the two surfaces saying the same thing about the same event.
   *
   * **It is `null` for `scheduled`, for `null`, and for a status this system has never
   * heard of** (ASSUMPTION-9) — a screen that rendered an unknown status as "unknown"
   * would be inventing a claim about the world.
   *
   * **It takes precedence over the sold-out line**, and the precedence is not
   * arbitrary: a line reading "Sold out — tickets no longer available" on an event
   * that has been cancelled invites the reader to wait for tickets for an event that
   * is not happening. The event that is not happening is the bigger fact.
   */
  const stateLine = statusLineFor(event.status);

  const content = (
    <article className="mx-auto w-full max-w-(--layout-container-reading)">
      {/*
        **FR-24's second signal, fired for a signed-in reader only.**

        A neighbour is someone who saved **or opened**, and until now only the save was
        ever recorded. `read.kind === "found"` is precisely the signed-in Detail Screen:
        `"anonymous"` is the same screen without a session, and the public page is a
        different branch. The endpoint answers 401 to an anonymous caller, so this is a
        correctness condition and not a nicety.

        It renders nothing and blocks nothing.
      */}
      {read.kind === "found" ? <RecordDetailOpen eventId={event.id} /> : null}

      {/* The way back (the mockup's "← Today"): the digest for a signed-in reader, the
          preview they came from for an anonymous one. */}
      <Link
        href={read.kind === "anonymous" ? "/preview" : "/"}
        className="mb-8 inline-flex min-h-[44px] items-center gap-2 text-ink-secondary hover:text-ink-primary [font:var(--type-scale-meta-md)]"
      >
        <span aria-hidden="true">←</span>
        {read.kind === "anonymous" ? "Preview" : "Today"}
      </Link>

      <DetailHeader
        eventId={event.id}
        title={event.title}
        venueName={event.venue_name ?? null}
        venueCity={event.venue_city ?? null}
        times={times}
        approximate={event.tz_review_pending === true}
        sourceBadgeKey={why?.source_badge ?? null}
        confidence={why ? why.bucket : null}
        factors={factors}
        // **The server's fact.** The payload names the caller's active pair for this
        // event, or names none — the header does not decide whether a clash exists.
        hasConflict={personal?.conflict != null}
      />

      {/* The same three tags, in the same order, as the card (FR-21). */}
      {tags.length > 0 ? (
        <div className="mt-4">
          <DetailTags tags={tags} />
        </div>
      ) : null}

      {event.description ? (
        <p className="mt-6 text-ink-secondary [font:var(--type-scale-body-lg)]">
          {event.description}
        </p>
      ) : null}

      {/*
        **The sold-out state narrows the actions; it does not replace them**
        (A-15, FR-53). The state is one calm line, and it is not an error: the event
        exists, it is simply gone.

        **And the Share control stays.** A sold-out event is still published, still
        public, and still has a public page — what it has lost is its tickets, not its
        page. The Pulse Card offers a share for a sold-out event, so the Detail Screen
        must too; offering it in one place and not the other would be the inconsistency
        the AC names. So the row *narrows*: sold out → the notice plus Share; otherwise
        → Save, Share, Reminder.

        **A cancelled or postponed event gets its own line, from the same shared
        table.** The Detail screen is a surface with room for a sentence, so it says
        the thing in words — and it says the *same* words the public page says, because
        both read `lib/event-state.ts`. A Detail screen that said "Cancelled" where
        the public page said "Cancelled — this event is not happening" would be two
        vocabularies for one fact, which is the drift the shared table exists to stop.

        **The lifecycle state wins over the sold-out flag here, for the same reason it
        wins on the card**: a badge — or a line — reading "Sold out" on an event that
        has been cancelled would invite the reader to wait for tickets for an event
        that is not happening.
      */}
      {stateLine ? (
        <p className="mt-6 text-ink-secondary [font:var(--type-scale-body-md)]" data-detail-state>
          {stateLine}
        </p>
      ) : event.is_sold_out ? (
        <p
          className="mt-6 text-ink-secondary [font:var(--type-scale-body-md)]"
          data-detail-sold-out
        >
          {SOLD_OUT_LINE}
        </p>
      ) : null}

      {/*
        **The state-change banner (FR-54).**
        **It comes after the state line and before the actions**, and the order is the
        reading order: *what the event is now* (the state line), then *what changed and
        what it means for your reminders* (the banner), then *what you can do about it*
        (the actions).

        **The banner needs the personal payload**, because both of its facts live there:
        `personal.notice` is the newest notice for this event and `personal.muted` is
        FR-55's per-event mute. **No new read** — the Detail read already carries both
        (AD-10: the server states the facts; the page renders them).

        **It renders nothing for an anonymous reader**, and so does the whole `personal`
        branch below it: an anonymous visitor has no notices and no mute, because a mute
        is a thing about *their* relationship with the event and they have none.
      */}
      {personal ? (
        <DetailNoticeBanner
          notice={personal.notice ?? null}
          muted={personal.muted}
          eventId={event.id}
        />
      ) : null}

      {/*
        **The picker and the action row are for a signed-in reader only.** A
        reminder plan and a save both belong to an account; an anonymous visitor has
        neither, and offering them a control that could not be persisted is the
        same failure as a control that does nothing.
      */}
      {personal ? (
        <>
          {/*
            **The reminder plan is a link now, not a display.**

            The section used to render the plan's chips as `<span>`s, because
            *"nothing schedules sends"* — the delivery intent had not built the
            scheduler. **That is no longer true**: the plan is written through
            `PUT /api/reminders/…`, and the Reminder Picker is where it is edited.

            So the section became a link to the picker, and the display-only
            component was deleted. A `<span>` that looks like a control and is not
            one is worse than a link that plainly is.

            **And a sold-out event has no plan to remind anyone about** — the event
            it would remind for is gone — so the link goes with the Save button.
          */}
          {event.is_sold_out ? null : (
            <div className="mt-8">
              <DetailReminderLink eventId={event.id} />
            </div>
          )}

          <div className="mt-8">
            {/*
              **The action row owns the conflict prompt.** The mark in the header is
              a server-rendered fact that *announces* the open; the prompt lives in
              this island, and the event's own title and times are handed over so
              the prompt can name the side the user is looking at.

              **The slug and the origin are the share's facts (FR-28).** The control
              shares the *public* page — `/events/{slug}` — and never this screen's
              own address, which is `/events/{uuid}` and a sign-in wall for anyone
              who was not already signed in. The origin is resolved on the server,
              because `PUBLIC_SITE_URL` has no `NEXT_PUBLIC_` prefix and a client
              component cannot read it.
            */}
            <DetailActions
              eventId={event.id}
              slug={event.slug}
              shareOrigin={siteUrl()?.origin ?? null}
              saved={personal.saved}
              conflict={personal.conflict ?? null}
              eventName={event.title}
              startTimeUtc={event.start_time_utc}
              endTimeUtc={event.end_time_utc ?? null}
              soldOut={event.is_sold_out}
            />
          </div>
        </>
      ) : null}

      {/* The breakdown is absent when there is no composition — the section element is
          not in the DOM at all, which is what the criterion asks for. */}
      {why ? (
        <div className="mt-12">
          <DetailBreakdown tags={tags} />
        </div>
      ) : null}

      {/* The neighbor count is silent below the k-anonymity threshold. */}
      {personal ? (
        <div className="mt-12">
          <DetailNeighbors bucket={personal.neighbor_bucket ?? null} />
        </div>
      ) : null}

      {/* The source link. The canonical URL is the event's own, and it is a plain
          anchor — an external link, not a route. */}
      {event.canonical_url ? (
        <p className="mt-12 text-ink-muted [font:var(--type-scale-meta-sm)]">
          <a
            href={event.canonical_url}
            rel="noopener noreferrer nofollow"
            target="_blank"
            className="underline underline-offset-4"
          >
            {event.source_name} — open the listing
          </a>
        </p>
      ) : null}
    </article>
  );

  // **The signed-in reader gets the app shell; the anonymous reader gets the public
  // one.** The Detail Screen is "Authed + Anon (read-only)", and an anonymous visitor
  // has no sidenav and no bottom-tab bar — they have the preview's chrome.
  if (read.kind === "anonymous") {
    return <PublicShell>{content}</PublicShell>;
  }

  const session = await getSession();
  const name = session.kind === "signed-in" ? displayName(session.user) : "";
  const email = session.kind === "signed-in" ? session.user.email : "";
  const avatarUrl = session.kind === "signed-in" ? session.user.avatar_url : "";

  return (
    <AppShell name={name} email={email} avatarUrl={avatarUrl}>
      {content}
    </AppShell>
  );
}

/**
 * The public chrome: the brand topbar and the pre-auth footer.
 *
 * **The anonymous Detail Screen and the public event page are both public documents.**
 * They carry no sidenav, no bottom-tab bar, and no account row — a visitor without a
 * session has none of those things, and rendering an empty account row would be
 * inventing one.
 */
function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <BrandTopbar />
      <main className="fade-in mx-auto w-full max-w-(--layout-container-max) flex-1 px-6 py-8">
        {children}
      </main>
      <PreAuthFooter />
    </div>
  );
}

/**
 * The public page's own failure state: the API could not be reached.
 *
 * **This is not a 404.** A 404 is a claim about the world — this event is not public.
 * A failure to reach the API is a claim about us, and the two must not be confused: a
 * crawler that records "this does not exist" because we could not answer would put a
 * wrong fact into an index that is very hard to correct. So the page says "not right
 * now", and the status stays a server error.
 */
function PublicEventUnavailable() {
  return (
    <article className="mx-auto w-full max-w-(--layout-container-reading)">
      <h1 className="text-ink-primary [font:var(--type-scale-display-md)]">
        We couldn&apos;t load this event.
      </h1>
      <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-lg)]">
        Something went wrong on our side. Try again in a moment.
      </p>
    </article>
  );
}

/**
 * The Detail Screen's loading skeleton — the `<Suspense>` fallback.
 *
 * **The Detail Screen's own shape** — one header block, one meta row and three chip
 * skeletons — and the same fade as the content it stands in for.
 *
 * **It is the page's fallback, not the route's `loading.tsx`.** A segment-level
 * `loading.tsx` puts a Suspense boundary *above* the page, which streams the fallback
 * before the page has decided anything — and a response that has already streamed can
 * no longer carry a 404 status, so the public branch's unknown slug would answer
 * **200**. That was measured against a running production server. The skeleton lives
 * here instead: the boundary is *below* the public branch's `notFound()` call site, so
 * the public branch is never inside a pending subtree.
 */
export function DetailLoading() {
  return (
    <div className="mx-auto w-full max-w-(--layout-container-reading)">
      <DetailSkeleton />
    </div>
  );
}

