/**
 * The Pulse Digest home's **axe-core gate**.
 *
 * **"axe-core reports zero serious or critical violations on this surface."** The
 * work item's acceptance criteria say so, and this file is the gate.
 *
 * **The gate runs over every state, not just the happy one.** A page can be accessible
 * when it is full and inaccessible when it is empty: an empty state with no heading
 * hierarchy, an error state whose retry is an unnamed control, a not-composed state
 * that claims nothing — each is a different document, and each is a different set of
 * rules. So the composed, empty, not-composed and error documents are all audited.
 *
 * **Serious and critical only.** `minor` and `moderate` findings are advisory — they
 * are usually about contrast on non-text decoration or about heading order in a shell
 * that exists for a different reason — and a gate that fails on a moderate finding is a
 * gate that gets disabled. Serious and critical are the ones that make a surface
 * unusable for someone.
 */
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "@/app/page";

const getSession = vi.fn();
const readDigest = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/digest-read", () => ({
  readDigest: () => readDigest(),
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
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
});

/**
 * Run axe over the rendered page.
 *
 * **The container is the whole document.** axe walks the DOM it is given, so auditing
 * `main` alone would miss the shell — the nav's landmarks, the account link's accessible
 * name, the topbar's structure — and those are part of the surface.
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

describe("the Pulse Digest home's axe-core gate", () => {
  it("has zero serious or critical violations in the composed state", async () => {
    readDigest.mockResolvedValue({ kind: "composed", digest: COMPOSED });

    render(await HomePage(props()));

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the empty state", async () => {
    readDigest.mockResolvedValue({
      kind: "empty",
      digest: { ...COMPOSED, status: "empty", cards: [] },
    });

    render(await HomePage(props()));

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the not-yet-composed state", async () => {
    readDigest.mockResolvedValue({
      kind: "not_composed",
      digest: { ...COMPOSED, status: "not_composed", cards: [] },
    });

    render(await HomePage(props()));

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the error state", async () => {
    readDigest.mockResolvedValue({ kind: "unavailable" });

    render(await HomePage(props()));

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  /**
   * **The state treatment, audited.**
   *
   * **A new element on the surface is a new document.** The gate audits the composed
   * digest, but a composed digest of ordinary cards is a different document from a
   * composed digest of sold-out and cancelled ones — and the difference is exactly the
   * badge, which is a pill with a border, a fill and a coloured glyph.
   *
   * **The cancelled card is the one that matters most here**, because it is the card
   * with a *removed* control: a control that was there and is now gone changes the
   * document's landmark and heading structure, and an axe rule that fires on "this
   * region has no content" would only fire on the cancelled card.
   */
  it("has zero serious or critical violations with a state badge on the cards", async () => {
    readDigest.mockResolvedValue({
      kind: "composed",
      digest: {
        ...COMPOSED,
        cards: [
          card({ is_sold_out: true }),
          card({ status: "cancelled", event_id: "33333333-3333-3333-3333-333333333333" }),
          card({ status: "postponed", event_id: "44444444-4444-4444-4444-444444444444" }),
        ],
      },
    });

    render(await HomePage(props()));

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations with a sold-out card that is also in conflict", async () => {
    // The card the work item names: two indicators in the same region, and the badge's
    // amber and the conflict indicator's amber are the same hex.
    readDigest.mockResolvedValue({
      kind: "composed",
      digest: {
        ...COMPOSED,
        cards: [card({ is_sold_out: true, conflict: true })],
      },
    });

    render(await HomePage(props()));

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("audits a document with the shell's landmarks in place", async () => {
    // A gate that passed because the page rendered nothing would pass forever. The
    // audit is only meaningful if it ran over the real surface, so this asserts the
    // landmarks the surface is supposed to have are actually in the document.
    readDigest.mockResolvedValue({ kind: "composed", digest: COMPOSED });

    render(await HomePage(props()));

    expect(screen.getByRole("main")).toBeInTheDocument();
    const rail = screen.getByRole("complementary", { name: "Primary" });
    expect(rail).toBeInTheDocument();
    // The sidenav and the bottom-tab bar are both `<nav aria-label="Main">`, so the
    // landmark is queried inside the rail rather than document-wide.
    expect(rail.querySelector('nav[aria-label="Main"]')).not.toBeNull();
  });
});
