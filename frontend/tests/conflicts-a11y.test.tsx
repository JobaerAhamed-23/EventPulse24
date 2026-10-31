import { cleanup, render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ConflictsPage from "@/app/conflicts/page";
import { ConflictsSkeleton } from "@/components/conflicts/conflicts-states";

/**
 * `/conflicts` — the Conflict Review screen's **axe-core gate**.
 *
 * **"axe-core reports zero serious or critical violations on this surface."** The work
 * item's acceptance criteria say so, and this file is the gate.
 *
 * **The gate runs over every state.** A page can be accessible when it is full and
 * inaccessible when it is empty: a pair with two unnamed buttons, a failure whose retry
 * is an unnamed link, a resolved row that is a wall of unlabelled colour — each is a
 * different document, and each is a different set of rules. So the populated page, the
 * quiet page, the failure and the skeleton are all audited.
 *
 * **Serious and critical only.** `minor` and `moderate` findings are advisory, and a
 * gate that fails on a moderate finding is a gate that gets disabled.
 */

const getSession = vi.fn();
const readConflicts = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/conflict-list-read", () => ({
  readConflicts: () => readConflicts(),
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  usePathname: () => "/conflicts",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  onboarding: { completed: true, current_step: null },
};

function personalSide(overrides: Record<string, unknown> = {}) {
  return {
    available: true,
    end_time_utc: null,
    id: "11111111-1111-1111-1111-111111111111",
    kind: "personal_event",
    name: "Work standup",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-09-08T13:00:00Z",
    ...overrides,
  };
}

function savedSide(overrides: Record<string, unknown> = {}) {
  return {
    available: true,
    end_time_utc: null,
    id: "22222222-2222-2222-2222-222222222222",
    kind: "saved_event",
    name: "Designers coffee chat",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-09-08T13:15:00Z",
    ...overrides,
  };
}

function activePair() {
  return {
    actions: ["keep_both", "edit_new", "skip_public"],
    kind: "time",
    left: personalSide(),
    pair_id: "44444444-4444-4444-4444-444444444444",
    right: savedSide(),
    status: "active",
  };
}

function resolvedPair() {
  return {
    actions: [],
    kind: "time",
    left: personalSide(),
    pair_id: "55555555-5555-5555-5555-555555555555",
    resolution: "skip_public",
    resolved_at: "2026-09-11T23:00:00Z",
    right: savedSide(),
    status: "resolved",
  };
}

beforeEach(() => {
  getSession.mockReset();
  readConflicts.mockReset();
  redirect.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readConflicts.mockResolvedValue({
    kind: "pairs",
    pairs: { active: [activePair()], resolved: [resolvedPair()] },
  });
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

describe("the Conflict Review's axe-core gate", () => {
  it("has zero serious or critical violations in the populated state", async () => {
    render(await ConflictsPage());

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the quiet state", async () => {
    readConflicts.mockResolvedValue({ kind: "pairs", pairs: { active: [], resolved: [] } });

    render(await ConflictsPage());

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the error state", async () => {
    readConflicts.mockResolvedValue({ kind: "unavailable" });

    render(await ConflictsPage());

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the skeleton", async () => {
    render(<ConflictsSkeleton />);

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("audits a document with the shell's landmarks in place", async () => {
    // A gate that passed because the page rendered nothing would pass forever. The
    // audit is only meaningful if it ran over the real surface.
    render(await ConflictsPage());

    expect(screen.getByRole("main")).toBeInTheDocument();
    const rail = screen.getByRole("complementary", { name: "Primary" });
    expect(rail).toBeInTheDocument();
    expect(rail.querySelector('nav[aria-label="Main"]')).not.toBeNull();
  });
});

describe("the Conflict Review's touch targets", () => {
  it("gives every action a target of at least 44px", async () => {
    render(await ConflictsPage());

    // The AC says "≥44px targets", and the action buttons are the page's own
    // controls. jsdom does no layout, so the check is on the class that carries the
    // height: `py-3` on a `meta-md` line is the smallest that reaches 44px.
    //
    // **The check is scoped to the page's own buttons.** The shell's nav buttons are
    // the shell's business — they were sized before this page existed, and they are
    // audited by their own surface's gate.
    const group = screen.getByRole("group", { name: /Choices for the conflict/ });
    const buttons = within(group).getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      expect(button.className).toMatch(/py-3/);
    }
  });
});
