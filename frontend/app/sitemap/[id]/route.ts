import { readUrlFeedRange } from "@/lib/url-feed-read";
import { childStart, isNamedChild, MAX_URLS_PER_SITEMAP } from "@/lib/sitemap-plan";
import { siteUrl } from "@/lib/site-url";

/**
 * `/sitemap/{id}.xml` — one **child** sitemap: a `<urlset>` of at most 50,000 URLs.
 *
 * **The child is a slice of the feed, and the slice is exact.** The feed is one flat
 * list in one total order — events then cities, each ordered by its own key — so
 * position `n` in the feed is a well-defined URL, and the children partition the feed:
 * child 0 is positions `[0, 50_000)`, child 1 is `[50_000, 100_000)`, and so on.
 *
 * **The id is the child's index, with the `.xml` suffix Next hands us.** Next's dynamic
 * segment swallows the suffix into the parameter, so `params.id` arrives as `"0.xml"`.
 * The index advertises `/sitemap/0.xml`, and this route serves exactly that name.
 *
 * **A child the index does not name is a 404.** The split itself lives in
 * `lib/sitemap-plan.ts`, so the index and the children cannot disagree about how many
 * children there are. The child learns the feed's total from the same read that
 * produces its URLs, so the question costs no extra request and the whole read stays
 * cached.
 *
 * **A failure to read the feed is a 503, not an empty sitemap.** A child that listed
 * nothing would say the site has no pages, and a child that listed half its URLs would
 * say something just as false. A crawler takes the document as the truth.
 */
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await context.params;

  const child = parseChildId(id);

  if (child === null) {
    return new Response("no such sitemap\n", {
      status: 404,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  // **The child's slice, and the slice carries the feed's total.** The range read
  // walks the feed's pages that overlap this child, and the first page it reads
  // answers with the feed's `total` — so the "is this child named?" question is
  // answered from the *same read* that produces the URLs, and it costs no extra
  // request.
  //
  // **The range's total is the feed's total, not the total of the pages it walked.**
  // Every page the backend answers carries the feed's size in its `total` field, so
  // the range's `total` is that number — including when the walk stopped on the first
  // page because the catalog is shorter than the run asked for.
  const read = await readUrlFeedRange(childStart(child), MAX_URLS_PER_SITEMAP);

  if (read.kind !== "found") {
    return new Response("the sitemap is temporarily unavailable\n", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  // **A child the index does not name is a 404, not an empty document.** The index
  // names `max(1, ceil(total / 50_000))` children, and a request for a child beyond
  // that is a request for a sitemap that does not exist. An empty `<urlset>` would say
  // "this site has no pages" — which is false, and false in the way that erodes a
  // crawler's trust in the whole document.
  //
  // **The whole child's read is cached**, so the second request for the same child
  // costs no request to the backend.
  if (!isNamedChild(child, read.page.total)) {
    return new Response("no such sitemap\n", {
      status: 404,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const body = urlSet(siteUrl(), read.page.items);

  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": "public, max-age=0, s-maxage=3600, stale-while-revalidate=86400",
    },
  });
}

/**
 * The child's index, from the route's parameter.
 *
 * **The parameter is `"0.xml"`, and the suffix is stripped here.** A child that is not
 * a number is a 404 rather than a crash: a crawler walking off the end of the index is
 * doing something ordinary, and the answer is "no such sitemap".
 */
export function parseChildId(raw: string): number | null {
  const withoutSuffix = raw.replace(/\.xml$/, "");
  if (!/^\d+$/.test(withoutSuffix)) return null;
  const parsed = Number.parseInt(withoutSuffix, 10);
  if (!Number.isSafeInteger(parsed) || parsed < 0) return null;
  return parsed;
}

/**
 * One `<urlset>` document.
 *
 * **Every entry carries a `lastmod`, because the feed knows it.** The feed's
 * `last_modified` is the page's real last change — taken from the event's append-only
 * state history, not from a timestamp of convenience — so a crawler is told the truth
 * about what moved and can skip what has not.
 *
 * **The XML is escaped.** A path is built from a slug and a city slug, and the escaping
 * is what makes the document well-formed whatever those contain.
 */
export function urlSet(
  origin: URL | undefined,
  items: { path: string; last_modified: string }[],
): string {
  const lines: string[] = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  ];

  for (const item of items) {
    lines.push("  <url>");
    lines.push(`    <loc>${escapeXml(location(origin, item.path))}</loc>`);
    lines.push(`    <lastmod>${escapeXml(item.last_modified)}</lastmod>`);
    lines.push("  </url>");
  }

  lines.push("</urlset>");

  return `${lines.join("\n")}\n`;
}

/**
 * One URL's absolute location.
 *
 * **The origin is the site's public origin, not the server's** — `siteUrl()` reads
 * `PUBLIC_SITE_URL`, so a deployment changes it without a rebuild. An unset origin in
 * production yields `undefined`, and the location is then the **relative** path, which
 * the protocol allows for a same-site reference and which is far better than an
 * absolute URL pointing at `localhost`.
 */
function location(origin: URL | undefined, path: string): string {
  return origin ? new URL(path, origin).toString() : path;
}

/**
 * The five XML entities, escaped.
 *
 * **Every one of them, and not just `&` and `<`.** A path or a timestamp that carried a
 * quote or an apostrophe would produce a document that no parser accepts — and a
 * sitemap that does not parse is worth nothing to a crawler.
 */
function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
