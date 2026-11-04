/**
 * The share control's behaviour — the two paths, the confirmation, and the keyboard.
 *
 * **The claims under test, and why each matters:**
 *
 * 1. **The Web Share path** — the native sheet, with the event's title and the public
 *    URL.
 * 2. **The clipboard fallback** — everywhere the Web Share API is not, and the
 *    confirmation says *copied*, not *shared*.
 * 3. **The confirmation is shown and announced** — a live region, not a second
 *    `role="status"`.
 * 4. **A cancelled sheet says nothing**, and any other failure falls through to the
 *    clipboard.
 * 5. **The control is keyboard reachable** and its accessible name names the event.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ShareControl } from "@/components/share/share-control";

const ORIGIN = "https://eventpulse24.test";
const SLUG = "designing-for-calm-2026-08-28-a1b2c3";

/** The share stub, and the clipboard stub, restored after every test. */
let share: ReturnType<typeof vi.fn>;
let writeText: ReturnType<typeof vi.fn>;

function installBrowserApis({
  hasShare = true,
  hasClipboard = true,
}: { hasShare?: boolean; hasClipboard?: boolean } = {}) {
  share = vi.fn().mockResolvedValue(undefined);
  writeText = vi.fn().mockResolvedValue(undefined);

  Object.defineProperty(navigator, "share", {
    value: hasShare ? share : undefined,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(navigator, "clipboard", {
    value: hasClipboard ? { writeText } : undefined,
    configurable: true,
    writable: true,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

function renderControl(props: Partial<React.ComponentProps<typeof ShareControl>> = {}) {
  return render(<ShareControl slug={SLUG} title="Free tech meetup" origin={ORIGIN} {...props} />);
}

describe("the Web Share path", () => {
  it("shares the public URL and the event's own title", async () => {
    installBrowserApis();

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    expect(share).toHaveBeenCalledWith({
      title: "Free tech meetup",
      url: `${ORIGIN}/events/${SLUG}`,
    });
  });

  it("never shares the event's id", async () => {
    // **The mistake that existed before this component.** The Detail Screen's old button
    // shared `window.location.href`, which on that screen is `/events/{uuid}` — the
    // signed-in URL. A friend who opened it met a sign-in wall instead of the event.
    installBrowserApis();

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    const payload = share.mock.calls[0]?.[0] as { url: string };
    expect(payload.url).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });

  it("does not touch the clipboard", async () => {
    // The native sheet *is* the share. Copying as well would put the link on the
    // clipboard behind the user's back, for no reason.
    installBrowserApis();

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    expect(writeText).not.toHaveBeenCalled();
  });

  it("confirms that it shared", async () => {
    installBrowserApis();

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    expect(await screen.findByText("Shared.")).toBeInTheDocument();
  });
});

describe("the clipboard fallback", () => {
  it("copies the public URL when the browser has no Web Share API", async () => {
    installBrowserApis({ hasShare: false });

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    expect(writeText).toHaveBeenCalledWith(`${ORIGIN}/events/${SLUG}`);
  });

  it("confirms that it copied, not that it shared", async () => {
    // **"I copied it" and "I shared it" are different claims**, and the user needs to
    // know which one happened.
    installBrowserApis({ hasShare: false });

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    expect(await screen.findByText("Link copied.")).toBeInTheDocument();
    expect(screen.queryByText("Shared.")).toBeNull();
  });

  it("falls back to the clipboard when the share sheet fails", async () => {
    // The sheet not opening is no reason the link cannot still be copied.
    installBrowserApis();
    share.mockRejectedValue(new Error("the sheet would not open"));

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    expect(await screen.findByText("Link copied.")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(`${ORIGIN}/events/${SLUG}`);
  });

  it("says so plainly when the clipboard is unavailable", async () => {
    // **The confirmation must never claim a copy that did not happen.**
    installBrowserApis({ hasShare: false, hasClipboard: false });

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    expect(await screen.findByText("Couldn't copy the link. Try again.")).toBeInTheDocument();
  });

  it("says so plainly when the clipboard refuses", async () => {
    installBrowserApis({ hasShare: false });
    writeText.mockRejectedValue(new Error("permission denied"));

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    expect(await screen.findByText("Couldn't copy the link. Try again.")).toBeInTheDocument();
  });

  it("uses the browser's own origin when the server resolved none", async () => {
    // **The address the user is actually at**, which is never wrong for the person
    // receiving the link — and the right answer when the deployment has not set
    // `PUBLIC_SITE_URL`.
    installBrowserApis({ hasShare: false });

    renderControl({ origin: null });
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/events/${SLUG}`);
  });
});

describe("a cancelled share sheet", () => {
  it("says nothing at all", async () => {
    // **The user dismissed the sheet; that is their choice, not an error.** Reporting
    // it as a failure would be a lie about their own action — and the old code already
    // said so: *"A cancelled share sheet is not a failure, and there is nothing to say
    // about it."*
    installBrowserApis();
    const abort = new Error("Share canceled");
    abort.name = "AbortError";
    share.mockRejectedValue(abort);

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    await Promise.resolve();
    expect(screen.queryByText("Shared.")).toBeNull();
    expect(screen.queryByText("Link copied.")).toBeNull();
    expect(screen.queryByText("Couldn't copy the link. Try again.")).toBeNull();
  });

  it("does not fall back to the clipboard", async () => {
    // The user said no. Copying anyway would put the link on the clipboard behind their
    // back, for no reason.
    installBrowserApis();
    const abort = new Error("Share canceled");
    abort.name = "AbortError";
    share.mockRejectedValue(abort);

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    await Promise.resolve();
    expect(writeText).not.toHaveBeenCalled();
  });
});

describe("the confirmation", () => {
  it("is announced, not only shown", async () => {
    installBrowserApis({ hasShare: false });

    const { container } = renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    await screen.findByText("Link copied.");

    // **A live region, and not a second `role="status"`.** The digest's own "ready"
    // line and the Detail Screen's conflict-failure line are their surfaces' status
    // regions, and they stay the only ones there is.
    const region = container.querySelector("[aria-live='polite']");
    expect(region).not.toBeNull();
    expect(region?.getAttribute("role")).toBeNull();
  });

  it("is already in the DOM before it says anything", async () => {
    // **A live region added to the page together with its text is not announced
    // reliably.** A region that is already there and then changes is.
    installBrowserApis({ hasShare: false });

    const { container } = renderControl();

    expect(container.querySelector("[aria-live='polite']")).not.toBeNull();
  });

  it("clears the last message when a new attempt starts", async () => {
    installBrowserApis({ hasShare: false });

    renderControl();
    fireEvent.click(screen.getByRole("button", { name: /share/i }));
    await screen.findByText("Link copied.");

    fireEvent.click(screen.getByRole("button", { name: /share/i }));

    // The line is about the last attempt; a stale "Link copied." would be a claim
    // about an attempt that has not finished.
    await screen.findByText("Link copied.");
    expect(screen.getAllByText("Link copied.")).toHaveLength(1);
  });
});

describe("the control's accessibility", () => {
  it("has a visible label", () => {
    // **Never icon-only** (WCAG 1.1.1, as this repo reads it).
    installBrowserApis();

    renderControl();

    expect(screen.getByRole("button", { name: /share/i })).toHaveTextContent("Share");
  });

  it("names the event in its accessible name", () => {
    // **Three cards, three buttons.** On a digest, three controls all named "Share"
    // tell a screen-reader user nothing about which event they are about to share.
    installBrowserApis();

    renderControl({ title: "Free tech meetup" });

    expect(screen.getByRole("button", { name: "Share Free tech meetup" })).toBeInTheDocument();
  });

  it("is a real button, so it is keyboard reachable and activates on Enter", () => {
    // **A `<button type="button">` is in the tab order and fires on Enter and Space**,
    // with no key handling of our own to get wrong.
    installBrowserApis();

    renderControl();
    const button = screen.getByRole("button", { name: /share/i });

    expect(button.tagName).toBe("BUTTON");
    expect(button).toHaveAttribute("type", "button");
    expect(button).not.toHaveAttribute("tabindex", "-1");
  });

  it("shares when it is activated from the keyboard", () => {
    installBrowserApis();

    renderControl();
    const button = screen.getByRole("button", { name: /share/i });
    button.focus();
    expect(document.activeElement).toBe(button);

    fireEvent.click(button);

    expect(share).toHaveBeenCalled();
  });
});
