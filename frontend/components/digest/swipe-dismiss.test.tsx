import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SwipeDismiss, MAX_TRAVEL_PX, SWIPE_THRESHOLD_PX } from "@/components/digest/swipe-dismiss";

const recordDismissal = vi.fn();

vi.mock("@/lib/dismissal-write", () => ({
  recordDismissal: (...args: unknown[]) => recordDismissal(...args),
}));

/**
 * The swipe-to-dismiss control (FR-25).
 *
 * **The gesture is the product's; the button is the contract.** The mockup's swipe is
 * what makes FR-25 feel like part of the digest, and the button is what makes it
 * reachable at all — a gesture-only control excludes keyboard users and screen reader
 * users entirely. So both are tested, and the button is tested for *the same action*,
 * not for a similar one.
 *
 * **The server decides what a dismissal means.** These tests never assert that the
 * client counted anything: the client sends an event id and renders what comes back.
 * The one thing the client *does* decide is what to do when the write fails — and the
 * answer is "nothing", so the card stays.
 */

const EVENT_ID = "11111111-1111-1111-1111-111111111111";

/** The server's answer for a dismissal that counted and did not complete a cluster. */
const ADVANCED = { cluster_advanced: true, prompt_due: false, prompt: null };

/** The server's answer for a dismissal that completed a cluster. */
const PROMPTED = {
  cluster_advanced: true,
  prompt_due: true,
  prompt: {
    title: "Less arts & culture in your next digest?",
    description: "You've swiped past 3 similar events.",
    category_key: "arts_culture",
  },
};

function renderSwipe(
  overrides: {
    onDismissed?: (eventId: string) => void;
    onPromptDue?: (prompt: unknown) => void;
  } = {},
) {
  const onDismissed = overrides.onDismissed ?? vi.fn();
  const onPromptDue = overrides.onPromptDue ?? vi.fn();
  render(
    <SwipeDismiss
      eventId={EVENT_ID}
      title="Brooklyn Symphony open rehearsal"
      onDismissed={onDismissed}
      onPromptDue={onPromptDue}
    >
      <article>the card</article>
    </SwipeDismiss>,
  );
  return { onDismissed, onPromptDue };
}

/** The wrapper the gesture moves. */
function wrapper(): HTMLElement {
  const element = document.querySelector(`[data-swipe-dismiss='${EVENT_ID}']`);
  if (!element) throw new Error("no swipe wrapper");
  return element as HTMLElement;
}

beforeEach(() => {
  recordDismissal.mockReset();
  recordDismissal.mockResolvedValue(ADVANCED);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the keyboard-reachable button", () => {
  it("is a real button, not a gesture-only affordance", () => {
    // **A gesture-only control excludes keyboard and screen reader users.** The button
    // is the reason this feature is reachable at all, so its absence is the failure
    // this assertion exists to catch.
    renderSwipe();

    expect(screen.getByRole("button", { name: /Show me less of this/ })).toBeInTheDocument();
  });

  it("names the event, so the reader knows which one it dismisses", () => {
    renderSwipe();

    const button = screen.getByRole("button", { name: /Show me less of this/ });
    expect(button.getAttribute("aria-label")).toContain("Brooklyn Symphony open rehearsal");
  });

  it("does the same thing the swipe does — one write, one event id", async () => {
    const { onDismissed } = renderSwipe();

    fireEvent.click(screen.getByRole("button", { name: /Show me less of this/ }));

    await waitFor(() => expect(recordDismissal).toHaveBeenCalledTimes(1));
    expect(recordDismissal).toHaveBeenCalledWith(EVENT_ID);
    await waitFor(() => expect(onDismissed).toHaveBeenCalledWith(EVENT_ID));
  });

  it("has a 44px hit area", () => {
    renderSwipe();

    expect(screen.getByRole("button", { name: /Show me less of this/ }).className).toContain(
      "min-h-[44px]",
    );
  });

  it("is quiet, so the swipe stays the primary affordance", () => {
    // The mockup's affordance is the gesture; the button is the fallback for people
    // who cannot make one. It must not compete with the card for attention.
    renderSwipe();

    const button = screen.getByRole("button", { name: /Show me less of this/ });
    expect(button.className).toContain("text-ink-muted");
  });

  it("does not say the word 'dismiss'", () => {
    // "Dismiss" is a word about the product's internals. The card speaks the user's
    // language, and the prompt's own verb is "show me less".
    renderSwipe();

    expect(screen.getByRole("button", { name: /Show me less of this/ }).textContent).not.toMatch(
      /dismiss/i,
    );
  });
});

describe("the swipe", () => {
  it("dismisses when the card is pushed past the threshold", async () => {
    const { onDismissed } = renderSwipe();

    const target = wrapper();
    fireEvent.pointerDown(target, { clientY: 0 });
    fireEvent.pointerMove(target, { clientY: SWIPE_THRESHOLD_PX + 10 });
    fireEvent.pointerUp(target, { clientY: SWIPE_THRESHOLD_PX + 10 });

    await waitFor(() => expect(recordDismissal).toHaveBeenCalledWith(EVENT_ID));
    await waitFor(() => expect(onDismissed).toHaveBeenCalledWith(EVENT_ID));
  });

  it("does not dismiss when the card is pushed less than the threshold", async () => {
    renderSwipe();

    const target = wrapper();
    fireEvent.pointerDown(target, { clientY: 0 });
    fireEvent.pointerMove(target, { clientY: SWIPE_THRESHOLD_PX - 10 });
    fireEvent.pointerUp(target, { clientY: SWIPE_THRESHOLD_PX - 10 });

    // The write is async, so give it a tick before asserting nothing happened.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(recordDismissal).not.toHaveBeenCalled();
  });

  it("ignores an upward drag, because that is a scroll", async () => {
    renderSwipe();

    const target = wrapper();
    fireEvent.pointerDown(target, { clientY: 200 });
    fireEvent.pointerMove(target, { clientY: 0 });
    fireEvent.pointerUp(target, { clientY: 0 });

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(recordDismissal).not.toHaveBeenCalled();
  });

  it("does not start a swipe that began on a control", async () => {
    // The card is covered in buttons — the confidence pulse, the source badge, the share
    // control — and a drag that began on one of them would be swallowed by the button
    // and the card would jump out from under the reader's finger.
    render(
      <SwipeDismiss
        eventId={EVENT_ID}
        title="Brooklyn Symphony open rehearsal"
        onDismissed={vi.fn()}
        onPromptDue={vi.fn()}
      >
        <article>
          <button type="button">a control</button>
        </article>
      </SwipeDismiss>,
    );

    const target = wrapper();
    const button = screen.getByRole("button", { name: "a control" });
    fireEvent.pointerDown(button, { clientY: 0 });
    fireEvent.pointerMove(target, { clientY: 200 });
    fireEvent.pointerUp(target, { clientY: 200 });

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(recordDismissal).not.toHaveBeenCalled();
  });

  it("caps how far the card travels, so a long drag does not throw it off screen", () => {
    renderSwipe();

    const target = wrapper();
    fireEvent.pointerDown(target, { clientY: 0 });
    fireEvent.pointerMove(target, { clientY: 5000 });

    expect(target.style.transform).toBe(`translateY(${MAX_TRAVEL_PX}px)`);
  });

  it("puts the card back when the gesture did not reach the threshold", () => {
    renderSwipe();

    const target = wrapper();
    fireEvent.pointerDown(target, { clientY: 0 });
    fireEvent.pointerMove(target, { clientY: 10 });
    fireEvent.pointerUp(target, { clientY: 10 });

    expect(target.style.transform).toBe("");
  });
});

describe("what the client does not decide", () => {
  it("does not count dismissals — it asks the server and renders the answer", async () => {
    // The cosine threshold, the 24-hour window, the three-distinct-events rule and the
    // rage-dismiss guard are all server facts. A client that counted for itself would
    // be answering the server's question with a different number.
    const { onPromptDue } = renderSwipe();
    recordDismissal.mockResolvedValue(PROMPTED);

    const target = wrapper();
    fireEvent.pointerDown(target, { clientY: 0 });
    fireEvent.pointerMove(target, { clientY: SWIPE_THRESHOLD_PX + 10 });
    fireEvent.pointerUp(target, { clientY: SWIPE_THRESHOLD_PX + 10 });

    await waitFor(() => expect(onPromptDue).toHaveBeenCalledTimes(1));
    // **The server's copy, verbatim.** The client writes none of it.
    expect(onPromptDue).toHaveBeenCalledWith(PROMPTED.prompt);
  });

  it("does not open the prompt when the server says the cluster has not completed", async () => {
    const { onPromptDue } = renderSwipe();
    recordDismissal.mockResolvedValue(ADVANCED);

    const target = wrapper();
    fireEvent.pointerDown(target, { clientY: 0 });
    fireEvent.pointerMove(target, { clientY: SWIPE_THRESHOLD_PX + 10 });
    fireEvent.pointerUp(target, { clientY: SWIPE_THRESHOLD_PX + 10 });

    await waitFor(() => expect(recordDismissal).toHaveBeenCalled());
    expect(onPromptDue).not.toHaveBeenCalled();
  });

  it("does not open the prompt when the server says the dismissal did not count", async () => {
    // A dismissal the rage-dismiss guard rejected did not advance the counter, so it
    // cannot complete a cluster — and the client has no way to know that.
    const { onPromptDue, onDismissed } = renderSwipe();
    recordDismissal.mockResolvedValue({ cluster_advanced: false, prompt_due: false, prompt: null });

    const target = wrapper();
    fireEvent.pointerDown(target, { clientY: 0 });
    fireEvent.pointerMove(target, { clientY: SWIPE_THRESHOLD_PX + 10 });
    fireEvent.pointerUp(target, { clientY: SWIPE_THRESHOLD_PX + 10 });

    await waitFor(() => expect(onDismissed).toHaveBeenCalled());
    expect(onPromptDue).not.toHaveBeenCalled();
  });
});

describe("a dismissal the server refused", () => {
  it("leaves the card where it was", async () => {
    // **A card that vanished without a recorded dismissal would come back in the next
    // digest with no explanation.** So a failed write dismisses nothing.
    const { onDismissed } = renderSwipe();
    recordDismissal.mockResolvedValue(null);

    const target = wrapper();
    fireEvent.pointerDown(target, { clientY: 0 });
    fireEvent.pointerMove(target, { clientY: SWIPE_THRESHOLD_PX + 10 });
    fireEvent.pointerUp(target, { clientY: SWIPE_THRESHOLD_PX + 10 });

    await waitFor(() => expect(recordDismissal).toHaveBeenCalled());
    expect(onDismissed).not.toHaveBeenCalled();
    expect(target.style.transform).toBe("");
  });

  it("re-enables the button, so the user can try again", async () => {
    renderSwipe();
    recordDismissal.mockResolvedValue(null);

    fireEvent.click(screen.getByRole("button", { name: /Show me less of this/ }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Show me less of this/ })).not.toBeDisabled(),
    );
  });

  it("ignores a second swipe while the first is in flight", async () => {
    // The server is idempotent per event, so a repeat would not corrupt anything — but
    // it would open the prompt twice, and a prompt that appears twice is the nag
    // FR-25's guard exists to prevent.
    renderSwipe();
    let release: (value: unknown) => void = () => {};
    recordDismissal.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /Show me less of this/ }));
    fireEvent.click(screen.getByRole("button", { name: /Show me less of this/ }));

    await waitFor(() => expect(recordDismissal).toHaveBeenCalledTimes(1));
    release(ADVANCED);
    await waitFor(() => expect(recordDismissal).toHaveBeenCalledTimes(1));
  });
});
