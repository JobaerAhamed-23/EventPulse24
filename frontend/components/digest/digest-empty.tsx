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
 * ## There is no link here, and that is Amendment A-26
 *
 * This file used to render one: a low-weight `Text.Meta` "Suggest an event" opening
 * `/suggest`, specified by FR-8 and by §5. **`/suggest` was never built, in any layer** —
 * no FR, no model, no endpoint, no table, no admin — so the link resolved to a 404 for
 * as long as it shipped, and a user reported it on 2026-11-20.
 *
 * **The reasoning this file used to carry was sound and still lost.** It argued that a
 * real link beats a disabled control, which promises a destination the product cannot
 * deliver, and beats an inert button, which would be worse than either. That is correct
 * about those three options. The fourth — **not making the promise** — was never on the
 * list, and A-26 takes it: the empty state is the one surface whose whole argument is
 * that it offers nothing, and a 404 is the noisiest thing it could have offered, because
 * it costs a click to find out.
 *
 * **Do not restore the link without a destination.** A-26 records the one argument that
 * would justify it — §5's SEO cold-start case, where a visitor arriving from a search
 * engine in an uncovered city has no other way to signal that they exist — and that
 * placement is `/preview`, not here. `tests/internal-links.test.ts` fails on any internal
 * `href` that resolves to nothing, so this cannot quietly come back.
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
    </div>
  );
}
