import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NoticeStrip, type StripNotice } from "@/components/state/notice-strip";

/**
 * The state-change strip, on the digest home.
 *
 * **A strip, not an inbox.** FR-10 removed the topbar Notifications button, and the
 * reason it gives is that there is no in-app notifications inbox. So there is no bell,
 * no badge count, no history, and no "view all" — and these tests hold that, because a
 * strip that grew a badge would be the beginning of an inbox.
 *
 * **An empty strip renders no element at all.** The AC says the home screen must render
 * "exactly as it does today, with no layout shift", and an empty `<section>` is a layout
 * shift waiting for a stylesheet. No element is not.
 *
 * **The dismissal is a write.** A client-only dismissal would empty the strip until the
 * next page load and let the same notice come back, so the entry goes only when the
 * server says so.
 */
const POST = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
  },
}));

beforeEach(() => {
  POST.mockReset();
  POST.mockResolvedValue({ data: {}, response: { status: 200 } });
});

/** One open notice, as the server's list hands it over. */
function notice(overrides: Partial<StripNotice> = {}): StripNotice {
  return {
    id: "notice-1",
    event_id: "event-1",
    change_kind: "cancelled",
    ...overrides,
  };
}

describe("the strip", () => {
  it("renders nothing at all when there is nothing to say", () => {
    // **No visible element in the DOM.** Not an empty section, not a hidden one — the
    // home screen renders byte-for-byte as it does today.
    //
    // **The one exception is the `sr-only` live region**, which must be in the DOM
    // before its text arrives; see the live-region tests below. It takes no space, so
    // the "no layout shift" claim still holds.
    const { container } = render(<NoticeStrip notices={[]} />);

    expect(container.querySelector("[aria-label='Changes to your saved events']")).toBeNull();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Dismiss:/ })).not.toBeInTheDocument();
    expect(document.querySelector("[aria-live='polite']")?.className).toContain("sr-only");
  });

  it("says what changed and what it means for the user's reminders", () => {
    render(<NoticeStrip notices={[notice()]} />);

    // The two sentences of FR-54's body requirement: what changed, and what it means.
    expect(screen.getByText("This event was cancelled.")).toBeInTheDocument();
    expect(
      screen.getByText("Your reminders for this event have been cancelled."),
    ).toBeInTheDocument();
  });

  it("links the change's sentence to the event's own page", () => {
    render(<NoticeStrip notices={[notice({ event_id: "event-42" })]} />);

    const link = screen.getByRole("link", { name: "This event was cancelled." });
    expect(link).toHaveAttribute("href", "/events/event-42");
  });

  it("names the event in the dismiss control's accessible name", () => {
    // Three "Dismiss" buttons with no object would tell a screen-reader user nothing
    // about which one they are about to press.
    render(<NoticeStrip notices={[notice()]} />);

    expect(
      screen.getByRole("button", { name: "Dismiss: This event was cancelled. (1 of 1)" }),
    ).toBeInTheDocument();
  });

  it("gives two identical changes distinguishable dismiss buttons", () => {
    // **Two events cancelled on the same day produce two buttons with the same
    // sentence.** A screen reader offering two identical "Dismiss: This event was
    // cancelled." buttons tells the reader nothing about which one they are about to
    // press — and the strip cannot name the event, because the payload carries no
    // title (AD-13).
    //
    // **So the name carries the position as well.** It is the only disambiguator the
    // strip has.
    render(<NoticeStrip notices={[notice({ id: "notice-1" }), notice({ id: "notice-2" })]} />);

    expect(
      screen.getByRole("button", { name: "Dismiss: This event was cancelled. (1 of 2)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Dismiss: This event was cancelled. (2 of 2)" }),
    ).toBeInTheDocument();
  });

  it("counts the position over the entries that render, not over the ones it cannot say", () => {
    // **An unknown kind renders nothing at all** (ASSUMPTION-9), so it is not a thing
    // the reader can dismiss — counting it would make the positions skip a number.
    render(
      <NoticeStrip
        notices={[
          notice({ id: "notice-1", change_kind: "rescheduled_for_tuesday" }),
          notice({ id: "notice-2" }),
        ]}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Dismiss: This event was cancelled. (1 of 1)" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /\(2 of 2\)/ })).not.toBeInTheDocument();
  });

  it("has no badge count, no history, and no 'view all'", () => {
    render(<NoticeStrip notices={[notice(), notice({ id: "notice-2" })]} />);

    // **FR-10: there is no in-app notifications inbox.** A count would be the first
    // step towards one.
    expect(screen.queryByText(/2 notices/)).not.toBeInTheDocument();
    expect(screen.queryByText(/view all/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /history/i })).not.toBeInTheDocument();
  });

  it("announces the count in words, not as a number on the page", () => {
    render(<NoticeStrip notices={[notice(), notice({ id: "notice-2" })]} />);

    // **The live region is a sentence.** A screen reader can say it out loud without a
    // number appearing anywhere on the page.
    const live = document.querySelector("[aria-live='polite']");
    expect(live).not.toBeNull();
    expect(live).toHaveTextContent("2 changes to events you saved.");
  });

  it("says 'one change' in the singular", () => {
    render(<NoticeStrip notices={[notice()]} />);

    const live = document.querySelector("[aria-live='polite']");
    expect(live).toHaveTextContent("One change to an event you saved.");
  });

  it("counts only the changes it can put into words", () => {
    // **A notice with an unknown kind renders nothing at all** (ASSUMPTION-9), so it is
    // not a change the reader was told about. Announcing "Two changes" over a screen
    // showing one would be a claim the screen does not support.
    render(
      <NoticeStrip
        notices={[
          notice({ id: "notice-1", change_kind: "rescheduled_for_tuesday" }),
          notice({ id: "notice-2" }),
        ]}
      />,
    );

    const live = document.querySelector("[aria-live='polite']");
    expect(live).toHaveTextContent("One change to an event you saved.");
  });

  it("keeps the live region in the DOM when the strip empties", async () => {
    // **A live region that arrives with its text is not announced reliably; a region
    // that is already there and then changes is.** The moment that matters most is the
    // dismissal of the *last* notice — which is exactly when a strip that returned
    // `null` would take its own live region with it.
    render(<NoticeStrip notices={[notice()]} />);

    const live = document.querySelector("[aria-live='polite']");
    expect(live).not.toBeNull();

    screen.getByRole("button", { name: /Dismiss:/ }).click();

    await waitFor(() =>
      expect(screen.queryByText("This event was cancelled.")).not.toBeInTheDocument(),
    );

    // **The region is still there**, and its text has changed to nothing.
    expect(document.querySelector("[aria-live='polite']")).not.toBeNull();
    expect(document.querySelector("[aria-live='polite']")).toHaveTextContent("");
  });

  it("is not a second status region on the page", () => {
    render(<NoticeStrip notices={[notice()]} />);

    // **The digest home already owns one `role="status"`** ("Pulse Digest ready, N
    // events for today."). Two status regions would make "which one is the page
    // talking?" a question the DOM cannot answer.
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("dismissing a change", () => {
  it("posts the dismissal with the notice's id", async () => {
    render(<NoticeStrip notices={[notice({ id: "notice-7" })]} />);

    screen.getByRole("button", { name: /Dismiss:/ }).click();

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/notices/{notice_id}/dismiss", {
        params: { path: { notice_id: "notice-7" } },
      }),
    );
  });

  it("removes the entry once the server has closed it", async () => {
    render(<NoticeStrip notices={[notice()]} />);

    screen.getByRole("button", { name: /Dismiss:/ }).click();

    await waitFor(() =>
      expect(screen.queryByText("This event was cancelled.")).not.toBeInTheDocument(),
    );
    // And with the last one gone, the strip leaves the DOM entirely.
    expect(document.querySelector("[aria-label='Changes to your saved events']")).toBeNull();
  });

  it("keeps the entry when the dismissal fails", async () => {
    // **A failed dismissal puts the notice back.** The entry was not closed, and a
    // strip that showed it as closed would be claiming something that did not happen.
    POST.mockResolvedValue({ data: undefined, response: { status: 500 } });

    render(<NoticeStrip notices={[notice()]} />);

    screen.getByRole("button", { name: /Dismiss:/ }).click();

    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(screen.getByText("This event was cancelled.")).toBeInTheDocument();
  });

  it("keeps the entry when the dismissal throws", async () => {
    POST.mockRejectedValue(new Error("offline"));

    render(<NoticeStrip notices={[notice()]} />);

    screen.getByRole("button", { name: /Dismiss:/ }).click();

    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(screen.getByText("This event was cancelled.")).toBeInTheDocument();
  });

  it("treats an already-dismissed notice as dismissed", async () => {
    // The endpoint is idempotent: a notice that was already closed answers 200 with
    // `changed: false` — and it *is* closed, so the entry still goes.
    POST.mockResolvedValue({
      data: { dismissed: true, changed: false },
      response: { status: 200 },
    });

    render(<NoticeStrip notices={[notice()]} />);

    screen.getByRole("button", { name: /Dismiss:/ }).click();

    await waitFor(() =>
      expect(screen.queryByText("This event was cancelled.")).not.toBeInTheDocument(),
    );
  });

  it("does not dismiss the same notice twice while a dismissal is in flight", async () => {
    /** The write's resolver — released once the assertions are done. */
    let release: (() => void) | undefined;
    POST.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ data: {}, response: { status: 200 } });
        }),
    );

    render(<NoticeStrip notices={[notice()]} />);

    const button = screen.getByRole("button", { name: /Dismiss:/ });
    button.click();
    await waitFor(() => expect(button).toBeDisabled());

    button.click();
    expect(POST).toHaveBeenCalledTimes(1);

    release?.();
  });
});

describe("a change kind the frontend cannot put into words", () => {
  it("renders nothing at all for that entry", () => {
    // **ASSUMPTION-9: a kind this system has never heard of shows nothing.** The backend
    // does the same — `domain/notices.py`'s `subject_template` raises `KeyError` rather
    // than produce a generic subject, because "a wrong subject is worse than no email".
    //
    // **So the strip says nothing rather than something generic.** "An event you saved
    // has changed." would be a claim about the world made by a client that was told
    // *what* changed and could not understand it.
    const { container } = render(
      <NoticeStrip notices={[notice({ change_kind: "rescheduled_for_tuesday" })]} />,
    );

    expect(container.querySelector("[data-notice-strip-item]")).toBeNull();
    expect(screen.queryByText("An event you saved has changed.")).not.toBeInTheDocument();
    expect(screen.queryByText(/Your reminders/)).not.toBeInTheDocument();
  });

  it("still renders the entries it can put into words", () => {
    // **One unknown kind does not take the whole strip down.** The server's list is
    // bounded, and the other entries are still true.
    render(
      <NoticeStrip
        notices={[
          notice({ id: "notice-1", change_kind: "rescheduled_for_tuesday" }),
          notice({ id: "notice-2", change_kind: "postponed" }),
        ]}
      />,
    );

    expect(screen.getByText("This event was moved to a new time.")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-notice-strip-item]")).toHaveLength(1);
  });
});
