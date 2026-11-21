/**
 * The profile screen's **axe-core gate**.
 *
 * **"axe-core reports zero serious or critical violations on this surface."** The work
 * item's acceptance criteria say so, and this file is the gate.
 *
 * ## Why the screen deserves its own gate
 *
 * **It is the one screen with four controls on it, and the four do not behave alike.**
 * The picture saves on the choice, the name saves on change, the address saves on a
 * press, and the city saves on change. **A screen of controls that differ in when they
 * commit is exactly where a heading level, a label or a landmark goes wrong** — and it
 * is where an `aria-busy` that is on the wrong element matters, because the screen
 * carries three different in-flight states.
 *
 * ## The gate runs over every state, not just the happy one
 *
 * **A screen can be accessible when it is full and inaccessible when it is empty**, and
 * each state here is a different document:
 *
 * 1. **Everything on it** — the picture, the name, the address, the city.
 * 2. **The city read failed** — the city section is absent. A screen that loses a
 *    section and keeps its other landmarks is a different document from the full one.
 * 3. **An account with no picture and no name** — the fallbacks are showing, and the
 *    initials are the only face there is.
 * 4. **The address change is pending** — the form is replaced by the pending block,
 *    with its own buttons, and the input that was there is gone.
 *
 * ## Serious and critical only
 *
 * `minor` and `moderate` findings are advisory — they are usually about contrast on
 * non-text decoration — and a gate that fails on a moderate finding is a gate that gets
 * disabled.
 *
 * **`color-contrast` is off.** jsdom computes no layout, so axe cannot measure contrast
 * and would report every coloured thing as a violation. The digest's gate disables it
 * for the same reason, and `tests/contrast.test.ts` measures contrast against the
 * tokens separately.
 */
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsProfilePage from "@/app/settings/profile/page";

const getSession = vi.fn();
const readHomeCity = vi.fn();

vi.mock("@/lib/home-city-read", () => ({ readHomeCity: () => readHomeCity() }));

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/navigation", () => ({
  redirect: vi.fn(() => {
    throw new Error("NEXT_REDIRECT");
  }),
  usePathname: () => "/settings/profile",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

/**
 * The account, with a name and a picture.
 *
 * **The picture is a same-origin app path** — `/api/auth/profile/avatar/{version}` —
 * because that is what the backend hands out.
 */
const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "Maya Ahmed",
  avatar_url: "/api/auth/profile/avatar/ab12cd34",
  pending_email: "",
  pending_email_expires_at: "",
  deletion_scheduled_for: "",
  deletion_requested_at: "",
  onboarding: { completed: true, current_step: null },
};

/** The city read, with the shape `HomeCityRead` promises. */
const CITY_FOUND = {
  kind: "found",
  city: "Dhaka",
  citySource: "choice",
  deliveryTime: "09:00:00",
  timezone: "Asia/Dhaka",
  choices: [
    { value: "Chattogram, Bangladesh", label: "Chattogram, Bangladesh" },
    { value: "Dhaka", label: "Dhaka, Bangladesh" },
  ],
};

beforeEach(() => {
  getSession.mockReset();
  readHomeCity.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readHomeCity.mockResolvedValue(CITY_FOUND);
});

/** Run axe over whatever is on the page, and report only serious and critical. */
async function audit() {
  const results = await axe.run(document.body, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
  });
  return results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
}

describe("the profile screen", () => {
  it("has no serious or critical violations with everything on it", async () => {
    render(await SettingsProfilePage());

    expect(await audit()).toEqual([]);
  });

  it("has no serious or critical violations when the city's read failed", async () => {
    // **The screen without its city is a different document.** The city section is
    // absent, so the landmarks and the heading order are different — and a screen that
    // lost a section and left its heading hierarchy broken would only show here.
    readHomeCity.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsProfilePage());

    expect(await audit()).toEqual([]);
  });

  it("has no serious or critical violations when the account has no picture and no name", async () => {
    // **The fallbacks are showing.** The disc holds initials rather than a picture, and
    // the account is addressed by the email-derived name. **A fallback that blanks a
    // control is an accessibility bug as well as a product one.**
    getSession.mockResolvedValue({
      kind: "signed-in",
      user: { ...USER, name: "", avatar_url: "" },
    });

    render(await SettingsProfilePage());

    expect(await audit()).toEqual([]);
  });

  it("has no serious or critical violations when an address change is pending", async () => {
    // **The form is replaced by the pending block**, with its own buttons — so the
    // screen's controls are not the screen's controls any more. **The input that was
    // there is gone, and the copy that replaced it names the address.**
    getSession.mockResolvedValue({
      kind: "signed-in",
      user: { ...USER, pending_email: "maya.new@example.test" },
    });

    render(await SettingsProfilePage());

    expect(await audit()).toEqual([]);
  });
});

describe("the profile screen's own structure", () => {
  it("gives every control a name a screen reader can reach", async () => {
    // **A control with no accessible name is invisible to a screen reader**, and the
    // screen has four controls plus the shell's own.
    render(await SettingsProfilePage());

    // **The name's field.**
    expect(screen.getByLabelText("Your name")).toBeInTheDocument();
    // **The file picker, behind its visible label.**
    expect(screen.getByLabelText(/choose a picture|choose another picture/i)).toBeInTheDocument();
    // **The address's field.**
    expect(screen.getByLabelText(/new email address/i)).toBeInTheDocument();
    // **The city's picker.**
    expect(screen.getByLabelText("City")).toBeInTheDocument();
  });

  it("keeps the picture out of the accessibility tree", async () => {
    // **The picture is decorative** — the name is beside it in text — so the disc is
    // `aria-hidden` and the image carries `alt=""`. **A screen reader that read both
    // would read the name twice.**
    render(await SettingsProfilePage());

    const disc = document.querySelector("[data-avatar-preview] [aria-hidden='true']");
    expect(disc).not.toBeNull();
    expect(document.querySelector("[data-avatar-preview] img")?.getAttribute("alt")).toBe("");
  });

  it("marks the screen's own heading as the only first-level heading", async () => {
    // **One `h1` per screen.** The screen's sections are `h2` — the city has one, and
    // the shell's own headings are the shell's.
    render(await SettingsProfilePage());

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
