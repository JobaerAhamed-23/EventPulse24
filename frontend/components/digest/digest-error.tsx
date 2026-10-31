import Link from "next/link";

/**
 * The Pulse Digest's error state (`EXPERIENCE.md` §5, Error Patterns).
 *
 * **"Couldn't reach Pulse. Try again."** with a single retry action. No stack trace, no
 * emoji.
 *
 * **The retry is a `Button.Primary`** — terracotta fill, `color.surface.paper` text.
 * This is the *second* sanctioned terracotta use, and it fits: terracotta is rationed to
 * four places, and the primary CTA is one of them. A failure that asks the user for a
 * decision is a decision moment.
 *
 * **On the second consecutive failure the label becomes "Refresh page."** §5 says so
 * verbatim, and it is a *stateful* rule, so the count travels in the retry link's URL
 * (`lib/digest-attempt.ts`) and the server passes the count in.
 *
 * **The two failures are different failures, and the two actions do different things.**
 * The first **re-runs the digest read** — the same request, the server renders again.
 * The second **reloads the document**, because by then the failure is probably not in
 * the one request: two consecutive failures of the same call mean something wider is
 * wrong, and re-running one request would just fail again.
 *
 * **The read is re-run by the server, not by the browser.** The digest is a *personal*
 * page read on the server, and a client-side re-fetch would be a second reader of the
 * same endpoint with a different failure mode. So the retry navigates to the same URL,
 * which makes the server render again — and the server's own read is the one that
 * failed, so re-running it is the honest retry.
 */
export function DigestError({ attempt }: { attempt: number }) {
  const second = attempt >= 1;

  return (
    <div className="max-w-(--layout-container-reading)">
      <h2 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        Couldn&apos;t reach Pulse. Try again.
      </h2>
      <p className="mt-3 text-ink-secondary [font:var(--type-scale-body-md)]">
        Your events are safe. This is on our side.
      </p>

      {/*
        A link, not a button: both actions are navigations, and a link says so. The
        first carries `retry=1`, which makes the server render again rather than serve
        the failure it already rendered, and tells it this is the second attempt; the
        second reloads the document outright.
      */}
      <Link
        href={second ? "/" : "/?retry=1"}
        className="mt-6 inline-block rounded-control bg-accent-terracotta px-6 py-3 text-ink-inverse [font:var(--type-scale-meta-md)]"
      >
        {second ? "Refresh page." : "Try again"}
      </Link>
    </div>
  );
}
