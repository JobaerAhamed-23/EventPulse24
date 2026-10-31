import Link from "next/link";

/**
 * The Conflict Review screen's states (`EXPERIENCE.md` §5).
 *
 * **Three states, three different claims.**
 *
 *   - **No overlaps** is the *quiet* state: the user has events and none of them
 *     clash. "No overlaps." with the microcopy line, and one `Text.Meta` link.
 *   - **Loading** draws the page's shape: two section skeletons with row skeletons. No
 *     spinner.
 *   - **The error** says the read failed, and offers one retry.
 */

/**
 * A user with no overlaps at all.
 *
 * **"No overlaps."** — the calm, flat claim. **"Conflicts appear here as you save
 * events."** says what the page is for without nagging.
 *
 * **One `Text.Meta` link, low weight, muted ink** — "What counts as a conflict?" It is
 * a real link to a real place, and it is a link rather than a button because it is
 * navigation, not an action. **No terracotta CTA**: terracotta is rationed to four
 * sanctioned uses and a quiet page is not one of them.
 */
export function NoOverlaps() {
  return (
    <div className="max-w-(--layout-container-reading)">
      <h2 className="text-ink-primary [font:var(--type-scale-headline-lg)]">No overlaps.</h2>
      <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
        Conflicts appear here as you save events.
      </p>
      <p className="mt-3">
        <Link
          href="/timeline"
          className="text-ink-muted underline underline-offset-4 [font:var(--type-scale-meta-md)]"
        >
          What counts as a conflict?
        </Link>
      </p>
    </div>
  );
}

/**
 * The Conflicts page could not be read.
 *
 * **"Couldn't analyze conflicts. Try again."** with one retry — the same shape as the
 * digest's and the Timeline's error states, and for the same reason.
 *
 * **The retry is a `Button.Primary`** — a terracotta fill. Terracotta is rationed, and
 * the primary CTA is one of the four sanctioned uses: a failure that asks the user for
 * a decision is a decision moment.
 *
 * **The retry is a link that re-navigates to the same URL**, which makes the server
 * render again. The page is a server-side read, and a client-side re-fetch would be a
 * second reader of the same endpoint with a different failure mode.
 */
export function ConflictsError({ href }: { href: string }) {
  return (
    <div className="max-w-(--layout-container-reading)">
      <h2 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        Couldn&apos;t analyze conflicts. Try again.
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
 * The page's skeleton.
 *
 * **Two section skeletons — Active and Resolved — each with row skeletons.** The
 * skeleton is the page's shape, not its content: a spinner would say "something is
 * happening" and nothing about what is coming.
 *
 * **No section labels.** A skeleton that prints "Active" is half a rendering, and a
 * half-rendering that then changes is worse than an empty frame — the user reads the
 * label, then watches it move.
 */
export function ConflictsSkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-8">
      {[0, 1].map((section) => (
        <section key={section} className="flex flex-col gap-3">
          <div className="skeleton-pulse h-[22px] w-20 rounded-subtle bg-surface-subtle" />
          {Array.from({ length: section === 0 ? 2 : 3 }, (_, row) => (
            <div
              key={row}
              className="skeleton-pulse h-[76px] rounded-timeline-cell bg-surface-subtle"
            />
          ))}
        </section>
      ))}
    </div>
  );
}
