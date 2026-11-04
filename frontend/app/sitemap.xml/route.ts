import { readUrlFeed } from "@/lib/url-feed-read";
import { sitemapChildren } from "@/lib/sitemap-plan";
import { siteUrl } from "@/lib/site-url";

/**
 * `/sitemap.xml` — the **sitemap index**.
 *
 * **Why this is a route handler and not `app/sitemap.ts`.** Measured, against Next
 * 16.3.8: `app/sitemap.ts` emits a `<urlset>` and never a `<sitemapindex>`, and
 * `app/sitemap.ts` cannot coexist with `app/sitemap.xml/route.ts` in one build — the
 * build fails with *"Conflicting route and metadata at /sitemap.xml"*. So the index is
 * hand-written, and `app/sitemap.ts` does not exist.
 *
 * **The index names its children, and the children are the feed's pages.** The feed is
 * one flat list in one total order — events then cities, each ordered by its own key —
 * so a child is a contiguous slice of that list and the children partition it. The
 * number of children is `max(1, ceil(total / 50_000))`, because the protocol's ceiling
 * is 50,000 URLs per sitemap and a catalog that exceeds it must be split rather than
 * truncated.
 *
 * **The split is chosen now, not discovered at scale.** One URL makes one child; 120,000
 * URLs make three. The rule is a pure function of the feed's `total`, so the index is
 * correct at any size without a deployment.
 *
 * **A failure to read the feed is a 503, not an empty sitemap.** A sitemap that lists
 * nothing says "this site has no pages", and a sitemap that lists half the pages says
 * something just as false. A crawler that fetched a truncated sitemap would take the
 * truncation as the truth.
 */
export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  // **The total is read uncached, and that is the point.** The total decides how many
  // children there are, so a cached total is a stale total, and a stale total means
  // the index names the wrong number of children — a crawler would either stop early,
  // with URLs on no page, or fetch a child that does not exist. The index is one small
  // request; the *children* are where the volume is, and those stay cached.
  const read = await readUrlFeed(1, { skipCache: true });

  if (read.kind !== "found") {
    // **The feed could not be read, so the sitemap cannot be written.** The honest
    // answer is "not now" — a server error — and not an empty document.
    return new Response("the sitemap is temporarily unavailable\n", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const origin = siteUrl();
  const total = read.page.total;
  // **The count comes from `lib/sitemap-plan.ts`, not from arithmetic here.** The index
  // names the children and the children answer "am I one of the named ones?", and the
  // two must not compute the split separately — a disagreement between them is a
  // sitemap that describes itself inconsistently.
  const children = sitemapChildren(total);

  const body = sitemapIndex(origin, children);

  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": "public, max-age=0, s-maxage=3600, stale-while-revalidate=86400",
    },
  });
}

/**
 * The index document.
 *
 * **The origin is the site's public origin, not the server's.** `siteUrl()` reads
 * `PUBLIC_SITE_URL`, so a deployment changes it without a rebuild — and in production an
 * unset origin yields `undefined`, in which case the document carries **relative**
 * locations. A relative `<loc>` is what the sitemap protocol allows for a same-site
 * reference, and it is far better than an absolute URL pointing at `localhost`.
 */
export function sitemapIndex(origin: URL | undefined, children: number): string {
  const lines: string[] = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  ];

  for (let id = 0; id < children; id += 1) {
    lines.push(`  <sitemap><loc>${childLocation(origin, id)}</loc></sitemap>`);
  }

  lines.push("</sitemapindex>");

  return `${lines.join("\n")}\n`;
}

/**
 * One child's location.
 *
 * **The child is `/sitemap/{id}.xml`.** Next's dynamic segment swallows the `.xml`
 * suffix into the parameter, so the route reads `params.id` as `"0.xml"` and the file
 * it serves is named `0.xml` — which is the name the index advertises and the name a
 * crawler will fetch.
 */
export function childLocation(origin: URL | undefined, id: number): string {
  const path = `/sitemap/${id}.xml`;
  return origin ? new URL(path, origin).toString() : path;
}
