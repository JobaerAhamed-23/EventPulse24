import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CityEventCard } from "@/components/city-page/city-event-card";
import { CityPage } from "@/components/city-page/city-page";
import type { CityPageOut } from "@/lib/city-page-read";

/**
 * The city page's body.
 *
 * **This file defends two claims that a rendering cannot make for itself.**
 *
 * 1. **The score and the tags are the server's.** AD-10 forbids recomputing and
 *    re-ranking on the client, and the two visible symptoms of a client-side re-rank are
 *    a score that does not match the payload and an order that does not match the
 *    payload. Both are asserted here.
 * 2. **The page does not pretend to do things it cannot do.** The mockup's filter chips,
 *    category stripes, source badges and prices are all things the payload does not
 *    carry, and a chip that cannot filter is a lie about what the page can do.
 */

function event(overrides: Record<string, unknown> = {}) {
  return {
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
    tags: ["tonight"],
    title: "Designing for Calm",
    tz_review_pending: false,
    venue_name: "Brooklyn Arts Council",
    ...overrides,
  };
}

function cityPage(overrides: Record<string, unknown> = {}): CityPageOut {
  return {
    country_code: "US",
    event_count: 12,
    has_next: false,
    is_published: true,
    items: [],
    name: "Brooklyn",
    page: 1,
    page_size: 20,
    region: "NY",
    slug: "brooklyn",
    ...overrides,
  } as CityPageOut;
}

/* ── the card ─────────────────────────────────────────────────────────────────── */

describe("the city event card", () => {
  it("links to the event's public page", () => {
    render(<CityEventCard event={event() as never} />);

    expect(screen.getByRole("link", { name: "Designing for Calm" })).toHaveAttribute(
      "href",
      "/events/designing-for-calm-2026-08-28-a1b2c3",
    );
  });

  it("shows the Event Fit's score as served", () => {
    render(<CityEventCard event={event({ score: 3 }) as never} />);

    // **The score is the server's fact.** A card that recomputed it would show a
    // different number the moment the fit was refreshed.
    expect(screen.getByRole("button", { name: "Event Fit 3 of 5" })).toBeInTheDocument();
  });

  it("shows the tags as served", () => {
    render(<CityEventCard event={event({ tags: ["tonight", "in_brooklyn"] }) as never} />);

    expect(screen.getByText("Tonight")).toBeInTheDocument();
    expect(screen.getByText("In Brooklyn")).toBeInTheDocument();
  });

  it("shows the event's own time, in the event's own zone", () => {
    render(<CityEventCard event={event() as never} />);

    // 22:30 UTC is 6:30 PM in `America/New_York` (UTC-4 in August).
    expect(screen.getByText(/6:30 PM EDT/)).toBeInTheDocument();
  });

  it("shows the venue", () => {
    render(<CityEventCard event={event() as never} />);

    expect(screen.getByText("Brooklyn Arts Council")).toBeInTheDocument();
  });

  it("shows no category stripe, because there is no session to decide one", () => {
    render(<CityEventCard event={event() as never} />);

    // **Must-know / Nearby / Discovery are digest categories**, decided at composition
    // time from a session. A stripe on a session-free surface would be a category
    // invented on the client.
    expect(document.querySelector("[data-city-stripe]")).toBeNull();
    expect(document.querySelector(".stripe")).toBeNull();
    expect(screen.queryByText(/Must-know/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Discovery/i)).not.toBeInTheDocument();
  });

  it("shows no source badge, because the payload carries no source name", () => {
    render(<CityEventCard event={event() as never} />);

    // **`CityPageEventOut` has no `source_name`** — so a badge would be a fact
    // invented on the client.
    expect(
      screen.queryByText(/Verified|Community|Unverified|Listing site/i),
    ).not.toBeInTheDocument();
  });

  it("shows no price, because the payload carries none", () => {
    render(<CityEventCard event={event() as never} />);

    expect(screen.queryByText(/\$\d/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^free$/i)).not.toBeInTheDocument();
  });

  it("has no Save button, because a Save button is a session-bound control", () => {
    render(<CityEventCard event={event() as never} />);

    expect(screen.queryByRole("button", { name: /Save/i })).not.toBeInTheDocument();
  });

  it("says so when the event is sold out", () => {
    render(<CityEventCard event={event({ is_sold_out: true }) as never} />);

    expect(screen.getByText(/Sold out/)).toBeInTheDocument();
  });
});

/* ── the page ─────────────────────────────────────────────────────────────────── */

describe("the city page", () => {
  it("names the city in the heading", () => {
    render(<CityPage page={cityPage()} currentPage={1} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Events in Brooklyn");
  });

  it("shows the region's name in the city pill", () => {
    render(<CityPage page={cityPage()} currentPage={1} />);

    expect(screen.getByText(/Brooklyn, NY/)).toBeInTheDocument();
  });

  it("words the count to what the number actually is", () => {
    // **`event_count` is the qualifying count** — the number FR-27's threshold was
    // decided on, measured over the backend's 365-day window. The mockup's "147 events
    // this week" would be a false claim about a period the payload never states.
    render(<CityPage page={cityPage({ event_count: 147 })} currentPage={1} />);

    expect(screen.getByText(/147 events on record/)).toBeInTheDocument();
    // **And the pill itself does not claim a period.** The count is a 365-day
    // qualifying count, so "this week" beside it would be a false claim — the
    // assertion is on the pill, because the eyebrow names the listing's window and
    // the count is a different number.
    const pill = document.querySelector("[data-city-meta]");
    expect(pill?.textContent ?? "").not.toMatch(/this week/i);
  });

  it("shows no filter chips, because nothing can filter", () => {
    // **The backend's city read accepts only `page` and `page_size`.** There is no
    // category, price or date-window filter, and the mockup's "When" chips are not the
    // Event Fit tags. A chip that cannot filter is a lie about what the page can do.
    render(<CityPage page={cityPage()} currentPage={1} />);

    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
    expect(screen.queryByText("This week")).not.toBeInTheDocument();
    expect(screen.queryByText("Weekend")).not.toBeInTheDocument();
    expect(screen.queryByText("Tonight")).not.toBeInTheDocument();
    expect(screen.queryByText("Music")).not.toBeInTheDocument();
    expect(screen.queryByText("Category")).not.toBeInTheDocument();
  });

  it("shows no SEO footer's neighbour-city links, because those URLs do not exist", () => {
    // **The mockup links `/c/manhattan` and `/c/brooklyn/tech`.** Those routes do not
    // exist in this system, and a public page full of dead links is worse than one
    // without them. The neighbour-city footer belongs to the sitemap item.
    render(<CityPage page={cityPage()} currentPage={1} />);

    expect(screen.queryByRole("link", { name: /Events in Manhattan/i })).not.toBeInTheDocument();
    expect(document.querySelector('a[href^="/c/"]')).toBeNull();
  });

  it("shows the listing's events", () => {
    render(
      <CityPage
        page={cityPage({
          items: [event(), event({ id: "second", title: "Smorgasburg food market" })],
        })}
        currentPage={1}
      />,
    );

    expect(document.querySelectorAll("[data-city-event]")).toHaveLength(2);
  });

  it("keeps the listing's order", () => {
    // **AD-10.** The backend ordered the listing by `-score, start_time_utc, event_id` —
    // a total order. The page renders the payload's order and computes nothing.
    render(
      <CityPage
        page={cityPage({
          items: [
            event({ id: "a", title: "First", score: 5 }),
            event({ id: "b", title: "Second", score: 3 }),
          ],
        })}
        currentPage={1}
      />,
    );

    const titles = Array.from(document.querySelectorAll("[data-city-event] h3")).map(
      (heading) => heading.textContent,
    );
    expect(titles).toEqual(["First", "Second"]);
  });

  it("shows the coming-soon state for a sparse city", () => {
    render(<CityPage page={cityPage({ is_published: false, event_count: 2 })} currentPage={1} />);

    expect(
      screen.getByText(/Coming soon — we're growing Brooklyn's coverage\./),
    ).toBeInTheDocument();
  });

  it("does not claim a city has no events when the page is merely past the end", () => {
    // **A page beyond the end is not an empty city.** The backend answers a page past
    // the last one "with the same page shape with no items" — a crawler walking off the
    // end of a listing is doing something ordinary. But an empty page *one* and an empty
    // page *five* are different facts, and only the first one means the city has
    // nothing on.
    //
    // **Saying the wrong one would be a false claim on a crawlable page** — a reader,
    // or an index, would be told that Brooklyn has no upcoming events when it has
    // four pages of them.
    render(<CityPage page={cityPage({ items: [] })} currentPage={5} />);

    expect(document.querySelector("[data-city-empty]")).toBeNull();
    expect(document.querySelector("[data-city-past-end]")).not.toBeNull();
    expect(screen.queryByText(/no upcoming events/i)).not.toBeInTheDocument();
  });

  it("points a page past the end back to the first page, as a link", () => {
    // **A crawler follows links.** The way back has to be a link in the server-rendered
    // HTML, not a sentence that tells a human where to click.
    render(<CityPage page={cityPage({ items: [] })} currentPage={5} />);

    expect(screen.getByRole("link", { name: /start from the first page/i })).toHaveAttribute(
      "href",
      "/events-in-brooklyn",
    );
  });

  it("still claims an empty first page as an empty city", () => {
    // **The counterpart.** An empty page one really does mean the city has nothing
    // upcoming — between seasons — and the count on the pill is still true.
    render(<CityPage page={cityPage({ items: [] })} currentPage={1} />);

    expect(document.querySelector("[data-city-empty]")).not.toBeNull();
    expect(document.querySelector("[data-city-past-end]")).toBeNull();
  });

  it("shows no listing for a sparse city", () => {
    render(<CityPage page={cityPage({ is_published: false, event_count: 2 })} currentPage={1} />);

    expect(document.querySelectorAll("[data-city-event]")).toHaveLength(0);
  });

  it("shows no next-page link when the backend says there is none", () => {
    render(<CityPage page={cityPage({ has_next: false })} currentPage={1} />);

    expect(screen.queryByRole("link", { name: /Next page/ })).not.toBeInTheDocument();
  });

  it("shows the next page as a link when the backend says there is one", () => {
    render(<CityPage page={cityPage({ has_next: true })} currentPage={1} />);

    // **A crawler follows links.** The paging is an anchor in the server-rendered HTML.
    expect(screen.getByRole("link", { name: /Next page/ })).toHaveAttribute(
      "href",
      "/events-in-brooklyn?page=2",
    );
  });

  it("links back to page one without a query, so page one is not two URLs", () => {
    render(<CityPage page={cityPage({ has_next: true })} currentPage={2} />);

    expect(screen.getByRole("link", { name: /Previous page/ })).toHaveAttribute(
      "href",
      "/events-in-brooklyn",
    );
  });
});
