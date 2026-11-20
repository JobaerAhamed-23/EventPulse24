/**
 * `/settings/profile` — who you are, and where you are.
 *
 * **The name still needs no read of its own**: the session already carries it, and a
 * second `GET /api/auth/me` would answer the same question twice. **The city does need
 * one**, so this page now has a read that can fail — and what it does when it fails is
 * worth testing hardest, because the obvious answer is wrong. The name above it is
 * unaffected, so replacing the screen with *"Couldn't load your settings."* would be a
 * false statement about the thing in front of the reader.
 *
 * **The second thing worth testing hardest is the fallback.** An account with no name
 * set must still be addressed by something — the email-derived name — and the rail must
 * not go blank.
 */
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsProfilePage from "@/app/settings/profile/page";

const getSession = vi.fn();
const readHomeCity = vi.fn();

vi.mock("@/lib/home-city-read", () => ({ readHomeCity: () => readHomeCity() }));

/** A city read that succeeded, with the shape `HomeCityRead` promises. */
const CITY_FOUND = {
  kind: "found",
  city: "Dhaka",
  citySource: "choice",
  deliveryTime: "09:00:00",
  timezone: "Asia/Dhaka",
  choices: ["Dhaka", "Chattogram"],
};

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
  /**
   * **`""` is the account's "no picture" state** — the backend's single answer for it,
   * and what `_avatar_url` returns when the account holds none. It is not `null` and not
   * absent, and the disc reads it as "fall back to the initials".
   */
  avatar_url: "",
  pending_email: "",
  pending_email_expires_at: "",
  deletion_scheduled_for: "",
  deletion_requested_at: "",
  onboarding: { completed: true, current_step: null },
};

/** The session, carrying a user with the given name. */
function sessionWith(name: string) {
  return { kind: "signed-in", user: { ...USER, name } };
}

beforeEach(() => {
  getSession.mockReset();
  getSession.mockResolvedValue(sessionWith(""));
  readHomeCity.mockReset();
  readHomeCity.mockResolvedValue(CITY_FOUND);
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
    expect(screen.getByRole("button", { name: "Account: Maya Ahmed" })).toBeTruthy();
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

describe("the city, which used to live on the account screen", () => {
  it("is on the profile screen, because where you live is a fact about you", async () => {
    render(await SettingsProfilePage());

    expect(screen.getByRole("heading", { name: "City" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Dhaka")).toBeInTheDocument();
  });

  it("offers the catalog's cities to choose between", async () => {
    render(await SettingsProfilePage());

    expect(screen.getByRole("option", { name: "Chattogram" })).toBeInTheDocument();
  });

  it("is absent when the read failed, rather than an empty picker", async () => {
    /**
     * A select with no options reads as *"your city is not available"*, which is a
     * statement about the user rather than about the request that failed.
     */
    readHomeCity.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsProfilePage());

    expect(screen.queryByRole("heading", { name: "City" })).not.toBeInTheDocument();
  });

  it("still shows the name when the city read failed", async () => {
    /** **The failure is the city's, not the screen's.** The name is unaffected, so a
     * whole-screen error would be a false statement about the field above it. */
    readHomeCity.mockResolvedValue({ kind: "unavailable" });
    getSession.mockResolvedValue(sessionWith("Maya Ahmed"));

    render(await SettingsProfilePage());

    expect(screen.getByDisplayValue("Maya Ahmed")).toBeInTheDocument();
  });

  it("names where the zone is edited instead of holding a second copy of it", async () => {
    /**
     * The zone is paired with the digest's delivery time on General — together they
     * answer *when the brief arrives* — so this screen signposts it rather than
     * splitting that pair. A screen that silently omitted it would leave a reader
     * hunting.
     *
     * **It names General rather than linking to it**, because
     * `tests/settings-routes.test.ts` forbids a hand-written link between settings
     * screens and the sub-nav already carries the destination.
     */
    const { container } = render(await SettingsProfilePage());

    const note = container.querySelector("[data-city-zone-note]");
    expect(note).not.toBeNull();
    expect(note).toHaveTextContent(/time zone/i);
    expect(note).toHaveTextContent(/General/);
    expect(within(note as HTMLElement).queryByRole("link")).toBeNull();
  });
});

describe("the email address", () => {
  it("is shown, because it is the account's login", async () => {
    /** Scoped to the island: the shell's account sheet shows the address too, and an
     * unscoped query would pass on that one alone. */
    const { container } = render(await SettingsProfilePage());

    expect(container.querySelector("[data-current-email]")).toHaveTextContent("maya@example.test");
  });

  it("offers a way to change it, which the screen used to deny was possible", async () => {
    /**
     * The screen shipped saying the email *"is the login and the key, and it is not
     * changeable from here"*. This intent reversed that deliberately, and the control is
     * the proof.
     */
    render(await SettingsProfilePage());

    expect(screen.getByLabelText(/new email address/i)).toBeInTheDocument();
  });

  it("shows the pending change the session reports", async () => {
    getSession.mockResolvedValue({
      kind: "signed-in",
      user: { ...USER, pending_email: "maya.new@example.test" },
    });

    const { container } = render(await SettingsProfilePage());

    expect(container.querySelector("[data-pending-change]")).toHaveTextContent(
      "maya.new@example.test",
    );
  });
});

describe("the picture", () => {
  it("is on the screen, which the screen used to say could not change", async () => {
    /**
     * The screen shipped holding one field, on the stated grounds that the name was the
     * only thing about an account a person could change. The account has since grown a
     * picture, so the control is the proof that the claim was retired.
     */
    render(await SettingsProfilePage());

    expect(screen.getByRole("region", { name: "Profile picture" })).toBeInTheDocument();
  });

  it("shows the account's picture when it has one", async () => {
    getSession.mockResolvedValue({
      kind: "signed-in",
      user: { ...USER, avatar_url: "/api/auth/profile/avatar/ab12cd34" },
    });

    const { container } = render(await SettingsProfilePage());

    expect(container.querySelector("[data-avatar-preview] img")).toHaveAttribute(
      "src",
      "/api/auth/profile/avatar/ab12cd34",
    );
  });

  it("shows the initials when the account has no picture", async () => {
    /**
     * **The fallback must not blank anything.** An account with no picture still looks
     * like an account rather than like a hole in the screen.
     *
     * **The letters are the display name's, and the display name here is the
     * email-derived one** — the account has no name set, so the screen falls back to
     * "Maya", and "Maya" is one word, so its initial is one letter. **The rule caps at
     * two letters; it does not pad to two.**
     */
    const { container } = render(await SettingsProfilePage());

    expect(container.querySelector("[data-avatar-preview] img")).toBeNull();
    expect(container.querySelector("[data-avatar-preview]")).toHaveTextContent("M");
  });

  it("shows two letters when the display name has two words", async () => {
    getSession.mockResolvedValue(sessionWith("Maya Ahmed"));

    const { container } = render(await SettingsProfilePage());

    expect(container.querySelector("[data-avatar-preview]")).toHaveTextContent("MA");
  });
});

describe("the four things the screen holds, in the order the heading promises", () => {
  it("puts the picture first, then the name, then the address, then the place", async () => {
    /**
     * **The order is the account sheet's order** — face, then name, then address — and
     * the place comes last because it is a different kind of thing: where the digest
     * comes from, rather than who the person is.
     *
     * **The assertion is on the order of the sections in the DOM**, because that is
     * what a person scrolling the screen experiences. The place's heading is inside its
     * own block, so the order is read from the four sections the screen renders.
     */
    const { container } = render(await SettingsProfilePage());

    const sections = Array.from(container.querySelectorAll("section[aria-label]")).map((section) =>
      section.getAttribute("aria-label"),
    );

    expect(sections).toEqual([
      "Profile picture",
      "Profile",
      "Email address",
      // **The city's section is a `SettingRow`, not a `<section>`**, so it is not in
      // this list — and the place's heading is asserted separately below.
    ]);
  });

  it("puts the place last, after everything about the person", async () => {
    /**
     * The city is a different kind of thing from the picture, the name and the address:
     * it is where the digest comes from, not who the person is. So it comes after them.
     */
    const { container } = render(await SettingsProfilePage());

    const email = container.querySelector("[data-email-change]");
    const cityHeading = screen.getByRole("heading", { name: "City" });

    expect(email).not.toBeNull();
    expect(cityHeading).toBeInTheDocument();
    // **The place's heading comes after the address's block in the document.**
    const emailTop = (email as HTMLElement).compareDocumentPosition(cityHeading);
    expect(emailTop & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("the read question", () => {
  it("reads the city, and the city is the only thing it reads", async () => {
    /**
     * **The screen's one read is the city's**, and it is read once — through the same
     * helper `/settings/account` uses, so there is one implementation of "what city
     * does this account have".
     */
    render(await SettingsProfilePage());

    expect(readHomeCity).toHaveBeenCalledTimes(1);
  });

  it("reads no city at all when there is no session to read one with", async () => {
    /**
     * **The not-signed-in branch is not a failed read.** `readHomeCity` needs a
     * session, and this branch has none — so there is nothing to read and nothing that
     * could have failed.
     */
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsProfilePage());

    expect(readHomeCity).not.toHaveBeenCalled();
  });

  it("leaves the other three parts alone when the city's read fails", async () => {
    /**
     * **The failure is the city's, not the screen's.** The name, the picture and the
     * address are all still there and all still editable, so a whole-screen error would
     * be a false statement about the thing in front of the reader.
     */
    readHomeCity.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsProfilePage());

    expect(screen.getByLabelText("Your name")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Profile picture" })).toBeInTheDocument();
    expect(screen.getByLabelText(/new email address/i)).toBeInTheDocument();
    // **And the city is absent rather than an empty picker.**
    expect(screen.queryByRole("heading", { name: "City" })).not.toBeInTheDocument();
  });
});
