import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ConflictsPage from "@/app/conflicts/page";

/**
 * `/conflicts` — the Conflict Review screen.
 *
 * **The page is a server component that renders what the server sent.** These tests
 * pin the things it is allowed to decide — the heading, the two sections, their counts,
 * and which sections are present — and the three states it draws: the quiet page, the
 * populated page, and the failure.
 *
 * **The counts are the server's.** "Active (n)" and "Resolved (n)" are the lengths of
 * the two lists the server sent, so the count can never disagree with what is under it.
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

const PERSONAL_ID = "11111111-1111-1111-1111-111111111111";
const SAVED_ID = "22222222-2222-2222-2222-222222222222";

function personalSide(overrides: Record<string, unknown> = {}) {
  return {
    available: true,
    end_time_utc: null,
    id: PERSONAL_ID,
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
    id: SAVED_ID,
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
  readConflicts.mockResolvedValue({ kind: "pairs", pairs: { active: [], resolved: [] } });
});

afterEach(() => {
  cleanup();
});

describe("the page's heading", () => {
  it("is the locked microcopy", async () => {
    render(await ConflictsPage());

    expect(
      screen.getByRole("heading", { level: 1, name: "These days overlap." }),
    ).toBeInTheDocument();
  });
});

describe("the two sections", () => {
  it("shows Active with its count", async () => {
    readConflicts.mockResolvedValue({
      kind: "pairs",
      pairs: { active: [activePair()], resolved: [] },
    });

    render(await ConflictsPage());

    // The count is a badge beside the word, so the heading's text is "Active1".
    expect(screen.getByRole("heading", { name: /Active/ })).toHaveTextContent("Active1");
  });

  it("shows Resolved with its count", async () => {
    readConflicts.mockResolvedValue({
      kind: "pairs",
      pairs: { active: [], resolved: [resolvedPair()] },
    });

    render(await ConflictsPage());

    expect(screen.getByRole("heading", { name: /Resolved/ })).toHaveTextContent("Resolved1");
  });

  it("omits Active when there are no active pairs but there are resolved ones", async () => {
    // EXPERIENCE.md: "For a user with resolved-but-no-active pairs, the Resolved
    // section renders; Active is absent."
    readConflicts.mockResolvedValue({
      kind: "pairs",
      pairs: { active: [], resolved: [resolvedPair()] },
    });

    render(await ConflictsPage());

    expect(screen.queryByRole("heading", { name: /Active/ })).toBeNull();
    expect(screen.getByRole("heading", { name: /Resolved/ })).toBeInTheDocument();
  });

  it("omits Resolved when there are no resolved pairs", async () => {
    readConflicts.mockResolvedValue({
      kind: "pairs",
      pairs: { active: [activePair()], resolved: [] },
    });

    render(await ConflictsPage());

    expect(screen.getByRole("heading", { name: /Active/ })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Resolved/ })).toBeNull();
  });

  it("shows both when there are both", async () => {
    readConflicts.mockResolvedValue({
      kind: "pairs",
      pairs: { active: [activePair()], resolved: [resolvedPair()] },
    });

    render(await ConflictsPage());

    expect(screen.getByRole("heading", { name: /Active/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Resolved/ })).toBeInTheDocument();
  });
});

describe("the quiet state", () => {
  it("says 'No overlaps.' when there is nothing at all", async () => {
    render(await ConflictsPage());

    expect(screen.getByText("No overlaps.")).toBeInTheDocument();
    expect(screen.getByText("Conflicts appear here as you save events.")).toBeInTheDocument();
  });

  it("offers no sections when there is nothing at all", async () => {
    render(await ConflictsPage());

    expect(screen.queryByRole("heading", { name: /Active/ })).toBeNull();
    expect(screen.queryByRole("heading", { name: /Resolved/ })).toBeNull();
  });
});

describe("the failure state", () => {
  it("says the read failed, and offers a retry", async () => {
    readConflicts.mockResolvedValue({ kind: "unavailable" });

    render(await ConflictsPage());

    expect(screen.getByText("Couldn't analyze conflicts. Try again.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/conflicts");
  });

  it("does not say 'No overlaps.' when the read failed", async () => {
    // A failed read must not be indistinguishable from an empty list.
    readConflicts.mockResolvedValue({ kind: "unavailable" });

    render(await ConflictsPage());

    expect(screen.queryByText("No overlaps.")).toBeNull();
  });

  it("says the read failed when the session could not be read", async () => {
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await ConflictsPage());

    expect(screen.getByText("Couldn't analyze conflicts. Try again.")).toBeInTheDocument();
  });
});

describe("the route's guards", () => {
  it("sends an anonymous visitor to the preview", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    render(await ConflictsPage());

    expect(redirect).toHaveBeenCalledWith("/preview");
  });

  it("sends a half-onboarded visitor to the onboarding", async () => {
    getSession.mockResolvedValue({
      kind: "signed-in",
      user: { ...USER, onboarding: { completed: false, current_step: "interests" } },
    });

    render(await ConflictsPage());

    expect(redirect).toHaveBeenCalledWith("/onboarding");
  });

  it("never reads the conflicts of a visitor it could not identify", async () => {
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await ConflictsPage());

    expect(readConflicts).not.toHaveBeenCalled();
  });
});

describe("the active pair", () => {
  it("shows both sides side by side", async () => {
    readConflicts.mockResolvedValue({
      kind: "pairs",
      pairs: { active: [activePair()], resolved: [] },
    });

    render(await ConflictsPage());

    const article = screen.getByRole("article");
    expect(within(article).getByText("Work standup")).toBeInTheDocument();
    expect(within(article).getByText("Designers coffee chat")).toBeInTheDocument();
    expect(within(article).getByText("Personal")).toBeInTheDocument();
    expect(within(article).getByText("Public event")).toBeInTheDocument();
  });
});
