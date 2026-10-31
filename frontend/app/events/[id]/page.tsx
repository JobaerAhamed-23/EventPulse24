import Link from "next/link";

import { DetailActions } from "@/components/detail/detail-actions";
import { DetailBreakdown, DetailTags } from "@/components/detail/detail-breakdown";
import { DetailHeader } from "@/components/detail/detail-header";
import { DetailNeighbors } from "@/components/detail/detail-neighbors";
import { DetailReminder } from "@/components/detail/detail-reminder";
import { DetailError, DetailRemoved, DetailSkeleton } from "@/components/detail/detail-states";
import { BrandTopbar } from "@/components/brand-topbar";
import { PreAuthFooter } from "@/components/pre-auth/pre-auth-footer";
import { AppShell } from "@/components/shell/app-shell";
import { factorLine } from "@/lib/detail-labels";
import { browserTimeZone, detailTimes } from "@/lib/detail-time";
import { readEventDetail } from "@/lib/event-detail-read";
import { getSession } from "@/lib/session";

/**
 * `/events/:id` — the Detail Screen.
 *
 * **This is the trust-signal elevation surface** (`EXPERIENCE.md` §12), and it is where
 * AD-10's durability rule becomes visible: an event this user was never shown gets **no
 * explanation at all**, rather than a plausible one generated on the spot.
 *
 * **The page renders what it was given.** Every fact on it — the event's fields, the
 * persisted tags, the bucket, the saved state, the neighbor bucket — was decided by the
 * server and persisted. The page scores nothing, sorts nothing, re-buckets nothing and
 * generates no reason (AD-10).
 *
 * **Four answers, four screens.** `found` and `anonymous` are two renderings of the same
 * payload; `removed` and `unavailable` are two different failures. The route is read on
 * the server, per request — the payload is per-user and neither it nor the 404 can be
 * baked into a build.
 */
export const dynamic = "force-dynamic";

export default async function EventDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
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

  const content = (
    <article className="mx-auto w-full max-w-(--layout-container-reading)">
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
        **The sold-out state replaces the Save and Reminder actions** (A-15, FR-53). The
        state is one calm line, and it is not an error: the event exists, it is simply
        gone.
      */}
      {event.is_sold_out ? (
        <p
          className="mt-6 text-ink-secondary [font:var(--type-scale-body-md)]"
          data-detail-sold-out
        >
          Sold out — tickets no longer available.
        </p>
      ) : (
        <>
          {/*
            **The picker and the action row are for a signed-in reader only.** A
            reminder plan and a save both belong to an account; an anonymous visitor has
            neither, and offering them a control that could not be persisted is the
            same failure as a control that does nothing.
          */}
          {personal ? (
            <>
              {/* The picker is display-only: nothing schedules sends yet. */}
              <div className="mt-8">
                <DetailReminder />
              </div>

              <div className="mt-8">
                {/*
                  **The action row owns the conflict prompt.** The mark in the header is
                  a server-rendered fact that *announces* the open; the prompt lives in
                  this island, and the event's own title and times are handed over so
                  the prompt can name the side the user is looking at.
                */}
                <DetailActions
                  eventId={event.id}
                  saved={personal.saved}
                  conflict={personal.conflict ?? null}
                  eventName={event.title}
                  startTimeUtc={event.start_time_utc}
                  endTimeUtc={event.end_time_utc ?? null}
                />
              </div>
            </>
          ) : null}
        </>
      )}

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
  const name = session.kind === "signed-in" ? displayName(session.user.email) : "";
  const email = session.kind === "signed-in" ? session.user.email : "";

  return (
    <AppShell name={name} email={email}>
      {content}
    </AppShell>
  );
}

/**
 * The public chrome: the brand topbar and the pre-auth footer.
 *
 * **The anonymous Detail Screen is a public document.** It carries no sidenav, no
 * bottom-tab bar, and no account row — a visitor without a session has none of those
 * things, and rendering an empty account row would be inventing one.
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
 * The loading skeleton, exported for the route's `loading.tsx`.
 *
 * **The Detail Screen's own shape** — one header block, one meta row and three chip
 * skeletons — and the same fade as the content it stands in for.
 */
export function DetailLoading() {
  return (
    <div className="mx-auto w-full max-w-(--layout-container-reading)">
      <DetailSkeleton />
    </div>
  );
}

/**
 * A name for the sidenav's account row.
 *
 * **The email's local part is the best name the session carries** — the same rule the
 * digest home uses.
 */
function displayName(email: string): string {
  const local = email.split("@")[0] ?? email;
  const words = local.split(/[._-]+/).filter(Boolean);
  if (words.length === 0) return email;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}
