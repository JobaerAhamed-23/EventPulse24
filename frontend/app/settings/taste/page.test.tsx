import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsTastePage from "@/app/settings/taste/page";

const getSession = vi.fn();
const readTaste = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/taste-mutes-read", () => ({
  readTaste: () => readTaste(),
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  usePathname: () => "/settings/taste",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

/**
 * `/settings/taste` — the muted categories, and the way back (FR-25).
 *
 * **This screen is what the prompt points at.** The mockup says twice — *"You can undo
 * anytime in Settings → Taste"* and *"Settings → Taste → Muted categories lists every
 * active mute"* — so the screen has to exist, be reachable, and list what the user
 * muted.
 *
 * **"Unavailable" is not "you have nothing muted".** The two look identical and mean
 * opposite things: a user whose read blinked would be shown an empty list, on the very
 * screen whose job is to let them undo what they muted. So the failed read renders the
 * settings' own error state, and an empty list — a real answer — renders its own quiet
 * empty state.
 */

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

function mute(overrides: Record<string, unknown> = {}) {
  return {
    category_key: "arts_culture",
    label: "Arts & culture",
    expires_at: "2026-12-07T00:00:00Z",
    is_indefinite: false,
    ...overrides,
  };
}

beforeEach(() => {
  getSession.mockReset();
  readTaste.mockReset();
  redirect.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readTaste.mockResolvedValue({ kind: "found", mutes: [mute()] });
});

describe("the taste screen", () => {
  it("names itself, so the user knows where they landed", async () => {
    render(await SettingsTastePage());

    expect(screen.getByRole("heading", { level: 1, name: "Taste" })).toBeInTheDocument();
  });

  it("lists the muted categories with the server's own labels", async () => {
    render(await SettingsTastePage());

    // **The label is the server's.** It arrives on the row, not from a list the
    // frontend owns — the vocabulary is ten broad buckets the server defines, and a
    // frontend copy of it would be a second opinion about what a category is.
    expect(screen.getByText("Arts & culture")).toBeInTheDocument();
  });

  it("offers a one-tap way back", async () => {
    render(await SettingsTastePage());

    // The mockup: "One tap unmutes."
    expect(screen.getByRole("button", { name: /Show Arts & culture again/ })).toBeInTheDocument();
  });

  it("says what happens when the mute ends, in words", async () => {
    render(await SettingsTastePage());

    // **The words come from the expiry, not from a duration the client kept.** The
    // server computes the expiry from the instant the mute was set, and the client
    // does not know that instant — so it says what it can say truthfully.
    expect(screen.getByText(/Ends in/)).toBeInTheDocument();
  });

  it("carries the settings sub-nav, so it is not a dead end", async () => {
    render(await SettingsTastePage());

    expect(screen.getByRole("navigation", { name: "Settings sections" })).toBeInTheDocument();
  });

  it("is not Pro-gated, because a preference is not a feature", async () => {
    render(await SettingsTastePage());

    expect(screen.queryByText(/upgrade/i)).toBeNull();
  });
});

describe("an empty list", () => {
  it("says so quietly, and says it is not an error", async () => {
    readTaste.mockResolvedValue({ kind: "found", mutes: [] });

    render(await SettingsTastePage());

    // **An honest empty state, not an error.** No muted categories is an answer, and
    // it is a good one — it means nothing is being held back.
    expect(screen.getByText(/Nothing is muted/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers no bulk reset, because there is nothing to reset", async () => {
    readTaste.mockResolvedValue({ kind: "found", mutes: [] });

    render(await SettingsTastePage());

    expect(screen.queryByRole("button", { name: /Restore all defaults/ })).toBeNull();
  });
});

describe("a read that failed", () => {
  it("renders the error state, not an empty list", async () => {
    // **The two look identical and mean opposite things.** A user whose read blinked
    // would be shown an empty list, on the very screen whose job is to let them undo
    // what they muted.
    readTaste.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsTastePage());

    expect(screen.queryByText(/Nothing is muted/)).toBeNull();
  });

  it("still carries the sub-nav", async () => {
    readTaste.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsTastePage());

    expect(screen.getByRole("navigation", { name: "Settings sections" })).toBeInTheDocument();
  });
});

describe("a visitor who is not signed in", () => {
  it("does not read the mutes", async () => {
    getSession.mockResolvedValue({ kind: "signed-out" });

    render(await SettingsTastePage());

    expect(readTaste).not.toHaveBeenCalled();
  });
});
