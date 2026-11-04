import { BrandTopbar } from "@/components/brand-topbar";
import { PublicEventNotFound } from "@/components/public-event/public-event-not-found";
import { PreAuthFooter } from "@/components/pre-auth/pre-auth-footer";

/**
 * `/events/[id]` — the route's 404.
 *
 * **This file is what makes the unknown-slug answer a real 404.** Next.js's rule is
 * exact: "To return a real `404` status, the resource has to be checked before the
 * response streams." The page calls `notFound()` in its render path, before any
 * `<Suspense>` boundary, and this file renders the document — which Next serves with a
 * **404 status** because nothing has streamed yet.
 *
 * **A `not-found.tsx` that is not here would render with a 200.** For a response that
 * has already streamed, Next's not-found boundary returns the document with a **200**
 * status, and a soft 404 poisons an index: a crawler records the URL as a page, and the
 * URL stays in the index forever.
 *
 * **It carries the public chrome, because the 404 it serves is the public page's 404.**
 * A stranger who followed a search result to a slug that no longer exists gets the
 * brand and the footer, exactly as the page they were looking for had — not the signed-in
 * app shell, which they cannot use and which would ask them to log in to a page they
 * never had access to.
 */
export default function EventNotFound() {
  return (
    <div className="flex min-h-screen flex-col">
      <BrandTopbar />
      <main className="fade-in mx-auto w-full max-w-(--layout-container-max) flex-1 px-6 py-8">
        <PublicEventNotFound />
      </main>
      <PreAuthFooter />
    </div>
  );
}
