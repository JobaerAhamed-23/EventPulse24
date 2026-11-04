import Link from "next/link";

import { BrandTopbar } from "@/components/brand-topbar";
import { PreAuthFooter } from "@/components/pre-auth/pre-auth-footer";

/**
 * `/events-in/[slug]` — the route's 404.
 *
 * **This file is what makes the unknown slug answer a real 404.** Next.js's rule is
 * exact: "To return a real `404` status, the resource has to be checked before the
 * response streams." The page calls `notFound()` in its render path, before any
 * `<Suspense>` boundary, and this file renders the document — which Next serves with a
 * **404 status** because nothing has streamed yet.
 *
 * **A `not-found.tsx` that is not here would render with a 200.** For a response that
 * has already streamed, Next's not-found boundary returns the document with a **200**
 * status, and a soft 404 poisons an index: a crawler records the URL as a page, and the
 * URL stays in the index forever. That is why this segment carries **no `loading.tsx`** —
 * a segment-level `loading.tsx` is a Suspense boundary *above* the page, so the response
 * streams before `notFound()` can set the status.
 *
 * **It takes no props, and it needs none.** Next's `createNotFoundLoaderTree` builds the
 * boundary with an empty params object, so a `not-found.tsx` cannot read the slug it was
 * reached for — the same reason `components/public-event/public-event-not-found.tsx`
 * takes none. There is nothing left to say that the 404 itself has not already said.
 *
 * **It carries the public chrome, because the 404 it serves is a public page's 404.** A
 * stranger who followed a search result to a city we do not publish gets the brand and
 * the footer, exactly as the page they were looking for had — not the signed-in app
 * shell, which they cannot use.
 *
 * **A sparse city does not land here.** A city that exists but has too few events reads
 * as **200** with `is_published: false`, and the page renders "coming soon". This
 * document is only ever shown for a slug that names no city at all.
 */
export default function CityNotFound() {
  return (
    <div className="flex min-h-screen flex-col">
      <BrandTopbar />
      <main className="fade-in mx-auto w-full max-w-(--layout-container-max) flex-1 px-6 py-8">
        <article className="mx-auto w-full max-w-(--layout-container-reading)">
          <h1 className="text-ink-primary [font:var(--type-scale-display-md)]">
            We don&apos;t have that city.
          </h1>
          <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-lg)]">
            The page you asked for isn&apos;t one we publish. We might not cover that area yet.
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
      </main>
      <PreAuthFooter />
    </div>
  );
}
