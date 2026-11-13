import { readFileSync } from "node:fs";
import path from "node:path";

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "@/app/page";

/**
 * `/` — the Pulse Digest: the routing decision and the four states.
 *
 * The three redirect branches are the heart of it: an anonymous visitor belongs on
 * `/preview`, a half-onboarded user on `/onboarding`, and an onboarded one here. The
 * fourth case — the API unreachable — must *not* redirect, or a blip would throw a
 * signed-in user out to the marketing page.
 */

const getSession = vi.fn();
const readDigest = vi.fn();
const readNotices = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  // `homeRoute` is the real one: it is the rule under test, and `lib/session.test.ts`
  // pins it directly. Stubbing it here would let the page and the rule drift apart.
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/digest-read", () => ({
  readDigest: () => readDigest(),
}));

vi.mock("@/lib/notice-read", () => ({
  readNotices: () => readNotices(),
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  usePathname: () => "/",
  // The page renders the real sign-out button, which is a client component with a router.
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  onboarding: { completed: true, current_step: null },
};

function card(overrides: Record<string, unknown> = {}) {
  return {
    bucket: 4,
    canonical_url: null,
    catalog_event_missing: false,
    conflict: false,
    end_time_utc: null,
    event_id: "22222222-2222-2222-2222-222222222222",
    event_kind: "public",
    location: "Brooklyn",
    slot: "must_know",
    source_badge: "official_site",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-11-07T23:00:00Z",
    tags: ["nearby", "tonight"],
    title: "Brooklyn Symphony open rehearsal",
    tz_review_pending: false,
    venue_city: "Brooklyn",
    venue_name: "BAM Howard Gilman Opera House",
    /**
     * **The event's public page slug (FR-28).**
     *
     * The server states shareability and the card reads it: the slug when the event is
     * public, `null` when it is not — a personal event, or one the public catalog does
     * not hold.
     */
    public_slug: "brooklyn-symphony-open-rehearsal-2026-11-07-a1b2c3",
    ...overrides,
  };
}

const COMPOSED = {
  status: "composed" as const,
  cards: [card(), card({ event_id: "33333333-3333-3333-3333-333333333333" })],
  city: "Brooklyn",
  city_source: "user",
  local_date: "2026-11-07",
  timezone: "America/New_York",
};

/** The props Next passes the page: no route params, and the query string given. */
function props(query: Record<string, string | string[]> = {}): PageProps<"/"> {
  return { params: Promise.resolve({}), searchParams: Promise.resolve(query) };
}

beforeEach(() => {
  getSession.mockReset();
  redirect.mockReset();
  readDigest.mockReset();
  readNotices.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readDigest.mockResolvedValue({ kind: "composed", digest: COMPOSED });
  readNotices.mockResolvedValue({ kind: "notices", notices: [] });
});

describe("the routing decision", () => {
  it("sends an anonymous visitor to the public preview", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    await HomePage(props());

    expect(redirect).toHaveBeenCalledWith("/preview");
  });

  it("sends a signed-in user who hasn't finished onboarding to /onboarding", async () => {
    getSession.mockResolvedValue({
      kind: "signed-in",
      user: { ...USER, onboarding: { completed: false, current_step: 1 } },
    });

    await HomePage(props());

    expect(redirect).toHaveBeenCalledWith("/onboarding");
  });

  it("keeps an onboarded user here", async () => {
    render(await HomePage(props()));

    expect(redirect).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { level: 1, name: "Today, three things matter." }),
    ).toBeInTheDocument();
  });

  it("shows the calm error, and does not redirect, when the session can't be read", async () => {
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await HomePage(props()));

    expect(redirect).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Couldn't reach Pulse. Try again.",
    );
  });

  it("does not read the digest when the visitor is not signed in", async () => {
    // The session is unreadable, so there is no digest to read. Reading it anyway would
    // be an anonymous read of a personal endpoint.
    getSession.mockResolvedValue({ kind: "unavailable" });

    await HomePage(props());

    expect(readDigest).not.toHaveBeenCalled();
  });
});

describe("the digest is alone", () => {
  it("shows no personal-events list, because the Timeline is where they live", async () => {
    render(await HomePage(props()));

    // The stopgap list is gone. The Timeline is the home of a personal event, so a
    // second list under the digest would be the same events in two places.
    expect(screen.queryByRole("region", { name: "Your personal events" })).toBeNull();
    expect(screen.queryByText("You haven't added any personal events yet.")).toBeNull();
    expect(screen.queryByRole("button", { name: "Add event" })).toBeNull();
  });

  it("reads the digest and nothing else", async () => {
    // The page's second read is gone with the list. A personal-events read on the
    // digest's home would fetch a list the page does not show.
    const source = readFileSync(path.join(__dirname, "page.tsx"), "utf8");
    expect(source).not.toContain("readPersonalEvents");
    expect(source).not.toContain("PersonalEventsPanel");
    expect(source).not.toContain("personal-events-section");
  });

  it("keeps the header's quick-add, because the add belongs to the page head", async () => {
    const { container } = render(await HomePage(props()));

    // The sidenav and the bottom-tab bar carry their own Add rows, and the shell's
    // topbar is brand-only — so the header's quick-add is found by its place in the
    // digest's own header rather than by its name.
    const main = container.querySelector("main");
    expect(main?.querySelector("header")?.textContent).toContain("Add personal event");
  });
});

describe("the digest", () => {
  it("renders the cards in the server's order", async () => {
    // The order is a persisted fact: the composition service chose the slot order and
    // stored it. A client that re-sorted would be re-deciding it at render (AD-10).
    const titles = ["First card", "Second card", "Third card"];
    readDigest.mockResolvedValue({
      kind: "composed",
      digest: {
        ...COMPOSED,
        cards: titles.map((title, index) =>
          card({ title, event_id: `00000000-0000-0000-0000-00000000000${index}` }),
        ),
      },
    });

    render(await HomePage(props()));

    const headlines = screen.getAllByRole("heading", { level: 3 }).map((el) => el.textContent);
    expect(headlines).toEqual(titles);
  });

  it("renders no more cards than the server sent", async () => {
    render(await HomePage(props()));

    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(COMPOSED.cards.length);
  });

  it("shows the header's date line from the server's date and city", async () => {
    readDigest.mockResolvedValue({
      kind: "composed",
      digest: { ...COMPOSED, local_date: "2026-11-07", city: "Brooklyn" },
    });

    render(await HomePage(props()));

    // The weekday is read in the digest's own zone, so it is the server's Saturday —
    // and 2026-11-07 is a Saturday.
    const eyebrow = screen.getByText(/Saturday/);
    expect(eyebrow).toHaveTextContent("Saturday · Nov 7, 2026 · Brooklyn");
  });

  it("announces the digest once, in a live region, with the card count", async () => {
    render(await HomePage(props()));

    const region = screen.getByRole("status", { name: "" });
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveAttribute("aria-atomic", "true");
    expect(region).toHaveTextContent("Pulse Digest ready, 2 events for today.");
  });

  it("announces the digest with a comma, not a full stop", async () => {
    // The full stop would change the sentence boundary a screen reader hears.
    render(await HomePage(props()));

    const region = screen.getByRole("status", { name: "" });
    expect(region.textContent).toContain("ready, 2 events");
    expect(region.textContent).not.toContain("ready.");
  });

  it("is rendered per request, so the build never reads the user's digest", async () => {
    const page = await import("@/app/page");

    expect(page.dynamic).toBe("force-dynamic");
  });
});

describe("the digest's share affordance", () => {
  it("offers a share control on every card the server says is shareable", async () => {
    // **The server states shareability** (`public_slug`), and the card renders a
    // control exactly when it is set — it never infers it.
    render(await HomePage(props()));

    expect(screen.getAllByRole("button", { name: /share/i })).toHaveLength(COMPOSED.cards.length);
  });

  it("offers none on a card the server says is not shareable", async () => {
    // A personal event, or an event the public catalog does not hold — either way, a
    // share control would produce a link that 404s for the friend who opened it.
    readDigest.mockResolvedValue({
      kind: "composed",
      digest: { ...COMPOSED, cards: [card({ public_slug: null })] },
    });

    render(await HomePage(props()));

    expect(screen.queryByRole("button", { name: /share/i })).toBeNull();
  });

  it("keeps the digest's single status region, even with the cards' confirmations", async () => {
    // The cards' own confirmations are **bare** `aria-live="polite"` regions. A second
    // `role="status"` on the page would make "which one is the page talking?" a
    // question the DOM cannot answer.
    render(await HomePage(props()));

    expect(screen.getAllByRole("status")).toHaveLength(1);
  });
});

describe("the empty state", () => {
  beforeEach(() => {
    readDigest.mockResolvedValue({
      kind: "empty",
      digest: { ...COMPOSED, status: "empty", cards: [] },
    });
  });

  it("reads the locked copy", async () => {
    render(await HomePage(props()));

    expect(
      screen.getByRole("heading", { name: "Nothing on the pulse today. The calendar is yours." }),
    ).toBeInTheDocument();
  });

  it("names the city in the line below the card", async () => {
    render(await HomePage(props()));

    expect(screen.getByText("No qualifying events in Brooklyn.")).toBeInTheDocument();
  });

  it("offers one low-weight link, and no button", async () => {
    const { container } = render(await HomePage(props()));

    const link = screen.getByRole("link", { name: "Suggest an event" });
    expect(link).toHaveAttribute("href", "/suggest");

    // No CTA pair, no carousel, no upsell: the empty state is the message. The shell's
    // own controls (the Add slot, the Search button) are not part of the empty state,
    // and neither is anything else outside `main` — so the assertion is over the whole
    // digest region, which is what is left now the personal-events list is gone.
    const main = container.querySelector("main");
    expect([...(main?.querySelectorAll("button") ?? [])]).toHaveLength(0);
    expect([...(main?.querySelectorAll("a") ?? [])]).toHaveLength(1);
  });

  it("carries no terracotta, which is rationed to four uses", async () => {
    const { container } = render(await HomePage(props()));

    // The shell's brand mark is terracotta, and so is the header's `Indicator.Today`
    // dot — both are sanctioned uses. The *empty state* may carry neither: the
    // mockup's terracotta primary button is the violation.
    const main = container.querySelector("main");
    const empty = main?.querySelector("article");
    expect(empty?.querySelector(".bg-accent-terracotta")).toBeNull();
  });

  it("is distinct from the not-yet-composed state", async () => {
    render(await HomePage(props()));

    expect(screen.queryByRole("heading", { name: /being prepared/i })).not.toBeInTheDocument();
  });
});

describe("the not-yet-composed state", () => {
  beforeEach(() => {
    readDigest.mockResolvedValue({
      kind: "not_composed",
      digest: { ...COMPOSED, status: "not_composed", cards: [] },
    });
  });

  it("says the digest is being prepared, and claims nothing about the world", async () => {
    render(await HomePage(props()));

    expect(
      screen.getByRole("heading", { name: "Your Pulse is being prepared." }),
    ).toBeInTheDocument();

    // "No qualifying events" is a claim about the world, and the world has not been
    // asked yet.
    expect(screen.queryByText(/No qualifying events/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Nothing on the pulse today/)).not.toBeInTheDocument();
  });

  it("is not the empty state", async () => {
    render(await HomePage(props()));

    expect(
      screen.queryByRole("heading", { name: "Nothing on the pulse today. The calendar is yours." }),
    ).not.toBeInTheDocument();
  });
});

describe("the error state", () => {
  beforeEach(() => {
    readDigest.mockResolvedValue({ kind: "unavailable" });
  });

  it("says so, and offers one retry", async () => {
    render(await HomePage(props()));

    expect(screen.getByRole("heading", { name: /Couldn't reach Pulse/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Try again" })).toBeInTheDocument();
  });

  it("says 'Refresh page.' on the second consecutive failure", async () => {
    // The second failure is the render the first failure's retry link asked for.
    render(await HomePage(props({ retry: "1" })));

    expect(screen.getByRole("link", { name: "Refresh page." })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("follows its own retry link to the second-failure label", async () => {
    // The two halves of the count have to agree: the link the first failure renders is
    // the URL that makes the next failure the second.
    render(await HomePage(props()));
    const href = screen.getByRole("link", { name: "Try again" }).getAttribute("href") ?? "";
    const query = Object.fromEntries(new URL(href, "http://pulse.test").searchParams);
    cleanup();

    render(await HomePage(props(query)));
    expect(screen.getByRole("link", { name: "Refresh page." })).toBeInTheDocument();
  });

  it("treats a malformed retry value as a first failure", async () => {
    render(await HomePage(props({ retry: "junk" })));
    expect(screen.getByRole("link", { name: "Try again" })).toBeInTheDocument();
  });

  it("renders the digest on a retry that succeeds", async () => {
    readDigest.mockResolvedValue({ kind: "composed", digest: COMPOSED });
    render(await HomePage(props({ retry: "1" })));
    expect(screen.queryByRole("link", { name: "Refresh page." })).not.toBeInTheDocument();
    expect(screen.getAllByText("Brooklyn Symphony open rehearsal")).not.toHaveLength(0);
  });

  it("writes no cookie, because a page render may not", async () => {
    // The cookie version of the count threw "Cookies can only be modified in a Server
    // Action or Route Handler" on every render of `/` in the real Next runtime. The
    // page must not reach for the cookie store at all.
    const source = readFileSync(path.join(__dirname, "page.tsx"), "utf8");
    expect(source).not.toMatch(/next\/headers|cookies\(/);
  });

  it("retries the read rather than reloading the document on the first failure", async () => {
    render(await HomePage(props()));

    // The retry carries `retry=1`, so the server renders again rather than serving the
    // failure it already rendered, and knows the next failure is the second.
    const retry = screen.getByRole("link", { name: "Try again" });
    expect(retry).toHaveAttribute("href", "/?retry=1");
  });

  it("is not the session error", async () => {
    // The session is fine here; the digest read failed. Two different failures, and the
    // digest's error is the one inside the page's main region.
    const { container } = render(await HomePage(props()));

    const main = container.querySelector("main");
    expect(main?.querySelectorAll("h2")).toHaveLength(1);
    expect(main?.querySelector("h1")).toBeNull();
  });
});

describe("the state-change strip", () => {
  /**
   * One notice, as the strip's own read hands it over.
   *
   * **The payload carries no title** (AD-13) — so the strip says "This event" and the
   * page's own surface says which one.
   */
  function notice(overrides: Record<string, unknown> = {}) {
    return {
      id: "notice-1",
      event_id: "22222222-2222-2222-2222-222222222222",
      change_kind: "cancelled",
      event_version: 3,
      local_date: "2026-11-07",
      seen_at: null,
      dismissed_at: null,
      created_at: "2026-11-07T12:00:00Z",
      ...overrides,
    };
  }

  it("renders nothing at all when there are no notices", async () => {
    // **No element in the DOM.** The AC says the home screen must render "exactly as it
    // does today, with no layout shift", and an empty `<section>` is a layout shift
    // waiting for a stylesheet. No element is not.
    const { container } = render(await HomePage(props()));

    expect(screen.queryByRole("region", { name: "Changes to your saved events" })).toBeNull();
    expect(container.querySelector("[data-notice-strip-item]")).toBeNull();
  });

  it("renders the strip's sentence and the event's link", async () => {
    readNotices.mockResolvedValue({ kind: "notices", notices: [notice()] });

    render(await HomePage(props()));

    expect(screen.getByText("This event was cancelled.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "This event was cancelled." })).toHaveAttribute(
      "href",
      "/events/22222222-2222-2222-2222-222222222222",
    );
  });

  it("says what happened to the user's reminders", async () => {
    readNotices.mockResolvedValue({ kind: "notices", notices: [notice()] });

    render(await HomePage(props()));

    expect(
      screen.getByText("Your reminders for this event have been cancelled."),
    ).toBeInTheDocument();
  });

  it("renders nothing when the read fails, because 'we do not know' is not 'nothing changed'", async () => {
    // **The two are different claims about the world.** An empty list means nothing
    // changed; a failed read means we do not know. The page must not make the second
    // claim in the first one's voice.
    readNotices.mockResolvedValue({ kind: "unavailable" });

    const { container } = render(await HomePage(props()));

    expect(screen.queryByRole("region", { name: "Changes to your saved events" })).toBeNull();
    expect(container.querySelector("[data-notice-strip-item]")).toBeNull();
  });

  it("keeps the digest's single status region", async () => {
    // **Two status regions would make "which one is the page talking?" a question the
    // DOM cannot answer.** The strip announces through a bare `aria-live="polite"`.
    readNotices.mockResolvedValue({ kind: "notices", notices: [notice()] });

    render(await HomePage(props()));

    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("sits between the header and the cards", async () => {
    // **Above the header would be a banner**, and a banner is what this is not. Below
    // the header and above the cards is the reading order a reader expects: *here is
    // what changed; here is what is on today.*
    readNotices.mockResolvedValue({ kind: "notices", notices: [notice()] });

    const { container } = render(await HomePage(props()));
    const main = container.querySelector("main");
    const strip = main?.querySelector("[data-notice-strip-item]");
    const heading = screen.getByRole("heading", { level: 1 });
    const firstCard = screen.getAllByRole("heading", { level: 3 })[0];

    if (!strip) throw new Error("the strip is not in the document");

    expect(heading.compareDocumentPosition(strip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(
      strip.compareDocumentPosition(firstCard) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("does not read the notices when the visitor is not signed in", async () => {
    getSession.mockResolvedValue({ kind: "unavailable" });

    await HomePage(props());

    expect(readNotices).not.toHaveBeenCalled();
  });
});

describe("the shell", () => {
  /**
   * The sidenav and the bottom-tab bar both render the route labels, so a
   * document-wide query finds two of everything. These helpers scope to the one
   * rail or bar being tested.
   */
  function sidenav(): HTMLElement {
    return screen.getByRole("complementary", { name: "Primary" });
  }

  it("carries the six routes, in the locked order", async () => {
    render(await HomePage(props()));

    // The route list is the nav's own `<ul>`. Each route's name is a span of its own;
    // the Add row carries a button, and the glyphs are SVG. The "Coming soon" filter is
    // left in place for the next deferred route — the inert row still renders one, and
    // this test would otherwise read it as the route's name.
    const nav = sidenav().querySelector("nav");
    expect(nav).not.toBeNull();
    const labels = [...(nav?.querySelectorAll("li") ?? [])].map((li) => {
      const spans = [...li.querySelectorAll("span")];
      const named = spans.find(
        (span) =>
          span.textContent?.trim() !== "Coming soon" &&
          span.querySelector("svg") === null &&
          !span.hasAttribute("aria-hidden"),
      );
      return named?.textContent?.trim();
    });
    expect(labels).toEqual(["Digest", "Timeline", "Add", "Browse", "Conflicts", "Settings"]);
  });

  it("marks the active route with an ink pill, never a terracotta fill", async () => {
    render(await HomePage(props()));

    const active = sidenav().querySelector('a[aria-current="page"]');
    expect(active).not.toBeNull();
    expect(active?.textContent).toContain("Digest");
    expect(active?.className).toContain("bg-surface-subtle");
    expect(active?.className).not.toContain("terracotta");
  });

  it("makes Browse a real route, because the Browse surface shipped", async () => {
    render(await HomePage(props()));

    // **Browse was the last route the rail pretended did not exist.** The surface
    // shipped with the Browse read API, so the row is a link — a link to a 404 would
    // have been a lie, and so would a "Coming soon" label next to a city full of
    // events.
    const item = [...sidenav().querySelectorAll("li")].find((li) =>
      [...li.querySelectorAll("span")].some((span) => span.textContent?.trim() === "Browse"),
    );
    expect(item).not.toBeUndefined();
    expect(item?.querySelector("a")?.getAttribute("href")).toBe("/browse");
    expect(item?.querySelector("[aria-disabled='true']")).toBeNull();
    expect(item?.textContent).not.toContain("Coming soon");
  });

  it("leaves no route in the rail inert", async () => {
    render(await HomePage(props()));

    // **Every one of the six routes is a real screen now**, so the rail has no
    // `aria-disabled` row left — and the rule that governs an inert row (a `<span>`,
    // never an anchor) has nothing left to govern. The *rule* survives in the
    // component; this asserts that no row *uses* it.
    expect(sidenav().querySelector("[aria-disabled='true']")).toBeNull();
  });

  it("makes Settings a real route, because the settings screens exist", async () => {
    render(await HomePage(props()));

    const item = [...sidenav().querySelectorAll("li")].find((li) =>
      [...li.querySelectorAll("span")].some((span) => span.textContent?.trim() === "Settings"),
    );
    expect(item).not.toBeUndefined();
    expect(item?.querySelector("a")?.getAttribute("href")).toBe("/settings/reminders");
    // "Coming soon" is gone — the route is here.
    expect(item?.textContent).not.toContain("Coming soon");
  });

  it("makes Conflicts a real route, because the Conflict Review exists", async () => {
    render(await HomePage(props()));

    const item = [...sidenav().querySelectorAll("li")].find((li) =>
      [...li.querySelectorAll("span")].some((span) => span.textContent?.trim() === "Conflicts"),
    );
    expect(item).not.toBeUndefined();
    expect(item?.querySelector("a")?.getAttribute("href")).toBe("/conflicts");
    // "Coming soon" is gone — the route is here.
    expect(item?.textContent).not.toContain("Coming soon");
  });

  it("makes Timeline a real route, because the Timeline exists", async () => {
    render(await HomePage(props()));

    const item = [...sidenav().querySelectorAll("li")].find((li) =>
      [...li.querySelectorAll("span")].some((span) => span.textContent?.trim() === "Timeline"),
    );
    expect(item).not.toBeUndefined();
    expect(item?.querySelector("a")?.getAttribute("href")).toBe("/timeline");
    // "Coming soon" is gone — the route is here.
    expect(item?.textContent).not.toContain("Coming soon");
  });

  it("keeps the topbar brand-only", async () => {
    const { container } = render(await HomePage(props()));

    const header = container.querySelector("header");
    expect(header?.textContent).toContain("EventPulse24");
    // The brand glyph is decorative; the wordmark carries the name.
    expect(header?.querySelector("a")).toBeNull();
    expect(header?.querySelector("button")).toBeNull();
    expect(header?.querySelector("nav")).toBeNull();
  });

  it("constrains the content to the reading width, so a wide screen does not reflow it", async () => {
    const { container } = render(await HomePage(props()));

    // "Desktop adds whitespace, never features, screens, actions or copy" (§10). A wide
    // viewport stretches a card; a wide *card* changes how the card reads. So the
    // constraint is the whole of the desktop's contribution to the layout.
    const main = container.querySelector("main");
    expect(main?.className).toContain("max-w-(--layout-container-max)");
  });

  it("shows the account row in the sidenav footer", async () => {
    render(await HomePage(props()));

    // The row is a *button*, not a link. It used to be `<Link href="/settings">`, and
    // `/settings` does not exist — the sidenav's own rule against linking to a 404.
    expect(screen.getByRole("button", { name: /Account: Maya/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Search events" })).toBeInTheDocument();
  });

  it("puts sign out behind the account row, so a signed-in user can get out", async () => {
    render(await HomePage(props()));

    const account = screen.getByRole("button", { name: /Account: Maya/ });
    expect(account).toHaveAttribute("aria-haspopup", "dialog");

    fireEvent.click(account);

    // Scoped to the open sheet: the mobile More sheet renders the same panel, so the
    // email and the button are in the document twice — once per breakpoint's surface.
    const sheet = await screen.findByRole("dialog", { name: "Account" });
    expect(within(sheet).getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(within(sheet).getByText("maya@example.test")).toBeInTheDocument();
  });

  it("reaches sign out on mobile too, where the sidenav is hidden", async () => {
    render(await HomePage(props()));

    // The rail is `hidden md:flex`, so the bottom bar's More sheet is the only account
    // surface a phone has. Both carry the same panel.
    fireEvent.click(screen.getByRole("button", { name: "More" }));

    const sheet = await screen.findByRole("dialog", { name: "More" });
    expect(within(sheet).getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(within(sheet).getByText("maya@example.test")).toBeInTheDocument();
  });

  it("links the account row nowhere, because /settings does not exist", async () => {
    const { container } = render(await HomePage(props()));

    expect(container.querySelector('a[href="/settings"]')).toBeNull();
  });
});
