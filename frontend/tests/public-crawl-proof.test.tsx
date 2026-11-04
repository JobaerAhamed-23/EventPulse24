// @vitest-environment node
/**
 * The anonymous crawl, end to end — **as a crawler sees it**.
 *
 * **The crawler reads bytes.** It does not run React, it does not hydrate, and it does
 * not execute the client bundle. So every assertion here is made against **the markup a
 * server render produced** — `renderToStaticMarkup` over the route functions
 * themselves. A DOM test with JavaScript enabled proves something else: that the
 * *browser* can build the page. The crawler cannot.
 *
 * **And "no session" is structural, not incidental.** The work item is explicit about
 * this: *"Prefer a test harness that makes 'no session' structural (a client with no
 * cookie jar at all) over one that merely omits a login step, which a later change can
 * silently restore."*
 *
 * **So the cookie jar is not merely empty — it is unreachable.** `next/headers`'s
 * `cookies` is mocked to **throw**. A public page that called it would not render a page
 * with an empty session; it would fail loudly, and the crawl would go red. That is
 * stronger than asserting `cookies` was never called, because it removes the possibility
 * of a call that *returns* a session and is then ignored — and that call is exactly the
 * one that rots quietly, because every test that logs in first still passes.
 *
 * **The three hops are walked in one file, in order.** The city landing, then the event
 * page it links to, then the CTA that invites an account. **No hop redirects, no hop
 * walls.** A sign-in wall that creeps onto a public page is invisible to every test that
 * logs in first: the test would be green, the crawler would be redirected, and the page
 * would be unindexable.
 *
 * **The JSON-LD is asserted on the markup, and the agreement is asserted together.**
 * The structured data and the visible state come from the same `status` field, so the
 * proof cancels an event and asserts **both** in one place: the rendered
 * `data-public-status` line says it is cancelled, and the JSON-LD's `eventStatus` is
 * `https://schema.org/EventCancelled`. Asserted separately, the two could drift — one
 * test would pass while the page lied to half its readers.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CityPageRoute from "@/app/events-in/[slug]/page";
import EventDetailPage from "@/app/events/[id]/page";

/**
 * The reads the crawl walks. They are mocked so the proof can be about the *pages* —
 * what the markup says — and about the *anonymity*, which is the property no mock of
 * the backend could ever prove.
 *
 * **The mock is at the read boundary, not at the fetch boundary.** The reads themselves
 * are the code under test for the "no session" property, and they are asserted on the
 * source in the backend's contract file. Here they stand in for the backend's answers.
 */
const readPublicEvent = vi.fn();
const readCityPage = vi.fn();
const readEventDetail = vi.fn();
const readReminderPlan = vi.fn();
const getSession = vi.fn();

vi.mock("@/lib/public-event-read", () => ({
  readPublicEvent: (slug: string) => readPublicEvent(slug),
}));

vi.mock("@/lib/city-page-read", () => ({
  readCityPage: (slug: string, page: number) => readCityPage(slug, page),
  cityPageHref: (slug: string, page: number) =>
    page > 1 ? `/events-in-${slug}?page=${page}` : `/events-in-${slug}`,
}));

vi.mock("@/lib/event-detail-read", () => ({
  readEventDetail: (id: string) => readEventDetail(id),
}));

vi.mock("@/lib/reminder-plan-read", () => ({
  readReminderPlan: (kind: string, id: string) => readReminderPlan(kind, id),
}));

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

/**
 * **`cookies` throws.** This is the whole anonymity mechanism.
 *
 * **A call that throws cannot be ignored.** A page that read the cookies and then chose
 * not to send them would still have opted the route out of static generation and made
 * the page's content depend on who is asking — and the test would have passed. Throwing
 * removes that possibility: the crawl goes red at the exact hop that opened the jar.
 */
vi.mock("next/headers", () => ({
  cookies: () => {
    throw new Error("a public page read the cookie jar");
  },
  headers: () => {
    throw new Error("a public page read the request headers");
  },
}));

/**
 * **`notFound` and `permanentRedirect` throw**, exactly as Next does with them — which
 * is what makes a 404 assertable. The redirect's digest is Next's own format, so the
 * destination and the status can be read off it.
 */
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_HTTP_ERROR_FALLBACK;404");
  },
  permanentRedirect: (url: string) => {
    const error = new Error("NEXT_REDIRECT") as Error & { digest: string };
    error.digest = `NEXT_REDIRECT;replace;${url};308;`;
    throw error;
  },
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

/** A real UUIDv7, in the shape this system's ids have. */
const UUID_V7 = "0196c3a4-5b6d-7e8f-9a0b-1c2d3e4f5061";

/** A minted slug — the shape the backend mints, and the public page's address. */
const SLUG = "designing-for-calm-2026-08-28-a1b2c3";

/** The city's canonical slug — the URL segment of `/events-in-{city}`. */
const CITY_SLUG = "brooklyn";

/** The public event payload the catalog's read returns. */
function publicPage(overrides: Record<string, unknown> = {}) {
  return {
    canonical_url: "https://brooklynartscouncil.org/events/calm",
    description: "A short, opinionated panel on building products that respect attention.",
    end_time_utc: "2026-08-28T23:30:00Z",
    event_version: 3,
    id: UUID_V7,
    is_sold_out: false,
    schema_org: {
      "@context": "https://schema.org",
      "@type": "Event",
      name: "Designing for Calm",
      startDate: "2026-08-28T22:30:00Z",
      eventStatus: "https://schema.org/EventScheduled",
      offers: {
        "@type": "Offer",
        availability: "https://schema.org/InStock",
      },
    },
    slug: SLUG,
    source_name: "Brooklyn Arts Council",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-08-28T22:30:00Z",
    status: "scheduled",
    title: "Designing for Calm",
    tz_review_pending: false,
    venue_address: "27 Clinton Ave",
    venue_city: "Brooklyn",
    venue_country_code: "US",
    venue_name: "Brooklyn Arts Council",
    ...overrides,
  };
}

/** The city page payload the catalog's read returns. */
function cityPage(overrides: Record<string, unknown> = {}) {
  return {
    country_code: "US",
    event_count: 6,
    has_next: false,
    is_published: true,
    items: [
      {
        canonical_url: "https://brooklynartscouncil.org/events/calm",
        city: "Brooklyn",
        description: "A short, opinionated panel.",
        end_time_utc: "2026-08-28T23:30:00Z",
        event_version: 3,
        id: UUID_V7,
        is_sold_out: false,
        score: 4,
        slug: SLUG,
        start_time_tz: "America/New_York",
        start_time_utc: "2026-08-28T22:30:00Z",
        status: "scheduled",
        tags: ["tonight"],
        title: "Designing for Calm",
        tz_review_pending: false,
        venue_name: "Brooklyn Arts Council",
      },
    ],
    name: "Brooklyn",
    page: 1,
    page_size: 20,
    region: "",
    slug: CITY_SLUG,
    ...overrides,
  };
}

/** The city page's own route function, awaited the way Next awaits it. */
async function renderCity(slug: string = CITY_SLUG, page?: string) {
  const markup = renderToStaticMarkup(
    await CityPageRoute({
      params: Promise.resolve({ slug }),
      searchParams: Promise.resolve(page === undefined ? {} : { page }),
    }),
  );
  return markup;
}

/** The event route's own route function, awaited the way Next awaits it. */
async function renderEvent(id: string = SLUG) {
  return renderToStaticMarkup(await EventDetailPage({ params: Promise.resolve({ id }) }));
}

beforeEach(() => {
  readPublicEvent.mockReset();
  readCityPage.mockReset();
  readEventDetail.mockReset();
  readReminderPlan.mockReset();
  getSession.mockReset();
  readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });
  readCityPage.mockResolvedValue({ kind: "found", page: cityPage() });
  readEventDetail.mockResolvedValue({ kind: "removed" });
  readReminderPlan.mockResolvedValue({ kind: "found", plan: null });
  getSession.mockResolvedValue({ kind: "signed-in", user: { email: "maya@example.test" } });
});

// ── the first hop: the city landing ─────────────────────────────────────────────────

describe("the first hop — the city landing", () => {
  it("renders server-side, with no cookie jar to open", async () => {
    const markup = await renderCity();

    // **The crawl reached a document.** A wall — a redirect to a sign-in page — would
    // render the *sign-in page* here, and the assertion on the city's own heading
    // would fail.
    expect(markup).toContain("Events in Brooklyn");
  });

  it("links to the event the crawl opens next", async () => {
    const markup = await renderCity();

    // **The crawl's second hop starts here.** The link is a plain anchor in the
    // server-rendered markup — `next/link` renders as `<a href="…">` — so a crawler
    // that reads bytes can follow it.
    expect(markup).toContain(`href="/events/${SLUG}"`);
  });

  it("reads the city's own page and nothing else", async () => {
    await renderCity();

    expect(readCityPage).toHaveBeenCalledWith(CITY_SLUG, 1);
    expect(readPublicEvent).not.toHaveBeenCalled();
  });

  it("never opened the cookie jar", async () => {
    // **The structural anonymity, asserted at the hop.** The `cookies` mock throws, so
    // this test is really "the hop did not read the jar" — and if it had, the render
    // would have thrown and this test would have failed with the jar's own message.
    await renderCity();

    expect(readCityPage).toHaveBeenCalled();
  });

  it("never asked who the visitor is", async () => {
    await renderCity();

    expect(getSession).not.toHaveBeenCalled();
  });
});

// ── the second hop: the event page ─────────────────────────────────────────────────

describe("the second hop — the event page", () => {
  it("renders server-side, with no cookie jar to open", async () => {
    const markup = await renderEvent();

    expect(markup).toContain("Designing for Calm");
  });

  it("shows the event's description", async () => {
    const markup = await renderEvent();

    expect(markup).toContain("A short, opinionated panel");
  });

  it("shows the Save to Pulse call to action", async () => {
    const markup = await renderEvent();

    expect(markup).toContain("Save to Pulse");
    expect(markup).toContain("data-public-save-cta");
  });

  it("shows the event's own status, and only when there is one to show", async () => {
    // **The status line is one calm line, and it is not an error.** A postponed or
    // cancelled event still has a page, and the reader who came to it needs to know it
    // is not going to happen as advertised. A *scheduled* event says nothing — a line
    // reading "Scheduled" would tell a reader nothing they did not already assume.
    const markup = await renderEvent();

    expect(markup).not.toContain("data-public-status");

    readPublicEvent.mockResolvedValue({
      kind: "found",
      page: publicPage({ status: "postponed" }),
    });

    const postponed = await renderEvent();

    expect(postponed).toContain("data-public-status");
    expect(postponed).toContain("Postponed");
  });

  it("points the call to action at the sign-up page, as a plain link", async () => {
    const markup = await renderEvent();

    // **A plain link, not a client island.** The CTA invites an account; it does not
    // gate the content. A crawler that does not execute JavaScript still sees the
    // link, and a reader without an account still reads the whole event first.
    //
    // **The assertion is scoped to the CTA's own block**, because the page carries a
    // *second* `/signup` link — the closing invitation at the foot. A bare search for
    // `href="/signup"` would be satisfied by that one, so a CTA that had been turned
    // into a button would still pass. The CTA's block is found by its own marker, and
    // the link is looked for inside it.
    const cta = blockOf(markup, "data-public-save-cta");

    expect(cta).toContain('href="/signup"');
    expect(cta).toContain("Save to Pulse");
  });

  it("never opened the cookie jar", async () => {
    await renderEvent();

    expect(readPublicEvent).toHaveBeenCalled();
  });

  it("never asked who the visitor is", async () => {
    await renderEvent();

    expect(getSession).not.toHaveBeenCalled();
  });

  it("never read the signed-in surface", async () => {
    // **The two surfaces are separate.** A crawl that landed on the Detail Screen's
    // read would be reading somebody's personal page, and the read would have needed a
    // session to do it.
    await renderEvent();

    expect(readEventDetail).not.toHaveBeenCalled();
  });
});

// ── the structured data, in the crawler's own bytes ────────────────────────────────

describe("the JSON-LD, in the crawler's own bytes", () => {
  it("is in the server-rendered markup", async () => {
    const markup = await renderEvent();

    // **A crawler that does not execute JavaScript sees nothing else.** If the JSON-LD
    // were injected by a client script, this assertion would be the one that failed —
    // and it is the assertion that matters, because the structured data is the whole
    // reason the page exists for a crawler.
    expect(markup).toContain('type="application/ld+json"');
  });

  it("parses as a Schema.org Event", async () => {
    const markup = await renderEvent();

    const parsed = parseJsonLd(markup);

    expect(parsed["@context"]).toBe("https://schema.org");
    expect(parsed["@type"]).toBe("Event");
    expect(parsed["name"]).toBe("Designing for Calm");
    expect(parsed["startDate"]).toBe("2026-08-28T22:30:00Z");
  });

  it("carries the offer the backend projected", async () => {
    const markup = await renderEvent();

    const parsed = parseJsonLd(markup);

    expect(parsed["offers"]).toMatchObject({
      "@type": "Offer",
      availability: "https://schema.org/InStock",
    });
  });

  it("is the payload's own object, not a second one the page built", async () => {
    // **The page embeds the payload's object verbatim.** If the page built its own
    // JSON-LD, the two could disagree about the event — and the structured data would
    // be the half that lied, because nothing else checks it.
    const markup = await renderEvent();

    expect(parseJsonLd(markup)).toEqual(publicPage().schema_org);
  });
});

// ── the visible page and the structured data agree ──────────────────────────────────

describe("the visible page and the structured data agree", () => {
  it("says so, together, for a cancelled event", async () => {
    // **AD-12, asserted in one place.** The visible line and the `eventStatus` come
    // from the same `status` field, so they cannot drift — and the proof shows it by
    // cancelling the event and asserting **both** halves from one render.
    readPublicEvent.mockResolvedValue({
      kind: "found",
      page: publicPage({
        status: "cancelled",
        schema_org: {
          ...publicPage().schema_org,
          eventStatus: "https://schema.org/EventCancelled",
        },
      }),
    });

    const markup = await renderEvent();

    // **The visible half.** The reader sees it.
    expect(markup).toContain("data-public-status");
    expect(markup).toContain("Cancelled");
    // **And the machine-readable half.** A crawler reads it.
    expect(parseJsonLd(markup)["eventStatus"]).toBe("https://schema.org/EventCancelled");
  });

  it("says nothing about a scheduled event, and the structured data agrees", async () => {
    // **A scheduled event is the ordinary case**, and a line reading "Scheduled" tells
    // a reader nothing they did not already assume — so the page says nothing. **And
    // the structured data says the same thing it always says**, because "scheduled" is
    // what the payload says.
    const markup = await renderEvent();

    expect(markup).not.toContain("data-public-status");
    expect(parseJsonLd(markup)["eventStatus"]).toBe("https://schema.org/EventScheduled");
  });
});

// ── the crawl's failure modes ──────────────────────────────────────────────────────

describe("the crawl's failure modes", () => {
  it("raises a real 404 for an unknown slug", async () => {
    // **A soft 404 is a URL a crawler records as a page that exists.** The throw is
    // how the proof sees that the page reached `notFound()` in the render path.
    readPublicEvent.mockResolvedValue({ kind: "not-found", code: null, supersededBySlug: null });

    await expect(renderEvent()).rejects.toThrow("NEXT_HTTP_ERROR_FALLBACK;404");
  });

  it("says so when the API could not be reached, rather than pretending it does not exist", async () => {
    // **A failure to answer is not an answer.** Telling a crawler an event does not
    // exist because we could not reach the API would put a wrong fact into an index
    // that is very hard to correct.
    readPublicEvent.mockResolvedValue({ kind: "unavailable" });

    const markup = await renderEvent();

    expect(markup).toContain("couldn&#x27;t load this event");
  });

  it("sends a superseded event's reader to the replacement", async () => {
    // **The link a crawler already holds resolves forward rather than dying.**
    readPublicEvent.mockResolvedValue({
      kind: "not-found",
      code: "not_found",
      supersededBySlug: "designing-for-calm-2026-09-02-d4e5f6",
    });

    const error = await renderEvent().catch((thrown: unknown) => thrown as Error);

    expect((error as Error & { digest: string }).digest).toBe(
      "NEXT_REDIRECT;replace;/events/designing-for-calm-2026-09-02-d4e5f6;308;",
    );
  });
});

// ── the authed surfaces are not broken ─────────────────────────────────────────────

describe("the authed surfaces still branch", () => {
  it("reads the detail endpoint for a UUID, and not the public one", async () => {
    // **The branching route did not regress the signed-in Detail Screen.** A UUID is
    // the Detail Screen's address, so it reads the detail endpoint — and the public
    // read is not called at all, which is what keeps the two surfaces separate.
    await renderEvent(UUID_V7);

    expect(readEventDetail).toHaveBeenCalledWith(UUID_V7);
    expect(readPublicEvent).not.toHaveBeenCalled();
  });

  it("reads the detail endpoint for a UUID even though the public one would answer", async () => {
    // **The discriminator, not the answer.** The public read is mocked to answer
    // happily, so if the branch ever went the wrong way this test would catch it: the
    // UUID would have rendered the *public* page, and a crawler could have indexed
    // somebody's Detail Screen.
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    await renderEvent(UUID_V7);

    expect(readEventDetail).toHaveBeenCalled();
    expect(readPublicEvent).not.toHaveBeenCalled();
  });
});

// ── the helper ─────────────────────────────────────────────────────────────────────

/**
 * The JSON-LD block, parsed out of the server-rendered markup.
 *
 * **It is parsed out of the markup, not read off the payload** — because the payload
 * being correct is the backend's claim, and the *markup* carrying it is the frontend's.
 * The proof is about the bytes the crawler receives.
 */
function parseJsonLd(markup: string): Record<string, unknown> {
  const match = /<script type="application\/ld\+json">([\s\S]*?)<\/script>/.exec(markup);
  if (!match) throw new Error("the server-rendered markup carried no JSON-LD block");
  return JSON.parse(match[1]) as Record<string, unknown>;
}

/**
 * The markup of the element carrying a `data-` marker, and everything inside it.
 *
 * **Scoped assertions, because the public page says some things twice.** The event
 * page carries a `/signup` link in its call to action *and* in its closing invitation,
 * and a bare search for the first would be satisfied by the second — so an assertion
 * about the CTA has to look at the CTA's own block.
 *
 * **The block is found by walking the tag nesting from the marker's own element.** The
 * marker attribute is on the element that opens the block, and the block ends when the
 * nesting returns to the depth it started at — which is what a browser does, and what
 * a crawler's parser does.
 */
function blockOf(markup: string, marker: string): string {
  const open = new RegExp(`<([a-z][a-z0-9]*)[^>]*\\b${marker}\\b[^>]*>`, "i").exec(markup);
  if (!open) throw new Error(`the markup carried no element with ${marker}`);
  const tag = open[1].toLowerCase();
  const start = open.index;
  const end = closingIndex(markup, start, tag);
  return markup.slice(start, end);
}

/**
 * The index just past the tag that closes the element which opened at `start`.
 *
 * **The opening tag is the first thing scanned, so the depth starts at one.** The
 * element's own closing tag is the one that brings the depth back to zero — and the
 * scan begins *after* the opening tag, so the opening tag is not counted twice.
 */
function closingIndex(markup: string, start: number, tag: string): number {
  const scanner = new RegExp(`<(/?)${tag}\\b[^>]*>`, "gi");
  // Start *after* the opening tag, so the depth counts only what is inside it.
  scanner.lastIndex = start + 1;
  let depth = 1;
  let end = markup.length;
  let match: RegExpExecArray | null;
  while ((match = scanner.exec(markup)) !== null) {
    if (match[1] === "/") {
      depth -= 1;
      if (depth === 0) {
        end = match.index + match[0].length;
        break;
      }
    } else {
      depth += 1;
    }
  }
  return end;
}
