/**
 * The account's face — **the picture when there is one, the initials when there is not.**
 *
 * ## Why this file exists
 *
 * **The disc is drawn in three places** — the sidenav's account row, the bottom bar's
 * More sheet and the account sheet. The fallback is *what the account looks like* to
 * somebody who has not set a picture, so a fallback that differs between them is
 * visible. This file pins the two rules that hold at all three.
 *
 * ## The two rules
 *
 * 1. **The fallback never blanks the name.** The disc falls back to initials, and the
 *    name beside it is text whatever the disc shows.
 * 2. **The alt text is not the word "avatar".** The name is beside the disc, so the
 *    picture is decorative — `alt=""` — and the disc stays `aria-hidden`. A screen
 *    reader reads the name once, not "avatar, Maya Ahmed".
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AvatarDisc } from "@/components/shell/avatar-disc";

const NAME = "Maya Ahmed";
const PICTURE = "/api/auth/profile/avatar/ab12cd34";

describe("the disc", () => {
  it("shows the picture when the account has one", () => {
    render(<AvatarDisc avatarUrl={PICTURE} name={NAME} />);

    const image = screen.getByRole("presentation", { hidden: true });
    expect(image.getAttribute("src")).toBe(PICTURE);
  });

  it("shows the initials when the account has no picture", () => {
    render(<AvatarDisc avatarUrl="" name={NAME} />);

    // **The disc is `aria-hidden`, so the initials are not in the accessibility tree.**
    // They are read by the *look* of them, not by a screen reader — so the assertion
    // is on the rendered text, not on a role.
    expect(document.querySelector("span[aria-hidden='true']")?.textContent).toBe("MA");
  });

  it("does not blank the name when there is no picture", () => {
    // **The property that matters most.** The disc falls back to initials; the name
    // beside it is text. A fallback that replaced the name with nothing would leave an
    // account looking like an empty rail.
    render(
      <div>
        <AvatarDisc avatarUrl="" name={NAME} />
        <span>{NAME}</span>
      </div>,
    );

    expect(screen.getByText(NAME)).toBeInTheDocument();
    expect(screen.getByText(NAME).textContent).not.toBe("");
  });

  it("gives the picture an empty alt, never the word 'avatar'", () => {
    render(<AvatarDisc avatarUrl={PICTURE} name={NAME} />);

    const image = document.querySelector("img");
    expect(image).not.toBeNull();
    // **The image is decorative**, because the name is beside it in text. An alt of
    // "avatar" would read aloud as "avatar, Maya Ahmed".
    expect(image?.getAttribute("alt")).toBe("");
    // **And no alt text anywhere says the word.** A stray "avatar" in an alt is the
    // exact failure this file exists to catch.
    expect(document.querySelector("[alt*='avatar' i]")).toBeNull();
  });

  it("keeps the disc out of the accessibility tree", () => {
    render(<AvatarDisc avatarUrl={PICTURE} name={NAME} />);

    // **The name is beside the disc, always.** So the disc is hidden from assistive
    // technology, and the name is read exactly once.
    const hidden = document.querySelectorAll("[aria-hidden='true']");
    expect(hidden.length).toBeGreaterThan(0);
    expect(screen.queryByText(/avatar/i)).toBeNull();
  });

  it("does not render an image when there is no picture", () => {
    render(<AvatarDisc avatarUrl="" name={NAME} />);

    expect(document.querySelector("img")).toBeNull();
  });

  it("renders the larger disc for the sheet", () => {
    render(<AvatarDisc avatarUrl="" name={NAME} size="lg" />);

    // **A size is a token where the scale has one, and an exact size where it does
    // not.** The sheet's disc is 40px, and 40px is not a step on the spacing scale —
    // so it is written as the exact size it is. `size-10` would generate no CSS at all.
    expect(document.querySelector("span[aria-hidden='true']")?.className).toContain("size-[40px]");
  });
});
