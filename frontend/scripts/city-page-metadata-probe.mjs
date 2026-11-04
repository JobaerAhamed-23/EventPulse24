/**
 * The city page's **metadata**, read out of the served HTML.
 *
 * **The unit tests assert on the metadata object; this asserts on the bytes a crawler
 * actually reads.** A `Metadata` object and a `<meta>` tag in the response are not the
 * same thing, and the differences between them — a relative `og:url`, a canonical that
 * names the internal segment — are exactly the kind a source-level test cannot see.
 */
const BASE = process.env.PAGE_BASE ?? "http://127.0.0.1:3220";

/** The one tag the crawler reads, extracted by name. */
function tag(html, attribute, name) {
  const pattern = new RegExp(`<meta ${attribute}="${name}" content="([^"]*)"`);
  return (html.match(pattern) ?? [])[1] ?? null;
}

function link(html, relation) {
  const pattern = new RegExp(`<link rel="${relation}" href="([^"]*)"`);
  return (html.match(pattern) ?? [])[1] ?? null;
}

async function inspect(path) {
  const response = await fetch(`${BASE}${path}`, { redirect: "manual" });
  const html = await response.text();

  return {
    path,
    status: response.status,
    title: (html.match(/<title>([^<]*)<\/title>/) ?? [])[1] ?? null,
    description: tag(html, "name", "description"),
    canonical: link(html, "canonical"),
    "og:title": tag(html, "property", "og:title"),
    "og:url": tag(html, "property", "og:url"),
    "og:type": tag(html, "property", "og:type"),
    "og:image": tag(html, "property", "og:image"),
    "twitter:card": tag(html, "name", "twitter:card"),
    "link:prev": link(html, "prev"),
    "link:next": link(html, "next"),
  };
}

for (const path of [
  "/events-in-brooklyn",
  "/events-in-brooklyn?page=2",
  "/events-in-quiet",
  "/events-in-atlantis",
]) {
  console.log(JSON.stringify(await inspect(path), null, 1));
}
