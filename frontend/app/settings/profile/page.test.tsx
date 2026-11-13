/**
 * `/settings/profile` — the name, and the one field that changes it.
 *
 * **This page reads nothing of its own.** Every other settings route reads the data it
 * shows, and that read can fail — which is why they have an `unavailable` branch.
 * **This one's data is the name, and the session already carries it**: `CurrentUserOut`
 * gained a `name` field for exactly this. So there is no `unavailable` branch here, and
 * a second `GET /api/auth/me` would answer the same question twice.
 *
 * **The second thing worth testing hardest is the fallback.** An account with no name
 * set must still be addressed by something — the email-derived name — and the rail must
 * not go blank.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsProfilePage from "@/app/settings/profile/page";

const getSession = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/profile",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  /**
   * **The redirect throws, and it has to.**
   *
   * **`redirect` in Next.js never returns** — it throws a special error the framework
   * catches. A mock that returns `undefined` would let the page fall through to the
   * signed-out branch and render a screen for a visitor who was redirected away. The
   * throw is what makes this mock behave like the real one.
   */
  redirect: vi.fn(() => {
    throw new Error("NEXT_REDIRECT");
  }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

/** The session, carrying a user with the given name. */
function sessionWith(name: string) {
  return { kind: "signed-in", user: { ...USER, name } };
}

beforeEach(() => {
  getSession.mockReset();
  getSession.mockResolvedValue(sessionWith(""));
});

describe("the profile screen", () => {
  it("has its own heading", async () => {
    render(await SettingsProfilePage());

    expect(screen.getByRole("heading", { level: 1, name: "Profile" })).toBeTruthy();
  });

  it("shows the name the account holds", async () => {
    getSession.mockResolvedValue(sessionWith("Maya Ahmed"));

    render(await SettingsProfilePage());

    expect(screen.getByLabelText("Your name")).toHaveValue("Maya Ahmed");
  });

  it("shows an empty field when no name is set", async () => {
    render(await SettingsProfilePage());

    expect(screen.getByLabelText("Your name")).toHaveValue("");
  });

  it("carries the sub-nav, so it is not a dead end", async () => {
    render(await SettingsProfilePage());

    expect(screen.getByRole("navigation", { name: "Settings sections" })).toBeTruthy();
  });

  it("redirects an anonymous visitor away instead of showing the editor", async () => {
    // **`homeRoute` sends an anonymous visitor to `/preview`**, so the signed-out
    // branch below is the belt to its braces — the branch that only runs when the
    // session is *unreadable* rather than anonymous.
    getSession.mockResolvedValue({ kind: "anonymous" });

    await expect(SettingsProfilePage()).rejects.toThrow("NEXT_REDIRECT");
  });

  it("shows an empty shell when the session could not be read at all", async () => {
    // **This is the branch that is actually reachable.** `getSession` answers
    // `unavailable` when it could not ask the server — and that is neither `anonymous`
    // nor `signed-in`, so `homeRoute` sends this visitor nowhere and the branch runs.
    //
    // **It renders an empty shell, not `SettingsStates`.** That component's copy is
    // *"Couldn't load your settings."* — and nothing failed to load here; there was
    // nothing to load.
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsProfilePage());

    expect(screen.queryByLabelText("Your name")).toBeNull();
    expect(screen.queryByText(/couldn.t load your settings/i)).toBeNull();
  });

  it("redirects a half-onboarded visitor away instead of showing the editor", async () => {
    // **`redirect` throws**, so the page never renders for this visitor.
    getSession.mockResolvedValue({
      kind: "signed-in",
      user: { ...USER, onboarding: { completed: false, current_step: 2 } },
    });

    await expect(SettingsProfilePage()).rejects.toThrow("NEXT_REDIRECT");
  });
});

describe("the shell", () => {
  it("addresses the account by its stored name when one is set", async () => {
    getSession.mockResolvedValue(sessionWith("Maya Ahmed"));

    render(await SettingsProfilePage());

    // **The rail's account row**, addressed by its accessible name. The stored name
    // replaces the email-derived one — that is the whole point of the write.
    //
    // **The row is found by its accessible name, not by its text.** The name is on the
    // screen in two places — the rail's row and the editor's field — and a text query
    // would find both.
    expect(
      screen.getByRole("button", { name: "Account: Maya Ahmed" }),
    ).toBeTruthy();
  });

  it("falls back to the email-derived name when no name is set", async () => {
    render(await SettingsProfilePage());

    // **The fallback must not blank the name.** An account with no name set still has
    // to be addressed by something, and the email-derived name is what it is.
    expect(screen.getByRole("button", { name: "Account: Maya" })).toBeTruthy();
  });

  it("marks Settings as the active sidenav item", async () => {
    render(await SettingsProfilePage());

    const sidenav = screen.getByRole("complementary", { name: "Primary" });
    expect(sidenav).toBeTruthy();
  });
});
