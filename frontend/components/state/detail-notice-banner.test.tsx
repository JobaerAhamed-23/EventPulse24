import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DetailNoticeBanner, type BannerNotice } from "@/components/state/detail-notice-banner";

/**
 * The Detail Screen's state-change banner, and the per-event mute control beside it.
 *
 * **The banner is persistent where the strip is dismissible.** The user came to this
 * page on purpose, and the page's whole job here is to tell them what happened to the
 * event they were planning around.
 *
 * **A dismissed notice still shows.** The backend reports the newest notice for the
 * event *whether or not it has been dismissed* — dismissing the strip on the digest home
 * must not hide "this event was cancelled" from the event's own page.
 *
 * **A muted event gets no banner.** FR-55's mute silences the correction, and the banner
 * *is* the correction. The mute control stays, because a mute the user cannot undo is a
 * trap.
 */
const PUT = vi.fn();
const DELETE = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    PUT: (...args: unknown[]) => PUT(...args),
    DELETE: (...args: unknown[]) => DELETE(...args),
  },
}));

beforeEach(() => {
  PUT.mockReset();
  DELETE.mockReset();
  PUT.mockResolvedValue({ data: {}, response: { status: 200 } });
  DELETE.mockResolvedValue({ data: {}, response: { status: 200 } });
});

/** One notice, as the Detail read hands it over. */
function notice(overrides: Partial<BannerNotice> = {}): BannerNotice {
  return {
    id: "notice-1",
    change_kind: "cancelled",
    dismissed_at: null,
    ...overrides,
  };
}

function renderBanner(props: Partial<React.ComponentProps<typeof DetailNoticeBanner>> = {}) {
  return render(
    <DetailNoticeBanner notice={notice()} muted={false} eventId="event-1" {...props} />,
  );
}

describe("the banner", () => {
  it("renders no banner when the event has no notice", () => {
    // **The server's answer, not the client's** (AD-10). No notice has been raised, so
    // there is nothing to say — and the banner element is not in the DOM at all.
    renderBanner({ notice: null });

    expect(
      screen.queryByRole("region", { name: "This event has changed" }),
    ).not.toBeInTheDocument();
    expect(document.querySelector("[data-detail-notice]")).toBeNull();
  });

  it("says what changed and what it means for the user's reminders", () => {
    renderBanner();

    expect(screen.getByText("This event was cancelled.")).toBeInTheDocument();
    expect(
      screen.getByText("Your reminders for this event have been cancelled."),
    ).toBeInTheDocument();
  });

  it("says what a postponement did to the reminders", () => {
    // **The second sentence is the point.** It tells the reader whether their
    // 1-day-before reminder still fires, and when.
    renderBanner({ notice: notice({ change_kind: "postponed" }) });

    expect(screen.getByText("This event was moved to a new time.")).toBeInTheDocument();
    expect(
      screen.getByText("Your reminders have been rescheduled to the new time."),
    ).toBeInTheDocument();
  });

  it("is a labelled region, so a reader can find it", () => {
    renderBanner();

    expect(screen.getByRole("region", { name: "This event has changed" })).toBeInTheDocument();
  });

  it("is not an alert, and does not interrupt", () => {
    renderBanner();

    // **FR-54's "one calm correction."** An alert interrupts; this is quiet.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("says so when the notice was already dismissed", () => {
    // **The notice is still the truth about this event**, and pretending the correction
    // never happened would be the other lie.
    renderBanner({ notice: notice({ dismissed_at: "2026-11-10T12:00:00Z" }) });

    expect(screen.getByText("This event was cancelled.")).toBeInTheDocument();
    expect(screen.getByText("You've already dismissed this.")).toBeInTheDocument();
  });

  it("does not say 'already dismissed' for an open notice", () => {
    renderBanner();

    expect(screen.queryByText("You've already dismissed this.")).not.toBeInTheDocument();
  });

  it("renders no banner for a kind it cannot put into words", () => {
    // **ASSUMPTION-9: a kind this system has never heard of shows nothing.** The backend
    // does the same — `domain/notices.py`'s `subject_template` raises `KeyError` rather
    // than produce a generic subject, because "a wrong subject is worse than no email".
    //
    // **So the banner says nothing rather than something generic.** "This event has
    // changed." would be a claim about the world made by a client that was told *what*
    // changed and could not understand it.
    renderBanner({ notice: notice({ change_kind: "rescheduled_for_tuesday" }) });

    expect(
      screen.queryByRole("region", { name: "This event has changed" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("This event has changed.")).not.toBeInTheDocument();
    expect(screen.queryByText(/Your reminders/)).not.toBeInTheDocument();
  });
});

describe("an event with no notice", () => {
  it("still offers the mute", () => {
    // **A user who does not want to hear about changes to an event should be able to
    // say so *before* one arrives.** A control that only appears once there is
    // something to mute arrives too late to be useful.
    renderBanner({ notice: null });

    expect(
      screen.getByRole("button", { name: "Mute updates about this event" }),
    ).toBeInTheDocument();
  });
});

describe("a muted event", () => {
  it("renders no banner for a correction the mute silences", () => {
    // **The mute silences the correction, and the banner *is* the correction.** A banner
    // that kept showing would make the mute a lie.
    renderBanner({ muted: true, notice: notice({ change_kind: "postponed" }) });

    expect(
      screen.queryByRole("region", { name: "This event has changed" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("This event was moved to a new time.")).not.toBeInTheDocument();
  });

  it("still shows a terminal change, because the backend raised it despite the mute", () => {
    // **The backend raises a `cancelled` or `superseded` notice even when the event is
    // muted** — `services/state_notices.py` skips the mute check for exactly those two
    // kinds, and `services/mutes.py` says why: *"FR-55 has already removed the event
    // from their digest, so silence about it is the one failure with no second channel to
    // catch it."*
    //
    // **So the mute does not hide this one.** A frontend that hid it would be undoing
    // the server's deliberate decision, and the reader would never learn the event was
    // off (AD-10: the client does not re-decide a fact the server has stated).
    renderBanner({ muted: true, notice: notice({ change_kind: "cancelled" }) });

    expect(screen.getByRole("region", { name: "This event has changed" })).toBeInTheDocument();
    expect(screen.getByText("This event was cancelled.")).toBeInTheDocument();
  });

  it("still shows a supersede, because the backend raised it despite the mute", () => {
    renderBanner({ muted: true, notice: notice({ change_kind: "superseded" }) });

    expect(screen.getByRole("region", { name: "This event has changed" })).toBeInTheDocument();
    expect(screen.getByText("This event was replaced by another event.")).toBeInTheDocument();
  });

  it("keeps the mute control, because a mute the user cannot undo is a trap", () => {
    renderBanner({ muted: true });

    expect(
      screen.getByRole("button", { name: "Mute updates about this event" }),
    ).toBeInTheDocument();
  });
});

describe("the mute control", () => {
  it("says in words what it will do when the event is not muted", () => {
    renderBanner();

    expect(
      screen.getByRole("button", { name: "Mute updates about this event" }),
    ).toBeInTheDocument();
  });

  it("says in words that the event is muted when it is", () => {
    // **WCAG 1.4.1: colour is never the sole carrier of meaning.** A toggle whose only
    // signal is a filled circle fails this — the state is in the *shape*. The visible
    // text carries it in words.
    renderBanner({ muted: true });

    expect(screen.getByText("Updates about this event are muted")).toBeInTheDocument();
  });

  it("keeps the accessible name stable while the state changes", () => {
    // **A toggle button whose accessible name changes with its state is a
    // contradiction.** "Mute updates about this event" says *press me to mute*, and
    // "Updates about this event are muted" is a status with nothing to press — so a
    // reader meeting the second one has no action to take.
    //
    // **So the name names the action and stays put**, and `aria-pressed` carries the
    // state (WCAG 4.1.2).
    renderBanner({ muted: true });

    expect(screen.getByRole("button", { name: "Mute updates about this event" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("carries the state to assistive technology", () => {
    renderBanner({ muted: true });

    expect(screen.getByRole("button", { name: "Mute updates about this event" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("says what a mute does not do", () => {
    // A user who thinks "mute" means "stop the reminders" would be badly wrong, and the
    // cost of that mistake is a reminder they expected and did not get.
    renderBanner();

    expect(screen.getByText("Reminders are not affected.")).toBeInTheDocument();
  });

  it("mutes with a PUT, because a mute is a state with two values", async () => {
    renderBanner();

    screen.getByRole("button", { name: "Mute updates about this event" }).click();

    await waitFor(() =>
      expect(PUT).toHaveBeenCalledWith("/api/notices/events/{event_id}/mute", {
        params: { path: { event_id: "event-1" } },
      }),
    );
  });

  it("unmutes with a DELETE", async () => {
    renderBanner({ muted: true });

    screen.getByRole("button", { name: "Mute updates about this event" }).click();

    await waitFor(() =>
      expect(DELETE).toHaveBeenCalledWith("/api/notices/events/{event_id}/mute", {
        params: { path: { event_id: "event-1" } },
      }),
    );
  });

  it("takes the banner away once the server has confirmed the mute", async () => {
    // **A postponement is the kind a mute silences**, so the banner goes. (A
    // cancellation would not — the backend raised it despite the mute.)
    //
    // **And it goes when the *server* says so, not when the button is pressed.** The
    // banner's disappearance is a claim about the world — "you will not be told about
    // changes to this event" — and a claim the server has not agreed to is the client
    // deciding the server's fact (AD-10).
    renderBanner({ notice: notice({ change_kind: "postponed" }) });

    screen.getByRole("button", { name: "Mute updates about this event" }).click();

    await waitFor(() =>
      expect(
        screen.queryByRole("region", { name: "This event has changed" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("keeps the banner while the mute is still in flight", async () => {
    // **The client does not claim the server's fact before the server states it.** The
    // button's label flips at once — so the control feels responsive — but the banner
    // stays until the write comes back, because until then the event is not muted.
    let release: (() => void) | undefined;
    PUT.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ data: {}, response: { status: 200 } });
        }),
    );

    renderBanner({ notice: notice({ change_kind: "postponed" }) });

    screen.getByRole("button", { name: "Mute updates about this event" }).click();

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(screen.getByRole("region", { name: "This event has changed" })).toBeInTheDocument();

    release?.();

    await waitFor(() =>
      expect(
        screen.queryByRole("region", { name: "This event has changed" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("keeps the banner when the mute fails", async () => {
    // **A failed write leaves the banner exactly where it was.** The server did not
    // record the mute, so the event is not muted, and a hidden banner would be claiming
    // something that did not happen.
    //
    // **The banner never leaves in the first place** — it only goes when the server
    // confirms — so a failed write leaves no gap and nothing to restore.
    PUT.mockResolvedValue({ data: undefined, response: { status: 500 } });

    renderBanner({ notice: notice({ change_kind: "postponed" }) });

    screen.getByRole("button", { name: "Mute updates about this event" }).click();

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(screen.getByRole("region", { name: "This event has changed" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Mute updates about this event" }),
    ).toBeInTheDocument();
  });

  it("says so calmly when the mute cannot be recorded", async () => {
    PUT.mockResolvedValue({ data: undefined, response: { status: 500 } });

    renderBanner();

    screen.getByRole("button", { name: "Mute updates about this event" }).click();

    await waitFor(() =>
      expect(screen.getByText("Couldn't record that. Try again.")).toBeInTheDocument(),
    );
  });

  it("puts the state back when the mute throws", async () => {
    PUT.mockRejectedValue(new Error("offline"));

    renderBanner();

    screen.getByRole("button", { name: "Mute updates about this event" }).click();

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(screen.getByRole("region", { name: "This event has changed" })).toBeInTheDocument();
  });

  it("does not record a mute twice while one is in flight", async () => {
    /** The write's resolver — released once the assertions are done. */
    let release: (() => void) | undefined;
    PUT.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ data: {}, response: { status: 200 } });
        }),
    );

    renderBanner();

    const button = screen.getByRole("button", { name: "Mute updates about this event" });
    button.click();
    await waitFor(() => expect(button).toBeDisabled());

    button.click();
    expect(PUT).toHaveBeenCalledTimes(1);

    release?.();
  });
});
