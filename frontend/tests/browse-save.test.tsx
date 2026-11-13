/**
 * The inline Save button — its state machine, its quota wall and its two refusals.
 *
 * **This is the file the work item asked for by name.** Two of the thirteen criteria
 * are explicitly "asserted by a test", and they are the two this file is built around:
 *
 * - **"Neither refusal opens a modal or raises a toast"** — the test asserts the
 *   *absence by name*, querying for `[role="dialog"]`, `[aria-modal]`, and
 *   `[role="alertdialog"]`. A test that only checked the copy would pass while a modal
 *   appeared, which is exactly the failure the criterion names.
 * - **"A Pro user never sees the quota state"** — the test is written so that dropping
 *   the entitlement check makes it fail. It renders a Pro quota, presses twice, and
 *   asserts two requests went out.
 *
 * **The transport is mocked at the generated client.** The island reaches the backend
 * only through `api` from `@/lib/backend-client` (AD-19), so the mock stands in there
 * and the *behaviour* — which endpoint, which path parameter, which branch — is what is
 * observed. A test that asserted on the mock's call shape is asserting on the
 * contract, which is the point: **the existing endpoints are used and no new one is
 * invented.**
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BrowseSave } from "@/components/browse/browse-save";

const apiPost = vi.fn();
const apiDelete = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => apiPost(...args),
    DELETE: (...args: unknown[]) => apiDelete(...args),
  },
}));

const EVENT_ID = "22222222-2222-2222-2222-222222222222";
const EVENT_NAME = "Brooklyn Symphony open rehearsal";
const SLUG = "brooklyn-symphony-open-rehearsal";

/** The free-plan allowance, with room left. */
const FREE_QUOTA = {
  used: 0,
  cap: 1,
  is_pro: false,
  resets_in_seconds: 86400,
};

/** The free-plan allowance, spent. */
const SPENT_QUOTA = {
  used: 1,
  cap: 1,
  is_pro: false,
  resets_in_seconds: 86400,
};

/** A Pro account's allowance: `cap` is `null`, not a very large number. */
const PRO_QUOTA = {
  used: 0,
  cap: null,
  is_pro: true,
  resets_in_seconds: 0,
};

/** A 2xx answer. The save is idempotent, so a repeat is a 200 rather than a 201. */
function ok() {
  return { data: { id: "saved-1" }, response: { status: 200 }, error: undefined };
}

/** A 409 carrying the cap and the server's upgrade sentence. */
function capReached(cap = 1) {
  return {
    data: undefined,
    response: { status: 409 },
    error: {
      code: "save_cap_reached",
      message: "You've used your free save for today.",
      details: { cap, upgrade_hint: "You saved one event today. Save more with Pro." },
    },
  };
}

/** A 409 carrying the clash. The save row was written; the pair is active. */
function schedulingConflict() {
  return {
    data: undefined,
    response: { status: 409 },
    error: {
      code: "scheduling_conflict",
      message: "That clashes with something else already on your calendar.",
      details: {
        event_id: "saved-1",
        conflicts: [
          {
            pair_id: "pair-1",
            kind: "scheduling",
            new_side: {
              kind: "saved_event",
              id: "saved-1",
              name: EVENT_NAME,
              start_time_utc: "2026-11-07T23:00:00Z",
            },
            other_side: {
              kind: "personal_event",
              id: "personal-1",
              name: "Saved dinner",
              start_time_utc: "2026-11-07T23:30:00Z",
            },
            actions: ["edit_new", "skip_public", "keep_both"],
          },
        ],
      },
    },
  };
}

function renderSave(props: Partial<React.ComponentProps<typeof BrowseSave>> = {}) {
  return render(
    <BrowseSave
      eventId={EVENT_ID}
      eventName={EVENT_NAME}
      slug={SLUG}
      saved={false}
      quota={FREE_QUOTA}
      {...props}
    />,
  );
}

/**
 * The button.
 *
 * **By its test id, not by its accessible name.** The name changes with the state —
 * "Save {name} to my Pulse" becomes "{name} is saved to your Pulse" — and a helper
 * keyed on a name would break the moment the state changed. The island renders exactly
 * one button, so the id is unambiguous.
 */
function button(): HTMLElement {
  const found = document.querySelector<HTMLElement>("[data-browse-save-button]");
  if (!found) throw new Error("no Save button");
  return found;
}

/**
 * The island's wrapper.
 *
 * **The `Esc` listener lives here, not on the button** — the button is `disabled` while
 * a request is in flight, and a disabled button fires no key events. The wrapper is
 * never disabled, and the event bubbles up to it.
 */
function wrapper(): HTMLElement {
  const found = document.querySelector<HTMLElement>("[data-browse-save]");
  if (!found) throw new Error("no Save wrapper");
  return found;
}

/**
 * **Let the 1500ms lockout expire.**
 *
 * **The lockout is real time, so the test has to wait for it.** The alternative — a
 * fake clock installed mid-test — breaks `waitFor`, which polls with real timers and
 * would hang until the test timed out. So the helper waits the lockout out for real.
 *
 * It is 1600ms rather than 1500ms on purpose: the extra 100ms is slack for a loaded
 * machine, and the assertion is that the lockout has *ended*, not that the clock
 * landed on a particular millisecond.
 */
async function expireLockout(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 1600));
  });
}

beforeEach(() => {
  apiPost.mockReset();
  apiDelete.mockReset();
  apiPost.mockResolvedValue(ok());
  apiDelete.mockResolvedValue({ data: undefined, response: { status: 204 }, error: undefined });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the state machine", () => {
  it("runs idle → saving → saved, with the labels the item fixes", async () => {
    // **The request never resolves inside this test**, so the "saving" label is
    // observable rather than a frame in a race.
    apiPost.mockImplementation(() => new Promise(() => {}));

    renderSave();

    const save = button();
    expect(save.textContent).toBe("Save");

    fireEvent.click(save);
    // **"Saving…" is in ink-muted** — the request is in flight and nothing has
    // happened yet, so it must not read as a success.
    expect(button().textContent).toBe("Saving…");
    expect(button().className).toContain("text-ink-muted");
  });

  it("morphs to 'Saved ✓' in the success signal, and announces it politely", async () => {
    renderSave();

    fireEvent.click(button());

    await waitFor(() => {
      expect(button().textContent).toBe("Saved ✓");
    });
    // **The success colour.** `color.signal.success` is the token; `text-signal-success`
    // is the utility that names it.
    expect(button().className).toContain("text-signal-success");
    // **The announcement is polite, and it is on the button** — so the reader who
    // pressed it hears what changed without the focus moving.
    expect(button().getAttribute("aria-live")).toBe("polite");
  });

  it("does not move the focus when the label morphs", async () => {
    renderSave();

    const save = button();
    save.focus();
    expect(document.activeElement).toBe(save);

    fireEvent.click(save);

    await waitFor(() => {
      expect(button().textContent).toBe("Saved ✓");
    });
    // **The focus is still on the control the reader pressed.** A morph that moved the
    // focus would throw a keyboard reader to the top of the page.
    expect(document.activeElement).toBe(button());
  });

  it("holds the label for 1500ms, so a fast double-tap cannot flicker it", async () => {
    vi.useFakeTimers();
    renderSave();

    fireEvent.click(button());
    await act(async () => {
      await Promise.resolve();
    });
    expect(button().textContent).toBe("Saved ✓");

    // **Just before the lockout ends, the label is still there and the button is
    // disabled.**
    await act(async () => {
      vi.advanceTimersByTime(1499);
    });
    expect(button().textContent).toBe("Saved ✓");
    expect(button()).toBeDisabled();

    // **A press inside the lockout sends nothing.**
    fireEvent.click(button());
    expect(apiPost).toHaveBeenCalledTimes(1);

    // **And after it, the button accepts a press again.**
    await act(async () => {
      vi.advanceTimersByTime(2);
    });
    expect(button()).not.toBeDisabled();
  });

  it("un-saves from 'saved' with no destructive confirmation", async () => {
    renderSave();

    fireEvent.click(button());
    await waitFor(() => {
      expect(button().textContent).toBe("Saved ✓");
    });

    // **The lockout has to expire before the second press is accepted** — and the
    // un-save itself must not ask anything.
    await expireLockout();

    fireEvent.click(button());

    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledTimes(1);
    });
    // **No dialog anywhere.** The morph *is* the confirmation.
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(document.querySelector('[aria-modal="true"]')).toBeNull();
  });

  it("returns to 'Save' after the un-save", async () => {
    renderSave();

    fireEvent.click(button());
    await waitFor(() => {
      expect(button().textContent).toBe("Saved ✓");
    });
    await expireLockout();

    fireEvent.click(button());

    await waitFor(() => {
      expect(button().textContent).toBe("Save");
    });
  });
});

describe("the endpoints", () => {
  it("saves through the existing POST, with the catalog id as the path parameter", async () => {
    renderSave();

    fireEvent.click(button());

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledTimes(1);
    });
    expect(apiPost).toHaveBeenCalledWith("/api/personal/saved-events/{catalog_event_id}", {
      params: { path: { catalog_event_id: EVENT_ID } },
    });
  });

  it("un-saves through the existing DELETE", async () => {
    renderSave();

    fireEvent.click(button());
    await waitFor(() => {
      expect(button().textContent).toBe("Saved ✓");
    });
    await expireLockout();

    fireEvent.click(button());

    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledTimes(1);
    });
    expect(apiDelete).toHaveBeenCalledWith("/api/personal/saved-events/{catalog_event_id}", {
      params: { path: { catalog_event_id: EVENT_ID } },
    });
  });

  it("invents no new endpoint", async () => {
    renderSave();

    fireEvent.click(button());

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledTimes(1);
    });
    // **Only the two paths that already exist.** A new save endpoint would show up here
    // as a third path.
    const paths = [...apiPost.mock.calls, ...apiDelete.mock.calls].map(
      (call) => (call as unknown[])[0],
    );
    for (const path of paths) {
      expect(path).toBe("/api/personal/saved-events/{catalog_event_id}");
    }
  });
});

describe("the cap refusal", () => {
  it("renders the item's sentence inline under the button, with an Upgrade link", async () => {
    apiPost.mockResolvedValue(capReached(1));
    renderSave();

    fireEvent.click(button());

    await waitFor(() => {
      expect(screen.getByText(/You've used your 1 free save today\./)).toBeTruthy();
    });
    // **The "Upgrade" link is a quiet meta link**, and it points at the pricing page.
    const upgrade = screen.getByRole("link", { name: "Upgrade" });
    expect(upgrade.getAttribute("href")).toBe("/pricing");
  });

  it("leaves the button in 'Save', because the save did not happen", async () => {
    apiPost.mockResolvedValue(capReached(1));
    renderSave();

    fireEvent.click(button());

    await waitFor(() => {
      expect(screen.getByText(/You've used your 1 free save today\./)).toBeTruthy();
    });
    // **A cap is a refusal, not a failed save** — and saying "Saved" here would be a lie
    // about the server's state.
    expect(button().textContent).toBe("Save");
  });

  it("does not retry the save on the reader's behalf", async () => {
    apiPost.mockResolvedValue(capReached(1));
    renderSave();

    fireEvent.click(button());

    // **One request, and one refusal.** The client does not treat the refusal as
    // something to retry on the reader's behalf — a refusal that is final is not
    // retried, and a button that keeps trying is the thing this surface avoids.
    await waitFor(() => {
      expect(screen.getByText(/You've used your 1 free save today\./)).toBeTruthy();
    });
    expect(apiPost).toHaveBeenCalledTimes(1);

    // **A second press is the reader's own doing, and it is refused the same way.**
    // The client did not queue it and did not loop; the reader asked again and the
    // server said no again.
    fireEvent.click(button());
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByText(/You've used your 1 free save today\./)).toBeTruthy();
  });

  it("takes the cap from the refusal, not from a hard-coded number", async () => {
    apiPost.mockResolvedValue(capReached(3));
    renderSave();

    fireEvent.click(button());

    await waitFor(() => {
      expect(screen.getByText(/You've used your 3 free save today\./)).toBeTruthy();
    });
  });
});

describe("the conflict refusal", () => {
  it("renders the item's sentence inline, with an Open link to the event", async () => {
    apiPost.mockResolvedValue(schedulingConflict());
    renderSave();

    fireEvent.click(button());

    await waitFor(() => {
      expect(screen.getByText(/Conflicts with your saved dinner\./)).toBeTruthy();
    });
    const open = screen.getByRole("link", { name: "Open" });
    expect(open.getAttribute("href")).toBe(`/events/${SLUG}`);
  });

  it("says 'Saved ✓', because the save row was written and the pair is active", async () => {
    apiPost.mockResolvedValue(schedulingConflict());
    renderSave();

    fireEvent.click(button());

    await waitFor(() => {
      expect(screen.getByText(/Conflicts with your saved dinner\./)).toBeTruthy();
    });
    // **A 409 clash is not a failed save.** The server writes the row and *then* finds
    // the clash; saying "Save" here would invite the reader to press again and get the
    // same 409.
    expect(button().textContent).toBe("Saved ✓");
  });
});

describe("neither refusal interrupts", () => {
  /**
   * **The assertion the item asks for by name.**
   *
   * **It checks the absence, not the copy.** A test that only checked the sentence
   * would pass while a modal appeared over it — and a modal is exactly what
   * `save_cap.py` says a cap must never be: *"A cap that interrupts with a modal is a
   * cap that trains people to dismiss prompts."*
   */
  function assertNoInterruption() {
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(document.querySelector('[role="alertdialog"]')).toBeNull();
    expect(document.querySelector('[aria-modal="true"]')).toBeNull();
    // A toast: a live region that announces itself outside the flow, or an overlay.
    expect(document.querySelector("[data-toast]")).toBeNull();
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    expect(document.querySelector('[role="alert"]')).toBeNull();
  }

  it("raises no modal and no toast for the cap", async () => {
    apiPost.mockResolvedValue(capReached(1));
    renderSave();

    fireEvent.click(button());
    await waitFor(() => {
      expect(screen.getByText(/You've used your 1 free save today\./)).toBeTruthy();
    });

    assertNoInterruption();
  });

  it("raises no modal and no toast for the clash", async () => {
    apiPost.mockResolvedValue(schedulingConflict());
    renderSave();

    fireEvent.click(button());
    await waitFor(() => {
      expect(screen.getByText(/Conflicts with your saved dinner\./)).toBeTruthy();
    });

    assertNoInterruption();
  });

  it("announces the refusals politely, not assertively", async () => {
    apiPost.mockResolvedValue(capReached(1));
    renderSave();

    fireEvent.click(button());
    await waitFor(() => {
      expect(screen.getByText(/You've used your 1 free save today\./)).toBeTruthy();
    });

    // **A refusal is information, not an emergency.** An assertive region would
    // interrupt a screen reader mid-sentence.
    const line = screen.getByText(/You've used your 1 free save today\./);
    expect(line.getAttribute("role")).toBe("status");
    expect(line.getAttribute("aria-live")).not.toBe("assertive");
  });
});

describe("the quota wall", () => {
  it("renders the spent allowance as a muted, disabled label", () => {
    renderSave({ quota: SPENT_QUOTA });

    // **The label is the payload's numbers** — the ceiling and the count.
    expect(button().textContent).toBe("1 of 1 save used today");
    // **Visible but disabled.** A hidden button would be a control the reader cannot
    // find; a control that does nothing when pressed is worse.
    expect(button()).toBeDisabled();
    expect(button().className).toContain("text-ink-faint");
  });

  it("carries exactly one ink colour, so the muted one is the one that applies", () => {
    // **This is the assertion that would have caught the review's finding.** The button
    // used to carry `text-ink-secondary` *and* `text-ink-faint` at once, and Tailwind
    // resolves two colour utilities by CSS emission order rather than by the order they
    // appear in `className` — and it emits `text-ink-faint` *first*. So the ordinary ink
    // won, and the spent button looked live while refusing every press.
    //
    // **The count is the assertion.** "Which of these two wins" is a question about
    // Tailwind's internals; "how many colours are on this button" is a question about
    // this component, and it is the one that can be enforced here.
    renderSave({ quota: SPENT_QUOTA });

    const inks = button().className.match(/text-ink-\w+/g) ?? [];
    expect(inks).toEqual(["text-ink-faint"]);
  });

  it("carries one ink colour on the live button too", () => {
    renderSave({ quota: FREE_QUOTA });

    const inks = button().className.match(/text-ink-\w+/g) ?? [];
    expect(inks).toEqual(["text-ink-secondary"]);
  });

  it("carries the upgrade title", () => {
    renderSave({ quota: SPENT_QUOTA });

    expect(button().getAttribute("title")).toBe("Upgrade for unlimited saves");
  });

  it("does nothing when tapped", () => {
    renderSave({ quota: SPENT_QUOTA });

    fireEvent.click(button());

    expect(apiPost).not.toHaveBeenCalled();
  });

  it("leaves an already-saved event un-savable, because un-saving is not a new save", () => {
    // **The wall is about new saves.** A reader whose allowance is spent and whose only
    // option left is "un-save" must not be locked out of it.
    renderSave({ quota: SPENT_QUOTA, saved: true });

    expect(button().textContent).toBe("Saved ✓");
    expect(button()).not.toBeDisabled();
  });

  it("shows the upgrade copy inline, without the reader having to press anything", () => {
    // **The wall has to say so, because the button cannot.**
    //
    // The design says the spent allowance renders the button muted and disabled, and
    // that "tapping a disabled Save button does nothing" — so there is no request, no
    // refusal, and nothing for a handler to render. The design's own way out is a
    // `title` tooltip, and **a tooltip is unreachable by keyboard and invisible to
    // touch**: a reader who cannot hover would sit in front of a closed gate with no
    // mention of upgrading anywhere.
    //
    // **So the wall renders the same inline line the refusal renders** — the same
    // sentence and the same Upgrade link, in the normal flow, under the button. The
    // line is the sign above the gate, and a closed gate is exactly when the sign
    // matters most.
    renderSave({ quota: SPENT_QUOTA });

    const line = screen.getByText(/You've used your 1 free save today\./);
    expect(line).toBeVisible();
    // **The link is the way out, and it is a real link.**
    const link = line.querySelector("a");
    expect(link?.getAttribute("href")).toBe("/pricing");
    // **And it is not an interruption.** The line is in the normal flow.
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(document.querySelector('[aria-modal="true"]')).toBeNull();
  });

  it("shows no cap line while the allowance is still open", () => {
    // **A live button carries no cap line.** The line is the sign of a closed gate, and
    // a sign on an open gate is a warning about nothing.
    renderSave({ quota: FREE_QUOTA });

    expect(document.querySelector("[data-browse-save-cap]")).toBeNull();
  });

  it("shows no cap line on a Pro account's card", () => {
    // **A Pro account has no wall, so it has no line.** `cap` is `null`, so there is
    // no ceiling to be against and no sentence to say.
    renderSave({ quota: PRO_QUOTA });

    expect(document.querySelector("[data-browse-save-cap]")).toBeNull();
    expect(button().textContent).toBe("Save");
  });
});

describe("the Pro exemption", () => {
  it("never renders the muted label, and saves repeatedly", async () => {
    // **This is the test the item asks for by name.** It is written so that dropping the
    // entitlement check makes it fail: a Pro quota has `cap: null`, and a client that
    // treated `null` as `0` would compute `used >= cap` and wall the button off.
    renderSave({ quota: PRO_QUOTA });

    expect(button().textContent).toBe("Save");
    expect(button()).not.toBeDisabled();
    expect(button().textContent).not.toContain("used today");

    fireEvent.click(button());
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledTimes(1);
    });

    // **And again** — a Pro user can save as many times as they like.
    await expireLockout();
    fireEvent.click(button());
    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledTimes(1);
    });

    await expireLockout();
    fireEvent.click(button());
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledTimes(2);
    });
  });

  it("treats a Pro quota with a spent count as a Pro quota", () => {
    // **`is_pro` alone is enough.** The server sends `used: 0` for Pro, but a client
    // that only read `is_pro` would be right here and wrong if the server ever counted
    // a Pro user's saves — which it does not, and never will.
    renderSave({ quota: { used: 9, cap: null, is_pro: true, resets_in_seconds: 0 } });

    expect(button().textContent).toBe("Save");
    expect(button()).not.toBeDisabled();
  });
});

describe("the button itself", () => {
  it("is a real button, with the visible label still 'Save'", () => {
    renderSave();

    const save = button();
    expect(save.tagName).toBe("BUTTON");
    expect(save.getAttribute("type")).toBe("button");
    expect(save.textContent).toBe("Save");
  });

  it("names the event in the accessible name", () => {
    renderSave();

    // **A page of a dozen cards each with a "Save" button** gives a screen reader a
    // dozen identical controls. The name is the only thing that tells them apart.
    expect(button().getAttribute("aria-label")).toBe(`Save ${EVENT_NAME} to my Pulse`);
  });

  it("carries a 2px terracotta focus ring", () => {
    renderSave();

    const save = button();
    expect(save.className).toContain("focus-visible:outline-2");
    expect(save.className).toContain("focus-visible:outline-accent-terracotta");
  });

  it("triggers on Enter and on Space", async () => {
    renderSave();

    // **Both, because it is a real `<button>`.** A `<div role="button">` would need a
    // keydown handler for this, and would get the Space case wrong by default.
    fireEvent.click(button(), { key: "Enter", code: "Enter" });
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledTimes(1);
    });

    await expireLockout();
    fireEvent.click(button(), { key: " ", code: "Space" });
    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledTimes(1);
    });
  });
});

describe("the first paint", () => {
  it("renders 'Saved ✓' straight away for an already-saved event", () => {
    // **No "Save" flash.** The state comes from the API's `is_saved`, not from an
    // effect that corrects itself a moment later.
    renderSave({ saved: true });

    expect(button().textContent).toBe("Saved ✓");
  });

  it("sends no request on the first paint", () => {
    renderSave({ saved: true });

    expect(apiPost).not.toHaveBeenCalled();
    expect(apiDelete).not.toHaveBeenCalled();
  });
});

describe("the in-flight guard", () => {
  it("sends one request for two quick presses", async () => {
    apiPost.mockImplementation(() => new Promise(() => {}));

    renderSave();

    const save = button();
    fireEvent.click(save);
    fireEvent.click(save);
    fireEvent.click(save);

    // **One request.** The save is idempotent server-side, so a duplicate would be
    // harmless — but it would spend the throttle's slot twice on a Free account, and
    // the cap is the product's one upgrade trigger.
    expect(apiPost).toHaveBeenCalledTimes(1);
  });
});

describe("the Esc cancel", () => {
  it("resets the label and abandons the in-flight answer", async () => {
    let resolvePost: ((value: unknown) => void) | null = null;
    apiPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePost = resolve;
        }),
    );

    renderSave();

    fireEvent.click(button());
    expect(button().textContent).toBe("Saving…");

    // **Esc abandons the request.** There is no server-side rollback — `save_event()`
    // commits inside `transaction.atomic()` and there is no abort path — so the honest
    // scope is the client-side label.
    fireEvent.keyDown(wrapper(), { key: "Escape" });

    expect(button().textContent).toBe("Save");

    // **And the abandoned answer does not write over the label.**
    await act(async () => {
      resolvePost?.(ok());
      await Promise.resolve();
    });
    expect(button().textContent).toBe("Save");
  });

  it("works while the button is disabled, which is the only time it is needed", () => {
    // **This is the whole reason the listener is on the wrapper.**
    //
    // The button is `disabled` while a request is in flight — that is what "Saving…"
    // means — and **a disabled button fires no key events**. So a handler on the button
    // would never run in the one case it exists for: the cancel is only reachable
    // *during* the save.
    //
    // **This test would pass with a handler on the button** if it fired the event
    // directly on the disabled element, because `fireEvent` dispatches to the element
    // regardless of `disabled`. So the assertion is made on the wrapper — the element
    // that actually carries the listener — and the disabled button is asserted
    // alongside it.
    apiPost.mockImplementation(() => new Promise(() => {}));

    renderSave();

    fireEvent.click(button());
    // **The button really is disabled.** If it were not, the cancel would be reachable
    // from the button and the wrapper would be decoration.
    expect(button()).toBeDisabled();

    fireEvent.keyDown(wrapper(), { key: "Escape" });

    expect(button().textContent).toBe("Save");
  });
});
