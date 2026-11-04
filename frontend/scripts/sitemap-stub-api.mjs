/**
 * A stub catalog API for the sitemap's production check.
 *
 * It answers `GET /api/catalog/url-feed` and **counts its requests**, so the caching
 * claims can be measured rather than asserted.
 *
 *   - `?page=1` → 200, the first page of the feed
 *   - `?page=N` → 200, the Nth page, sized by `FEED_PAGE_SIZE`
 *   - anything else → 404, the backend's own `ErrorOut`
 *
 * **The feed's size is settable**, because the sitemap's *index split* is the claim the
 * probe exists to measure: a feed of 120,000 URLs must produce three children, and the
 * only way to see that is to tell the stub the feed is that big.
 */
import { createServer } from "node:http";

let requests = 0;

/**
 * Whether the feed should answer with a failure instead of a page.
 *
 * **The probe needs a feed that cannot answer**, because a sitemap that answers "I have
 * no pages" when the truth is "I could not look" is the failure mode the 503 exists to
 * prevent — and that failure mode is invisible in a test that only ever sees a working
 * backend.
 */
let failing = false;

/** How many URLs the feed holds. The probe sets this to measure the index split. */
let total = Number.parseInt(process.env.FEED_TOTAL ?? "3", 10);

/** How many URLs each feed page holds, when the caller does not ask for a size. */
const defaultPageSize = Number.parseInt(process.env.FEED_PAGE_SIZE ?? "2", 10);

/** The most URLs the real feed will put on one page. */
const MAX_PAGE_SIZE = 1000;

function entry(index) {
  return {
    kind: index % 2 === 0 ? "event" : "city",
    last_modified: "2026-08-20T09:14:00Z",
    path:
      index % 2 === 0
        ? `/events/some-event-${index}-2026-08-28-a1b2c3`
        : `/events-in-some-city-${index}`,
  };
}

function feedPage(page, pageSize) {
  const start = (page - 1) * pageSize;
  const count = Math.max(0, Math.min(pageSize, total - start));

  return {
    has_next: start + count < total,
    items: Array.from({ length: count }, (_, offset) => entry(start + offset)),
    page,
    page_size: pageSize,
    total,
  };
}

const server = createServer((request, response) => {
  const url = new URL(request.url, "http://localhost");

  if (url.pathname === "/__count") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ requests }));
    return;
  }

  if (url.pathname === "/__reset") {
    requests = 0;
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ ok: true }));
    return;
  }

  if (url.pathname === "/__fail") {
    // **The probe turns the failure on and off.** With the feed failing, the sitemap
    // must answer 503 — not an empty document, and not a 404.
    failing = url.searchParams.get("value") !== "0";
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ failing }));
    return;
  }

  if (url.pathname === "/__total") {
    // **The probe sets the feed's size** so it can measure the index split.
    const requested = Number.parseInt(url.searchParams.get("value") ?? "", 10);
    if (Number.isFinite(requested) && requested >= 0) total = requested;
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ total }));
    return;
  }

  if (url.pathname === "/api/catalog/url-feed") {
    requests += 1;

    if (failing) {
      // **A 500, and the backend's own error shape.** The sitemap must not read this
      // as "the feed is empty".
      response.writeHead(500, { "content-type": "application/json" });
      response.end(
        JSON.stringify({
          code: "internal_error",
          message: "We couldn't read the feed.",
          details: null,
        }),
      );
      return;
    }

    const raw = url.searchParams.get("page") ?? "1";
    const parsed = Number.parseInt(raw, 10);
    const page = Number.isFinite(parsed) && parsed > 0 ? parsed : 1;

    // **The stub honours the page size the caller asks for.** The real feed caps it at
    // 1,000, and the sitemap's child size is the feed's page size — so a stub that
    // ignored the parameter would be answering a question the frontend never asked.
    const requestedSize = Number.parseInt(url.searchParams.get("page_size") ?? "", 10);
    const pageSize =
      Number.isFinite(requestedSize) && requestedSize > 0
        ? Math.min(requestedSize, MAX_PAGE_SIZE)
        : defaultPageSize;

    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(feedPage(page, pageSize)));
    return;
  }

  response.writeHead(404, { "content-type": "application/json" });
  response.end(
    JSON.stringify({
      code: "not_found",
      message: "We couldn't find that feed.",
      details: null,
    }),
  );
});

server.listen(Number.parseInt(process.env.STUB_PORT ?? "8124", 10), () => {
  console.log(`the stub catalog API is listening on ${JSON.stringify(server.address())}`);
});
