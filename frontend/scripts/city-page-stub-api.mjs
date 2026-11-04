/**
 * A stub catalog API for the city page's production check.
 *
 * It answers `GET /api/catalog/cities/by-slug/{slug}` and **counts its requests**, so
 * the caching claims can be measured rather than asserted.
 *
 *   - `brooklyn`   → 200, a published city with two events
 *   - `quiet`      → 200, `is_published: false` — the sparse city
 *   - `page2`      → 200, a second page of `brooklyn`'s listing
 *   - anything else → 404, the backend's own `ErrorOut`
 */
import { createServer } from "node:http";

let requests = 0;

const EVENT = {
  canonical_url: "https://brooklynartscouncil.org/events/calm",
  city: "Brooklyn",
  description: "A short, opinionated panel on building products that respect attention.",
  end_time_utc: null,
  event_version: 3,
  id: "0196c3a4-5b6d-7e8f-9a0b-1c2d3e4f5061",
  is_sold_out: false,
  score: 4,
  slug: "designing-for-calm-2026-08-28-a1b2c3",
  start_time_tz: "America/New_York",
  start_time_utc: "2026-08-28T22:30:00Z",
  status: "published",
  tags: ["tonight", "in_brooklyn"],
  title: "Designing for Calm",
  tz_review_pending: false,
  venue_name: "Brooklyn Arts Council",
};

const SECOND_EVENT = {
  ...EVENT,
  id: "0196c3a4-5b6d-7e8f-9a0b-1c2d3e4f5062",
  score: 2,
  slug: "smorgasburg-food-market-2026-08-29-c3d4e5",
  title: "Smorgasburg food market",
  tags: ["this_weekend"],
};

const CITY = {
  country_code: "US",
  event_count: 12,
  has_next: true,
  is_published: true,
  items: [EVENT],
  name: "Brooklyn",
  page: 1,
  page_size: 20,
  region: "NY",
  slug: "brooklyn",
};

function pageNumber(url) {
  const raw = url.searchParams.get("page");
  const parsed = Number.parseInt(raw ?? "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

const server = createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");

  if (url.pathname === "/__count") {
    // **The counter does not count itself.** A `/__count` that bumped the number it
    // reports would make every measurement wrong by one — and the measurement is the
    // whole point of the stub.
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ requests }));
    return;
  }

  if (url.pathname === "/__reset") {
    requests = 0;
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ requests }));
    return;
  }

  requests += 1;

  const match = url.pathname.match(/^\/api\/catalog\/cities\/by-slug\/([^/]+)$/);
  if (match) {
    const slug = decodeURIComponent(match[1]);

    if (slug === "brooklyn" || slug === "page2") {
      const page = pageNumber(url);
      response.writeHead(200, { "content-type": "application/json" });
      response.end(
        JSON.stringify({
          ...CITY,
          slug: "brooklyn",
          page,
          // **A page past the end comes back with the same shape and no items** —
          // the backend's own rule ("a crawler walking off the end of a listing is
          // doing something ordinary"), and the frontend has to tell it apart from an
          // empty *first* page.
          items: page === 1 ? [EVENT] : page === 2 ? [SECOND_EVENT] : [],
          has_next: page === 1,
        }),
      );
      return;
    }

    if (slug === "quiet") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(
        JSON.stringify({
          ...CITY,
          slug: "quiet",
          name: "Quiet",
          is_published: false,
          event_count: 2,
          items: [],
          has_next: false,
        }),
      );
      return;
    }

    response.writeHead(404, { "content-type": "application/json" });
    response.end(
      JSON.stringify({
        code: "not_found",
        message: "We couldn't find that city.",
        details: { slug },
      }),
    );
    return;
  }

  response.writeHead(404, { "content-type": "application/json" });
  response.end(JSON.stringify({ code: "not_found", message: "no such endpoint" }));
});

server.listen(8123, "127.0.0.1", () => {
  process.stdout.write("stub catalog API on http://127.0.0.1:8123\n");
});
