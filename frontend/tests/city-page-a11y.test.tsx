/**
 * The city page's **axe-core gate**.
 *
 * **`/events-in-{city-slug}` — the landing page that answers the search** (FR-27).
 *
 * **"axe-core reports zero serious or critical violations on this surface."** Every
 * surface in this project carries one axe gate, and the city page is a *new public
 * surface*, so it carries one too.
 *
 * **The gate runs over every state, not just the happy one.** A page can be accessible
 * when it is full and inaccessible when it is empty — and this page has four documents
 * that are four different documents:
 *
 * - the **populated** listing (cards, tags, the Event Fit trigger, the paging),
 * - the **empty** listing (a published city between seasons),
 * - the **sparse** city ("coming soon", a 200),
 * - the **unavailable** document (the API could not be reached), and
 * - the **404** document (a slug that names no city at all).
 *
 * The sparse state and the 404 are the two that are easy to forget, and they are the two
 * a stranger is most likely to land on: one from a stale search result, one from a
 * mistyped URL.
 *
 * **Serious and critical only.** `minor` and `moderate` findings are advisory, and a
 * gate that fails on a moderate finding is a gate that gets disabled.
 *
 * **`color-contrast` is disabled explicitly.** jsdom computes no layout, so axe has no
 * boxes to compare and the rule reports false positives rather than findings. The
 * contrast requirement belongs to a real browser — and to
 * `tests/contrast.test.ts`, which checks the tokens themselves.
 */
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CityNotFound from "@/app/events-in/[slug]/not-found";
import CityPageRoute from "@/app/events-in/[slug]/page";

const readCityPage = vi.fn();

/**
 * **The mock replaces only the read, not the module.**
 *
 * The route builds its canonical and its paging links from the module's URL helpers, and
 * those are the *real* ones — a re-implementation in a test is a second definition that
 * can drift from the first.
 */
vi.mock("@/lib/city-page-read", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/city-page-read")>();
  return {
    ...actual,
    readCityPage: (slug: string, page: number) => readCityPage(slug, page),
  };
});

/**
 * **`notFound` throws.** That is what Next does with it, and it is what makes the 404
 * assertable.
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
});

/**
 * Run axe over the rendered page.
 *
 * **The container is the whole document.** axe walks the DOM it is given, so auditing
 * `main` alone would miss the shell — the topbar's landmark, the footer's nav, the
 * account links' accessible names — and those are part of the surface.
 */
async function audit() {
  const results = await axe.run(document.body, {
    resultTypes: ["violations"],
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
}

/** The violations, in a form a failure message can read. */
function describeViolations(violations: Awaited<ReturnType<typeof audit>>) {
  return violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`);
}

async function renderPage(query: Record<string, string> = {}) {
  render(
    await CityPageRoute({
      params: Promise.resolve({ slug: SLUG }),
      searchParams: Promise.resolve(query),
    }),
  );
}

describe("the city page's axe-core gate", () => {
  it("has zero serious or critical violations in the populated state", async () => {
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({
        has_next: true,
        items: [
          event(),
          event({ id: "second", title: "Smorgasburg food market", tags: ["in_brooklyn"] }),
        ],
      }),
    });

    await renderPage();

    expect(describeViolations(await audit())).toEqual([]);
  });

  it("has zero serious or critical violations in the empty listing", async () => {
    // **A published city with nothing on the listing** — between seasons. It is a 200,
    // it has no cards at all, and it is a different document from the full one.
    readCityPage.mockResolvedValue({ kind: "found", page: cityPage({ items: [] }) });

    await renderPage();

    expect(screen.getByText(/no upcoming events/i)).toBeInTheDocument();
    expect(describeViolations(await audit())).toEqual([]);
  });

  it("has zero serious or critical violations in the sparse state", async () => {
    // **The "coming soon" city** — a 200 whose whole body is a heading and a paragraph.
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ is_published: false, event_count: 2 }),
    });

    await renderPage();

    expect(screen.getByText(/Coming soon/)).toBeInTheDocument();
    expect(describeViolations(await audit())).toEqual([]);
  });

  it("has zero serious or critical violations in the unavailable state", async () => {
    // **A failure to answer is not an answer** — the page says so rather than claiming
    // the city does not exist.
    readCityPage.mockResolvedValue({ kind: "unavailable" });

    await renderPage();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/couldn't load/i);
    expect(describeViolations(await audit())).toEqual([]);
  });

  it("has zero serious or critical violations in the 404 document", async () => {
    render(<CityNotFound />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/don't have that city/i);
    expect(describeViolations(await audit())).toEqual([]);
  });

  it("has zero serious or critical violations on a later page, with the paging", async () => {
    // **Page two carries a different document** — the previous link, the page number, and
    // no next link when the backend says there is none.
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ has_next: true, page: 2, items: [event()] }),
    });

    await renderPage({ page: "2" });

    expect(describeViolations(await audit())).toEqual([]);
  });

  it("audits a document with the real landmarks in place", async () => {
    // A gate that passed because the page rendered nothing would pass forever. The
    // audit is only meaningful if it ran over the real surface.
    readCityPage.mockResolvedValue({
      kind: "found",
      page: cityPage({ items: [event()] }),
    });

    await renderPage();

    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Events in Brooklyn");
    expect(screen.getByRole("navigation", { name: "Brand" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Footer" })).toBeInTheDocument();
  });

  it("can fail, so the passes above mean something", async () => {
    // **A gate that cannot fail is a gate that has been switched off.**
    //
    // The mutation here is the one this page is most likely to develop: **the listing's
    // `<li>`s replaced by `<div>`s.** The listing is a `<ul>` of `<li>` cards, and a
    // future edit that swaps the element — for a layout reason, with no thought to the
    // semantics — silently breaks the list. A screen reader would announce the cards as
    // ungrouped text, and the count of the city's events would be lost with them.
    //
    // **The `list` rule is serious**, so the gate's own filter catches it — which is
    // exactly what this test is checking.
    render(
      <ul>
        <div>a card</div>
      </ul>,
    );

    const ids = (await audit()).map((violation) => violation.id);

    expect(ids).toContain("list");
  });
});
