/**
 * The city page's production probe.
 *
 * **Every claim the unit tests cannot see is measured here**, against a running
 * production server (`next start`) and a stub catalog API that counts its requests.
 */
const BASE = process.env.PAGE_BASE ?? "http://127.0.0.1:3220";
const STUB = process.env.STUB_BASE ?? "http://127.0.0.1:8123";

async function count() {
  const response = await fetch(`${STUB}/__count`);
  return (await response.json()).requests;
}

async function reset() {
  await fetch(`${STUB}/__reset`);
}

/** The status and the `location` header, without following the redirect. */
async function head(path) {
  const response = await fetch(`${BASE}${path}`, { redirect: "manual" });
  return { status: response.status, location: response.headers.get("location") };
}

async function html(path) {
  const response = await fetch(`${BASE}${path}`, { redirect: "manual" });
  return { status: response.status, body: await response.text() };
}

/**
 * **Empty the server's cache without restarting it.**
 *
 * **The probe's own earlier requests warm the cache**, so a "prime" measured after them
 * would cost no request and prove nothing. The revalidation signal is the only way to
 * clear the server's cache while it runs — and using it here doubles as a check that
 * the signal works.
 */
async function flush(paths = ["/events-in-brooklyn"]) {
  const response = await fetch(`${BASE}/revalidate`, {
    method: "POST",
    headers: {
      authorization: "Bearer test-secret",
      "content-type": "application/json",
    },
    body: JSON.stringify({ paths, event_version: 1 }),
  });
  if (response.status !== 200) {
    throw new Error(`the flush failed: ${response.status}`);
  }
}

async function main() {
  console.log("── the public URL ──────────────────────────────────────────");
  console.log(
    `/events-in-brooklyn            ${JSON.stringify(await head("/events-in-brooklyn"))}`,
  );
  console.log(
    `/events-in-brooklyn?page=2     ${JSON.stringify(await head("/events-in-brooklyn?page=2"))}`,
  );
  console.log(
    `/events-in/brooklyn (internal) ${JSON.stringify(await head("/events-in/brooklyn"))}`,
  );
  console.log(
    `/events-in/brooklyn?page=2     ${JSON.stringify(await head("/events-in/brooklyn?page=2"))}`,
  );
  console.log(
    `/events-in-brooklyn/extra      ${JSON.stringify(await head("/events-in-brooklyn/extra"))}`,
  );

  console.log("");
  console.log("── the statuses ───────────────────────────────────────────");
  console.log(
    `/events-in-brooklyn            ${JSON.stringify(await head("/events-in-brooklyn"))}`,
  );
  console.log(`/events-in-quiet (sparse)       ${JSON.stringify(await head("/events-in-quiet"))}`);
  console.log(
    `/events-in-atlantis (unknown)   ${JSON.stringify(await head("/events-in-atlantis"))}`,
  );

  console.log("");
  console.log("── the caching ───────────────────────────────────────────");
  // **The cache is emptied first**, so the "prime" below is a genuine first read and
  // not a read of a page the probe's own earlier sections already warmed.
  await flush();
  await reset();
  await head("/events-in-brooklyn");
  console.log(`prime                         api requests: ${await count()}`);
  await head("/events-in-brooklyn");
  console.log(`cached                        api requests: ${await count()}`);
  await head("/events-in-atlantis");
  console.log(`a 404 (first)                 api requests: ${await count()}`);
  await head("/events-in-atlantis");
  console.log(`a 404 (again)                 api requests: ${await count()}`);

  console.log("");
  console.log("── the revalidation signal ───────────────────────────────");
  await flush();
  await reset();
  await head("/events-in-brooklyn");
  await head("/events-in-brooklyn?page=2");
  console.log(`two pages primed               api requests: ${await count()}`);
  const revalidated = await fetch(`${BASE}/revalidate`, {
    method: "POST",
    headers: {
      authorization: "Bearer test-secret",
      "content-type": "application/json",
    },
    body: JSON.stringify({ paths: ["/events-in-brooklyn"], event_version: 2 }),
  });
  console.log(`POST /revalidate               ${revalidated.status}`);
  await head("/events-in-brooklyn");
  console.log(`page 1 after the signal        api requests: ${await count()}`);
  await head("/events-in-brooklyn?page=2");
  console.log(`page 2 after the signal        api requests: ${await count()}`);

  console.log("");
  console.log("── the pages are separate facts ───────────────────────────");
  // **Page 2 is cached on its own.** If the two pages shared an entry, page 2 would
  // render page 1's events — and the "next page" link would loop forever on the same
  // listing. So a first read of page 2 costs a request, and a second read costs none.
  await flush();
  await reset();
  await head("/events-in-brooklyn?page=2");
  console.log(`page 2 (first read)            api requests: ${await count()}`);
  await head("/events-in-brooklyn?page=2");
  console.log(`page 2 (second read)           api requests: ${await count()}`);

  console.log("");
  console.log("── the markup ────────────────────────────────────────────");
  const page = await html("/events-in-brooklyn");
  console.log(`status                         ${page.status}`);
  console.log(`has the h1                     ${page.body.includes("Events in Brooklyn")}`);
  console.log(
    `links to /events/{slug}        ${page.body.includes("/events/designing-for-calm-2026-08-28-a1b2c3")}`,
  );
  console.log(`has the next-page link         ${page.body.includes("/events-in-brooklyn?page=2")}`);
  console.log(`has the canonical              ${page.body.includes('rel="canonical"')}`);
  console.log(
    `has the title                  ${page.body.includes("Events in Brooklyn · This week and next · EventPulse24")}`,
  );
  console.log(`has the filter chips           ${page.body.includes(">This week<")}`);

  const sparse = await html("/events-in-quiet");
  console.log("");
  console.log(`sparse status                  ${sparse.status}`);
  console.log(`has the coming-soon copy       ${sparse.body.includes("Coming soon")}`);

  // **A page past the end of the listing.** The backend answers it with the same page
  // shape and no items, so the page must not claim the city has no upcoming events —
  // it must point back to where they are. A crawler walking off the end of a listing
  // is doing something ordinary, and it must not be told a falsehood on the way.
  const pastEnd = await html("/events-in-brooklyn?page=99");
  console.log("");
  console.log(`past-the-end status            ${pastEnd.status}`);
  console.log(`claims the city is empty       ${pastEnd.body.includes("no upcoming events")}`);
  console.log(
    `points back to page one        ${pastEnd.body.includes("start from the first page")}`,
  );

  // **A page number too large to write.** `Number.parseInt` reads the digits and then
  // prints the result in scientific notation — `1e+23` — which is not an integer the
  // backend accepts, and which would land in the canonical URL. It has to come back as
  // the first page.
  const hugePage = await html("/events-in-brooklyn?page=99999999999999999999999");
  console.log("");
  console.log(`huge-page status               ${hugePage.status}`);
  console.log(
    `canonical is scientific        ${hugePage.body.includes("page=1e+23") || hugePage.body.includes("1e%2B23")}`,
  );
  console.log(
    `canonical is page one          ${hugePage.body.includes('canonical" href="http://eventpulse24.test/events-in-brooklyn"')}`,
  );

  const unknown = await html("/events-in-atlantis");
  console.log("");
  console.log(`unknown status                 ${unknown.status}`);
  console.log(
    `has the 404 copy               ${unknown.body.includes("We don't have that city.")}`,
  );

  console.log("");
  console.log("── the session ────────────────────────────────────────────");
  const response = await fetch(`${BASE}/events-in-brooklyn`, { redirect: "manual" });
  console.log(
    `set-cookie                     ${response.headers.get("set-cookie") ?? "(none set)"}`,
  );

  // **A failure to answer is not the city's content, so it must not be indexed.**
  //
  // **The status cannot carry this.** The failure is measured at **200** — Next offers
  // no way to set a 503 from a server component, and throwing would answer 500 while
  // replacing the document with Next's own error shell, losing the copy. So the
  // instruction goes in the `<head>` instead: `robots: { index: false }`.
  //
  // **This block reads the `<meta>` a crawler reads.** The `Metadata` **object** is not
  // a thing a crawler can see, and a test that asserts on the object proves only that
  // the object was built. The two branches the probe *can* reach — the city that
  // answered and the slug that names no city — must carry **no** instruction, so that
  // the instruction the failure carries is unmistakably the failure's own.
  console.log("");
  console.log("── the index instruction ──────────────────────────────────");
  console.log(`a city that answered           robots: ${robotsOf(page.body)}`);
  console.log(`a slug that names no city      robots: ${robotsOf(unknown.body)}`);
}

/**
 * The `<meta name="robots">` a document carries, or `(none)`.
 *
 * **Read from the served bytes**, because the `<meta>` is what a crawler reads — and
 * the `Metadata` **object** is not a thing a crawler can see.
 */
function robotsOf(body) {
  const match = body.match(/<meta name="robots" content="([^"]*)"/i);
  return match ? match[1] : "(none)";
}

await main();
