import Link from "next/link";

/**
 * The empty Pulse Digest (`EXPERIENCE.md` §5 — canonical).
 *
 * **"A user opening Pulse to nothing should feel the absence of the product's noise,
 * not be marketed at."** So there is no CTA, no carousel and no upsell of any kind —
 * and the as-built mockup violates all three: it ships a terracotta primary "Suggest an
 * event" button, a ghost "Browse all sources" button, and a "Suggested sources for you"
 * panel. None of them is reproduced.
 *
 * **The copy is locked.** "Nothing on the pulse today. The calendar is yours." in the
 * card's headline slot, and "No qualifying events in {city}." below it in `Text.Meta`.
 *
 * **The city is the server's.** The API carries `city_source` precisely so the client
 * does not have to guess whether it is the user's city or the server's fallback — and
 * FR-8's copy is a claim about where there is nothing.
 *
 * **The one link is low-weight.** `Text.Meta`, muted ink, present but not prominent.
 * "Suggest an event" opens `/suggest` (PRD FR-8). That route does not exist yet, and the
 * link is still a **real link**: a disabled control would promise a destination the
 * product cannot deliver, and a button that does nothing would be worse than either.
 */
export function DigestEmpty({ city }: { city: string | null }) {
  return (
    <div className="max-w-(--layout-container-reading)">
      {/*
        A single `Card.PulseDigest` variant — no second card. The card's own anatomy
        holds the headline, so the empty state reads as the product it is rather than as
        a page with a missing section.
      */}
      <article className="fade-in rounded-card border border-border-subtle bg-surface-elevated p-6">
        <h2 className="text-ink-primary [font:var(--type-scale-headline-md)]">
          Nothing on the pulse today. The calendar is yours.
        </h2>
      </article>

      {city ? (
        <p className="mt-3 text-ink-muted [font:var(--type-scale-meta-md)]">
          No qualifying events in {city}.
        </p>
      ) : null}

      {/*
        One link, low weight, no CTA. Not terracotta — terracotta is rationed to four
        uses, and this is not one of them.
      */}
      <p className="mt-1">
        <Link
          href="/suggest"
          className="text-ink-muted underline underline-offset-4 [font:var(--type-scale-meta-md)]"
        >
          Suggest an event
        </Link>
      </p>
    </div>
  );
}
