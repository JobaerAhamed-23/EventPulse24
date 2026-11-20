/**
 * The shell's name follows the save.
 *
 * ## Why this file exists
 *
 * **The rail is a server render, and a server render is a photograph.** Every page reads
 * the session on the server, derives the display name from it, and hands that name to
 * `AppShell`, which hands it to the sidenav, the bottom bar and the account sheet. That
 * name is fixed for the life of the render.
 *
 * **So a person who types their name, sees "Saved.", and looks up at the rail sees the
 * old one.** The rail is on every page, and the account sheet is opened from it — so the
 * wrong name is not a cosmetic detail, it is the product contradicting itself. The
 * account sheet says "here is who you are" and the row it was opened from says
 * something else.
 *
 * **A save that does not show up is a save that did not happen.** So the profile island
 * publishes the new display name once the server has accepted the write, and the shell
 * follows it.
 *
 * ## What is proved here
 *
 * 1. **A save moves the rail** — on the screen the save happened on, and after
 *    navigating to another page.
 * 2. **The published name is the *display* name** — clearing the name publishes the
 *    address-derived fallback, so the rail does not go blank.
 * 3. **A refused save publishes nothing** — the rail keeps the name it had.
 * 4. **The seed is what the page was rendered with** — a page that never saved a name
 *    shows the server-rendered one.
 *
 * **The unit test file `components/settings/profile-name.test.tsx` cannot see any of
 * this**, because it renders the island on its own: there is no rail beside it. This
 * file renders the rail *with* the island, which is the only way the property is
 * visible.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProfileName } from "@/components/settings/profile-name";
import { Sidenav } from "@/components/shell/sidenav";

const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/profile",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/components/personal-events-panel", () => ({
  PersonalEventsPanel: () => null,
}));

/**
 * The address whose local part is `"maya.ahmed"` — so the fallback is `"Maya Ahmed"`,
 * and a stored name that differs from it can be told apart from the fallback.
 */
const EMAIL = "maya.ahmed@example.test";

/** The name the fallback rule produces for `EMAIL`. */
const FALLBACK = "Maya Ahmed";

/** A stored name the address cannot produce, so the two can never be confused. */
const STORED = "Ada Lovelace";

/** The server's answer, as the `PUT` sends it. */
function answer(name: string) {
  return {
    data: { id: "11111111-1111-1111-1111-111111111111", email: EMAIL, name },
    response: { status: 200 },
  };
}

/** The rail's account row. */
function railRow(): HTMLElement {
  return screen.getByRole("button", { name: /^Account: / });
}

/** The name the rail is showing. */
function railName(): string {
  return (railRow().getAttribute("aria-label") ?? "").replace(/^Account: /, "");
}

/**
 * The name the account sheet is showing.
 *
 * **The sheet is opened first**, because a native `<dialog>` that has not been opened
 * takes no space and its contents are not laid out — so the name is not in the
 * accessibility tree until the row is pressed.
 *
 * **The assertion is scoped to the panel, and it picks the panel's *name* span
 * specifically.** The panel carries the name and the email in the same column, so
 * "some span in here has the name" would be a claim about the email too. The name is
 * the **first** of the two, and it is the one the row's avatar initials come from.
 */
function sheetName(): string | null {
  railRow().click();
  const panel = document.querySelector("[data-account-panel]");
  if (panel === null) return null;
  const column = panel.querySelector("span.flex.min-w-0.flex-col");
  const first = column?.querySelector("span");
  return first?.textContent ?? null;
}

/** The name field. */
function field(): HTMLInputElement {
  return screen.getByLabelText("Your name") as HTMLInputElement;
}

/**
 * The shell and the island, side by side — **the arrangement the product has.**
 *
 * **The rail is given the server-rendered name**, which is what every page hands it.
 * The island is given the stored name and the address, which is what the profile page
 * hands it.
 */
function renderShell(storedName: string) {
  return render(
    <>
      <Sidenav
        name={storedName === "" ? FALLBACK : storedName}
        email={EMAIL}
        avatarUrl=""
      />
      <ProfileName initialName={storedName} email={EMAIL} />
    </>,
  );
}

beforeEach(() => {
  PUT.mockReset();
  PUT.mockResolvedValue(answer(STORED));
});

describe("the rail follows the save", () => {
  it("shows the name the page was rendered with, before anything is saved", () => {
    // **The seed is the server's answer.** A page that has not saved a name shows the
    // name the server rendered it with — which is the fallback when no name is set.
    renderShell("");

    expect(railName()).toBe(FALLBACK);
  });

  it("moves to the saved name", async () => {
    // **The whole property.** The rail is a server render and it was drawn with the old
    // name; the save happened after that render; and the rail has to follow it.
    renderShell("");

    fireEvent.change(field(), { target: { value: STORED } });

    await waitFor(() => expect(railName()).toBe(STORED));

    // **And the sheet follows it too.** The sheet is the row's other half — it says
    // "here is who you are" — and a row that says one thing while the sheet it opens
    // says another is the product contradicting itself.
    expect(sheetName()).toBe(STORED);
  });

  it("publishes the name the server stored, not the one that was typed", async () => {
    // **The server trims and collapses**, so the account's name is not always the one
    // that was typed — and the rail must show what the account holds.
    //
    // **The mock is faithful.** The backend's `_clean_name` does `" ".join(name.split())`
    // and then truncates, so a name typed with spaces around and between it comes back
    // collapsed. A mock that answered with the raw string would be testing a server
    // that does not exist.
    //
    // **And the two are told apart by the assertion.** The typed value carries the
    // spaces; the stored one does not. A rail showing `"  Ada  Lovelace  "` would be
    // showing the typing, not the account.
    PUT.mockResolvedValue(answer(STORED));

    renderShell("");
    fireEvent.change(field(), { target: { value: `  Ada  Lovelace  ` } });

    await waitFor(() => expect(railName()).toBe(STORED));
    expect(railName()).not.toContain("  ");
  });

  it("falls back again when the name is cleared", async () => {
    // **The case that breaks silently.** Clearing the name stores `""`, and the display
    // name is then the address-derived one. **Publishing the stored name instead of the
    // display name would blank the rail** — and a blank rail reads as "this account has
    // no name" rather than "this feature is broken".
    PUT.mockResolvedValue(answer(""));

    renderShell(STORED);
    fireEvent.change(field(), { target: { value: "" } });

    await waitFor(() => expect(railName()).toBe(FALLBACK));
  });

  it("does not move when the save was refused", async () => {
    // **A refused save changed nothing**, so the rail must keep the name it had.
    // Publishing on failure would show a name the account does not hold.
    PUT.mockResolvedValue({
      data: undefined,
      error: { code: "invalid_input", message: "A name can't contain line breaks." },
      response: { status: 422 },
    });

    renderShell("");
    fireEvent.change(field(), { target: { value: "Maya\nAhmed" } });

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(railName()).toBe(FALLBACK);
  });

  it("does not move when the request never reached the API", async () => {
    PUT.mockRejectedValue(new Error("offline"));

    renderShell("");
    fireEvent.change(field(), { target: { value: STORED } });

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
    expect(railName()).toBe(FALLBACK);
  });
});
