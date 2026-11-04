import Link from "next/link";

/**
 * The public event page's 404 — the document a stranger gets for a slug that names no
 * public event.
 *
 * **It says what happened, and it offers one way out.** "This event isn't available" is
 * a fact about the world; a bare error page is a shrug. The reader who followed a link
 * from a search result needs to know the page is gone rather than broken, and to be
 * able to leave.
 *
 * **A superseded event does not land here.** Its 404 carries the successor's slug, and
 * the page turns that into a **308 redirect** to the successor (`app/events/[id]/page.tsx`)
 * — the link a crawler already holds resolves forward rather than dying, which is what
 * the backend carries the slug *for*. So this document is only ever shown for a slug
 * that names no public event at all, and it takes no props: there is nothing left for
 * it to say that the redirect has not already said.
 */
export function PublicEventNotFound() {
  return (
    <article className="mx-auto w-full max-w-(--layout-container-reading)">
      <h1 className="text-ink-primary [font:var(--type-scale-display-md)]">
        This event isn&apos;t available.
      </h1>
      <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-lg)]">
        The listing may have been withdrawn, or the event may have been replaced by another one.
      </p>

      <div className="mt-8 flex flex-wrap items-center gap-6">
        <Link
          href="/preview"
          className="[font:var(--type-scale-body-sm)] text-ink-secondary underline underline-offset-4"
        >
          Browse what&apos;s on
        </Link>
      </div>
    </article>
  );
}
