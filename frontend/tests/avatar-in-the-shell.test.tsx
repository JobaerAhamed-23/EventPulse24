/**
 * The shell's picture follows the save.
 *
 * ## Why this file exists
 *
 * **The face is drawn in three places** — the sidenav's account row, the bottom bar's
 * More sheet and the account sheet — and **the shell is a server render, which is a
 * photograph.** Every page reads the session on the server, takes the picture URL from
 * it, and hands that URL to `AppShell`, which hands it to the sidenav and the bottom
 * bar. That URL is fixed for the life of the render.
 *
 * **So a person who uploads a picture, sees "Saved.", and looks up at the rail sees the
 * old one** — and the rail is on every page, so the wrong face is on every page. The
 * account sheet says "here is who you are" and the row it was opened from shows
 * someone else.
 *
 * **A save that does not show up is a save that did not happen.** So the upload island
 * publishes the new picture once the server has accepted the write, and the shell
 * follows it.
 *
 * ## What is proved here
 *
 * 1. **A save moves all three places** — the rail row, the bottom bar's sheet and the
 *    account sheet — without a reload.
 * 2. **A removal reverts all three to the initials**, and the name is not blanked in
 *    any of them.
 * 3. **A refused upload publishes nothing** — the shell keeps the face it had.
 * 4. **The seed is what the page was rendered with** — an account with no picture shows
 *    the initials from the start.
 * 5. **The initials are one rule** — the same letters everywhere, including the
 *    two-word case where the first two *characters* are not the first two *letters*.
 *
 * **The unit test file `components/settings/avatar-upload.test.tsx` cannot see any of
 * this**, because it renders the island on its own: there is no rail beside it. This
 * file renders the shell *with* the island, which is the only way the property is
 * visible.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AvatarUpload } from "@/components/settings/avatar-upload";
import { BottomTabNav } from "@/components/shell/bottom-tab-nav";
import { Sidenav } from "@/components/shell/sidenav";

const POST = vi.fn();
const DELETE = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
    DELETE: (...args: unknown[]) => DELETE(...args),
  },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/profile",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/components/personal-events-panel", () => ({
  PersonalEventsPanel: () => null,
}));

/** The name the account holds, and the source of the initials. */
const NAME = "Maya Ahmed";

/**
 * The address, for the account sheet.
 *
 * **It is only here to be shown** — the picture's fallback does not come from the
 * address the way the name's does. The name is handed to the disc directly, so the
 * initials are the name's own letters.
 */
const EMAIL = "maya@example.test";

/** The picture the server stored, and the URL the shell is given. */
const PICTURE = "/api/auth/profile/avatar/ab12cd34";

/** The server's answer, as the endpoints send it. */
function answer(avatarUrl: string) {
  return {
    data: {
      id: "11111111-1111-1111-1111-111111111111",
      email: EMAIL,
      name: NAME,
      avatar_url: avatarUrl,
    },
    response: { status: 200 },
  };
}

/** A file the browser hands to the input. */
function pictureFile(name = "maya.png") {
  return new File([new Uint8Array([1, 2, 3])], name, { type: "image/png" });
}

/** The file input. */
function input(): HTMLInputElement {
  return document.querySelector("[data-avatar-input]") as HTMLInputElement;
}

/** The rail's account row. */
function railRow(): HTMLElement {
  return screen.getByRole("button", { name: /^Account: / });
}

/**
 * The picture the rail's account row is showing.
 *
 * **The row's own disc**, found by the row's own button — so the assertion is about the
 * row and not about some other disc on the page.
 */
function railPicture(): string | null {
  return railRow().querySelector("img")?.getAttribute("src") ?? null;
}

/**
 * The initials the rail's account row is showing.
 *
 * **The disc's own text**, found by the row's own button.
 */
function railInitials(): string | null {
  const disc = railRow().querySelector("span[aria-hidden='true']");
  return disc?.textContent ?? null;
}

/**
 * The picture the account sheet is showing.
 *
 * **The sheet is opened first**, because a native `<dialog>` that has not been opened
 * takes no space and its contents are not laid out — so the picture is not in the tree
 * until the row is pressed.
 */
function sheetPicture(): string | null {
  railRow().click();
  const panel = document.querySelector("[data-account-panel]");
  return panel?.querySelector("img")?.getAttribute("src") ?? null;
}

/**
 * The picture the bottom bar's More sheet is showing.
 *
 * **The More sheet is opened first**, for the same reason the account sheet is: an
 * unopened `<dialog>` has no laid-out contents.
 */
function bottomBarPicture(): string | null {
  const more = screen.getByRole("button", { name: "More" });
  more.click();
  // **The More sheet's panel is the same `AccountPanel`**, so it carries the same
  // `data-account-panel` marker — and the account sheet is not open at this point, so
  // the one in the tree is this one's.
  const panels = document.querySelectorAll("[data-account-panel]");
  const panel = panels[panels.length - 1];
  return panel?.querySelector("img")?.getAttribute("src") ?? null;
}

/**
 * The shell and the island, side by side — **the arrangement the product has.**
 *
 * **The rail is given the server-rendered picture**, which is what every page hands it.
 * The island is given the same seed and the name, which is what the profile page hands
 * it.
 */
function renderShell(avatarUrl: string) {
  return render(
    <>
      <Sidenav name={NAME} email={EMAIL} avatarUrl={avatarUrl} />
      <BottomTabNav name={NAME} email={EMAIL} avatarUrl={avatarUrl} />
      <AvatarUpload initialAvatarUrl={avatarUrl} name={NAME} />
    </>,
  );
}

beforeEach(() => {
  POST.mockReset();
  DELETE.mockReset();
  POST.mockResolvedValue(answer(PICTURE));
  DELETE.mockResolvedValue(answer(""));
});

describe("the shell follows the picture", () => {
  it("shows the initials when the account has no picture", () => {
    // **The seed is the server's answer.** An account with no picture shows the
    // initials from the start — and the name beside it is never blanked.
    renderShell("");

    expect(railPicture()).toBeNull();
    expect(railInitials()).toBe("MA");
    // **And the name is still there.** The initials are a fallback for the picture, not
    // a replacement for the name.
    expect(railRow().textContent).toContain(NAME);
  });

  it("shows the picture the page was rendered with, before anything is uploaded", () => {
    renderShell(PICTURE);

    expect(railPicture()).toBe(PICTURE);
  });

  it("moves all three places to the saved picture", async () => {
    // **The whole property.** The shell was rendered on the server with no picture; the
    // upload happened after that render; and every place the face is drawn has to
    // follow it.
    renderShell("");

    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(railPicture()).toBe(PICTURE));
    // **The account sheet is the row's other half** — it says "here is who you are" —
    // and a row that shows one face while the sheet it opens shows another is the
    // product contradicting itself.
    expect(sheetPicture()).toBe(PICTURE);
    // **And the bottom bar's sheet**, which is the mobile half of the same surface.
    expect(bottomBarPicture()).toBe(PICTURE);
  });

  it("reverts all three places to the initials when the picture is removed", async () => {
    // **The removal is the case that breaks silently.** A removal that cleared the URL
    // without clearing the picture would leave the rail showing a face the account no
    // longer holds — and the account sheet, opened from that rail, would show it too.
    renderShell(PICTURE);

    fireEvent.click(document.querySelector("[data-avatar-remove]") as HTMLButtonElement);

    await waitFor(() => expect(railPicture()).toBeNull());
    expect(railInitials()).toBe("MA");
    expect(sheetPicture()).toBeNull();
    expect(bottomBarPicture()).toBeNull();
    // **And the name is still there in all of them.** A removal must not blank the
    // account's name.
    expect(railRow().textContent).toContain(NAME);
  });

  it("does not move when the upload was refused", async () => {
    // **A refused upload changed nothing**, so the shell must keep the face it had.
    // Publishing on failure would show a picture the account does not hold.
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "invalid_input", message: "That file isn't an image we can read." },
      response: { status: 422 },
    });

    renderShell("");

    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(railPicture()).toBeNull();
    expect(railInitials()).toBe("MA");
  });

  it("does not move when the request never reached the API", async () => {
    POST.mockRejectedValue(new Error("offline"));

    renderShell("");

    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
    expect(railPicture()).toBeNull();
  });
});

describe("the initials are one rule", () => {
  it("takes one letter from each of the first two words", () => {
    // **The case the naive rule gets wrong.** `name.slice(0, 2)` would give `"MA"` for
    // "Mary-Jane Watson" — the first two *characters* rather than the first two
    // *letters* — and a rail whose initials are the wrong letters is a rail whose
    // fallback has drifted from the name's.
    render(
      <>
        <Sidenav name="Mary-Jane Watson" email={EMAIL} avatarUrl="" />
        <BottomTabNav name="Mary-Jane Watson" email={EMAIL} avatarUrl="" />
      </>,
    );

    expect(railInitials()).toBe("MW");
  });

  it("takes the same letters in every place", () => {
    // **One rule, used everywhere.** The rail and the sheet are the same component, so
    // they cannot drift — but the assertion is on the sheet too, because a copy of the
    // disc somewhere would be a second rule.
    renderShell("");

    railRow().click();
    const panel = document.querySelector("[data-account-panel]");
    expect(panel?.querySelector("span[aria-hidden='true']")?.textContent).toBe("MA");
  });
});
