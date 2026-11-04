/**
 * The sitemap and robots policy's production probe.
 *
 * **Every claim the unit tests cannot see is measured here**, against a running
 * production server (`next start`) and a stub catalog API that counts its requests.
 *
 * The claims:
 *
 * 1. **`/robots.txt` is served, and it carries the policy** — the public surface
 *    allowed, the authed and dev prefixes disallowed, and the sitemap named.
 * 2. **`/sitemap.xml` is a `<sitemapindex>`**, not a `<urlset>` — the index names its
 *    children, and a crawler walks them.
 * 3. **The index splits at 50,000 URLs** — a feed of 120,000 produces three children,
 *    and a feed of three produces one.
 * 4. **A child is a `<urlset>` with a `<loc>` and a `<lastmod>` per URL.**
 * 5. **A child that does not exist is a 404**, and a child whose read fails is a **503**
 *    rather than an empty document.
 * 6. **The feed's facts are cached** — the second request for the same child costs no
 *    request to the backend.
 */
const BASE = process.env.SITEMAP_BASE ?? "http://127.0.0.1:3230";
const STUB = process.env.STUB_BASE ?? "http://127.0.0.1:8124";

async function count() {
  const response = await fetch(`${STUB}/__count`);
  return (await response.json()).requests;
}

async function reset() {
  await fetch(`${STUB}/__reset`);
}

async function setTotal(value) {
  await fetch(`${STUB}/__total?value=${value}`);
}

/** Makes the stub's feed fail, or stop failing. */
async function setFailing(value) {
  await fetch(`${STUB}/__fail?value=${value}`);
}

/**
 * **Empty the server's cache without restarting it.**
 *
 * **The probe's own earlier requests warm the cache**, so a measurement taken after
 * them would cost no request and prove nothing. The revalidation signal is the only way
 * to clear the server's cache while it runs — and using it here doubles as a check that
 * the signal works.
 */
async function flush() {
  const response = await fetch(`${BASE}/revalidate`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${process.env.REVALIDATION_SECRET ?? "local-dev-only-revalidation-secret-not-for-production"}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ paths: ["/sitemap.xml"], event_version: 1 }),
  });
  if (response.status !== 200) {
    throw new Error(`the flush failed: ${response.status}`);
  }
}

async function text(path) {
  const response = await fetch(`${BASE}${path}`, { redirect: "manual" });
  return { status: response.status, body: await response.text() };
}

/** The `<loc>` values in a document. */
function locations(body) {
  return [...body.matchAll(/<loc>([^<]*)<\/loc>/g)].map((match) => match[1] ?? "");
}

async function main() {
  console.log("── the robots file ─────────────────────────────────────────");
  const robots = await text("/robots.txt");
  console.log(`status                 ${robots.status}`);
  console.log(robots.body.trimEnd());
  console.log(
    `names the sitemap      ${robots.body.includes("Sitemap:") ? "yes" : "NO — the crawler is never told where the sitemap is"}`,
  );
  console.log(
    `disallows the authed   ${
      ["/settings", "/timeline", "/conflicts", "/onboarding", "/dev"].every((prefix) =>
        robots.body.includes(`Disallow: ${prefix}`),
      )
        ? "yes"
        : "NO — an authed route is crawlable"
    }`,
  );
  console.log(
    `allows the public      ${
      robots.body.includes("Allow: /") && !robots.body.includes("Disallow: /events")
        ? "yes"
        : "NO — the public event pages are not crawlable"
    }`,
  );

  console.log("");
  console.log("── the sitemap index ──────────────────────────────────────");
  await setTotal(3);
  await flush();
  await reset();
  const index = await text("/sitemap.xml");
  console.log(`status                 ${index.status}`);
  console.log(`is a sitemapindex      ${index.body.includes("<sitemapindex") ? "yes" : "NO"}`);
  console.log(`children               ${locations(index.body).join(", ")}`);

  console.log("");
  console.log("── the split at the ceiling ───────────────────────────────");
  // **The split is chosen now, not discovered at scale.** A feed of 120,000 URLs is
  // three children of at most 50,000 each.
  //
  // **The cache is flushed between the measurements**, because the total decides the
  // child count and a cached total is a stale total.
  await setTotal(120000);
  await flush();
  const big = await text("/sitemap.xml");
  console.log(`feed of 120,000        ${locations(big.body).length} children`);
  console.log(`                        ${locations(big.body).join(", ")}`);

  await setTotal(50000);
  await flush();
  const exact = await text("/sitemap.xml");
  console.log(
    `feed of 50,000         ${locations(exact.body).length} children (the limit is legal)`,
  );

  await setTotal(50001);
  await flush();
  const over = await text("/sitemap.xml");
  console.log(`feed of 50,001         ${locations(over.body).length} children`);

  console.log("");
  console.log("── a child sitemap ────────────────────────────────────────");
  await setTotal(3);
  await flush();
  await reset();
  const child = await text("/sitemap/0.xml");
  console.log(`status                 ${child.status}`);
  console.log(`is a urlset            ${child.body.includes("<urlset") ? "yes" : "NO"}`);
  console.log(`urls                   ${locations(child.body).length}`);
  console.log(
    `every url has a lastmod ${
      (child.body.match(/<lastmod>/g) ?? []).length === locations(child.body).length
        ? "yes"
        : "NO — a crawler is not told what moved"
    }`,
  );
  for (const location of locations(child.body)) console.log(`  ${location}`);

  console.log("");
  console.log("── a child that does not exist ────────────────────────────");
  const missing = await text("/sitemap/abc.xml");
  console.log(`/sitemap/abc.xml       ${missing.status}`);
  // **A child beyond the end of the feed is also a child that does not exist.** The
  // index names `max(1, ceil(total / 50_000))` children, so a request for a child past
  // that is a request for a sitemap that is not there — and the answer is a 404, not
  // an empty `<urlset>`, because an empty document says "this site has no pages" and
  // that is false.
  await setTotal(3);
  await flush();
  const beyond = await text("/sitemap/9.xml");
  console.log(`/sitemap/9.xml         ${beyond.status}`);
  console.log(
    `not an empty document  ${
      beyond.status === 404 && !beyond.body.includes("<urlset")
        ? "yes"
        : "NO — a child that does not exist is dressed up as an empty sitemap"
    }`,
  );

  console.log("");
  console.log("── the children partition the feed ───────────────────────");
  // **The children are a partition, not a cover with overlaps.** A URL served by two
  // children is a URL counted twice, and a URL in no child is a page the crawler never
  // finds. A feed of 50,001 is split at 50,000, so the first child holds 50,000 and the
  // second holds the one that is left — and the two must not share a URL.
  await setTotal(50001);
  await flush();
  const firstChild = await text("/sitemap/0.xml");
  const secondChild = await text("/sitemap/1.xml");
  const firstLocations = locations(firstChild.body);
  const secondLocations = locations(secondChild.body);
  const overlap = firstLocations.filter((location) => secondLocations.includes(location));
  console.log(`first child            ${firstLocations.length} urls`);
  console.log(`second child           ${secondLocations.length} urls`);
  console.log(`together               ${firstLocations.length + secondLocations.length} urls`);
  console.log(
    `no url is served twice ${overlap.length === 0 ? "yes" : `NO — ${overlap.length} overlapping`}`,
  );
  console.log(
    `no child is over 50,000 ${
      firstLocations.length <= 50000 && secondLocations.length <= 50000
        ? "yes"
        : "NO — a child breaks the protocol's ceiling"
    }`,
  );

  console.log("");
  console.log("── a feed that cannot answer ────────────────────────────");
  // **A failure is a 503, not an empty sitemap.** A sitemap that lists nothing says
  // "this site has no pages", and a crawler that fetched it would take the emptiness
  // as the truth.
  await setFailing(1);
  await flush();
  const brokenIndex = await text("/sitemap.xml");
  const brokenChild = await text("/sitemap/0.xml");
  console.log(`/sitemap.xml           ${brokenIndex.status} (a failure, not an empty document)`);
  console.log(`/sitemap/0.xml         ${brokenChild.status}`);
  console.log(
    `the index says so      ${
      brokenIndex.status === 503 && !brokenIndex.body.includes("<sitemapindex")
        ? "yes"
        : "NO — the failure is disguised as an answer"
    }`,
  );
  await setFailing(0);
  await flush();

  console.log("");
  console.log("── the caching ────────────────────────────────────────────");
  // **The second request costs no request to the backend.** The feed's facts are in the
  // data cache, and the sitemap's document is a projection of them.
  //
  // **The feed is small here**, so the number of backend requests is the *number of
  // feed pages* the child had to read, and not the size of the catalog.
  await setTotal(3);
  await flush();
  await reset();
  await text("/sitemap/0.xml");
  const first = await count();
  await text("/sitemap/0.xml");
  const second = await count();
  console.log(`first request          ${first} backend request(s)`);
  console.log(`second request         ${second} backend request(s)`);
  console.log(
    `the second is free     ${second === first ? "yes" : "NO — the feed is read on every request"}`,
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
