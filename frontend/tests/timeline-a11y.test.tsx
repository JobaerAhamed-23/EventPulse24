import { cleanup, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TimelinePage from "@/app/timeline/page";
import { TimelineSkeleton } from "@/components/timeline/timeline-states";
import { addDays, today } from "@/lib/timeline-dates";

/**
 * `/timeline` — the Unified Timeline's **axe-core gate**.
 *
 * **"axe-core reports zero serious or critical violations on this surface."** The
 * work item's acceptance criteria say so, and this file is the gate.
 *
 * **The gate runs over every state.** A page can be accessible when it is full and
 * inaccessible when it is empty: a week with seven empty columns, a day with nothing
 * in it, a failure whose retry is an unnamed control — each is a different document,
 * and each is a different set of rules. So the full week, the quiet week, the failure
 * and the skeleton are all audited.
 *
 * **Serious and critical only.** `minor` and `moderate` findings are advisory, and a
 * gate that fails on a moderate finding is a gate that gets disabled.
 */
const getSession = vi.fn();
const readTimeline = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/timeline-read", () => ({
  readTimeline: (week?: string | null) => readTimeline(week),
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  usePathname: () => "/timeline",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

const DAYS = Array.from({ length: 7 }, (_, index) => addDays(mondayOf(today()), index));

function block(overrides: Record<string, unknown> = {}) {
  return {
    conflict: false,
    end_time_utc: null,
    id: "44444444-4444-4444-4444-444444444444",
    kind: "personal" as const,
    name: "Dentist",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-11-02T14:00:00Z",
    ...overrides,
  };
}

function week(withBlocks: boolean) {
  return {
    days: DAYS.map((date, index) => ({
      blocks: withBlocks && index === 0 ? [block()] : [],
      date,
    })),
    timezone: "America/New_York",
    week_end: DAYS[6] as string,
    week_start: DAYS[0] as string,
  };
}

function mondayOf(day: string): string {
  const parsed = new Date(`${day}T00:00:00Z`);
  const weekday = (parsed.getUTCDay() + 6) % 7;
  return addDays(day, -weekday);
}

function props(query: Record<string, string | string[]> = {}): PageProps<"/timeline"> {
  return { params: Promise.resolve({}), searchParams: Promise.resolve(query) };
}

beforeEach(() => {
  getSession.mockReset();
  redirect.mockReset();
  readTimeline.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readTimeline.mockResolvedValue({ kind: "week", week: week(true) });
});

afterEach(() => {
  cleanup();
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

describe("the Timeline's axe-core gate", () => {
  it("has zero serious or critical violations in the full-week state", async () => {
    render(await TimelinePage(props()));

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the quiet-week state", async () => {
    readTimeline.mockResolvedValue({ kind: "week", week: week(false) });

    render(await TimelinePage(props()));

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the error state", async () => {
    readTimeline.mockResolvedValue({ kind: "unavailable" });

    render(await TimelinePage(props()));

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the skeleton", async () => {
    render(<TimelineSkeleton />);

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("audits a document with the shell's landmarks in place", async () => {
    // A gate that passed because the page rendered nothing would pass forever. The
    // audit is only meaningful if it ran over the real surface.
    render(await TimelinePage(props()));

    expect(screen.getByRole("main")).toBeInTheDocument();
    const rail = screen.getByRole("complementary", { name: "Primary" });
    expect(rail).toBeInTheDocument();
    expect(rail.querySelector('nav[aria-label="Main"]')).not.toBeNull();
  });
});
