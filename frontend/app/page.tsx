import Link from "next/link";
import { redirect } from "next/navigation";

import { PulseCard } from "@/components/digest/pulse-card";
import { DigestCardList } from "@/components/digest/digest-card-list";
import { DigestEmpty } from "@/components/digest/digest-empty";
import { DigestError } from "@/components/digest/digest-error";
import { DigestHeader } from "@/components/digest/digest-header";
import { DigestPreparing } from "@/components/digest/digest-preparing";
import { AppShell } from "@/components/shell/app-shell";
import { NoticeStrip } from "@/components/state/notice-strip";
import { RETRY_PARAM, attemptFromQuery } from "@/lib/digest-attempt";
import { readDigest } from "@/lib/digest-read";
import { displayName } from "@/lib/display-name";
import { readNotices } from "@/lib/notice-read";
import { getSession, homeRoute } from "@/lib/session";
import { siteUrl } from "@/lib/site-url";

/**
 * `/` — the Pulse Digest: the signed-in home, and the route decision that gets people
 * to the right one.
 *
 * **Three visitors, three answers** (`lib/session.ts` holds the rule, as a pure function
 * this page calls):
 *
 *   - anonymous → `/preview`, the public preview (AD-12);
 *   - signed in, onboarding unfinished → `/onboarding`, which resumes at their step;
 *   - signed in and onboarded → this page.
 *
 * A fourth case is not a redirect: when the API cannot be reached, the page says so.
 * Sending a signed-in user to the anonymous preview because one request failed would tell
 * them they are logged out when they are not.
 *
 * **The decision is made here, not in `proxy.ts`.** The proxy has one job — forward
 * `/api/*` to Django — and a redirect rule there would be a second one, running on every
 * request to every route. Here it is a function call on the route that needs it.
 *
 * **The page renders what it was given.** Every fact on it — the cards, their order, the
 * city, the date, the status — was decided by the composition service and persisted.
 * The page scores nothing, sorts nothing and re-buckets nothing (AD-10).
 *
 * **The digest is alone here.** It carried a personal-events list as a stopgap, added
 * before the Timeline existed. The Timeline does now, so the list is gone and with it
 * the page's second read. The header's "+ Add personal event" stays — the *add* belongs
 * to the page head — and it confirms the add inline, with a link to the week the event
 * landed on, so an add from here never again looks like nothing happened.
 *
 * The page is rendered **per request**, as it was before: it shows the signed-in user's
 * own digest, and neither can be baked into a build.
 */
export const dynamic = "force-dynamic";

export default async function HomePage({ searchParams }: PageProps<"/">) {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  if (session.kind !== "signed-in") return <HomeUnavailable />;

  /**
   * **The digest and the strip's notices, read together.**
   *
   * **`DigestOut` carries no notices field**, so the strip needs its own read. The two
   * are started **together**, so the strip is not a second round trip *after* the digest:
   * the page waits for both at once and renders both at once. **Both promises are created
   * before either is awaited** — that is what makes them concurrent, and it is the
   * difference between a page that waits for `max(digest, notices)` and one that waits for
   * `digest + notices`.
   *
   * **And the strip still renders nothing when the read fails.** `unavailable` is not an
   * empty list — an empty list means "nothing changed", and a failed read means "we do
   * not know". The two are different claims about the world, and the page must not make
   * the second one in the first one's voice.
   */
  const [digest, notices] = await Promise.all([readDigest(), readNotices()]);

  /**
   * **The failure count is the server's, and it is consecutive.**
   *
   * It is read from the URL and never written: the first failure's retry link carries
   * `?retry=1`, so a failure on that render is the second in a row and renders "Refresh
   * page.". `lib/digest-attempt.ts` says why it is not a cookie.
   */
  const attempt = attemptFromQuery((await searchParams)[RETRY_PARAM]);

  return (
    <AppShell name={displayName(session.user)} email={session.user.email}>
      {digest.kind === "unavailable" ? (
        <DigestError attempt={attempt} />
      ) : (
        <>
          <DigestHeader
            localDate={digest.digest.local_date}
            timezone={digest.digest.timezone}
            city={digest.digest.city ?? null}
            empty={digest.kind === "empty"}
          />

          {/*
            The strip. **It is between the header and the cards**, not inside the
            header and not above it.

            **Above the header would be a banner**, and a banner is what this is not:
            FR-10 removed the topbar Notifications button because "there is no in-app
            notifications inbox", and a strip pinned to the very top of the page reads
            as exactly that — an alert region the reader has to clear before the page
            begins.

            **Below the header and above the cards** puts it where the user already is,
            after the greeting and before the digest, and it is the reading order a
            reader expects: *here is what changed; here is what is on today.*

            **It is a sibling of the header, not a child of it.** The header is the
            digest's own heading — "Today, three things matter." — and a change notice
            is not part of the digest's headline. Putting it inside the header would
            make the strip part of the greeting.
          */}
          {notices.kind === "notices" ? <NoticeStrip notices={notices.notices} /> : null}

          <div className="mt-8">
            {digest.kind === "not_composed" ? <DigestPreparing /> : null}

            {digest.kind === "empty" ? <DigestEmpty city={digest.digest.city ?? null} /> : null}

            {digest.kind === "composed" ? (
              <DigestCards digest={digest.digest} origin={siteUrl()?.origin ?? null} />
            ) : null}
          </div>
        </>
      )}
    </AppShell>
  );
}

/**
 * The three cards, in the server's order.
 *
 * **The order is the server's.** The composition service chose the slot order and
 * persisted it; the page renders `digest.cards` as they came and does not re-sort. A
 * client that re-sorted would be re-deciding a persisted fact at render, which is the
 * failure AD-10 exists to prevent.
 *
 * **`card.bucket` is the persisted bucket, not a score.** The API sends the bucket on
 * purpose — the raw score is an internal number, and sending it would invite the
 * frontend to re-bucket it. The card draws the bucket's dots and re-buckets nothing.
 *
 * **The digest is always a Relevance Pulse.** `/` is the signed-in home, and the
 * per-user digest is the Relevance Pulse; the Event Fit belongs to the session-free
 * preview. The card names itself "Relevance" on screen, which is the words keeping the
 * two indicators apart.
 */
function DigestCards({
  digest,
  origin,
}: {
  digest: { cards: Parameters<typeof PulseCard>[0]["card"][] };
  /** The site's public origin, resolved on the server (FR-28). */
  origin: string | null;
}) {
  return (
    /*
     **The list is a client component, and the page's read stays on the server.**

     **FR-25's swipe is a gesture**, so the answer to it lives in the browser — and
     the component that holds that answer is the one that renders the cards. The
     digest is still read on the server, still composed by the backend, and still
     rendered in the order it was composed (AD-10): what moved into the browser is the
     gesture, not the facts.

     **The card's removal is local.** The server's composition is a record of a past
     decision, and it does not change because the user swiped a card on this page load
     — the *next* composition is what excludes it.
     */
    <DigestCardList cards={digest.cards} origin={origin} />
  );
}

/**
 * The API could not be reached. The user keeps their session and their place; they are
 * told what happened, in the product's error voice (`EXPERIENCE.md` §6: honest, brief).
 *
 * **This is not the digest's error state.** The session being unreadable and the digest
 * read failing are different failures: here the page does not even know who the user
 * is, and there is no digest to have failed. `DigestError` is for the case where the
 * session is fine and the digest request did not come back.
 */
function HomeUnavailable() {
  return (
    <div className="flex min-h-screen flex-col">
      <main className="fade-in mx-auto w-full max-w-(--layout-container-reading) flex-1 px-6 py-20">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
          Couldn&apos;t reach Pulse. Try again.
        </h1>
        <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-md)]">
          Your events are safe. This is on our side.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block text-accent-terracotta underline underline-offset-4 [font:var(--type-scale-body-sm)]"
        >
          Try again →
        </Link>
      </main>
    </div>
  );
}
