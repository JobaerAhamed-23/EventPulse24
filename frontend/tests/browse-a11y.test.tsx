/**
 * The Browse surface's **axe-core gate**.
 *
 * **"axe-core reports zero serious or critical violations on this surface."** The
 * work item's acceptance criteria say so, and this file is the gate.
 *
 * **The gate runs over every state, not just the happy one.** A page can be accessible
 * when it is full and inaccessible when it is empty: an empty state with no heading
 * hierarchy, an error state whose retry is an unnamed control, a loading skeleton with
 * twelve boxes a screen reader has to read twice — each is a different document, and
 * each is a different set of rules. So the populated, empty and error documents and the
 * loading skeleton are all audited.
 *
 * **Serious and critical only.** `minor` and `moderate` findings are advisory — they
 * are usually about contrast on non-text decoration — and a gate that fails on a
 * moderate finding is a gate that gets disabled. Serious and critical are the ones
 * that make a surface unusable for someone.
 *
 * **`color-contrast` is off.** jsdom computes no layout, so axe cannot measure
 * contrast and would report every coloured thing as a violation. The digest's gate
 * disables it for the same reason, and `tests/contrast.test.ts` measures contrast
 * against the tokens separately.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BrowseLoading from "@/app/browse/loading";
import BrowsePage from "@/app/browse/page";

const getSession = vi.fn();
const readBrowse = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/browse-read", () => ({
  readBrowse: (...args: unknown[]) => readBrowse(...args),
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  usePathname: () => "/browse",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "reader@example.test",
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
      is_saved: true,
    }),
  ],
  city: "Brooklyn",
  city_missing: false,
  has_more: true,
  quota: { cap: 10, is_pro: false, resets_in_seconds: 86400, used: 3 },
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
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readBrowse.mockResolvedValue({ kind: "browse", browse: PAYLOAD });
});

/**
 * Run axe over the rendered page.
 *
 * **The container is the whole document.** axe walks the DOM it is given, so auditing
 * `main` alone would miss the shell — the navs' landmarks, the account link's accessible
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

/** The violations, as a readable one-line list, for a failure message. */
function describeViolations(violations: Awaited<ReturnType<typeof audit>>): string[] {
  return violations.map(
    (violation) => `${violation.id}: ${violation.nodes.map((n) => n.target).join(", ")}`,
  );
}

describe("the Browse surface's axe-core gate", () => {
  it("has zero serious or critical violations in the populated state", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(describeViolations(await audit())).toEqual([]);
  });

  /**
   * **The no-match state is a different document.**
   *
   * The grid is emptied and replaced by one quiet block: the section heads go, the
   * `<ul>`s go, and a `role="status"` region appears with a heading inside it. That is
   * a different heading hierarchy and a different landmark set from the populated
   * page's, and a `region` rule or a `list` rule can fire on a document that was clean
   * a keystroke earlier.
   */
  it("has zero serious or critical violations in the no-match state", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "quantum" } });

    // The state really is the no-match state, or the gate is auditing the wrong
    // document.
    expect(document.querySelector("[data-browse-search-empty]")).toBeTruthy();

    expect(describeViolations(await audit())).toEqual([]);
  });

  /**
   * **A filtered state with cards on it is a third document again.** The grid is
   * shorter, the count line and the hint line are present, and the input has a value
   * and a clear button beside it.
   */
  it("has zero serious or critical violations in the filtered state", async () => {
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "jazz" } });

    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(1);

    expect(describeViolations(await audit())).toEqual([]);
  });

  /**
   * **The quota wall is a different document.**
   *
   * **The Save button's label changes from a verb to a sentence**, the button becomes
   * disabled, and a `title` appears. A disabled button is removed from the tab order,
   * and a `title` becomes its accessible name's *description* — so the control a reader
   * reaches by keyboard is a different control from the one in the ordinary state.
   */
  it("has zero serious or critical violations when the quota is spent", async () => {
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: { ...PAYLOAD, quota: { cap: 1, is_pro: false, resets_in_seconds: 86400, used: 1 } },
    });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    // The state really is the wall, or the gate is auditing the wrong document.
    expect(screen.getAllByText("1 of 1 save used today").length).toBeGreaterThan(0);

    expect(describeViolations(await audit())).toEqual([]);
  });

  it("has zero serious or critical violations in the empty state", async () => {
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: { ...PAYLOAD, cards: [], total: 0, has_more: false },
    });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(describeViolations(await audit())).toEqual([]);
  });

  it("has zero serious or critical violations in the error state", async () => {
    readBrowse.mockResolvedValue({ kind: "unavailable" });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(describeViolations(await audit())).toEqual([]);
  });

  it("has zero serious or critical violations in the loading state", async () => {
    render(<BrowseLoading />);

    expect(describeViolations(await audit())).toEqual([]);
  });

  /**
   * **A must-know card, a saved card and a card with no source badge.**
   *
   * **A new element on the surface is a new document.** The stripe is a coloured band on
   * the card's edge, the "Saved" state adds a word to the card's accessible name, and a
   * card with no source badge has one fewer control in its trust row — and the trust row
   * is a row of buttons, so a card with a badge and a card without one are different
   * documents to an axe rule about focus order or about a control's accessible name.
   */
  it("has zero serious or critical violations with every card treatment on the surface", async () => {
    readBrowse.mockResolvedValue({
      kind: "browse",
      browse: {
        ...PAYLOAD,
        cards: [
          card({ stripe: "must_know", confidence: 5 }),
          card({ event_id: "33333333-3333-3333-3333-333333333333", is_saved: true }),
          card({
            event_id: "44444444-4444-4444-4444-444444444444",
            source_badge: "",
            tags: [],
          }),
          card({
            event_id: "55555555-5555-5555-5555-555555555555",
            status: "cancelled",
            tz_review_pending: true,
          }),
        ],
      },
    });

    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    expect(describeViolations(await audit())).toEqual([]);
  });

  /**
   * **The gate must be able to fail.**
   *
   * **A repaired test that cannot fail is a test that was not repaired.** The `list` axe
   * rule is *serious*, and it is the rule Amendment A-12's "one `<ul>` per section"
   * structure exists to satisfy — a section head inside the `<ul>` turns the list into
   * a set of ungrouped text and loses the count of the city's events with it.
   *
   * **The probe is deliberately the mistake the rule is about.** A heading is moved
   * inside the first section's `<ul>`, exactly as a well-meaning edit would, and the
   * gate is required to notice. If the gate does not fire here, the gate is not
   * watching the thing it was written to watch, and every "zero violations" above is
   * worth nothing.
   */
  it("fires on a section head placed inside the list", async () => {
    // The probe is applied by patching the rendered DOM: the heading moves inside the
    // `<ul>`, which is what the mistake looks like in the DOM.
    render(await BrowsePage({ searchParams: Promise.resolve({}) }));

    const list = document.querySelector("section[data-browse-section] ul");
    const heading = document.querySelector("section[data-browse-section] h2");
    expect(list).toBeTruthy();
    expect(heading).toBeTruthy();

    list?.appendChild(heading as Node);

    const violations = await audit();
    expect(violations.map((violation) => violation.id)).toContain("list");
  });
});
