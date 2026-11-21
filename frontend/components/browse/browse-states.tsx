import Link from "next/link";
import type { ReactNode } from "react";

/**
 * Browse's non-populated states: the quiet empty state, the no-match empty state, the
 * collecting state, the no-sources state, the error state and the loading skeleton.
 *
 * **They are different things and must not share a treatment.** `DESIGN.md` says so
 * about the product's empty states generally: `component.emptystate.quiet` is *an
 * absence the system found*, a failure is a third thing, and telling a user their city
 * is empty because a request failed is a lie about the world.
 *
 * **The two empty states are the ones most easily confused, and they must not be.**
 * "Nothing nearby tonight" says *your city has nothing on*; "Nothing matched" says
 * *your query found nothing in what is loaded*. Their recovery actions point at
 * different places — one at the city's settings, one at the search box — and a reader
 * who was offered "Change city" for a query that simply matched nothing would be sent
 * to fix something that was not broken.
 *
 * **And a city with no events is not one thing either.** It can be **collecting** — we
 * have registered sources and are waiting for the first events — or it can be **quiet**
 * — covered, and simply nothing on tonight — or it can have **no sources** — we never
 * found anything to collect from. Those are three different facts, and the third one
 * has a way out the first two do not need.
 */

/**
 * The quiet empty state — `component.emptystate.quiet`.
 *
 * **"Nothing nearby tonight. Try a wider city?"** — and a "Change city" link, because a
 * quiet city is usually a narrow one and the way out is to widen it.
 *
 * **The `◌` glyph is decorative.** It is `aria-hidden`, so a screen reader hears the
 * sentence rather than the punctuation.
 *
 * **The heading is the page's `<h1>`.** The empty state *replaces* the hero — the page
 * renders one or the other, never both — so there is no hero h1 above it, and a page
 * whose only heading is an `<h2>` has no h1 at all. An `<h2>` with no `<h1>` before it
 * breaks the heading order the way a skipped level does.
 */
export function BrowseEmpty() {
  return (
    <section
      aria-label="No events nearby"
      className="mt-8 rounded-card border border-dashed border-border-strong bg-surface-elevated px-8 py-16 text-center"
      data-browse-empty
    >
      <span
        aria-hidden="true"
        className="mb-6 inline-flex size-[56px] items-center justify-center rounded-full bg-surface-subtle text-2xl text-accent-terracotta"
      >
        ◌
      </span>
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        Nothing nearby tonight. Try a wider city?
      </h1>
      <p className="mx-auto mt-3 max-w-[460px] text-ink-secondary [font:var(--type-scale-body-sm)]">
        There is nothing on in your city across tonight and the next seven days. A wider city would
        show more.
      </p>
      <Link
        href="/settings/profile"
        className="mt-6 inline-block text-accent-terracotta underline underline-offset-4 [font:var(--type-scale-body-sm)]"
        data-browse-change-city
      >
        Change city
      </Link>
    </section>
  );
}

/**
 * The collecting state — the city is covered *in progress*.
 *
 * **"We're collecting events for {city} — check back soon."**
 *
 * **This is not the quiet state, and the difference is the whole point.** A city that
 * is `collecting` has sources registered and nothing published yet; a city that is
 * quiet has been covered for a long time and simply has nothing on tonight. Telling the
 * first kind of reader that their city is empty is a lie — the city is not empty, our
 * collection of it has not answered yet.
 *
 * **It is `role="status"` and `aria-live="polite"`, because the reader is waiting on
 * it.** This is a state that is expected to change, and the screen reader user is the
 * one who most needs to hear that it has.
 *
 * **The heading is the page's `<h1>`, and it names the reader's own city.** The state
 * replaces the hero — the page renders one or the other, never both — so there is no
 * hero h1 above it. **And it is the hero's own heading**: "Events in {city}" is what the
 * page says when it has cards, and a collecting city is the same page with the events
 * not yet arrived. The reader should not be told their city has no events by a heading
 * that says they do.
 */
export function BrowseCollecting({ city }: { city: string }) {
  return (
    <section
      role="status"
      aria-live="polite"
      aria-label={`Collecting events for ${city}`}
      className="mt-8 rounded-card border border-dashed border-border-strong bg-surface-elevated px-8 py-16 text-center"
      data-browse-collecting
    >
      <span
        aria-hidden="true"
        className="mb-6 inline-flex size-[56px] items-center justify-center rounded-full bg-surface-subtle text-2xl text-accent-terracotta"
      >
        ◌
      </span>
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Events in {city}.</h1>
      <p className="mx-auto mt-3 max-w-[460px] text-ink-secondary [font:var(--type-scale-body-sm)]">
        We&apos;re collecting events for {city} — check back soon.
      </p>
    </section>
  );
}

/**
 * The no-sources state — we have nothing to collect this city from.
 *
 * **"We couldn't find any event sources for {city}."**
 *
 * **This is a different answer from the quiet state, and it must not be folded into
 * it.** The quiet state says *your city has nothing on*; this one says *we have no
 * sources for your city*, which is a fact about *our* coverage rather than about the
 * city's evening. A reader in this state has a way out — asking us to cover the city —
 * and a reader in the quiet state does not need one.
 *
 * **The same line serves four statuses.** `no_providers` (no provider covers this
 * city), `failed` (provisioning itself failed), `yielded_nothing` (every source gave
 * nothing) and `paused` (somebody stopped it) are four different facts — but from the
 * *reader's* side the honest sentence is the same: we have no sources here, so there
 * are no events, and here is the way to ask for one. **The distinction is not lost** —
 * it is in the payload, and it is what the editorial surface reads.
 *
 * **The heading is the page's `<h1>`.** Like the collecting state, it replaces the
 * hero.
 *
 * **The coverage-request slot is where item 10's control goes.** The slot renders
 * nothing until that control lands, so it offers the reader nothing it cannot do.
 */
export function BrowseNoSources({
  city,
  coverageRequest = null,
}: {
  city: string;
  coverageRequest?: ReactNode;
}) {
  return (
    <section
      aria-label={`No event sources for ${city}`}
      className="mt-8 rounded-card border border-dashed border-border-strong bg-surface-elevated px-8 py-16 text-center"
      data-browse-no-sources
    >
      <span
        aria-hidden="true"
        className="mb-6 inline-flex size-[56px] items-center justify-center rounded-full bg-surface-subtle text-2xl text-accent-terracotta"
      >
        ◌
      </span>
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        We couldn&apos;t find any event sources for {city}.
      </h1>
      <p className="mx-auto mt-3 max-w-[460px] text-ink-secondary [font:var(--type-scale-body-sm)]">
        We&apos;re not collecting events in {city} yet, so there is nothing to show. We list them as
        soon as we find a source.
      </p>
      <div data-browse-coverage-request className="mt-6">
        {coverageRequest}
      </div>
    </section>
  );
}

/**
 * The no-match empty state — `component.emptystate.quiet`, for a query that found
 * nothing.
 *
 * **It is a different answer from `BrowseEmpty`, and it is a different recovery.**
 * `BrowseEmpty` says the *city* has nothing on and sends the reader to the city's
 * settings. This one says the *query* found nothing and sends the reader back to the
 * search box. The two must never be merged: a reader whose city is full and whose query
 * was too narrow would be sent to change a city that was never the problem.
 *
 * **The terms are named back to the reader.** The mockup's copy — *"No cards in tonight +
 * 7 days satisfy both `quantum` and `poetry`. Drop a term, or browse the full list."* —
 * shows the intended tone. The mockup hard-codes two words because the mockup had no
 * reader; here the words are the reader's own, so the sentence is about their query.
 *
 * **It is a `<h2>`, because the hero's `<h1>` is still above it.** This state replaces
 * the *grid*, not the page — the hero stays, and the hero carries the h1. (The
 * zero-events state is the opposite: it replaces the hero, and so it is the h1.)
 *
 * **It is `role="status"`, and it announces itself.** The grid has just been emptied
 * under the reader, and a screen reader user would otherwise hear nothing at all.
 */
export function BrowseSearchEmpty({ terms }: { terms: string[] }) {
  const named = terms.filter(Boolean);

  return (
    <section
      role="status"
      aria-live="polite"
      aria-label="Nothing matched the search"
      className="mt-4 rounded-card border border-dashed border-border-strong bg-surface-elevated px-8 py-16 text-center"
      data-browse-search-empty
    >
      <span
        aria-hidden="true"
        className="mb-6 inline-flex size-[56px] items-center justify-center rounded-full bg-surface-subtle text-2xl text-accent-terracotta"
      >
        ◌
      </span>
      <h2 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Nothing matched.</h2>
      <p className="mx-auto mt-3 max-w-[460px] text-ink-secondary [font:var(--type-scale-body-sm)]">
        {named.length > 0
          ? `No cards in tonight + 7 days satisfy ${
              named.length === 1 ? `${named[0]}` : `all of ${named.join(" and ")}`
            }. Drop a term, or browse the full list.`
          : "No cards in tonight + 7 days match. Browse the full list."}
      </p>
    </section>
  );
}

/**
 * The error state.
 *
 * **"Couldn't reach Browse. Try again."** — the product's honest, brief error voice
 * (`EXPERIENCE.md` §6).
 *
 * **One retry button, and nothing else.** The page could not be read, so the page says
 * so and offers the one thing that might fix it. It does not apologise, does not explain
 * the backend, and does not offer a sign-out.
 *
 * **The shell stays functional around it.** The sidenav and the bottom-tab bar are
 * rendered by `AppShell`, *outside* this component, so the user can always leave. A
 * failure that traps the reader inside the broken page would be a worse failure than
 * the one it reports.
 */
export function BrowseError() {
  return (
    <section aria-label="Browse could not be loaded" data-browse-error>
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        Couldn&apos;t reach Browse. Try again.
      </h1>
      <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-md)]">
        Your saved events are safe. This is on our side.
      </p>
      <Link
        href="/browse"
        className="mt-6 inline-block text-accent-terracotta underline underline-offset-4 [font:var(--type-scale-body-sm)]"
        data-browse-retry
      >
        Try again →
      </Link>
    </section>
  );
}

/**
 * The loading skeleton.
 *
 * **Twelve card-shaped rectangles, pulsing at 1800ms.** The product's single
 * animation — `motion.skeletonPulse`, declared once in `styles/globals.css` and
 * collapsed to an instant render under `prefers-reduced-motion`.
 *
 * **No spinners, anywhere.** A spinner is a visual urgency badge and the product
 * refuses urgency badges (PRD §13.1). A skeleton says "a card is coming and it is about
 * this big"; a spinner says "wait".
 *
 * **Twelve, not twenty-four.** The grid holds three columns at desktop and one on
 * mobile, so twelve fills four rows at desktop and twelve rows on a phone — enough to
 * hold the layout while the read is in flight, without promising a page the reader has
 * not been given yet.
 *
 * **The wrapper carries the accessible name** and the rectangles are `aria-hidden`, so
 * a screen reader hears "Loading Browse" once rather than twelve identical boxes.
 */
export function BrowseSkeleton() {
  return (
    <div role="status" aria-label="Loading Browse" className="mt-8" data-browse-skeleton>
      <div className="grid grid-cols-1 gap-[20px] md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
        {Array.from({ length: 12 }, (_, index) => (
          <div
            key={index}
            aria-hidden="true"
            className="skeleton-pulse h-[220px] rounded-card bg-surface-paper"
          />
        ))}
      </div>
    </div>
  );
}
