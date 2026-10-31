import Link from "next/link";

/**
 * The Timeline's states (`EXPERIENCE.md` §5).
 *
 * **Four states, four different claims.**
 *
 *   - **A quiet day** is a *cell* state: one day has nothing in it. The other six days
 *     may have plenty. "Quiet day." is centred in the cell, in muted meta ink.
 *   - **A quiet week** is a *page* state: nothing at all is scheduled. The grid is
 *     replaced by the week's own line and one link — a grid of seven empty columns
 *     saying "Quiet day." seven times says less than the week does.
 *   - **Loading** draws the week's shape: seven columns of `surface.elevated`
 *     rectangles. **No day labels** — the skeleton is the shape, not the content.
 *   - **The error** says the read failed, and offers one retry.
 */

/**
 * A day with nothing in it.
 *
 * **"Quiet day."** — `Text.Meta`, muted ink, centred. **No CTA and no upsell**: the
 * empty-pattern rule is that a quiet surface says so and stops. The Add affordance
 * lives in the nav, not in an empty column.
 */
export function QuietDay() {
  return (
    <p className="flex flex-1 items-center justify-center pt-6 text-center text-ink-muted italic [font:var(--type-scale-meta-md)]">
      Quiet day.
    </p>
  );
}

/**
 * A week with nothing in it.
 *
 * **"Your week is quiet. Pulse Digest is the place to discover."** — and one
 * `Text.Meta` "Open Pulse Digest" link, low weight, muted ink, to `/`.
 *
 * **One link, not a CTA.** Terracotta is rationed to four sanctioned uses and a
 * primary button is not one of them; the digest's own empty state makes the same
 * choice. And the link is a **real** link — `/` exists — so it is not a disabled
 * control promising a destination the product cannot deliver.
 */
export function QuietWeek() {
  return (
    <div className="max-w-(--layout-container-reading)">
      <h2 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        Your week is quiet. Pulse Digest is the place to discover.
      </h2>
      <p className="mt-3">
        <Link
          href="/"
          className="text-ink-muted underline underline-offset-4 [font:var(--type-scale-meta-md)]"
        >
          Open Pulse Digest
        </Link>
      </p>
    </div>
  );
}

/**
 * The Timeline could not be read.
 *
 * **"Couldn't reach Timeline. Try again."** with one retry — the same shape as the
 * digest's error state, and for the same reason.
 *
 * **The retry is a `Button.Primary`** — a terracotta fill. Terracotta is rationed, and
 * the primary CTA is one of the four sanctioned uses: a failure that asks the user for
 * a decision is a decision moment.
 *
 * **The retry is a link that re-navigates to the same URL**, which makes the server
 * render again. The Timeline is a server-side read, and a client-side re-fetch would
 * be a second reader of the same endpoint with a different failure mode.
 */
export function TimelineError({ href }: { href: string }) {
  return (
    <div className="max-w-(--layout-container-reading)">
      <h2 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        Couldn&apos;t reach Timeline. Try again.
      </h2>
      <p className="mt-3 text-ink-secondary [font:var(--type-scale-body-md)]">
        Your events are safe. This is on our side.
      </p>
      <Link
        href={href}
        className="mt-6 inline-block rounded-control bg-accent-terracotta px-6 py-3 text-ink-inverse [font:var(--type-scale-meta-md)]"
      >
        Try again
      </Link>
    </div>
  );
}

/**
 * The week's skeleton.
 *
 * **Seven columns, each a stack of three to five 40px rectangles.** The columns are
 * the week's shape; the rectangles are the blocks' shape.
 *
 * **No day labels.** A skeleton that prints "Mon" and "Tue" is half a rendering, and a
 * half-rendering that then changes is worse than an empty frame — the user reads the
 * label, then watches it move.
 */
export function TimelineSkeleton() {
  return (
    <div
      aria-hidden="true"
      className="hidden overflow-hidden rounded-timeline-cell border border-border-subtle bg-surface-elevated md:grid md:grid-cols-(--layout-timeline-grid)"
    >
      {Array.from({ length: 7 }, (_, column) => (
        <div
          key={column}
          className="flex min-h-[480px] flex-col gap-2 border-r border-border-subtle p-3 last:border-r-0"
        >
          {Array.from({ length: 3 + (column % 3) }, (_, row) => (
            <div key={row} className="skeleton-pulse h-[40px] rounded-subtle bg-surface-subtle" />
          ))}
        </div>
      ))}
    </div>
  );
}
