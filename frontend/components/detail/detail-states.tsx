import Link from "next/link";

/**
 * The Detail Screen's three non-content states: loading, removed and error.
 *
 * **Loading is the Detail Screen's own shape, not the digest's.** `EXPERIENCE.md` §12
 * describes it: "one full-width header block + one meta row + 3 chip skeletons. Same
 * fade animation." The **same fade** means `motion.fadeIn` — the product's single
 * transition — and **not** the digest's `skeleton-pulse` keyframe. The digest's pulse
 * is a *waiting* animation on a surface that waits; a detail page's skeleton is a
 * *shape* that fades in. The pulse belongs to the skeleton, and the skeleton here is
 * not the digest's.
 *
 * **Removed and error are different failures.** "This event is no longer available." is
 * a fact about the world — the event started, or it was withdrawn, or it was never
 * public. "Couldn't load this event." is a fact about us. Folding them together would
 * either lie about the event or lie about our infrastructure.
 *
 * **The error's copy carries its own instruction** — "Back to Pulse Digest." — and the
 * action matches it: one primary button home, and nothing else.
 */
export function DetailSkeleton() {
  return (
    <div aria-hidden="true" data-detail-skeleton>
      {/* The header block: one full-width rectangle. */}
      <div className="h-8 w-2/3 rounded-card bg-surface-elevated" />
      {/* The meta row: a shorter, quieter line. */}
      <div className="mt-4 h-4 w-1/2 rounded-card bg-surface-elevated" />
      {/* The three chip skeletons. */}
      <div className="mt-8 flex flex-col gap-3">
        <div className="h-16 rounded-card bg-surface-elevated" />
        <div className="h-16 rounded-card bg-surface-elevated" />
        <div className="h-16 rounded-card bg-surface-elevated" />
      </div>
    </div>
  );
}

/**
 * The event is gone — it has started, or it was withdrawn, or it was never public.
 *
 * **A back link, not a retry.** Retrying cannot bring an event back.
 */
export function DetailRemoved() {
  return (
    <div className="max-w-(--layout-container-reading)" data-detail-removed>
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        This event is no longer available.
      </h1>
      <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-md)]">
        It may have already started.
      </p>
      <Link
        href="/"
        className="mt-6 inline-block text-accent-terracotta underline underline-offset-4 [font:var(--type-scale-body-sm)]"
      >
        Back to Pulse Digest
      </Link>
    </div>
  );
}

/**
 * The API could not be reached.
 *
 * **One primary action, home.** The copy says where the action goes, and it is the only
 * thing offered — no "try again" on a screen whose retry would hit the same API.
 */
export function DetailError() {
  return (
    <div className="max-w-(--layout-container-reading)" data-detail-error>
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        Couldn&apos;t load this event. Back to Pulse Digest.
      </h1>
      <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-md)]">
        Your saved events are safe. This is on our side.
      </p>
      <Link
        href="/"
        className="mt-6 inline-block rounded-control bg-accent-terracotta px-5 py-2.5 text-ink-inverse [font:var(--type-scale-meta-md)]"
      >
        Back to Pulse Digest
      </Link>
    </div>
  );
}
