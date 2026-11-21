import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EventDetailPage, { generateMetadata } from "@/app/events/[id]/page";

/**
 * `/events/{id}` — the branch between the two surfaces.
 *
 * **This file is separate from `page.test.tsx` on purpose.** The Detail Screen's own
 * tests are the ones that must keep passing **unchanged** — "Existing tests for those
 * routes pass unchanged" is a criterion, and a criterion you satisfy by editing the
 * tests is a criterion you have not satisfied. So the detail screen's tests stay where
 * they are, untouched, and this file covers what is new: the branch, the public page, the
 * 404, the metadata, and the no-session render.
 *
 * **The branch is the whole design.** A minted slug is the public event page;
 * everything else is the signed-in Detail Screen. The two surfaces read different
 * endpoints, use different chrome, and — the part that matters most — the public one
 * never touches a session.
 */

/** A real UUIDv7, in the shape this system's ids have. */
const UUID_V7 = "0196c3a4-5b6d-7e8f-9a0b-1c2d3e4f5061";
const SLUG = "designing-for-calm-2026-08-28-a1b2c3";

const readEventDetail = vi.fn();
const readPublicEvent = vi.fn();
const getSession = vi.fn();
const cookies = vi.fn();

vi.mock("@/lib/event-detail-read", () => ({
  readEventDetail: (id: string) => readEventDetail(id),
}));

vi.mock("@/lib/public-event-read", () => ({
  readPublicEvent: (slug: string) => readPublicEvent(slug),
}));

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/headers", () => ({
  cookies: () => cookies(),
}));

/**
 * **`notFound` and `permanentRedirect` throw.** That is what Next does with them, and
 * that is what makes the 404 and the redirect assertable: the page's branch must
 * *reach* them, and the throw is how the test sees that it did. The precedent is
 * `app/dev/health/page.test.tsx`.
 *
 * **The redirect's digest is Next's own format** — `NEXT_REDIRECT;replace;<url>;308;` —
 * so the assertion can read the destination and the status code off it exactly as
 * Next's own runtime does.
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

vi.mock("@/components/detail/detail-actions", () => ({
  DetailActions: () => <div data-detail-actions-stub />,
}));

/** The public payload the catalog's read returns. */
function publicPage(overrides: Record<string, unknown> = {}) {
  return {
    canonical_url: "https://brooklynartscouncil.org/events/calm",
    description: "A short, opinionated panel on building products that respect attention.",
    end_time_utc: null,
    event_version: 3,
    id: UUID_V7,
    is_sold_out: false,
    schema_org: {
      "@context": "https://schema.org",
      "@type": "Event",
      name: "Designing for Calm",
      startDate: "2026-08-28T18:30:00-04:00",
    },
    slug: SLUG,
    source_name: "Brooklyn Arts Council",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-08-28T22:30:00Z",
    status: "published",
    title: "Designing for Calm",
    tz_review_pending: false,
    venue_address: "27 Clinton Ave",
    venue_city: "Brooklyn",
    venue_country_code: "US",
    venue_name: "Brooklyn Arts Council",
    ...overrides,
  };
}

/** The detail screen's own payload. */
function detailFacts(overrides: Record<string, unknown> = {}) {
  return {
    canonical_url: "https://example.test/event",
    description: "An event this user was shown.",
    end_time_utc: null,
    event_version: 1,
    id: UUID_V7,
    is_sold_out: false,
    slug: "designing-for-calm",
    source_name: "Brooklyn Arts Council",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-11-07T23:00:00Z",
    status: "published",
    title: "Designing for Calm",
    tz_review_pending: false,
    venue_city: "Brooklyn",
    venue_country_code: "US",
    venue_name: "Brooklyn Arts Council",
    ...overrides,
  };
}

beforeEach(() => {
  readEventDetail.mockReset();
  readPublicEvent.mockReset();
  getSession.mockReset();
  cookies.mockReset();
  cookies.mockResolvedValue(new Map());
  getSession.mockResolvedValue({
    kind: "signed-in",
    user: { id: "11111111-1111-7111-8111-111111111111", email: "maya@example.test", name: "", onboarding: "complete" },
  });
});

async function renderWith(id: string) {
  render(await EventDetailPage({ params: Promise.resolve({ id }) }));
}

/* ── the branch ──────────────────────────────────────────────────────────────── */

describe("the branch", () => {
  it("reads a UUIDv7 as the signed-in Detail Screen", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: detailFacts(), personal: { saved: false, conflict: null, why_this: null } },
    });

    await renderWith(UUID_V7);

    expect(readEventDetail).toHaveBeenCalledWith(UUID_V7);
    expect(readPublicEvent).not.toHaveBeenCalled();
  });

  it("reads anything else as a public slug", async () => {
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    await renderWith(SLUG);

    expect(readPublicEvent).toHaveBeenCalledWith(SLUG);
    expect(readEventDetail).not.toHaveBeenCalled();
  });

  it("does not send a minted slug to the signed-in surface", async () => {
    // **A minted slug is the public page, and only the public page.** The slug's
    // shape is knowable — the backend mints one format and never changes it — so
    // the discriminator can name it exactly, and it does.
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    await renderWith(SLUG);

    expect(readEventDetail).not.toHaveBeenCalled();
    expect(readPublicEvent).toHaveBeenCalledWith(SLUG);
  });

  it("routes a non-minted parameter to the signed-in surface, where the backend refuses it", async () => {
    // **The safe direction.** A parameter that is not a minted slug reaches
    // `GET /api/events/{event_id}`, whose parameter is typed `UUID` on the backend —
    // so a stray token is refused there rather than rendering somebody's personal
    // page. The frontend never has to guess an id's shape to be safe.
    //
    // **The mock answers what the backend actually answers.** django-ninja validates
    // the path parameter with pydantic, and a non-UUID raises a `ValidationError`,
    // which ninja answers with a **422** (`ninja/errors.py`). The read maps anything
    // that is not a 404 and carries no payload to "unavailable", so the page renders
    // its error state — **not** a personal event, and not the public page either.
    readEventDetail.mockResolvedValue({ kind: "unavailable" });

    await renderWith("event-1");

    expect(readEventDetail).toHaveBeenCalledWith("event-1");
    expect(readPublicEvent).not.toHaveBeenCalled();
    // **And no personal page was rendered.** This is the property the routing exists
    // for: a stray token cannot reach somebody's saved events.
    expect(screen.queryByText("Designing for Calm")).not.toBeInTheDocument();
  });

  it("routes a UUIDv4 to the signed-in surface, not the public one", async () => {
    // **A v4 uuid is not one of this system's ids, but it is still an id-shaped
    // parameter.** The detail endpoint's parameter is typed `UUID`, so a v4 uuid is
    // accepted there and refused with a 404. Either way it is the detail branch's
    // question to answer — the public branch's slug read would 404 it anyway, but
    // by the wrong route.
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: detailFacts(), personal: { saved: false, conflict: null, why_this: null } },
    });

    await renderWith("3f2504e0-4f89-41d3-9a0c-0305e82c3301");

    expect(readEventDetail).toHaveBeenCalledWith("3f2504e0-4f89-41d3-9a0c-0305e82c3301");
    expect(readPublicEvent).not.toHaveBeenCalled();
  });

  it("renders the public page for a slug", async () => {
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    await renderWith(SLUG);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Designing for Calm");
  });

  it("renders the Detail Screen for a UUIDv7, and not the public page", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: {
        event: detailFacts({ title: "A personal event" }),
        personal: { saved: false, conflict: null, why_this: null },
      },
    });

    await renderWith(UUID_V7);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("A personal event");
    // The public page's own furniture is absent — the two surfaces do not bleed.
    expect(document.querySelector("[data-public-save-cta]")).toBeNull();
  });
});

/* ── the no-session render ───────────────────────────────────────────────────── */

describe("the public branch without a session", () => {
  it("renders with no cookies present", async () => {
    // **The page renders for a stranger.** No cookie, no session, no redirect, no
    // sign-in wall. The read itself is what makes this true — it asks for no session —
    // and the render proves that nothing else wanted one.
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });
    cookies.mockResolvedValue(new Map());

    await renderWith(SLUG);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Designing for Calm");
  });

  it("never reads the request's cookies", async () => {
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    await renderWith(SLUG);

    // **The call is the thing that matters, not the header.** A module that read the
    // cookies and then chose not to send them would still have opted the route out of
    // static generation.
    expect(cookies).not.toHaveBeenCalled();
  });

  it("never asks who the visitor is", async () => {
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    await renderWith(SLUG);

    expect(getSession).not.toHaveBeenCalled();
  });
});

/* ── the 404 ─────────────────────────────────────────────────────────────────── */

describe("the unknown slug", () => {
  it("raises a 404", async () => {
    // **`notFound()` in the render path.** Next's rule is exact: "To return a real
    // `404` status, the resource has to be checked before the response streams." The
    // throw is how the test sees that the page reached it.
    readPublicEvent.mockResolvedValue({ kind: "not-found", code: null, supersededBySlug: null });

    await expect(renderWith(SLUG)).rejects.toThrow("NEXT_HTTP_ERROR_FALLBACK;404");
  });

  it("sends a superseded event's reader to the replacement", async () => {
    // **The link a crawler already holds resolves forward rather than dying.** The
    // backend 404s the superseded slug and carries the successor's slug in `details`,
    // so the page turns that into a **308** to the successor — a permanent redirect,
    // because the old URL is permanently wrong and the successor is a live, published
    // event with its own page.
    readPublicEvent.mockResolvedValue({
      kind: "not-found",
      code: "not_found",
      supersededBySlug: "designing-for-calm-2026-09-02-d4e5f6",
    });

    const error = await renderWith(SLUG).catch((thrown: unknown) => thrown as Error);

    expect((error as Error & { digest: string }).digest).toBe(
      "NEXT_REDIRECT;replace;/events/designing-for-calm-2026-09-02-d4e5f6;308;",
    );
  });

  it("does not redirect when the backend named no successor", async () => {
    // **An unknown slug has nowhere to send the reader.** The 404 is the whole
    // answer, and it is a real one.
    readPublicEvent.mockResolvedValue({
      kind: "not-found",
      code: "not_found",
      supersededBySlug: null,
    });

    await expect(renderWith(SLUG)).rejects.toThrow("NEXT_HTTP_ERROR_FALLBACK;404");
  });

  it("does not raise a 404 when the API could not be reached", async () => {
    // **A failure to answer is not an answer.** A 404 is a claim about the world; an
    // unreachable API is a claim about us, and the two must not be confused — a
    // crawler that records "this does not exist" because we could not answer would put
    // a wrong fact into an index that is very hard to correct.
    readPublicEvent.mockResolvedValue({ kind: "unavailable" });

    await renderWith(SLUG);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /couldn't load this event/i,
    );
  });
});

/* ── the metadata ────────────────────────────────────────────────────────────── */

describe("the metadata", () => {
  it("carries the event's own title and description", async () => {
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    const metadata = await generateMetadata({ params: Promise.resolve({ id: SLUG }) });

    expect(metadata.title).toBe("Designing for Calm");
    expect(metadata.description).toContain("A short, opinionated panel");
  });

  it("carries a canonical link to the public URL", async () => {
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    const metadata = await generateMetadata({ params: Promise.resolve({ id: SLUG }) });

    // **One URL, indexed once.** The canonical is the public page's own URL, so a
    // shared link never reads as duplicate content.
    expect(metadata.alternates?.canonical).toBe(`/events/${SLUG}`);
  });

  it("carries the Open Graph tags", async () => {
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    const metadata = await generateMetadata({ params: Promise.resolve({ id: SLUG }) });

    expect(metadata.openGraph?.title).toBe("Designing for Calm");
    expect(metadata.openGraph?.url).toBe(`/events/${SLUG}`);
    expect(metadata.openGraph?.images).toHaveLength(1);
  });

  it("carries the Open Graph description — FR-28's third field", async () => {
    // **FR-28: "The share-link is Open Graph-rich (title, description, image)."** The
    // tags above assert the title and the image. The description was the one field of
    // the three that nothing asserted, and it is the one that degrades *silently*: an
    // unfurl with a blank description still renders, still looks like a card, and tells
    // the recipient nothing about the event.
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    const metadata = await generateMetadata({ params: Promise.resolve({ id: SLUG }) });

    expect(metadata.openGraph?.description).toBe(
      "A short, opinionated panel on building products that respect attention.",
    );
    const twitter = metadata.twitter as { description?: string };
    expect(twitter.description).toBe(
      "A short, opinionated panel on building products that respect attention.",
    );
  });

  it("falls back to title and source when the event has no description", async () => {
    // **The branch that makes "Open Graph-rich" true for every event, not most of them.**
    // A sourced event with no description is ordinary — plenty of feeds carry a title, a
    // time and nothing else. Without this fallback the unfurl would be a blank-bodied
    // card; with it, the recipient at least learns what and from whom.
    readPublicEvent.mockResolvedValue({
      kind: "found",
      page: publicPage({ description: null }),
    });

    const metadata = await generateMetadata({ params: Promise.resolve({ id: SLUG }) });

    expect(metadata.openGraph?.description).toBe("Designing for Calm — Brooklyn Arts Council");
    // The description is never empty, whichever branch produced it.
    expect(metadata.openGraph?.description).not.toBe("");
  });

  it("truncates a long description to 200 characters", async () => {
    // Unfurl bodies are clipped by the consuming platform anyway; sending the whole
    // thing just makes the document bigger. 200 is the implementation's own bound.
    readPublicEvent.mockResolvedValue({
      kind: "found",
      page: publicPage({ description: "x".repeat(500) }),
    });

    const metadata = await generateMetadata({ params: Promise.resolve({ id: SLUG }) });

    expect(metadata.openGraph?.description).toHaveLength(200);
  });

  it("carries the Twitter Card tags", async () => {
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    const metadata = await generateMetadata({ params: Promise.resolve({ id: SLUG }) });

    // **The `card` field is only on some members of Next's `Twitter` union** — the
    // `TwitterMetadata` variant carries it and the app variants do not — so the
    // assertion names the variant it expects rather than reaching through a union.
    const twitter = metadata.twitter as { card?: string; title?: string; images?: unknown[] };
    expect(twitter.card).toBe("summary_large_image");
    expect(twitter.title).toBe("Designing for Calm");
    expect(twitter.images).toHaveLength(1);
  });

  it("carries a branded image", async () => {
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    const metadata = await generateMetadata({ params: Promise.resolve({ id: SLUG }) });

    /**
     * The share image is the OG card, not the square logo — asserted exactly, for the
     * same reason as the city page's test. The square logo is 1282×1288; the card is
     * 1200×630, and those are the dimensions the metadata must declare.
     */
    const images = metadata.openGraph?.images as
      | Array<{ url: string; width?: number; height?: number }>
      | undefined;
    expect(images?.[0]?.url).toBe("/brand/eventpulse24-og.png");
    expect(images?.[0]?.width).toBe(1200);
    expect(images?.[0]?.height).toBe(630);
  });

  it("reads no session to build the metadata", async () => {
    // **This is the constraint that keeps the public page static.** `generateMetadata`
    // runs for both branches, so a Request-time API here would opt the *whole route*
    // out of static generation — and the public page would stop being a cacheable
    // document.
    readPublicEvent.mockResolvedValue({ kind: "found", page: publicPage() });

    await generateMetadata({ params: Promise.resolve({ id: SLUG }) });

    expect(cookies).not.toHaveBeenCalled();
    expect(getSession).not.toHaveBeenCalled();
  });

  it("falls back to the route's title for the signed-in surface", async () => {
    // **A personal page is not a share artefact.** Its metadata is the same for
    // everyone who sees it, and nothing here reads a session to find out who that is.
    const metadata = await generateMetadata({ params: Promise.resolve({ id: UUID_V7 }) });

    expect(metadata.title).toBe("Event · EventPulse24");
    expect(readPublicEvent).not.toHaveBeenCalled();
  });

  it("falls back to the route's title when there is no public event", async () => {
    readPublicEvent.mockResolvedValue({ kind: "not-found", code: null, supersededBySlug: null });

    const metadata = await generateMetadata({ params: Promise.resolve({ id: SLUG }) });

    // **No promise of a title the page does not have.**
    expect(metadata.title).toBe("Event · EventPulse24");
  });
});
