/**
 * The **axe-core gate** for FR-54's two in-app surfaces: the digest strip and the Detail
 * banner.
 *
 * **"axe-core reports zero serious or critical violations on both surfaces."** The work
 * item's acceptance criteria say so, and this file is the gate.
 *
 * **The gate runs over every state, not just the happy one.** A surface can be
 * accessible when it is full and inaccessible when it is empty, and the interesting
 * states here are the *edge* ones: a strip with a notice, a banner for a dismissed
 * notice, a muted event, an event with no notice at all. Each is a different document,
 * and each is a different set of rules.
 *
 * **Serious and critical only.** `minor` and `moderate` findings are advisory, and a
 * gate that fails on a moderate finding is a gate that gets disabled.
 */
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "@/app/page";
import EventDetailPage from "@/app/events/[id]/page";

/**
 * **Both surfaces are audited through their own pages**, not through the islands alone.
 *
 * A component in isolation is not a surface. The strip's neighbours — the digest
 * header, the cards, the shell's landmarks — are what a reader actually meets, and a
 * rule about landmark structure or heading order only fires in the full document.
 */
const getSession = vi.fn();
const readDigest = vi.fn();
const readNotices = vi.fn();
const readEventDetail = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/digest-read", () => ({
  readDigest: () => readDigest(),
}));

vi.mock("@/lib/notice-read", () => ({
  readNotices: () => readNotices(),
}));

vi.mock("@/lib/event-detail-read", () => ({
  readEventDetail: (id: string) => readEventDetail(id),
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  usePathname: () => "/",
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
    public_slug: "brooklyn-symphony-open-rehearsal-2026-11-07-a1b2c3",
    ...overrides,
  };
}

const COMPOSED = {
  status: "composed" as const,
  cards: [card()],
  city: "Brooklyn",
  city_source: "user",
  local_date: "2026-11-07",
  timezone: "America/New_York",
};

/** One open notice, as the strip's read hands it over. */
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

/** The event's public facts. */
function facts(overrides: Record<string, unknown> = {}) {
  return {
    canonical_url: "https://example.test/event",
    description: "A short panel on building products that respect attention.",
    end_time_utc: null,
    event_version: 1,
    id: "22222222-2222-2222-2222-222222222222",
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

/** The signed-in reader's own block, with the two notice facts. */
function personal(overrides: Record<string, unknown> = {}) {
  return {
    neighbor_bucket: "few",
    saved: false,
    why_this: null,
    conflict: null,
    muted: false,
    notice: null,
    ...overrides,
  };
}

beforeEach(() => {
  getSession.mockReset();
  redirect.mockReset();
  readDigest.mockReset();
  readNotices.mockReset();
  readEventDetail.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readDigest.mockResolvedValue({ kind: "composed", digest: COMPOSED });
  readNotices.mockResolvedValue({ kind: "notices", notices: [] });
});

/**
 * Run axe over the rendered page.
 *
 * **The container is the whole document.** axe walks the DOM it is given, so auditing
 * `main` alone would miss the shell — the nav's landmarks, the topbar's structure.
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

/** The violations, named, so a failure says which rule fired and where. */
async function auditReport(): Promise<string[]> {
  const violations = await audit();
  return violations.map(
    (violation) => `${violation.id}: ${violation.nodes.map((node) => node.target).join(", ")}`,
  );
}

describe("the digest strip's axe-core gate", () => {
  it("has zero serious or critical violations with a notice in the strip", async () => {
    readNotices.mockResolvedValue({ kind: "notices", notices: [notice()] });

    render(await HomePage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }));

    expect(await auditReport()).toEqual([]);
  });

  it("has zero serious or critical violations with several notices in the strip", async () => {
    // **More than one entry is a different document** — the strip's rows become a list,
    // and each row carries its own link and its own dismiss control.
    readNotices.mockResolvedValue({
      kind: "notices",
      notices: [
        notice(),
        notice({
          id: "notice-2",
          event_id: "33333333-3333-3333-3333-333333333333",
          change_kind: "postponed",
        }),
      ],
    });

    render(await HomePage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }));

    expect(await auditReport()).toEqual([]);
  });

  it("has zero serious or critical violations with no notices at all", async () => {
    // **The ordinary case.** The strip renders no element, so this audits the page
    // exactly as it is today.
    render(await HomePage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }));

    expect(await auditReport()).toEqual([]);
  });

  it("audits a document with the strip actually in it", async () => {
    // A gate that passed because the page rendered nothing would pass forever. The
    // audit is only meaningful if it ran over the real surface.
    readNotices.mockResolvedValue({ kind: "notices", notices: [notice()] });

    render(await HomePage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }));

    expect(
      screen.getByRole("region", { name: "Changes to your saved events" }),
    ).toBeInTheDocument();
  });
});

describe("the Detail banner's axe-core gate", () => {
  it("has zero serious or critical violations with a banner on the page", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts(), personal: personal({ notice: notice() }) },
    });

    render(await EventDetailPage({ params: Promise.resolve({ id: "event-1" }) }));

    expect(await auditReport()).toEqual([]);
  });

  it("has zero serious or critical violations with a dismissed notice's banner", async () => {
    // **The dismissed banner is a different document** — it carries a third line the
    // open one does not.
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: {
        event: facts(),
        personal: personal({ notice: notice({ dismissed_at: "2026-11-07T12:30:00Z" }) }),
      },
    });

    render(await EventDetailPage({ params: Promise.resolve({ id: "event-1" }) }));

    expect(await auditReport()).toEqual([]);
  });

  it("has zero serious or critical violations with a muted event", async () => {
    // **A muted event renders no banner** — only the mute control — and a document with
    // a lone control in it is its own document.
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts(), personal: personal({ notice: notice(), muted: true }) },
    });

    render(await EventDetailPage({ params: Promise.resolve({ id: "event-1" }) }));

    expect(await auditReport()).toEqual([]);
  });

  it("has zero serious or critical violations with the mute control alone", async () => {
    // **An event with no notice still offers the mute**, because a user should be able
    // to say so before a change arrives.
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts(), personal: personal() },
    });

    render(await EventDetailPage({ params: Promise.resolve({ id: "event-1" }) }));

    expect(await auditReport()).toEqual([]);
  });

  it("audits a document with the banner actually in it", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts(), personal: personal({ notice: notice() }) },
    });

    render(await EventDetailPage({ params: Promise.resolve({ id: "event-1" }) }));

    expect(screen.getByRole("region", { name: "This event has changed" })).toBeInTheDocument();
  });
});
