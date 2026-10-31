import Link from "next/link";
import { redirect } from "next/navigation";

import { PulseCard } from "@/components/digest/pulse-card";
import { DigestEmpty } from "@/components/digest/digest-empty";
import { DigestError } from "@/components/digest/digest-error";
import { DigestHeader } from "@/components/digest/digest-header";
import { DigestPreparing } from "@/components/digest/digest-preparing";
import { AppShell } from "@/components/shell/app-shell";
import { RETRY_PARAM, attemptFromQuery } from "@/lib/digest-attempt";
import { readDigest } from "@/lib/digest-read";
import { getSession, homeRoute } from "@/lib/session";

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

  const digest = await readDigest();

  /**
   * **The failure count is the server's, and it is consecutive.**
   *
   * It is read from the URL and never written: the first failure's retry link carries
   * `?retry=1`, so a failure on that render is the second in a row and renders "Refresh
   * page.". `lib/digest-attempt.ts` says why it is not a cookie.
   */
  const attempt = attemptFromQuery((await searchParams)[RETRY_PARAM]);

  return (
    <AppShell name={displayName(session.user.email)} email={session.user.email}>
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

          <div className="mt-8">
            {digest.kind === "not_composed" ? <DigestPreparing /> : null}

            {digest.kind === "empty" ? <DigestEmpty city={digest.digest.city ?? null} /> : null}

            {digest.kind === "composed" ? <DigestCards digest={digest.digest} /> : null}
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
function DigestCards({ digest }: { digest: { cards: Parameters<typeof PulseCard>[0]["card"][] } }) {
  return (
    <>
      {/*
        The live region announces once, when the cards are in the DOM — not on the
        server, where it would be read before the cards exist. It is visually hidden
        and carries the count, so "Pulse Digest ready, 3 events for today."
      */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        Pulse Digest ready, {digest.cards.length} events for today.
      </div>

      <div className="flex flex-col gap-(--layout-card-spacing-mobile) md:gap-(--layout-card-spacing-desktop)">
        {digest.cards.map((card) => (
          <PulseCard
            key={card.event_id}
            card={card}
            explanation={{ kind: "relevance", value: card.bucket }}
          />
        ))}
      </div>
    </>
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

/**
 * A name for the sidenav's account row.
 *
 * **The email's local part is the best name the session carries.** `CurrentUserOut`
 * carries the email and the onboarding status, not a display name — the mockup's "Maya
 * Patel" is a persona, not a field. So the local part is used, and it is title-cased:
 * "maya@example.test" → "Maya".
 */
function displayName(email: string): string {
  const local = email.split("@")[0] ?? email;
  const words = local.split(/[._-]+/).filter(Boolean);
  if (words.length === 0) return email;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}
