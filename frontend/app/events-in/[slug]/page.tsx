import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { BrandTopbar } from "@/components/brand-topbar";
import { CityPage } from "@/components/city-page/city-page";
import { PreAuthFooter } from "@/components/pre-auth/pre-auth-footer";
import { cityPageHref, readCityPage } from "@/lib/city-page-read";

/**
 * `/events-in-{city-slug}` — the city landing page (FR-27, AD-12).
 *
 * **The public URL is the hyphenated form, and the route lives one segment deeper.**
 * Next.js has **no native prefixed dynamic segment**: `app/events-in-[slug]/page.tsx`
 * does not produce `/events-in-brooklyn`. That was measured, not inferred — the build
 * registers the route in `staticRoutes` with the regex `^/([^/]+?)(?:/)?$` and the
 * parameter named `nxtPslug`, so the request 404s and *no* `params.slug` ever arrives.
 * The cause is a disagreement inside Next between `get-segment-param.js` (a segment must
 * *be* a param) and `route-regex.js`'s `PARAMETER_PATTERN` (which accepts a literal
 * prefix) — and the parameter half wins.
 *
 * **So `next.config.ts` rewrites the public URL in and redirects the internal one back
 * out:**
 *
 * ```ts
 * rewrites:  [{ source: "/events-in-:slug", destination: "/events-in/:slug" }]
 * redirects: [{ source: "/events-in/:slug", destination: "/events-in-:slug", permanent: true }]
 * ```
 *
 * **The redirect is load-bearing, not cosmetic.** Without it the page is served at *two*
 * URLs, and a URL that forks after ranking splits the ranking across two copies. A
 * canonical link tag alone does not fix that — a crawler follows links, and the internal
 * URL is a real, reachable, indexable document.
 *
 * **The public URL is still `/events-in-brooklyn`.** The internal segment is a routing
 * detail; the canonical link, the OG URL, the cache tag and the revalidation path are
 * all the hyphenated form, and that is the only form the backend ever names.
 *
 * ---
 *
 * **`"force-dynamic"`, and this is a finding rather than a preference.**
 *
 * - **There must be no `generateStaticParams`.** Returning `[]` registers the route as
 *   prerenderable, and a prerendered route that bails to dynamic at request time throws
 *   *"Page changed from static to dynamic at runtime"* — a **500 for every URL**. The
 *   city slugs are minted at runtime by `mint_city_slug`, so a build machine cannot
 *   know them anyway.
 * - **There must be no `loading.tsx`.** A segment-level `loading.tsx` is a Suspense
 *   boundary *above* the page, so the response streams before `notFound()` can set the
 *   status — and the unknown city's 404 becomes a **soft 404 (200)**. That was measured
 *   in the previous work item: 200 with the file, 404 without it.
 * - **The segment cannot be static anyway.** The listing is *paged* (`?page=N`), and a
 *   static segment cannot serve an unbounded number of query-string variants without a
 *   `generateStaticParams` per page.
 *
 * **So the segment is dynamic and the *facts* are cached**, in the data cache, exactly
 * as `lib/public-event-read.ts` does it. The cache tag is `/events-in-{slug}` — the same
 * string `domain/revalidation.py`'s `CITY_PATH_PREFIX` builds — so the `/revalidate`
 * handler's existing `revalidateTag(path, { expire: 0 })` already drops it. **No change
 * to `app/revalidate/route.ts` is needed.**
 *
 * **AD-12's "statically generated or ISR'd" is met at the level below the page:** the
 * facts are cached under the city's own path and invalidated on demand by the signal
 * the backend already sends. The page itself is dynamic because a paged listing cannot
 * be enumerated at build time — and this is stated plainly rather than papered over.
 */
export const dynamic = "force-dynamic";
export const dynamicParams = true;

/**
 * The page's metadata — the **per-city** title, description and canonical URL (FR-28).
 *
 * **It reads no cookies.** A Request-time API in `generateMetadata` would opt the whole
 * route out of static generation, and the read is a plain public read.
 *
 * **The canonical URL is the hyphenated public form**, because that is the address the
 * backend's revalidation signal names and the one that appears in a search result. The
 * internal segment is a routing detail and never appears in a link or a tag.
 */
export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ page?: string | string[] }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const query = await searchParams;
  const page = pageNumber(query.page);

  // **The metadata reads the page the URL asks for.** A canonical that always named
  // page one would tell a crawler that page 2 *is* page 1 — and a crawler that believes
  // its canonical is the truth drops every page past the first from its index. A paged
  // listing whose later pages are de-indexed is a listing of one page.
  const read = await readCityPage(slug, page);

  // **No city, no share metadata.** The page answers 404; the metadata answers with the
  // route's title rather than promising a description the page does not have.
  //
  // **And a failure to answer is asked not to be indexed.** The two failures are not
  // the same, and the metadata says which. A **404** is the backend's own statement
  // that the slug names no city — the URL does not exist, and there is nothing to
  // index. A **failure to answer** is a statement about *us*, not about the city, and
  // the document it produces says "We couldn't load this city". **That sentence is not
  // the city's content, and a crawler that stored it would be recording our outage as
  // the city's description.** So the failure carries `robots: { index: false }` — and
  // the 404 does not, because a 404 is not indexed either way and saying so would be
  // noise.
  if (read.kind === "unavailable") {
    return { title: "Events · EventPulse24", robots: { index: false, follow: false } };
  }

  if (read.kind !== "found") {
    return { title: "Events · EventPulse24" };
  }

  const city = read.page;
  const name = city.name;
  const title = `Events in ${name} · This week and next · EventPulse24`;
  const description = `Concerts, tech meetups, classes and neighborhood events in ${name}. Curated daily by EventPulse24 — we surface what matters, not what's trending.`;

  // **The canonical is this page's own URL** — the hyphenated form, with the page
  // number when the URL carries one. The internal segment is a routing detail and never
  // appears in a tag.
  const canonical = cityPageHref(city.slug, page);

  return {
    title,
    description,
    alternates: { canonical },
    /**
     * **The paging, as head links.**
     *
     * **The page's own anchors already carry `rel="prev"` and `rel="next"`** — a crawler
     * that reads the document finds them. But a crawler that reads only the `<head>`
     * does not, and the head links are the convention: `<link rel="prev">` says "this
     * page has a predecessor" without the reader having to find the anchor.
     *
     * **The flags are the backend's.** `has_next` is measured against the *upcoming*
     * count, so a city between seasons is not sent to an empty page forever. The
     * previous page exists whenever this page is not the first.
     */
    pagination: {
      previous: page > 1 ? cityPageHref(city.slug, page - 1) : null,
      next: city.has_next ? cityPageHref(city.slug, page + 1) : null,
    },
    openGraph: {
      type: "website",
      title,
      description,
      url: canonical,
      images: [BRANDED_IMAGE],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [BRANDED_IMAGE],
    },
  };
}

/**
 * The branded share image (FR-28).
 *
 * **It is static, and it is the same for every city.** FR-28's image was held static by
 * decision — a per-city rendered OG image would mean a render per share, on a deployment
 * whose public surface is meant to be a static document. The image is the brand's mark,
 * and the city's name carries the specificity.
 */
const BRANDED_IMAGE = {
  url: "/brand/eventpulse24-logo.png",
  width: 1200,
  height: 630,
  alt: "EventPulse24",
};

export default async function CityPageRoute({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ page?: string | string[] }>;
}) {
  const { slug } = await params;
  const query = await searchParams;
  const page = pageNumber(query.page);

  const read = await readCityPage(slug, page);

  if (read.kind === "not-found") {
    // **The unknown slug is a real 404.** The backend says this slug names no city,
    // and that is a fact about the world — so the page says so, with the status to
    // match. A soft 404 would put a wrong "this city does not exist" into a search
    // index.
    notFound();
  }

  if (read.kind === "unavailable") {
    // **A failure to answer is not an answer.** Telling a crawler a city does not exist
    // because we could not reach the API would put a wrong fact into an index that is
    // hard to correct. The server error says "not now"; the page says the same.
    return (
      <PublicShell>
        <CityUnavailable />
      </PublicShell>
    );
  }

  return (
    <PublicShell>
      <CityPage page={read.page} currentPage={page} />
    </PublicShell>
  );
}

/**
 * The public chrome: the brand topbar and the pre-auth footer.
 *
 * **A visitor without a session has no sidenav, no bottom-tab bar and no account row** —
 * and rendering an empty account row would be inventing one.
 */
function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <BrandTopbar />
      <main className="fade-in mx-auto w-full max-w-(--layout-container-max) flex-1 px-6 py-8">
        {children}
      </main>
      <PreAuthFooter />
    </div>
  );
}

/**
 * The city page's own failure state: the API could not be reached.
 *
 * **This is not a 404.** A 404 is a claim about the world — this city does not exist.
 * A failure to reach the API is a claim about us, and the two must not be confused.
 */
function CityUnavailable() {
  return (
    <article className="mx-auto w-full max-w-(--layout-container-reading)">
      <h1 className="text-ink-primary [font:var(--type-scale-display-md)]">
        We couldn&apos;t load this city.
      </h1>
      <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-lg)]">
        Something went wrong on our side. Try again in a moment.
      </p>
    </article>
  );
}

/**
 * The page number the URL asks for.
 *
 * **`?page=abc` is the same case as `?page=0`.** The reader meant the first page, and
 * the backend refuses a page below one with a 422 — it treats an out-of-range request as
 * a mistake. A crawler's `?page=0` is not a mistake to be answered with an error.
 *
 * **A number too large for a float is the same case too**, and this is not
 * hypothetical. `Number.parseInt("99999999999999999999999", 10)` returns **1e+23** —
 * the digits are read correctly, but the result is past the range where a float holds
 * every integer, so JavaScript prints it in scientific notation. That number then went
 * into the **canonical URL** (`?page=1e+23`) and into the **visible page text**
 * ("page 1e+23"), and it was sent to the backend as `page=1e%2B23` — which the
 * backend's `page: int = Field(1, ge=1)` **refuses with a 422**, because `1e+23` is
 * not an integer. A 422 becomes "unavailable", and the page renders "We couldn't load
 * this city" for a URL that only ever asked for a page past the end of the listing.
 *
 * **So a page number has to be an integer a person would write.** Anything else — not
 * a number, below one, or too large to write out — is the first page.
 */
function pageNumber(raw: string | string[] | undefined): number {
  const first = Array.isArray(raw) ? raw[0] : raw;
  if (first === undefined) return 1;
  const parsed = Number.parseInt(first, 10);
  if (!Number.isFinite(parsed)) return 1;
  if (parsed < 1) return 1;
  // **A float cannot hold every integer past 2^53**, and one that cannot is printed
  // in scientific notation — which is not a page number a URL can carry. The limit is
  // `Number.MAX_SAFE_INTEGER`, the largest integer JavaScript represents exactly.
  if (!Number.isSafeInteger(parsed)) return 1;
  return parsed;
}
