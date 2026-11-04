import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CityPageRoute, { generateMetadata } from "@/app/events-in/[slug]/page";

/**
 * `/events-in-{city-slug}` — the city landing page (FR-27, AD-12).
 *
 * **The properties this file defends are the ones a page cannot state about itself:**
 * the status of an unknown slug, the absence of a session, the crawlability of the
 * paging, and the per-city metadata. The rendered tree can be asserted on; the *status*
 * can only be asserted on by the throw that `notFound()` produces, and that is what
 * Next does with it — so the throw is the assertion.
 *
 * **The crawlable paging is asserted on the server-rendered HTML**, not on a hydrated
 * tree. A crawler that does not execute JavaScript reads the markup; a paging control
 * that only exists after hydration is invisible to it, and the whole point of the page
 * is to be found.
 */
const readCityPage = vi.fn();
const cookies = vi.fn();

/**
 * **The mock replaces only the read, not the module.**
 *
 * The route also imports the module's *URL helpers* — the shared definition of where a
 * city lives, which the canonical link, the OG URL and the paging links are all built
 * from. A mock that replaced the whole module would have to re-implement them, and a
 * re-implementation in a test is a second definition that can drift from the first.
 */
vi.mock("@/lib/city-page-read", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/city-page-read")>();
  return {
    ...actual,
    readCityPage: (slug: string, page: number) => readCityPage(slug, page),
  };
});

vi.mock("next/headers", () => ({
  cookies: () => cookies(),
}));

/**
 * **`notFound` throws.** That is what Next does with it, and that is what makes the
 * 404 assertable: the page's branch must *reach* it, and the throw is how the test
 * sees that it did. The precedent is `app/events/[id]/page.branch.test.tsx`.
 */
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_HTTP_ERROR_FALLBACK;404");
  },
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

const SLUG = "brooklyn";

/** The payload the catalog's city read returns. */
function cityPage(overrides: Record<string, unknown> = {}) {
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
    slug: SLUG,
    ...overrides,
  };
}

/** One event on the listing. */
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

beforeEach(() => {
  readCityPage.mockReset();
  cookies.mockReset();
  cookies.mockResolvedValue(new Map());
});

async function renderPage(query: Record<string, string> = {}) {
  render(
    await CityPageRoute({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve(query),
    }),
  );
}

/* ── the populated city ───────────────────────────────────────────────────────── */

describe("a populated city", () => {
  it("shows the city's name in the heading", async () => {
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });

    await renderPage();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Events in Brooklyn");
  });

  it("shows the events the listing carries", async () => {
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({
        items: [event(), event({ id: "second", title: "Smorgasburg food market" })],
      }),
    });

    await renderPage();

    expect(screen.getByRole("link", { name: "Designing for Calm" })).toHaveAttribute(
      "href",
      "/events/designing-for-calm-2026-08-28-a1b2c3",
    );
    expect(screen.getByRole("link", { name: "Smorgasburg food market" })).toHaveAttribute(
      "href",
      "/events/designing-for-calm-2026-08-28-a1b2c3",
    );
  });

  it("keeps the listing's order, because the backend ordered it", async () => {
    // **AD-10.** The backend ordered the listing by `-score, start_time_utc, event_id` —
    // a total order, so two pages cannot overlap and the order cannot shift between
    // them. The page renders the payload's order and computes nothing.
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({
        items: [
          event({ id: "a", title: "First", score: 5 }),
          event({ id: "b", title: "Second", score: 3 }),
        ],
      }),
    });

    await renderPage();

    const titles = screen
      .getAllByRole("link")
      .map((link) => link.textContent)
      .filter((text) => text === "First" || text === "Second");
    expect(titles).toEqual(["First", "Second"]);
  });

  it("shows the Event Fit's score as served", async () => {
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ items: [event({ score: 4 })] }),
    });

    await renderPage();

    // **The score is the server's fact.** It is not recomputed, and it is not
    // re-ranked on the client.
    expect(screen.getByRole("button", { name: "Event Fit 4 of 5" })).toBeInTheDocument();
  });

  it("shows the tags as served", async () => {
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ items: [event({ tags: ["tonight", "in_brooklyn"] })] }),
    });

    await renderPage();

    // **Through the shared `tagLabel`**, so a tag the frontend has never seen still
    // appears — this is a translation, not a filter.
    expect(screen.getByText("Tonight")).toBeInTheDocument();
    expect(screen.getByText("In Brooklyn")).toBeInTheDocument();
  });

  it("shows the event's own time, in the event's own zone", async () => {
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ items: [event()] }),
    });

    await renderPage();

    // 22:30 UTC is 6:30 PM in `America/New_York` (UTC-4 in August).
    expect(screen.getByText(/6:30 PM EDT/)).toBeInTheDocument();
  });
});

/* ── the sparse city ──────────────────────────────────────────────────────────── */

describe("a sparse city", () => {
  it("renders the coming-soon state, not an empty grid and not a 404", async () => {
    // **FR-27 asks for graceful degradation.** The city exists, it has too few events,
    // and the page says so — with a **200**, because the URL is real.
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ is_published: false, event_count: 2 }),
    });

    await renderPage();

    expect(
      screen.getByText(/Coming soon — we're growing Brooklyn's coverage\./),
    ).toBeInTheDocument();
    expect(document.querySelector("[data-city-coming-soon]")).not.toBeNull();
  });

  it("shows no listing in the sparse state", async () => {
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ is_published: false, event_count: 2 }),
    });

    await renderPage();

    expect(document.querySelectorAll("[data-city-event]")).toHaveLength(0);
    // And the paging is absent — there is nothing to page through.
    expect(document.querySelector("[data-city-paging]")).toBeNull();
  });

  it("is a 200, not a 404", async () => {
    // **The read answers "found" for a sparse city**, so the page never reaches
    // `notFound()`. A rendering that resolved is the assertion.
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ is_published: false, event_count: 2 }),
    });

    await expect(renderPage()).resolves.toBeUndefined();
  });
});

/* ── the unknown slug ─────────────────────────────────────────────────────────── */

describe("an unknown slug", () => {
  it("raises a real 404", async () => {
    // **Next's rule is exact**: "To return a real `404` status, the resource has to be
    // checked before the response streams." The throw is how the test sees that the
    // page reached `notFound()`.
    readCityPage.mockResolvedValue({ kind: "not-found", code: "not_found" });

    await expect(renderPage()).rejects.toThrow("NEXT_HTTP_ERROR_FALLBACK;404");
  });

  it("does not claim the city does not exist when the API could not be reached", async () => {
    // **A failure to answer is not an answer.** A 404 is a claim about the world; an
    // unreachable API is a claim about us, and the two must not be confused.
    readCityPage.mockResolvedValue({ kind: "unavailable" });

    await renderPage();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/couldn't load this city/i);
  });
});

/* ── the failure is not indexed ───────────────────────────────────────────────── */

describe("a failure to answer", () => {
  it("asks a crawler not to index the failure", async () => {
    // **The failure's text is not the city's content.**
    //
    // **The document says "We couldn't load this city" — and that sentence is about
    // *us*, not about Brooklyn.** A crawler that stored it would be recording our
    // outage as the city's description, and a description is what a search result
    // shows. The failure therefore carries `robots: { index: false }`.
    //
    // **This was found by measuring, not by reading.** The failure's status was
    // measured at **200** — a soft success — and Next offers no way to set a 503 from
    // a server component (`notFound()` is the only status setter it exposes, and it
    // would make the failure a claim that the city does not exist). Throwing was tried
    // and measured too: it answers **500**, but Next's error shell replaces the
    // document and the copy is **gone** — the crawler would be shown a blank page
    // instead of a page that says it could not be loaded.
    //
    // **So the copy stays and the index instruction goes.** A page that says "not now"
    // and asks not to be stored is the honest outcome; a page that says nothing and
    // answers 500 is worse for the reader and no better for the crawler.
    readCityPage.mockResolvedValue({ kind: "unavailable" });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({}),
    });

    expect(metadata.robots).toEqual({ index: false, follow: false });
  });

  it("asks a crawler to index a city that answered", async () => {
    // **The instruction must be on the failure alone.**
    //
    // **If this failed, the city pages themselves would be de-indexed** — which would
    // be worse than the problem it solves. The whole point of this page is to be
    // found, and a blanket "do not index" would defeat it. So the found branch must
    // carry no `robots` at all, and the test says so.
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({}),
    });

    expect(metadata.robots).toBeUndefined();
  });

  it("does not ask a crawler to index a slug that names no city", async () => {
    // **A 404 is not indexed either way**, so the instruction would be noise — and
    // noise in a `<head>` is a cost paid on every crawl of every URL that does not
    // exist. The distinction that matters is the one between a fact about the world
    // and a statement about us, and only the latter earns the instruction.
    readCityPage.mockResolvedValue({ kind: "not-found", code: "not_found" });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({}),
    });

    expect(metadata.robots).toBeUndefined();
  });
});

/* ── the no-session render ────────────────────────────────────────────────────── */

describe("the render without a session", () => {
  it("renders with no cookies present", async () => {
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });
    cookies.mockResolvedValue(new Map());

    await renderPage();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Events in Brooklyn");
  });

  it("never reads the request's cookies", async () => {
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });

    await renderPage();

    // **The call is the thing that matters, not the header.** A module that read the
    // cookies and then chose not to send them would still have opted the route out of
    // static generation.
    expect(cookies).not.toHaveBeenCalled();
  });
});

/* ── the paging ───────────────────────────────────────────────────────────────── */

describe("the paging", () => {
  it("puts the next page in the server-rendered HTML as a link", async () => {
    // **A crawler follows links; it does not press buttons.** The assertion is on the
    // document's own markup — a control that only exists after hydration is invisible
    // to a crawler that does not execute JavaScript.
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ has_next: true, page: 1 }),
    });

    await renderPage();

    const next = screen.getByRole("link", { name: /Next page/ });
    expect(next).toHaveAttribute("href", "/events-in-brooklyn?page=2");
    expect(next.closest("nav")).not.toBeNull();
  });

  it("offers no next-page link when the backend says there is none", async () => {
    // **`has_next` is the backend's.** It is measured against the *upcoming* count, so
    // a city between seasons is not sent to an empty page forever.
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ has_next: false, page: 1 }),
    });

    await renderPage();

    expect(screen.queryByRole("link", { name: /Next page/ })).not.toBeInTheDocument();
  });

  it("offers the previous page on page two", async () => {
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ has_next: true, page: 2 }),
    });

    await renderPage({ page: "2" });

    expect(screen.getByRole("link", { name: /Previous page/ })).toHaveAttribute(
      "href",
      "/events-in-brooklyn",
    );
    expect(screen.getByRole("link", { name: /Next page/ })).toHaveAttribute(
      "href",
      "/events-in-brooklyn?page=3",
    );
  });

  it("reads the page the URL asks for", async () => {
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage({ page: 2 }) });

    await renderPage({ page: "2" });

    expect(readCityPage).toHaveBeenCalledWith(SLUG, 2);
  });

  it("clamps a page below one, rather than provoking a 422", async () => {
    // **The backend refuses `page < 1` with a 422.** A crawler's `?page=0` is a
    // request for the first page, not a mistake.
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });

    await renderPage({ page: "0" });

    expect(readCityPage).toHaveBeenCalledWith(SLUG, 1);
  });

  it("treats a page that is not a number as the first page", async () => {
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });

    await renderPage({ page: "abc" });

    expect(readCityPage).toHaveBeenCalledWith(SLUG, 1);
  });

  it("treats a page too large to write as the first page", async () => {
    // **`Number.parseInt("99999999999999999999999", 10)` returns `1e+23`.** The digits
    // are read correctly, but the result is past the range where a float holds every
    // integer, so JavaScript prints it in scientific notation — and `1e+23` is not an
    // integer the backend will accept.
    //
    // **It was measured, not imagined.** Before the fix, `?page=99999999999999999999999`
    // rendered "page 1e+23" in the visible text and put `?page=1e+23` in the canonical
    // URL — and sent `page=1e%2B23` to the backend, whose `page: int = Field(1, ge=1)`
    // **refuses with a 422**. A 422 is "unavailable", so the page would have rendered
    // "We couldn't load this city" for a URL that only asked for a page past the end.
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });

    await renderPage({ page: "99999999999999999999999" });

    expect(readCityPage).toHaveBeenCalledWith(SLUG, 1);
  });

  it("never puts a scientific-notation number in the canonical URL", async () => {
    // **The canonical is a URL a crawler records.** A `?page=1e+23` in one is a
    // malformed address, and it is the address the page claims is its own.
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({ page: "99999999999999999999999" }),
    });

    expect(metadata.alternates?.canonical).toBe("/events-in-brooklyn");
  });

  it("keeps an ordinary large page number as it was asked", async () => {
    // **The guard is not "small numbers only".** A page number a person could write is
    // kept, however large — the backend answers a page past the end with the same
    // shape and no items, and that is an ordinary answer.
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage({ page: 5000 }) });

    await renderPage({ page: "5000" });

    expect(readCityPage).toHaveBeenCalledWith(SLUG, 5000);
  });
});

/* ── the metadata ─────────────────────────────────────────────────────────────── */

describe("the metadata", () => {
  it("carries a per-city title and description", async () => {
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({}),
    });

    expect(metadata.title).toBe("Events in Brooklyn · This week and next · EventPulse24");
    expect(metadata.description).toContain("Brooklyn");
  });

  it("carries a canonical link to the public URL", async () => {
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({}),
    });

    // **The hyphenated form** — the address the backend's revalidation signal names
    // and the one that appears in a search result. The internal segment is a routing
    // detail and never appears in a tag.
    expect(metadata.alternates?.canonical).toBe("/events-in-brooklyn");
  });

  it("canonicalises a later page to itself, not to the first page", async () => {
    // **A canonical that always named page one would de-index every page after it.**
    // A crawler treats the canonical as the truth about which URL is the original, so
    // a page two that claims page one is its canonical is a page two that does not
    // exist — and a paged listing whose later pages vanish is a listing of one page.
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage({ page: 2 }) });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({ page: "2" }),
    });

    expect(metadata.alternates?.canonical).toBe("/events-in-brooklyn?page=2");
  });

  it("reads the page the URL asks for, so the metadata matches the document", async () => {
    // **The metadata and the page must be about the same page.** If the metadata read
    // page one while the document rendered page two, the canonical would describe a
    // different document from the one served.
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage({ page: 2 }) });

    await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({ page: "2" }),
    });

    expect(readCityPage).toHaveBeenCalledWith(SLUG, 2);
  });

  it("carries the paging as head links, because a crawler reads the head", async () => {
    // **The page's own anchors carry `rel="prev"` and `rel="next"`** — but a crawler
    // that reads only the `<head>` does not see them, and the head links are the
    // convention for saying "this page has a neighbour".
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ has_next: true, page: 1 }),
    });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({}),
    });

    expect(metadata.pagination?.next).toBe("/events-in-brooklyn?page=2");
    expect(metadata.pagination?.previous).toBeNull();
  });

  it("offers no next head link when the backend says there is no next page", async () => {
    // **`has_next` is measured against the *upcoming* count**, so a city between
    // seasons is not sent to an empty page forever — and the head link says the same
    // thing the anchor says.
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ has_next: false, page: 1 }),
    });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({}),
    });

    expect(metadata.pagination?.next).toBeNull();
  });

  it("names the previous page in the head on page two", async () => {
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ has_next: true, page: 2 }),
    });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({ page: "2" }),
    });

    expect(metadata.pagination?.previous).toBe("/events-in-brooklyn");
    expect(metadata.pagination?.next).toBe("/events-in-brooklyn?page=3");
  });

  it("carries the Open Graph and Twitter tags with a branded image", async () => {
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({}),
    });

    expect(metadata.openGraph?.title).toBe(
      "Events in Brooklyn · This week and next · EventPulse24",
    );
    expect(metadata.openGraph?.url).toBe("/events-in-brooklyn");

    const twitter = metadata.twitter as { card?: string; title?: string; images?: unknown[] };
    expect(twitter.card).toBe("summary_large_image");
    expect(twitter.title).toBe("Events in Brooklyn · This week and next · EventPulse24");
    expect(twitter.images).toHaveLength(1);

    const images = metadata.openGraph?.images as Array<{ url: string }> | undefined;
    expect(images?.[0]?.url).toContain("/brand/");
  });

  it("reads no session to build the metadata", async () => {
    // **This is the constraint that keeps the route cacheable.** A Request-time API in
    // `generateMetadata` would opt the whole route out of static generation.
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });

    await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({}),
    });

    expect(cookies).not.toHaveBeenCalled();
  });

  it("falls back to the route's title when there is no city", async () => {
    readCityPage.mockResolvedValue({ kind: "not-found", code: "not_found" });

    const metadata = await generateMetadata({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve({}),
    });

    // **No promise of a title the page does not have.**
    expect(metadata.title).toBe("Events · EventPulse24");
  });
});
