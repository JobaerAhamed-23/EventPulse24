/**
 * The sitemap's **split** — the arithmetic that decides how many children there are and
 * where each one starts.
 *
 * **This lives in one module because the index and the children must agree.** The index
 * names `max(1, ceil(total / 50_000))` children, and a child answers "am I one of the
 * named ones?". If the two computed the count separately they could disagree — the
 * index would name a child that answers 404, or a child would answer 200 for a child
 * the index never named. Both are the same fault: **the sitemap would describe itself
 * inconsistently**, and a crawler that fetches a 404 from the sitemap it was just
 * given loses trust in the whole document.
 *
 * **The count is a pure function of the total, so it is correct at any size without a
 * deployment.** One URL makes one child; 120,000 URLs make three. The rule is chosen
 * now, not discovered at scale.
 */

/** The protocol's ceiling: 50,000 URLs in one sitemap. */
export const MAX_URLS_PER_SITEMAP = 50_000;

/**
 * How many children the sitemap is split into, for a feed of `total` URLs.
 *
 * **One URL still makes one child.** `max(1, ...)` rather than `ceil(...)`, because a
 * catalog of one URL produces a child holding one URL, and a catalog of *zero* URLs
 * produces a child holding none — an empty `<urlset>` is the honest answer for a site
 * with no public pages, and an index naming no children at all would be a document
 * that says "there is nothing here" without saying it in the form a crawler reads.
 */
export function sitemapChildren(total: number): number {
  if (!Number.isFinite(total) || total <= 0) return 1;
  return Math.max(1, Math.ceil(total / MAX_URLS_PER_SITEMAP));
}

/**
 * The first position in the feed that a child covers.
 *
 * **The children partition the feed.** Child 0 is positions `[0, 50_000)`, child 1 is
 * `[50_000, 100_000)`, and so on — so no URL is served twice and no URL is missed.
 */
export function childStart(id: number): number {
  return id * MAX_URLS_PER_SITEMAP;
}

/**
 * Whether a child is one the index names.
 *
 * **A child the index does not name does not exist.** The answer is a 404, not an
 * empty `<urlset>`: an empty document says "this site has no pages", and for a child
 * that was never named that is simply false. A 404 says "no such sitemap", which is
 * true.
 *
 * **The catalog can shrink between the index's read and the child's read**, so this is
 * not a formality. A crawler walking off the end of the index is doing something
 * ordinary, and so is a crawler holding an index from a larger catalog — either way
 * the honest answer is "that child is not there".
 */
export function isNamedChild(id: number, total: number): boolean {
  return id >= 0 && id < sitemapChildren(total);
}
