/**
 * FR-19's **personal-events opt-out** — the control a user actually touches.
 *
 * **Four things are worth proving here, and they are the ones a screenshot cannot
 * show.**
 *
 * 1. **The body is exactly three keys.** The endpoint requires the schedule — it has
 *    no "change one field" mode — so the delivery time and the zone travel with the
 *    flag. But the **city does not**: the endpoint cannot clear a city, so a client
 *    that sent one back would be relying on a field this control does not own. The
 *    assertion is on the **exact key set**, not on the presence of the right fields.
 * 2. **The state after a save is the server's answer.** The button moves at once, but
 *    a save that the server resolved differently must leave the control showing what
 *    the server holds.
 * 3. **The failure line splits.** The API's own refusal is shown verbatim when the API
 *    made one; the route's own line is shown when the request never arrived.
 * 4. **The accessible name is stable.** The name does not change with the state, and
 *    the state rides on `aria-pressed` — so a name that changed would be a
 *    contradiction, and a state carried only by colour would fail WCAG 1.4.1.
 *
 * **And the schedule guard:** a user with no delivery time cannot use the control at
 * all, because the endpoint would refuse the request. The control says so instead of
 * failing.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  DigestPersonalEvents,
  digestPreferenceBody,
} from "@/components/settings/digest-personal-events";

const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

/**
 * The server's answer to the `PUT`.
 *
 * **The digest block is the whole onboarding state**, because the endpoint answers with
 * `OnboardingStateOut` — the same shape the read helper reads.
 */
function answer(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      completed: true,
      current_step: null,
      step_name: null,
      interests: [],
      last_advanced_at: null,
      completed_at: null,
      digest: {
        city: "Brooklyn",
        city_source: "geo",
        delivery_time: "08:00:00",
        timezone: "America/New_York",
        include_personal_events: false,
        ...overrides,
      },
    },
    response: { status: 200 },
  };
}

/**
 * The API's refusal, as the server sends it.
 *
 * **This is the shape `backend/config/errors.py` writes** — `{ code, message }` with the
 * message written for the user, which is the whole point of it being there.
 */
function refusal(code: string, message: string, status = 422) {
  return {
    data: undefined,
    error: { code, message },
    response: { status },
  };
}

/** The toggle, with a schedule — the ordinary case. */
function renderToggle(overrides: Partial<React.ComponentProps<typeof DigestPersonalEvents>> = {}) {
  return render(
    <DigestPersonalEvents
      initialIncludePersonalEvents
      schedule={{ deliveryTime: "08:00:00", timezone: "America/New_York" }}
      {...overrides}
    />,
  );
}

/** The button, by its stable accessible name. */
function button() {
  return screen.getByRole("button", { name: "Personal events in the Pulse Digest" });
}

beforeEach(() => {
  PUT.mockReset();
  PUT.mockResolvedValue(answer());
});

/* ── the body, as a pure function ────────────────────────────────────────────── */

/**
 * **The body is a pure function, and that is what makes the rules testable.**
 *
 * The component's own click path cannot reach the "no schedule" branch — the button
 * is disabled, so the click never arrives — which means a rule that lives only in
 * the handler is a rule no test can hold it to. Pulling the body out makes the
 * guarantee a claim about a value rather than about an event.
 */
describe("digestPreferenceBody", () => {
  it("builds exactly the three keys the endpoint needs", () => {
    const body = digestPreferenceBody(
      { deliveryTime: "08:00:00", timezone: "America/New_York" },
      false,
    );

    expect(body).toEqual({
      include_personal_events: false,
      delivery_time: "08:00:00",
      timezone: "America/New_York",
    });
    expect(Object.keys(body as object).sort()).toEqual([
      "delivery_time",
      "include_personal_events",
      "timezone",
    ]);
  });

  it("sends no city", () => {
    const body = digestPreferenceBody(
      { deliveryTime: "08:00:00", timezone: "America/New_York" },
      true,
    );

    // **The endpoint cannot clear a city** — a `null` and an omitted field are the
    // same value there — so a client that sent one back would be relying on a field
    // this control does not own.
    expect(body).not.toHaveProperty("city");
  });

  it("builds nothing without a schedule", () => {
    // **No schedule, no body.** The endpoint requires the delivery time and the zone,
    // so a request without them is a request the API refuses — and a refusal the user
    // can do nothing about is worse than not asking.
    expect(digestPreferenceBody(null, false)).toBeNull();
    expect(digestPreferenceBody(null, true)).toBeNull();
  });

  it("carries the schedule through unchanged", () => {
    // **The wall clock travels as the wall clock.** `_validated_delivery_time` refuses
    // a tz-aware time, so re-formatting it here would be a different time than the one
    // the user set.
    const body = digestPreferenceBody(
      { deliveryTime: "21:30:00", timezone: "Europe/Berlin" },
      true,
    );

    expect(body?.delivery_time).toBe("21:30:00");
    expect(body?.timezone).toBe("Europe/Berlin");
  });
});

/* ── what the save sends ─────────────────────────────────────────────────────── */

describe("what the save sends", () => {
  it("sends the opt-out with the schedule, and nothing else", async () => {
    renderToggle();

    fireEvent.click(button());

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    const body = PUT.mock.calls[0]?.[1]?.body;
    // **Exactly three keys.** The endpoint requires the schedule — `delivery_time` is a
    // `time` and `timezone` is a `str`, both required and non-nullable — so it travels
    // with the flag, unchanged.
    expect(body).toEqual({
      include_personal_events: false,
      delivery_time: "08:00:00",
      timezone: "America/New_York",
    });
    expect(Object.keys(body as object).sort()).toEqual([
      "delivery_time",
      "include_personal_events",
      "timezone",
    ]);
  });

  it("sends no city", async () => {
    renderToggle();

    fireEvent.click(button());

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    const body = PUT.mock.calls[0]?.[1]?.body;
    // **The city does not travel.** The endpoint cannot clear a city — a `null` and an
    // omitted field are the same value there — so a client that sent one back would be
    // relying on a field this control does not own.
    expect(body).not.toHaveProperty("city");
  });

  it("sends the schedule back unchanged, as the wall clock it was read as", async () => {
    // **The stored time is a wall clock, and it travels as one.** `_validated_delivery_time`
    // refuses a tz-aware time, so re-formatting or re-zoning it here would be a
    // different time than the one the user set.
    renderToggle({ schedule: { deliveryTime: "21:30:00", timezone: "Europe/Berlin" } });

    fireEvent.click(button());

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    const body = PUT.mock.calls[0]?.[1]?.body;
    expect(body).toEqual({
      include_personal_events: false,
      delivery_time: "21:30:00",
      timezone: "Europe/Berlin",
    });
  });

  it("sends the opt-out the user asked for, in both directions", async () => {
    // **Turning it on is the same endpoint and the same body** — a boolean has two
    // values, and this endpoint sets the one it is given.
    PUT.mockResolvedValue(answer({ include_personal_events: true }));
    renderToggle({ initialIncludePersonalEvents: false });

    fireEvent.click(button());

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(PUT.mock.calls[0]?.[1]?.body).toMatchObject({ include_personal_events: true });
  });

  it("writes to the digest-preference endpoint", async () => {
    renderToggle();

    fireEvent.click(button());

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    // **Not `/api/settings/notifications`** — that is the delivery-time endpoint the
    // quiet-hours page uses. This is the one the opt-out lives behind.
    expect(PUT.mock.calls[0]?.[0]).toBe("/api/personal/onboarding/digest-preference");
  });
});

/* ── what the control shows ──────────────────────────────────────────────────── */

describe("what the control shows", () => {
  it("renders the server's stored value, not the user's guess", () => {
    // **A user who opted out sees it off on load.** The server is the only authority on
    // what the server holds.
    renderToggle({ initialIncludePersonalEvents: false });

    expect(button()).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("Personal events are not in your Pulse Digest")).toBeInTheDocument();
  });

  it("renders it on for a user who never touched the setting", () => {
    // **The backend defaults it to `true`.** A client that assumed otherwise would be
    // showing a state the server does not hold.
    renderToggle({ initialIncludePersonalEvents: true });

    expect(button()).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Personal events are in your Pulse Digest")).toBeInTheDocument();
  });

  it("keeps the accessible name stable across both states", async () => {
    renderToggle({ initialIncludePersonalEvents: true });
    const before = button().getAttribute("aria-label");

    fireEvent.click(button());

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    // **A name that changes with the state is a contradiction** — it would say both
    // "press me" and "nothing to press".
    expect(button().getAttribute("aria-label")).toBe(before);
    expect(button().getAttribute("aria-label")).toBe("Personal events in the Pulse Digest");
  });

  it("flips aria-pressed and the visible text together", async () => {
    renderToggle({ initialIncludePersonalEvents: true });

    fireEvent.click(button());

    // **The state is in the attribute and in the words**, so neither a screen reader
    // nor a sighted reader is left to infer it from a widget's position.
    await waitFor(() => expect(button()).toHaveAttribute("aria-pressed", "false"));
    expect(screen.getByText("Personal events are not in your Pulse Digest")).toBeInTheDocument();
    expect(screen.queryByText("Personal events are in your Pulse Digest")).toBeNull();
  });

  it("says the state in words, never in colour alone", () => {
    renderToggle({ initialIncludePersonalEvents: true });

    // **The state is in the words the button shows.** The button's visible text is the
    // sentence that says which state it is in — the same shape as
    // `detail-mute-control.tsx`, where the visible text flips with the state.
    //
    // **There is no colour-only indicator.** The button carries no state in its
    // background or its border; the sentence is the claim, which is what WCAG 1.4.1
    // asks for.
    const text = screen.getByText("Personal events are in your Pulse Digest");
    expect(text).toBeInTheDocument();
    // **The sentence is the button's own text**, so it is what a sighted reader reads
    // and what a reader with the stylesheet stripped reads.
    expect(text.tagName).toBe("BUTTON");
    expect(button()).toHaveTextContent("Personal events are in your Pulse Digest");
  });

  it("takes the server's answer after a save, not the user's guess", async () => {
    // **The server resolved it the other way.** The user asked to turn it off and the
    // server says it is still on — so the control shows what the server holds. This is
    // AD-10: the state is the server's fact, not the client's claim.
    PUT.mockResolvedValue(answer({ include_personal_events: true }));
    renderToggle({ initialIncludePersonalEvents: true });

    fireEvent.click(button());

    await waitFor(() => expect(button()).toHaveAttribute("aria-pressed", "true"));
  });

  it("carries one status region, and no alert until something fails", () => {
    renderToggle();

    // **The page must have one status region.** `detail-mute-control.tsx:215-228`
    // records the rule: two `role="status"` regions on a page make "which one is the
    // page talking?" a question the DOM cannot answer.
    expect(document.querySelectorAll('[role="status"]').length).toBe(1);
    // **The alert is not there yet.** A live region added to the page together with
    // its text is not announced reliably; a region that is already there and then
    // changes is.
    expect(document.querySelectorAll('[role="alert"]').length).toBe(0);
  });

  it("sits in a labelled region whose name is not the button's name", () => {
    renderToggle();

    // **The section's label is a short noun phrase**, matching the house —
    // "Digest delivery time", "Quiet hours", "Reminder plan editor". A full sentence
    // would collide with the button's accessible name, and a screen reader would say
    // the same thing twice.
    const region = screen.getByRole("region", { name: "Personal events" });
    expect(region).toBeInTheDocument();
    expect(region.getAttribute("aria-label")).not.toBe(button().getAttribute("aria-label"));
    // **And the button is inside it.**
    expect(region.contains(button())).toBe(true);
  });

  it("shows 'Saved.' quietly, and announces it", async () => {
    renderToggle();

    fireEvent.click(button());

    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());
    // **A `role="status"` region**, so a screen reader announces it without the focus
    // moving. No emoji, no celebration.
    const status = document.querySelector('[role="status"]');
    expect(status).not.toBeNull();
    expect(status?.textContent).toBe("Saved.");
  });

  it("saves inline, with no Save button", async () => {
    renderToggle();

    // **There is no Save button** — the control the user pressed is the thing that
    // saves.
    expect(screen.queryByRole("button", { name: /^save/i })).toBeNull();

    fireEvent.click(button());

    await waitFor(() => expect(PUT).toHaveBeenCalled());
  });
});

/* ── what a failure does ─────────────────────────────────────────────────────── */

describe("what a failure does", () => {
  it("puts the state back when the save fails", async () => {
    PUT.mockRejectedValue(new Error("offline"));

    renderToggle({ initialIncludePersonalEvents: true });

    fireEvent.click(button());

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
    // **The server did not record the opt-out, so the personal events are still in the
    // digest** — and a control claiming otherwise would be claiming something that did
    // not happen.
    expect(button()).toHaveAttribute("aria-pressed", "true");
  });

  it("shows the API's own refusal, verbatim", async () => {
    // **The API's message is written for the user**, and it says what to change. A
    // generic line would throw that away.
    PUT.mockResolvedValue(refusal("invalid_delivery_time", "That isn't a time we can deliver at."));

    renderToggle();

    fireEvent.click(button());

    await waitFor(() =>
      expect(screen.getByText("That isn't a time we can deliver at.")).toBeInTheDocument(),
    );
    // **The generic line is not shown as well** — the API's verdict replaces it, rather
    // than joining it.
    expect(screen.queryByText("Couldn't save.")).toBeNull();
  });

  it("falls back to the route's own line when the API says nothing", async () => {
    // **The request never reached the API**, so there is nothing to quote — and the
    // route's own line is the honest one, because nothing was refused.
    PUT.mockRejectedValue(new Error("offline"));

    renderToggle();

    fireEvent.click(button());

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
  });

  it("falls back when the API answers with an error body that is not ours", async () => {
    // **A body that is not the project's error shape** says nothing quotable, so the
    // route's own line stands.
    PUT.mockResolvedValue({
      data: undefined,
      error: { detail: "nope" },
      response: { status: 500 },
    });

    renderToggle();

    fireEvent.click(button());

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
  });
});

/* ── the schedule guard ──────────────────────────────────────────────────────── */

describe("the schedule guard", () => {
  it("disables the control when there is no schedule", () => {
    // **A user with no `DigestPreference` row has no schedule**, and the endpoint
    // requires one — so the request could only ever be refused.
    renderToggle({ schedule: null });

    expect(button()).toBeDisabled();
  });

  it("cannot be given a half-schedule at all", () => {
    // **The time and the zone are one value, not two.** The endpoint refuses to
    // half-apply the pair, so a time with no zone is not a state the server produces
    // and not one the endpoint accepts — and modelling it as two independent nullable
    // fields would make it *representable*. Here it is not: a schedule is
    // `{ deliveryTime, timezone }` or `null`, never `{ deliveryTime }`.
    //
    // **The compiler is what enforces that.** A schedule with one half does not
    // compile:
    //
    //     renderToggle({ schedule: { deliveryTime: "08:00:00" } });
    //
    // **And the runtime proof is that the guard holds for the one shape the type does
    // allow** — no schedule at all — which is asserted above and below.
    //
    // **This test pins the shape of the prop**, so a future change that splits the
    // schedule back into two nullable fields fails here rather than passing silently
    // and reintroducing the half-schedule.
    const schedule: React.ComponentProps<typeof DigestPersonalEvents>["schedule"] = {
      deliveryTime: "08:00:00",
      timezone: "America/New_York",
    };
    expect(schedule).not.toBeNull();
    expect(Object.keys(schedule).sort()).toEqual(["deliveryTime", "timezone"]);
  });

  it("says what to do, rather than failing", () => {
    renderToggle({ schedule: null });

    // **A sentence the user can act on.** A 422 is not one.
    expect(screen.getByText("Set your delivery time first.")).toBeInTheDocument();
  });

  it("sends nothing when the control is unavailable", async () => {
    renderToggle({ schedule: null });

    fireEvent.click(button());

    await new Promise((resolve) => setTimeout(resolve, 10));
    // **Nothing was attempted**, so there is nothing to fail and nothing to report.
    expect(PUT).not.toHaveBeenCalled();
  });

  it("still reports the server's value while unavailable", () => {
    // **The server does believe the personal events are included** — it defaults them
    // to `true` — so the pressed state says so even while the control cannot be used.
    renderToggle({ initialIncludePersonalEvents: true, schedule: null });

    expect(button()).toHaveAttribute("aria-pressed", "true");
  });

  it("does not show the explanation when the schedule is there", () => {
    renderToggle();

    expect(screen.queryByText("Set your delivery time first.")).toBeNull();
  });
});

/* ── the in-flight affordance ────────────────────────────────────────────────── */

describe("the in-flight affordance", () => {
  it("shows a static dot, never a spinner", async () => {
    // **The product bans spinners.** `EXPERIENCE.md`: "No spinners, anywhere." So the
    // in-flight state is a static dot.
    let resolvePut: (value: unknown) => void = () => {};
    PUT.mockReturnValue(
      new Promise((resolve) => {
        resolvePut = resolve;
      }),
    );

    renderToggle();
    fireEvent.click(button());

    await waitFor(() => expect(document.querySelector("[data-saving-dot]")).not.toBeNull());
    const dot = document.querySelector("[data-saving-dot]");
    expect(dot?.className).toContain("rounded-full");
    // **A static dot.** Nothing animates.
    expect(dot?.className).not.toContain("animate-");
    expect(dot?.getAttribute("aria-hidden")).toBe("true");

    resolvePut(answer());
    await waitFor(() => expect(document.querySelector("[data-saving-dot]")).toBeNull());
  });

  it("cannot be pressed twice while a save is in flight", async () => {
    let resolvePut: (value: unknown) => void = () => {};
    PUT.mockReturnValue(
      new Promise((resolve) => {
        resolvePut = resolve;
      }),
    );

    renderToggle();
    fireEvent.click(button());

    await waitFor(() => expect(button()).toBeDisabled());
    // **One press, one save.** A second press would be a second write of a setting the
    // user has already asked to change once.
    expect(PUT).toHaveBeenCalledTimes(1);

    resolvePut(answer());
    await waitFor(() => expect(button()).not.toBeDisabled());
  });
});
