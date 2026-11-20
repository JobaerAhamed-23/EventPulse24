/**
 * Browse's *rendering* properties — what the page looks like once the server's payload
 * has been handed to it.
 *
 * **The counterpart to `tests/browse-boundary.test.ts`.** That file asserts on the
 * *source*: it can see a Sign-up CTA that was written into a second file and never
 * reached this branch, or a persona string sitting in a comment. This file asserts on
 * the *rendered document*: it can see what the reader actually gets, in the order they
 * get it, with the roles and names they get it under.
 *
 * **Both are needed, and neither substitutes for the other.** A source scan cannot see
 * whether the component renders at all — a page that throws before its first card would
 * pass every source rule. A rendering test cannot see a string that is never rendered.
 * Amendment A-12 is a set of *absences*, and each kind of absence needs the instrument
 * that can see it.
 *
 * **The server's payload is the fixture.** The page never ranks, sorts, re-tiers or
 * re-buckets (AD-10), so a test that reorders the fixture and expects the page to
 * reorder it would be asserting the opposite of the rule. The fixture's order is
 * asserted *as given*.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BrowsePage from "@/app/browse/page";
import BrowseLoading from "@/app/browse/loading";

const ROOT = path.resolve(__dirname, "..");

const getSession = vi.fn();
const readBrowse = vi.fn();
const redirect = vi.fn();
const apiGet = vi.fn();
const apiPost = vi.fn();
const apiDelete = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/browse-read", () => ({
  readBrowse: (...args: unknown[]) => readBrowse(...args),
}));

/**
 * The chunk loader's transport.
 *
 * **The chunk loader is now the island's, and the island talks to the backend through
 * the generated client.** The mock stands in for `api.GET("/api/personal/browse")` so
 * the chunk's *behaviour* — the offset it asks for, the re-entrancy guard, the failure
 * path — can be observed without a server.
 */
vi.mock("@/lib/backend-client", () => ({
  api: {
    GET: (...args: unknown[]) => apiGet(...args),
    POST: (...args: unknown[]) => apiPost(...args),
    DELETE: (...args: unknown[]) => apiDelete(...args),
  },
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  usePathname: () => "/browse",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "reader@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

function card(overrides: Record<string, unknown> = {}) {
  return {
    canonical_url: null,
    confidence: 4,
    end_time_utc: null,
    event_id: "22222222-2222-2222-2222-222222222222",
    is_saved: false,
    slug: "brooklyn-symphony",
    source_badge: "official_site",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-11-07T23:00:00Z",
    status: "on",
    stripe: "public",
    tags: ["nearby", "tonight"],
    title: "Brooklyn Symphony open rehearsal",
    tz_review_pending: false,
    venue_city: "Brooklyn",
    venue_name: "BAM Howard Gilman Opera House",
    ...overrides,
  };
}

const PAYLOAD = {
  cards: [
    card(),
    card({
      event_id: "33333333-3333-3333-3333-333333333333",
      stripe: "must_know",
      title: "Rooftop jazz at Bar Part",
      confidence: 5,
    }),
    card({
      event_id: "44444444-4444-4444-4444-444444444444",
      title: "Gallery late opening",
      tags: ["nearby", "matches_arts_culture"],
    }),
  ],
  city: "Brooklyn",
  city_missing: false,
  has_more: true,
  quota: {
    cap: 10,
    is_pro: false,
    resets_in_seconds: 86400,
    used: 3,
  },
  tier_2_starts_at: 1,
  timezone: "America/New_York",
  total: 40,
  window_from: "2026-11-07T23:00:00Z",
  window_to: "2026-11-14T23:00:00Z",
};

beforeEach(() => {
  getSession.mockReset();
  redirect.mockReset();
  readBrowse.mockReset();
  apiGet.mockReset();
  apiPost.mockReset();
  apiDelete.mockReset();
  apiPost.mockResolvedValue({ data: {}, response: { status: 200 }, error: undefined });
  apiDelete.mockResolvedValue({ data: undefined, response: { status: 204 }, error: undefined });
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readBrowse.mockResolvedValue({ kind: "browse", browse: PAYLOAD });
});

describe("the Browse route", () => {
  it("redirects an anonymous reader away from a page about their city", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    await BrowsePage({ searchParams: Promise.resolve({}) });

    expect(redirect).toHaveBeenCalled();
  });

  it("renders the shell rather than a fork of it", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // The shell's own landmarks. A forked shell would re-declare them.
    expect(screen.getByRole("main")).toBeTruthy();
    // Both navs carry the name "Main": the sidenav on desktop, the bottom-tab bar on
    // mobile. The shell renders both and the CSS picks one.
    expect(screen.getAllByRole("navigation", { name: "Main" }).length).toBeGreaterThan(0);
  });

  it("renders one h1, and it is the hero's", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0].textContent).toContain("Events in");
  });

  it("names the city in the h1's emphasised span", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const h1 = screen.getByRole("heading", { level: 1 });
    const emphasis = h1.querySelector("em");
    expect(emphasis?.textContent).toContain("Brooklyn");
    // The emphasis is what carries the terracotta, so it must be an element, not a
    // class on a span with no semantics.
    expect(emphasis).toBeTruthy();
  });
});

describe("the hero", () => {
  it("states the city and the window", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText(/Brooklyn · Tonight \+ 7 days/)).toBeTruthy();
  });

  it("offers a real link to change the city", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const link = screen.getByRole("link", { name: "Change city" });
    // **The city picker is on `/settings/profile`.** This link pointed at
    // `/settings/account` while the picker was there; it moved with the control, and a
    // link to a screen with no city control is the same dead end this test was written
    // for.
    expect(link.getAttribute("href")).toBe("/settings/profile");
  });

  it("reports the quota the API stated, not a client guess", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // The API says 3 of 10 used. The page says so.
    expect(screen.getByText(/Free plan: 3 of 10 saves used today/)).toBeTruthy();
    // And it says when it resets, in the API's own unit.
    expect(screen.getByText(/resets in 24h/)).toBeTruthy();
  });

  it("says a Pro account has no limit", async () => {
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: { ...PAYLOAD, quota: { cap: null, is_pro: true, resets_in_seconds: 0, used: 99 } },
    });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText(/Pro plan · no save limit/)).toBeTruthy();
  });

  it("counts the pool, not the page", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // `total` is 40; the page holds 3. The count shown is the pool's.
    expect(screen.getByText("40 events")).toBeTruthy();
  });
});

describe("the two section heads", () => {
  it("names the first section and the second", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("heading", { level: 2, name: /worth your attention/i })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "More this week" })).toBeTruthy();
  });

  it("does not say a persona's name", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // The city page's "Maya-fit" is the pre-auth voice; a stranger does not know who
    // Maya is. This is the rendered form of the boundary test's source rule.
    expect(screen.queryByText(/Maya/i)).toBeNull();
  });

  it("carries the city's own facts in the mono meta", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // The section head's meta is the city's name and the window's date — and it is
    // distinct from the hero's eyebrow, which says "Brooklyn · Tonight + 7 days".
    const metas = screen.getAllByText(/^Brooklyn · /);
    expect(metas.some((meta) => /·\s*\w{3},/.test(meta.textContent ?? ""))).toBe(true);
  });

  it("counts the section's own events, not what is still to come", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **N is the size of the second section, not the remainder.** The mockup settles
    // it: the hero's pill says "147 events this week" and the second section's meta
    // says "144 events" — and 147 − 3 (the first section's cards) is 144. So the
    // number is the pool minus the first section's split.
    //
    // Here the pool is 40 and `tier_2_starts_at` is 1, so the second section holds
    // 39. Reading it as "what is still to come" would announce "37 events" above a
    // grid of 2 cards — a heading that contradicts the thing it heads.
    expect(screen.getByText(/39 events · scroll for more/)).toBeTruthy();
  });

  it("splits at the index the server gave", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const sections = Array.from(document.querySelectorAll("section[data-browse-section]"));
    expect(sections).toHaveLength(2);

    // `tier_2_starts_at` is 1, so the first section holds exactly one card.
    const first = within(sections[0] as HTMLElement);
    expect(first.getAllByRole("listitem")).toHaveLength(1);

    const second = within(sections[1] as HTMLElement);
    expect(second.getAllByRole("listitem")).toHaveLength(2);
  });
});

describe("the grid", () => {
  it("puts each card in a list item", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // One `<ul>` per section, and only `<li>`s inside them. A heading inside a list
    // makes it not a list, and the `list` axe rule is serious.
    const lists = Array.from(document.querySelectorAll("section[data-browse-section] ul"));
    expect(lists).toHaveLength(2);
    for (const list of lists) {
      expect(list.querySelector("ul")).toBeNull();
      for (const child of Array.from(list.children)) {
        expect(child.tagName).toBe("LI");
      }
    }
  });

  it("adds a column at every step, including the two above lg", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **A-12's range is unchanged**: one column, two at `md: 768px`, three at
    // `lg: 1024px` — three columns at ≥1280px and two at 1024–1279px, as asked.
    //
    // **The two steps above it are what stop a card growing into the space.** `lg` used
    // to be the last breakpoint the token file declared, so three columns was also the
    // answer at 2560px: the grid held the count and stretched each column to 739px,
    // against the same card's 312px at 1280px. `xl: 1440px` and `2xl: 2048px` are now
    // declared in `styles/tokens.css`, and without them these two classes would
    // generate no CSS — so this asserts the declaration as much as the class.
    //
    // The gap is 20px, and 20px is **not** on the spacing scale — the scale's `20` is
    // 80px. So the gap is the bracketed exact value, not `gap-5`.
    for (const list of Array.from(document.querySelectorAll("section[data-browse-section] ul"))) {
      const className = list.getAttribute("class") ?? "";
      expect(className).toContain("grid-cols-1");
      expect(className).toContain("md:grid-cols-2");
      expect(className).toContain("lg:grid-cols-3");
      expect(className).toContain("xl:grid-cols-4");
      expect(className).toContain("2xl:grid-cols-5");
      expect(className).toContain("gap-[20px]");
    }
  });

  it("carries no frame of its own, so it shares the shell's left edge", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **Browse used to add `px-2` on top of `<main>`'s `px-6`** to make itself a 32px
    // frame. That was 8px more than Settings, the Timeline and the digest, so the
    // heading stepped sideways on every nav change between them — one app rendering as
    // two pages.
    //
    // The shell's frame is responsive now (24/48/80px, from `--layout-page-padding-*`),
    // which is the wider frame Browse was reaching for, applied to every surface at
    // once. So this asserts the *absence* of a horizontal frame here: re-adding one
    // re-opens the 8px step.
    const frame = document.querySelector("[data-browse-hero]")?.parentElement;
    const className = frame?.getAttribute("class") ?? "";

    expect(frame, "the hero's wrapper is the frame under test").not.toBeNull();
    expect(className).not.toMatch(/\bp[xl]-/);
  });

  it("uses the denser Browse sizing on the cards", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // 22px padding, not the digest's. And an 18px headline, which is
    // `--type-scale-headline-sm` — the only size on this card the digest does not
    // share.
    const card = document.querySelector("[data-browse-card]");
    const className = card?.getAttribute("class") ?? "";
    expect(className).toContain("px-[22px]");
    expect(className).toContain("py-[22px]");

    const headline = card?.querySelector("h3");
    expect(headline?.getAttribute("class")).toContain("type-scale-headline-sm");
  });

  it("keeps the server's order", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const titles = screen
      .getAllByRole("heading", { level: 3 })
      .map((heading) => heading.textContent);
    expect(titles).toEqual([
      "Brooklyn Symphony open rehearsal",
      "Rooftop jazz at Bar Part",
      "Gallery late opening",
    ]);
  });

  it("links each card to its event", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const link = screen.getByRole("link", { name: /Brooklyn Symphony open rehearsal/ });
    expect(link.getAttribute("href")).toBe("/events/22222222-2222-2222-2222-222222222222");
  });

  it("uses only the two stripes, and names them in words", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // Colour is never the only carrier (WCAG 1.4.1): each card says which stripe it is.
    expect(screen.getByText("Must-know")).toBeTruthy();
    expect(screen.getAllByText("Public")).toHaveLength(2);
  });

  it("labels the indicator as the Relevance Pulse, not the Event Fit", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // AD-10: the two indicators look identical on screen; the words are what keep them
    // apart.
    expect(screen.getAllByRole("button", { name: /Relevance \d of 5/ }).length).toBe(3);
    expect(screen.queryByRole("button", { name: /Fit \d of 5/i })).toBeNull();
  });

  it("names the indicator the same way everywhere it appears", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **One clamp, three consumers.** The dots, the button's accessible name and the
    // card's accessible name all read the same clamped value, so the card cannot say
    // "1 of 5" in one place and "0 of 5" in another.
    const link = screen.getByRole("link", { name: /Brooklyn Symphony open rehearsal/ });
    expect(link.getAttribute("aria-label")).toContain("Relevance 4 of 5");
    // The visible label is "Relevance", and the number lives in the accessible name.
    expect(screen.getAllByText("Relevance").length).toBe(3);
  });

  it("says a cancelled event is cancelled", async () => {
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: {
        ...PAYLOAD,
        cards: [card({ status: "cancelled" }), ...PAYLOAD.cards.slice(1)],
      },
    });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // The badge is `aria-hidden` (it is the glanceable half), so the *link* is what
    // carries the state in words. A cancelled event the reader cannot hear is a
    // cancelled event that lies.
    const link = screen.getAllByRole("link", { name: /Brooklyn Symphony open rehearsal/ })[0];
    expect(link.getAttribute("aria-label")).toMatch(/cancel/i);
  });
});

describe("the conversion scaffolding is absent from the rendered document", () => {
  it("has no Sign-up call to action", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.queryByRole("link", { name: /sign[\s-]?up/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /sign[\s-]?up/i })).toBeNull();
  });

  it("has no How-it-works call to action", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.queryByRole("link", { name: /how[\s-]?it[\s-]?works/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /how[\s-]?it[\s-]?works/i })).toBeNull();
  });

  it("has no SEO neighbour-cities footer", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.queryByRole("contentinfo")).toBeNull();
    expect(document.querySelector("footer")).toBeNull();
  });

  it("has no filter chip rail", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.queryByText(/this weekend/i)).toBeNull();
    expect(screen.queryByText(/by category/i)).toBeNull();
  });
});

describe("the soft cap's way through", () => {
  it("asks the server for 24 cards, and no more", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **The soft cap is 24 and the chunk size is 24** — the page holds one chunk, and
    // the anchor asks for the next one. The cap is a page size, not a client-side
    // truncation: the page never slices the payload it was given.
    const source = readFileSync(path.join(ROOT, "app/browse/page.tsx"), "utf8");
    expect(source).toContain("const PAGE_SIZE = 24");
  });

  it("offers an anchor, not pagination chrome", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **It is a button, not a link.** The click is intercepted and the chunk is
    // fetched in place — no navigation happens. An element that behaves as a button
    // but announces as a link lies about what activating it does. The `href` stays,
    // because the chunk's real URL is the anchor's `href` and a reader with
    // JavaScript off still needs it.
    const anchor = screen.getByRole("button", { name: "More events below" });
    expect(anchor.getAttribute("href")).toBe("/browse?offset=3");
    // No pager, no page numbers, no "Load more" button.
    expect(screen.queryByRole("button", { name: /load more/i })).toBeNull();
    expect(screen.queryByRole("navigation", { name: /pagination/i })).toBeNull();
  });

  it("shows the anchor only when the server says there is more", async () => {
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: { ...PAYLOAD, total: PAYLOAD.cards.length, has_more: false },
    });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.queryByRole("button", { name: "More events below" })).toBeNull();
  });

  it("honours an offset in the URL", async () => {
    // The anchor's `href` is a real navigation, and the route honours it — a
    // middle-click or a reader with JavaScript off must land on the same chunk the
    // anchor names.
    render(await BrowsePage({ searchParams: Promise.resolve({ offset: "24" }) }));

    expect(readBrowse).toHaveBeenCalledWith(24);
  });

  it("treats a malformed offset as the first page", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({ offset: "abc" }) }));

    expect(readBrowse).toHaveBeenCalledWith(0);
  });
});

describe("the quiet empty state", () => {
  it("says so, and offers the way out", async () => {
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: { ...PAYLOAD, cards: [], total: 0, has_more: false },
    });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **The empty state replaces the hero**, so there is no hero h1 above it — the
    // empty state's heading is the page's h1. An `<h2>` with no `<h1>` before it
    // breaks the heading order the way a skipped level does.
    expect(screen.getByRole("heading", { level: 1, name: /Nothing nearby tonight/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Change city" }).getAttribute("href")).toBe(
      "/settings/profile",
    );
  });

  it("does not claim the page failed", async () => {
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: { ...PAYLOAD, cards: [], total: 0, has_more: false },
    });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.queryByText(/couldn't reach/i)).toBeNull();
  });
});

describe("the error state", () => {
  it("offers one retry, and it is a real link", async () => {
    readBrowse.mockResolvedValue({ kind: "unavailable" });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("heading", { level: 1, name: /Couldn't reach Browse/ })).toBeTruthy();
    const retry = screen.getByRole("link", { name: /try again/i });
    expect(retry.getAttribute("href")).toBe("/browse");
  });

  it("leaves the shell's navigation usable", async () => {
    readBrowse.mockResolvedValue({ kind: "unavailable" });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // A failure that traps the reader inside the broken page is a worse failure than
    // the one it reports.
    // Both navs carry the name "Main": the sidenav on desktop, the bottom-tab bar on
    // mobile. The shell renders both and the CSS picks one.
    expect(screen.getAllByRole("navigation", { name: "Main" }).length).toBeGreaterThan(0);
  });
});

describe("the loading state", () => {
  it("shows twelve pulsing card-shaped rectangles", () => {
    render(<BrowseLoading />);

    const status = screen.getByRole("status", { name: "Loading Browse" });
    const rectangles = status.querySelectorAll(".skeleton-pulse");
    expect(rectangles).toHaveLength(12);
  });

  it("hides the rectangles from the screen reader", () => {
    render(<BrowseLoading />);

    const status = screen.getByRole("status", { name: "Loading Browse" });
    for (const rectangle of Array.from(status.querySelectorAll(".skeleton-pulse"))) {
      expect(rectangle.getAttribute("aria-hidden")).toBe("true");
    }
  });
});

/**
 * The inline keyword search — Amendment A-11.
 *
 * **The search is the only filter surface on this page.** The city page's chip rail
 * does not migrate, and the rules here and in `tests/browse-boundary.test.ts` are two
 * instruments for one lock: this file sees the rendered document, that one sees the
 * source.
 */
describe("the inline keyword search", () => {
  it("is one search input, below the hero", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **One input, and it is the only one.** A second filter input would be a second
    // grammar, and the calm contract is one learnable grammar.
    const inputs = screen.getAllByRole("searchbox");
    expect(inputs).toHaveLength(1);

    // It sits below the hero: the hero's heading comes before the input in the
    // document. (The document holds other inputs — the shell's own — so the
    // comparison is between the two elements that matter.)
    const hero = screen.getByRole("heading", { level: 1 });
    const input = inputs[0];
    expect(hero.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("teaches the grammar in place with the verbatim placeholder", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(
      screen.getByPlaceholderText("Search this week — jazz, free, outdoor, tag:music"),
    ).toBeTruthy();
  });

  it("has an accessible label", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **The placeholder is not the label.** A placeholder disappears the moment the
    // reader types, and a control whose name disappears when it is used is a control
    // whose name is gone exactly when it is needed.
    const input = screen.getByRole("searchbox", { name: "Search this week" });
    expect(input).toBeTruthy();
  });

  it("sits in a search landmark", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("search")).toBeTruthy();
  });

  it("filters the cards as the reader types, with no network request", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const input = screen.getByRole("searchbox");
    fireEvent.change(input, { target: { value: "jazz" } });

    // Only the card whose headline says "jazz" survives.
    const cards = Array.from(document.querySelectorAll("[data-browse-card]"));
    expect(cards).toHaveLength(1);
    expect(cards[0].textContent).toContain("Rooftop jazz at Bar Part");

    // **No request per keystroke.** The filter is a pure function over the cards
    // already in the browser.
    expect(readBrowse).toHaveBeenCalledTimes(1);
  });

  it("keeps the server's order among the cards that matched", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "brooklyn" } });

    const cards = Array.from(document.querySelectorAll("[data-browse-card]"));
    expect(cards.length).toBeGreaterThan(1);
    // The first card in the payload is still the first card on the page.
    expect(cards[0].textContent).toContain("Brooklyn Symphony");
  });

  it("ANDs two plain words", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const input = screen.getByRole("searchbox");
    fireEvent.change(input, { target: { value: "jazz" } });
    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(1);

    // The second word is on no card, so nothing matches.
    fireEvent.change(input, { target: { value: "jazz quantum" } });
    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(0);
  });

  it("matches a `tag:` literal against the card's why-tags", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "tag:tonight" } });

    // Two of the three cards carry `tonight`; the third carries a chip tag instead.
    const cards = Array.from(document.querySelectorAll("[data-browse-card]"));
    expect(cards).toHaveLength(2);
  });

  it("resolves a friendly tag name to the server's key", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **The design names ten tags the server does not have, and six of them resolve.**
    // `tag:arts` is the friendly name for the server's `matches_arts_culture`, and the
    // third card carries exactly that.
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "tag:arts" } });

    const cards = Array.from(document.querySelectorAll("[data-browse-card]"));
    expect(cards).toHaveLength(1);
    expect(cards[0].textContent).toContain("Gallery late opening");
  });

  it("matches nothing for a `tag:` the server has no fact for", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **`tag:music` must not become a plain-word search for "music".** The card whose
    // headline says "jazz" is not a music card as far as the server is concerned.
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "tag:music" } });

    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(0);
    expect(document.querySelector("[data-browse-search-empty]")).toBeTruthy();
  });

  it("shows a clear button only when there is something to clear", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // A permanently visible ✕ on an empty input is a control that does nothing.
    expect(screen.queryByRole("button", { name: "Clear search" })).toBeNull();

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "jazz" } });
    expect(screen.getByRole("button", { name: "Clear search" })).toBeTruthy();
  });

  it("empties the input when the clear button is pressed", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const input = screen.getByRole("searchbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "jazz" } });
    expect(input.value).toBe("jazz");

    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));

    expect(input.value).toBe("");
    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(3);
  });

  it("reports how many cards matched, politely", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "jazz" } });

    // **The count is announced, not the grid.** The grid changing silently under a
    // screen reader user is the worst outcome: the page sounds identical before and
    // after a filter.
    const status = document.querySelector("[data-browse-search-status]");
    expect(status?.getAttribute("aria-live")).toBe("polite");
    expect(status?.textContent).toBe("1 event matched.");
  });

  it("says the count in the count line too", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "jazz" } });

    // The mockup's line: "**N events** matched · M of M events total · Clear filters".
    const meta = document.querySelector("[data-browse-search-meta]");
    expect(meta?.textContent).toContain("1 event");
    expect(meta?.textContent).toContain("matched");
    expect(meta?.textContent).toContain("of 40 events total");
    expect(meta?.textContent).toContain("Clear filters");
  });

  it("names the reader's own terms back to them", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "quantum poetry" } });

    // The mockup's tone: the sentence is about the reader's query, not a persona's.
    const empty = document.querySelector("[data-browse-search-empty]");
    expect(empty?.textContent).toContain("quantum");
    expect(empty?.textContent).toContain("poetry");
    // And the hint line reports the same terms, with the operator spelled out.
    const hint = document.querySelector("[data-browse-search-hint]");
    expect(hint?.textContent).toContain("Match: quantum AND poetry");
  });
});

/**
 * The two empty states.
 *
 * **They must be distinguishable in the DOM, not just to the eye.** A reader whose city
 * is full and whose query was too narrow must not be sent to change a city that was
 * never the problem.
 */
describe("the two empty states", () => {
  it("says different things and offers different ways out", async () => {
    // **The zero-events state.**
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: { ...PAYLOAD, cards: [], total: 0, has_more: false },
    });
    const empty = render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("heading", { level: 1, name: /Nothing nearby tonight/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Change city" })).toBeTruthy();
    // And it has no search box at all — the page never rendered one.
    expect(screen.queryByRole("searchbox")).toBeNull();
    empty.unmount();

    // **The no-match state.**
    readBrowse.mockResolvedValue({ kind: "browse", browse: PAYLOAD });
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "quantum" } });

    expect(screen.getByRole("heading", { level: 2, name: "Nothing matched." })).toBeTruthy();
    // **Different copy, and a different recovery action.**
    expect(screen.queryByText(/Nothing nearby tonight/)).toBeNull();

    // **The empty state's own recovery is the search box, not the city's settings.**
    // (The hero's "Change city" link is the hero's, and it is still there — the rule
    // is about what the *empty state* offers, because that is what a reader in the
    // state is looking at.)
    const emptyState = document.querySelector("[data-browse-search-empty]");
    expect(emptyState).toBeTruthy();
    expect(emptyState?.querySelector('a[href="/settings/profile"]')).toBeNull();

    // And the way out of a query that matched nothing is the query's own clear.
    expect(screen.getByRole("button", { name: /Clear filters/i })).toBeTruthy();
  });

  it("removes the section heads and the grid when nothing matched", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "quantum" } });

    // **A heading over nothing is a heading that lies.** "More this week" with no more
    // in it would be a promise the page cannot keep.
    expect(screen.queryByRole("heading", { name: "More this week" })).toBeNull();
    expect(screen.queryByRole("heading", { name: /worth your attention/i })).toBeNull();
    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(0);
    expect(document.querySelector("[data-browse-search-empty]")).toBeTruthy();
  });

  it("restores the grid when the query is cleared", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "quantum" } });
    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: /Clear filters/i }));

    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(3);
    expect(screen.getByRole("heading", { name: "More this week" })).toBeTruthy();
  });
});

/**
 * Amendment A-11's lock, seen in the rendered document.
 *
 * **The source scan in `tests/browse-boundary.test.ts` cannot see everything.** A chip
 * rail written into a component this branch never renders is invisible to the DOM; and
 * a category button that is present but hidden is invisible to a reader but visible to
 * a source scan. The two instruments together are the enforcement.
 */
describe("the conversion and filter scaffolding is absent from the rendered document", () => {
  it("has no chip rail, no category buttons and no date presets", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **The city page's chip vocabulary.** "When: This week / Weekend / Tonight / Free"
    // and "Category: All / Music / Tech / Community / Arts / Family / Food & drink /
    // Sports" — none of it migrates.
    expect(screen.queryByRole("button", { name: /this weekend/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^tonight$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^free$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^all$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /food\s*&\s*drink/i })).toBeNull();

    // **And no date picker.**
    //
    // **Scoped to Browse's own frame, because the shell has one of its own.** The
    // account row's date field belongs to `AppShell`, which every authed route
    // shares, and A-11's lock is about the *city page's* filter vocabulary — not
    // about the shell's account controls. A rule that scanned the whole document
    // would be a rule about the shell, and it would fail for the wrong reason.
    const frame = document.querySelector("[data-browse-hero]")?.parentElement;
    expect(frame?.querySelector('input[type="date"]')).toBeNull();
  });

  it("offers exactly one filter: the search input", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **Every control on the page is accounted for.** The surface's controls are the
    // search input, its clear button, the chunk anchor, and each card's own trust row
    // and save slot. A category button or a date preset would be one of them.
    const searchboxes = screen.getAllByRole("searchbox");
    expect(searchboxes).toHaveLength(1);
    expect(document.querySelectorAll('input[type="search"]')).toHaveLength(1);
  });
});

/**
 * **The tier split must survive the filter.**
 *
 * **This is a re-tiering defect the filter would otherwise cause.** The server's
 * `tier_2_starts_at` is an index into the *pool* it sent. The grid used to slice the
 * *filtered* list at that index, so a filter that removed the pool's tier-one card
 * would promote the next card up — and "3 worth your attention today" would head cards
 * the server never said were worth the reader's attention. That is AD-10's exact
 * failure wearing a search's clothes.
 *
 * **The fixture makes the case concrete.** `tier_2_starts_at` is 1, so the first card
 * is tier one and the other two are tier two. A search that matches only the *second*
 * card must leave that card in "More this week" — tier one is now empty, and the
 * second section's head is the only honest one left on the page.
 */
describe("the tier split under a filter", () => {
  it("does not promote a tier-two card into tier one", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // "Rooftop" is on the second card only.
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "rooftop" } });

    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(1);

    // **The tier-one section is gone.** Its only card did not match, so there is
    // nothing under "3 worth your attention today" — and a heading over nothing is a
    // heading that lies.
    expect(screen.queryByRole("heading", { name: /worth your attention/i })).toBeNull();

    // **And the survivor is still tier two.** It sits under "More this week", which is
    // where the server put it.
    const second = document.querySelector('section[data-browse-section="tier-2"]');
    expect(second).toBeTruthy();
    expect(within(second as HTMLElement).getAllByRole("listitem")).toHaveLength(1);
  });

  it("keeps a matched tier-one card in tier one", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // "Symphony" is on the first card only, and the first card is tier one.
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "symphony" } });

    const first = document.querySelector('section[data-browse-section="tier-1"]');
    expect(first).toBeTruthy();
    expect(within(first as HTMLElement).getAllByRole("listitem")).toHaveLength(1);

    // The tier-two section is empty and its head goes with it.
    expect(screen.queryByRole("heading", { name: "More this week" })).toBeNull();
  });

  it("counts the second section's own events under a filter", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // Unfiltered, the second section's meta reads the pool's tier-two size.
    expect(screen.getByText(/39 events · scroll for more/)).toBeTruthy();

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "rooftop" } });

    // **Filtered, it reads what the section holds.** "39 events" above a grid of one
    // card would contradict the count line's "1 event matched".
    const meta = document.querySelector("[data-browse-section='tier-2'] p");
    expect(meta?.textContent).toMatch(/^1 event/);
  });
});

/**
 * The chunk loader, which lives in the search island.
 *
 * **The previous item's review left this untested, and it is now the island's job.**
 * The chunk loader used to be its own client component with its own state; Amendment
 * A-11's search moved that state into the island, because a chunk becomes part of the
 * loaded set the moment it lands and the query has to reach it. The *load* still had no
 * test of its own — the axe gate covered the appended list's markup, but nothing
 * covered the request it makes, the guard around it, or what happens when it fails.
 *
 * **These are the three claims the island's doc comment makes about itself.** Each one
 * is asserted here rather than left as prose.
 */
describe("the Save button on the card", () => {
  it("renders one Save button per card", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **One per card.** A card with two Save buttons would be two controls for one
    // thing, and a page with none would be a card anatomy missing its one affordance.
    expect(document.querySelectorAll("[data-browse-save-button]")).toHaveLength(3);
  });

  it("names the event in the button's accessible name", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **The visible label stays "Save"; the accessible name says which event.** A page
    // of a dozen cards each with a "Save" button gives a screen reader a dozen
    // identical controls.
    const save = screen.getAllByRole("button", { name: /Save .* to my Pulse/ });
    expect(save).toHaveLength(3);
    expect(save[0]?.getAttribute("aria-label")).toBe(
      "Save Brooklyn Symphony open rehearsal to my Pulse",
    );
  });

  it("renders 'Saved ✓' on the first paint for an already-saved event", async () => {
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: {
        ...PAYLOAD,
        cards: [card({ is_saved: true }), ...PAYLOAD.cards.slice(1)],
      },
    });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **No "Save" flash.** The state comes from the API's `is_saved`, not from an
    // effect that corrects itself a moment later — so the very first DOM already says
    // "Saved ✓".
    const saved = document.querySelectorAll("[data-browse-save-button]");
    expect(saved[0]?.textContent).toBe("Saved ✓");
    // And the other two are still "Save".
    expect(saved[1]?.textContent).toBe("Save");
  });

  it("renders the muted quota label on every card when the allowance is spent", async () => {
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: { ...PAYLOAD, quota: { cap: 1, is_pro: false, resets_in_seconds: 86400, used: 1 } },
    });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **Every card's button**, because the wall is the account's and not the card's.
    const buttons = Array.from(document.querySelectorAll("[data-browse-save-button]"));
    expect(buttons).toHaveLength(3);
    for (const button of buttons) {
      expect(button.textContent).toBe("1 of 1 save used today");
      expect(button.hasAttribute("disabled")).toBe(true);
    }
  });

  it("never renders the wall for a Pro account", async () => {
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: { ...PAYLOAD, quota: { cap: null, is_pro: true, resets_in_seconds: 0, used: 9 } },
    });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // **A Pro account has no wall** — and the `used` count of 9 is the proof that the
    // check is on the entitlement and not on the arithmetic.
    for (const button of Array.from(document.querySelectorAll("[data-browse-save-button]"))) {
      expect(button.textContent).toBe("Save");
      expect(button.hasAttribute("disabled")).toBe(false);
    }
  });

  it("saves through the existing endpoint when the button is pressed", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const save = document.querySelector("[data-browse-save-button]") as HTMLElement;
    fireEvent.click(save);

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledTimes(1);
    });
    expect(apiPost).toHaveBeenCalledWith("/api/personal/saved-events/{catalog_event_id}", {
      params: { path: { catalog_event_id: "22222222-2222-2222-2222-222222222222" } },
    });
  });
});

describe("the chunk loader", () => {
  /** A chunk of two cards, as the server would send it. */
  const chunk = {
    data: {
      cards: [
        card({ event_id: "55555555-5555-5555-5555-555555555555", title: "Chunked gallery" }),
        card({ event_id: "66666666-6666-6666-6666-666666666666", title: "Chunked rooftop" }),
      ],
    },
  };

  it("asks for the chunk after the page's own cards", async () => {
    apiGet.mockResolvedValue(chunk);
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.click(screen.getByRole("button", { name: "More events below" }));

    expect(apiGet).toHaveBeenCalledTimes(1);
    expect(apiGet).toHaveBeenCalledWith("/api/personal/browse", {
      params: { query: { offset: 3, limit: 24 } },
    });
  });

  it("asks for the chunk after the appended one, not this page's", async () => {
    // **The offset advances.** Asking for the same offset twice would fetch the same
    // chunk twice, and the page would show the same events twice under duplicate React
    // keys.
    apiGet.mockResolvedValue(chunk);
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.click(screen.getByRole("button", { name: "More events below" }));
    await screen.findByText("Chunked gallery");
    fireEvent.click(screen.getByRole("button", { name: "More events below" }));

    expect(apiGet).toHaveBeenCalledTimes(2);
    expect(apiGet.mock.calls[1]?.[1]).toMatchObject({
      params: { query: { offset: 5, limit: 24 } },
    });
  });

  it("appends the chunk's cards to the page", async () => {
    apiGet.mockResolvedValue(chunk);
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(3);

    fireEvent.click(screen.getByRole("button", { name: "More events below" }));

    expect(await screen.findByText("Chunked gallery")).toBeTruthy();
    // **Five, not seven.** The grid draws the whole loaded set and the chunk loader
    // draws only the anchor — so a chunked card appears *once*. When the chunk's state
    // moved into the island, the loader's own list became a second rendering of the
    // same cards, and every chunked event appeared twice.
    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(5);
    expect(screen.getAllByText("Chunked gallery")).toHaveLength(1);
  });

  it("issues one request for a double click", async () => {
    // **The guard is inside the handler, not on the element.** `aria-disabled` is
    // advisory — it tells assistive technology the control is unavailable and does
    // **not** stop a second click from firing. Without the `busy` check, a double
    // click would issue two requests for the *same* offset, and both responses would
    // append: the page would show the same events twice, under duplicate React keys,
    // and the next request would skip a chunk of the pool entirely.
    //
    // **The request is left pending**, so the second click lands while the first is
    // still in flight — which is exactly when the guard has to hold.
    apiGet.mockImplementation(() => new Promise(() => {}));
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const anchor = screen.getByRole("button", { name: "More events below" });
    fireEvent.click(anchor);
    fireEvent.click(anchor);

    expect(apiGet).toHaveBeenCalledTimes(1);
  });

  it("says so when the chunk could not be fetched", async () => {
    apiGet.mockResolvedValue({ data: undefined });
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.click(screen.getByRole("button", { name: "More events below" }));

    expect(await screen.findByText(/Couldn't load more/i)).toBeTruthy();
    // **The reader's way back is still there.** A failed load is not the end of the
    // page — the anchor stays so the reader can try again.
    expect(screen.getByRole("button", { name: "More events below" })).toBeTruthy();
  });

  it("keeps the chunk's cards subject to the query", async () => {
    // **A chunk becomes part of the loaded set the moment it lands.** A reader who
    // typed a query and then pulled in a chunk expects the chunk to obey the query
    // too — and a chunk that ignored it would be a filter that lied about how much it
    // had narrowed.
    apiGet.mockResolvedValue(chunk);
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "rooftop" } });
    fireEvent.click(screen.getByRole("button", { name: "More events below" }));

    // "Chunked rooftop" matches; "Chunked gallery" does not; and the first page's
    // "Rooftop jazz at Bar Part" matches too.
    await screen.findByText("Chunked rooftop");
    expect(screen.queryByText("Chunked gallery")).toBeNull();
    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(2);
  });
});
