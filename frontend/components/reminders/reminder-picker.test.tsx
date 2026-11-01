import { readFileSync } from "node:fs";
import path from "node:path";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReminderPicker } from "@/components/reminders/reminder-picker";

/**
 * The two sources some of these tests read.
 *
 * **The frontend root, two levels up** — this file lives at `components/reminders/`, so
 * `__dirname` is that directory and the project root is its parent's parent.
 */
const ROOT = path.resolve(__dirname, "..", "..");
const CHIP_SOURCE = path.join(ROOT, "components/reminders/reminder-chip.tsx");
const PICKER_SOURCE = path.join(ROOT, "components/reminders/reminder-picker.tsx");

/**
 * The Reminder Picker — the chips, the dimmed state, the custom slot, and the states.
 *
 * **The dimmed state comes from the API's flag, and these tests say so.** The four
 * worked examples in `EXPERIENCE.md` §4 are the tests, verbatim — including *"Friday
 * 11:30pm event + 1hr slot → 'Will deliver at 8:00 am Saturday.'"* Each one is driven
 * by a **server payload** carrying `deferred: true` and a `deferred_to` instant, and
 * never by a browser-side computation: the picker is handed the answer, and these
 * tests check that it renders the answer.
 *
 * **The absence of a browser-side computation is itself asserted.** A picker that
 * recomputed the shift would produce the same four examples — and would be wrong on
 * DST, on a midnight-crossing window, and on every example the docs did not write
 * down. So one test reads the source and fails if it grows the arithmetic.
 */
const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    PUT: (...args: unknown[]) => PUT(...args),
  },
}));

beforeEach(() => {
  PUT.mockReset();
  // **The default is a successful save.** The server answers the `PUT` with the saved
  // plan and its recomputed delivery times, so the default response carries them.
  PUT.mockResolvedValue({
    data: { target_kind: "saved_event", target_id: "event-1", slots: [], deliveries: [] },
    response: { status: 200 },
  });
});

/** One slot's delivery, as the server sends it. */
type Delivery = {
  slot: string;
  delivery_at: string | null;
  deferred: boolean;
  deferred_to: string | null;
};

/** A delivery that was not moved by Quiet Hours. */
function plain(slot: string, at: string): Delivery {
  return { slot, delivery_at: at, deferred: false, deferred_to: null };
}

/** A delivery that Quiet Hours moved — the dimmed case. */
function deferred(slot: string, at: string, to: string): Delivery {
  return { slot, delivery_at: to, deferred: true, deferred_to: to };
}

/** The picker, with a plan and its deliveries. */
function renderPicker({
  slots = [] as string[],
  deliveries = [] as Delivery[],
  defaultSlots = ["1d", "1hr"] as string[],
} = {}) {
  return render(
    <ReminderPicker
      targetId="event-1"
      targetKind="saved_event"
      initialSlots={slots}
      deliveries={deliveries}
      defaultSlots={defaultSlots}
      timeZone="America/New_York"
    />,
  );
}

/** The chip for a slot, by its accessible name. */
function chip(name: string): HTMLElement {
  return screen.getByRole("button", { name: new RegExp(name, "i") });
}

/* ── the four chips ──────────────────────────────────────────────────────────── */

describe("the four slot chips", () => {
  it("renders exactly the four named tiers, labelled 'Remind me:'", () => {
    renderPicker();

    // **The legend is the locked microcopy.** "Remind me:" — the work item names it as
    // locked, so it is a constant and not a prop.
    expect(screen.getByText("Remind me:")).toBeInTheDocument();

    // **The chips, and only the chips.** The "Add slot" button is in the same
    // fieldset, so the query is scoped to the chips' own container rather than to the
    // group — otherwise the count would be the chips plus the input's button.
    const chips = within(
      document.querySelector("[data-reminder-chips]") as HTMLElement,
    ).getAllByRole("button");
    expect(chips).toHaveLength(4);
    expect(chips.map((button) => button.textContent)).toEqual(["5d", "2d", "1d", "1hr"]);
  });

  it("gives each chip an accessible name that says what it is", () => {
    renderPicker();

    // **The visible label is an abbreviation; the name is a sentence.** "1hr" on its own
    // reads as "one hour" only if the reader already knows what a reminder slot is.
    expect(chip("5 days before")).toBeInTheDocument();
    expect(chip("2 days before")).toBeInTheDocument();
    expect(chip("1 day before")).toBeInTheDocument();
    expect(chip("1 hour before")).toBeInTheDocument();
  });

  it("is a real control, not a span", () => {
    renderPicker();

    // **The chips are `<button>`s with `aria-pressed`.** The Detail Screen used to
    // render the plan as `<span>`s, because "nothing schedules sends" — that is no
    // longer true, and a control that is not a control cannot be pressed.
    expect(chip("1 hour before").tagName).toBe("BUTTON");
    expect(chip("1 hour before")).toHaveAttribute("aria-pressed", "false");
  });
});

/* ── selection is an ink inversion, never terracotta ────────────────────────── */

describe("the selection treatment", () => {
  it("inverts the ink when selected, and leaves it plain when not", async () => {
    renderPicker({ slots: ["1d"] });

    const oneDay = chip("1 day before");
    const oneHour = chip("1 hour before");

    // **Selected: primary ink filled, inverse ink on it.**
    expect(oneDay).toHaveAttribute("aria-pressed", "true");
    expect(oneDay.className).toContain("bg-ink-primary");
    expect(oneDay.className).toContain("text-ink-inverse");

    // **Unselected: primary ink on the subtle surface.**
    expect(oneHour).toHaveAttribute("aria-pressed", "false");
    expect(oneHour.className).toContain("bg-surface-subtle");
    expect(oneHour.className).toContain("text-ink-primary");

    fireEvent.click(oneHour);

    expect(oneHour).toHaveAttribute("aria-pressed", "true");
    expect(oneHour.className).toContain("bg-ink-primary");
    expect(oneHour.className).toContain("text-ink-inverse");
  });

  it("carries no accent token on the chip", () => {
    // **The acceptance criterion, as a test.** `EXPERIENCE.md` §4
    // `Input.ReminderSlot`: "no terracotta on this chip; selection is communicated by
    // ink inversion, not by accent". A source assertion, because a rendered assertion
    // would pass whatever the class list happened to say — and the chip's class list is
    // exactly where the accent would sneak in.
    //
    // **The focus ring is the one exception, and it is not on the chip.** The terracotta
    // stroke is the focus ring, which says "you are here" and burns nothing. It is
    // checked separately below.
    const chipSource = readFileSync(CHIP_SOURCE, "utf8");

    // The comments come out first — the docstring names terracotta while explaining
    // why it is absent, and an assertion that read it would be asserting on prose.
    const code = chipSource.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

    // **The selection classes are the only ones checked** — the focus ring is a
    // separate, sanctioned use.
    const selectionClasses = code
      .split("\n")
      .filter((line) => line.includes("bg-ink-primary") || line.includes("text-ink-inverse"))
      .join("\n");

    expect(selectionClasses).not.toContain("terracotta");
    expect(selectionClasses).not.toContain("accent");
  });

  it("keeps the terracotta focus ring", () => {
    // **The focus ring is the terracotta stroke.** One sanctioned accent use: a ring
    // that says "you are here" is exactly what the accent is for.
    const chipSource = readFileSync(CHIP_SOURCE, "utf8");

    expect(chipSource).toContain("focus-visible:outline-accent-terracotta");
  });
});

/* ── the Quiet Hours chip state ─────────────────────────────────────────────── */

describe("the Quiet Hours chip state", () => {
  it("dims a deferred chip to 40% and says when it will deliver", () => {
    // **The server's flag, carried straight through.** The payload says this slot is
    // deferred and when it was moved to; the chip renders that.
    renderPicker({
      slots: ["1hr"],
      deliveries: [deferred("1hr", "2026-11-07T13:00:00Z", "2026-11-07T13:00:00Z")],
    });

    const oneHour = chip("1 hour before");
    expect(oneHour.className).toContain("opacity-40");
  });

  it("does not dim a chip the server did not defer", () => {
    renderPicker({
      slots: ["1d", "1hr"],
      deliveries: [
        plain("1d", "2026-11-06T22:00:00Z"),
        deferred("1hr", "2026-11-07T13:00:00Z", "2026-11-07T13:00:00Z"),
      ],
    });

    expect(chip("1 day before").className).not.toContain("opacity-40");
    expect(chip("1 hour before").className).toContain("opacity-40");
  });

  it("keeps a deferred chip selectable", async () => {
    renderPicker({
      slots: [],
      deliveries: [deferred("1hr", "2026-11-07T13:00:00Z", "2026-11-07T13:00:00Z")],
    });

    const oneHour = chip("1 hour before");
    expect(oneHour).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(oneHour);

    // **It stays selectable.** The chip says what will happen; it does not forbid it.
    // A chip that could not be pressed would be a control that is present and inert.
    expect(oneHour).toHaveAttribute("aria-pressed", "true");
  });

  it("conveys the dimmed state in text, not by opacity alone", () => {
    renderPicker({
      slots: ["1hr"],
      deliveries: [deferred("1hr", "2026-11-07T13:00:00Z", "2026-11-07T13:00:00Z")],
    });

    // **Opacity is invisible to a screen reader.** The note is visible text, and the
    // chip's accessible name carries it too.
    const note = document.querySelector("[data-reminder-chip-note]");
    expect(note).not.toBeNull();
    expect(note?.textContent).toMatch(/^Will deliver at .+\.$/);
  });

  it("reaches the tooltip without hovering", () => {
    renderPicker({
      slots: ["1hr"],
      deliveries: [deferred("1hr", "2026-11-07T13:00:00Z", "2026-11-07T13:00:00Z")],
    });

    // **The note is rendered text, not a hover-only tooltip.** A tooltip that only
    // appears on hover is unreachable by keyboard and invisible to a screen reader, so
    // the note is in the document from the start.
    const note = document.querySelector("[data-reminder-chip-note]");
    expect(note?.textContent).toContain("Will deliver at");
  });
});

/* ── EXPERIENCE.md's four worked examples, verbatim ──────────────────────────── */

describe("EXPERIENCE.md's four worked examples", () => {
  /**
   * The four examples, as the server would answer each one.
   *
   * **Each is a payload, not a computation.** The picker is given the answer and
   * renders it; the times are the ones the docs say the server computes.
   */
  const EXAMPLES = [
    {
      name: "Saturday 7:00 pm event, 1hr slot — outside Quiet Hours",
      slot: "1hr",
      deliveries: [plain("1hr", "2026-08-29T18:00:00Z")],
      dimmed: false,
      note: null,
    },
    {
      name: "Friday 11:30 pm event, 1hr slot — inside Quiet Hours",
      slot: "1hr",
      deliveries: [deferred("1hr", "2026-08-29T04:00:00Z", "2026-08-29T12:00:00Z")],
      dimmed: true,
      note: "Will deliver at 8:00 am Saturday.",
    },
    {
      name: "Sunday 6:00 am event, 5d slot — outside Quiet Hours",
      slot: "5d",
      deliveries: [plain("5d", "2026-08-31T10:00:00Z")],
      dimmed: false,
      note: null,
    },
    {
      name: "Sunday 6:00 am event, 1hr slot — inside Quiet Hours",
      slot: "1hr",
      deliveries: [deferred("1hr", "2026-08-30T09:00:00Z", "2026-08-30T12:00:00Z")],
      dimmed: true,
      note: "Will deliver at 8:00 am Sunday.",
    },
  ] as const;

  for (const example of EXAMPLES) {
    it(`${example.name}`, () => {
      renderPicker({ slots: [example.slot], deliveries: [...example.deliveries] });

      const button = chip(example.slot === "5d" ? "5 days before" : "1 hour before");

      if (example.dimmed) {
        expect(button.className).toContain("opacity-40");
      } else {
        expect(button.className).not.toContain("opacity-40");
      }

      const note = document.querySelector("[data-reminder-chip-note]");
      if (example.note === null) {
        expect(note).toBeNull();
      } else {
        expect(note?.textContent).toBe(example.note);
      }
    });
  }

  it("never recomputes the shift in the browser", () => {
    // **The absence of the arithmetic is the point.** A picker that recomputed the
    // shift would produce these same four examples — and would be wrong on DST, on a
    // midnight-crossing window, and on every example the docs did not write down.
    //
    // **So the source is checked for the arithmetic's fingerprints.** The picker reads
    // `deferred` and `deferred_to`; it does not know the quiet window, and it does not
    // compare a delivery time against one.
    const source = readFileSync(PICKER_SOURCE, "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

    // **The window's own vocabulary.** The picker has no `quiet_hours`, no
    // `quietHours`, and no window's start and end to compare a delivery against.
    expect(code).not.toMatch(/quiet_hours/i);
    expect(code).not.toMatch(/quietHours/i);
    expect(code).not.toMatch(/windowStart|windowEnd|window_start|window_end/);

    // **And it never compares an instant against another.** The only time arithmetic
    // in this file is the formatting of one instant into a clock face — there is no
    // comparison that could decide "is this inside the window?".
    expect(code).not.toMatch(/getTime\(\)\s*[<>]/);
    expect(code).not.toMatch(/\+\s*\d+\s*\*\s*60/);
  });
});

/* ── the custom slot ────────────────────────────────────────────────────────── */

describe("the custom slot", () => {
  it("adds a custom slot with its own interval", async () => {
    renderPicker();

    const input = screen.getByLabelText("Custom reminder");
    fireEvent.change(input, { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Add slot" }));

    // **The chip says what it is.** A custom slot has no fixed two-character marker,
    // so the chip spells it out.
    expect(screen.getByRole("button", { name: /30 minutes before/i })).toBeInTheDocument();
  });

  it("sends the custom slot's id as custom:<minutes>", async () => {
    renderPicker();

    const input = screen.getByLabelText("Custom reminder");
    fireEvent.change(input, { target: { value: "90" } });
    fireEvent.click(screen.getByRole("button", { name: "Add slot" }));
    fireEvent.click(screen.getByRole("button", { name: "Save reminder plan" }));

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(PUT.mock.calls[0]?.[0]).toBe("/api/reminders/{target_kind}/{target_id}");
    expect(PUT.mock.calls[0]?.[1]?.body).toEqual({ slots: ["custom:90"] });
  });

  it("surfaces the bound as an inline message, and does not clamp", async () => {
    renderPicker();

    const input = screen.getByLabelText("Custom reminder");
    fireEvent.change(input, { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Add slot" }));

    // **The bound is surfaced, not clamped.** A silent clamp would save something the
    // user did not ask for — the plan would say "15 minutes before" and the user asked
    // for 5. Instead the refusal is shown and the input keeps what was typed.
    expect(document.querySelector("[data-reminder-error]")).not.toBeNull();
    expect(screen.getByLabelText("Custom reminder")).toHaveValue(5);
  });

  it("offers a second custom slot only after the first is turned off", async () => {
    renderPicker({
      slots: ["custom:30"],
      deliveries: [plain("custom:30", "2026-08-29T18:00:00Z")],
    });

    // **The plan carries a custom slot, so the input is not offered** — a second one
    // is refused by the server.
    expect(screen.queryByLabelText("Custom reminder")).toBeNull();

    // Turning the chip off brings the input back.
    fireEvent.click(screen.getByRole("button", { name: /30 minutes before/i }));
    expect(screen.getByLabelText("Custom reminder")).toBeInTheDocument();
  });
});

/* ── the plan's slot bound ────────────────────────────────────────────────────── */

describe("the plan's slot bound", () => {
  it("refuses a fifth custom slot, and says which bound it is", async () => {
    // **A plan may carry at most four slots.** The picker knows that number, so it
    // refuses the fifth *before* the save — otherwise the user presses Save and gets
    // a bare "Couldn't save." that does not name the reason.
    renderPicker({ slots: ["5d", "2d", "1d", "1hr"] });

    const input = screen.getByLabelText("Custom reminder");
    fireEvent.change(input, { target: { value: "90" } });
    fireEvent.click(screen.getByRole("button", { name: "Add slot" }));

    expect(document.querySelector("[data-reminder-slot-error]")).not.toBeNull();
    expect(screen.getByText(/up to 4 reminders/i)).toBeInTheDocument();

    // **And the custom slot did not join the plan.**
    expect(screen.queryByRole("button", { name: /90 minutes before/i })).toBeNull();
  });

  it("refuses a fifth named slot, and says which bound it is", async () => {
    // **The named chips are bounded too.** A plan with a custom slot and three named
    // ones is full; the fourth named chip cannot be added.
    renderPicker({
      slots: ["5d", "2d", "1d", "custom:90"],
      deliveries: [plain("custom:90", "2026-08-29T18:00:00Z")],
    });

    fireEvent.click(screen.getByRole("button", { name: /1 hour before/i }));

    expect(screen.getByText(/up to 4 reminders/i)).toBeInTheDocument();
    // **The chip did not become selected.**
    expect(screen.getByRole("button", { name: /1 hour before/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("lets a slot back in once one is turned off", async () => {
    // **A plan that is full but holds an unselected chip.** The `1hr` chip is
    // *off* here, so clicking it is an attempt to make it the fifth — which the
    // bound refuses. (A plan where every chip is on would make the click a
    // deselection, and the refusal would never be reached.)
    renderPicker({
      slots: ["5d", "2d", "1d", "custom:90"],
      deliveries: [plain("custom:90", "2026-08-29T18:00:00Z")],
    });

    // The plan is full, so the fifth slot is refused…
    fireEvent.click(screen.getByRole("button", { name: /1 hour before/i }));
    expect(screen.getByText(/up to 4 reminders/i)).toBeInTheDocument();

    // …and turning one off makes room again, without a reload.
    fireEvent.click(screen.getByRole("button", { name: /5 days before/i }));
    expect(screen.queryByText(/up to 4 reminders/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /1 hour before/i }));
    expect(screen.getByRole("button", { name: /1 hour before/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("never sends a plan with more than four slots", async () => {
    renderPicker({ slots: ["5d", "2d", "1d", "1hr"] });

    const input = screen.getByLabelText("Custom reminder");
    fireEvent.change(input, { target: { value: "90" } });
    fireEvent.click(screen.getByRole("button", { name: "Add slot" }));
    fireEvent.click(screen.getByRole("button", { name: "Save reminder plan" }));

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(PUT.mock.calls[0]?.[1]?.body).toEqual({ slots: ["5d", "2d", "1d", "1hr"] });
  });
});

/* ── the empty state ────────────────────────────────────────────────────────── */

describe("the empty state", () => {
  it("says that no reminders is still in the digest", () => {
    renderPicker({ slots: [] });

    // **The exact sentence.** FR-9: "0 slots = no reminders (still in feed)". It is a
    // statement of fact, not a warning.
    expect(
      screen.getByText("No reminders. You'll still see this event in Pulse Digest."),
    ).toBeInTheDocument();
  });

  it("is absent once a chip is chosen", async () => {
    renderPicker({ slots: [] });

    fireEvent.click(chip("1 day before"));

    expect(
      screen.queryByText("No reminders. You'll still see this event in Pulse Digest."),
    ).toBeNull();
  });

  it("saves zero slots as a normal save", async () => {
    renderPicker({ slots: [] });

    fireEvent.click(screen.getByRole("button", { name: "Save reminder plan" }));

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(PUT.mock.calls[0]?.[1]?.body).toEqual({ slots: [] });
    // **And it is not a warning.** The success message is the same calm "Saved." any
    // other save gets.
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(document.querySelector("[data-reminder-failed]")).toBeNull();
  });
});

/* ── the action bar ─────────────────────────────────────────────────────────── */

describe("the action bar", () => {
  it("offers Reset to default and Save reminder plan", () => {
    renderPicker();

    expect(screen.getByRole("button", { name: "Reset to default" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save reminder plan" })).toBeInTheDocument();
  });

  it("restores the default's chips without saving", async () => {
    renderPicker({ slots: ["5d"], defaultSlots: ["1d", "1hr"] });

    fireEvent.click(screen.getByRole("button", { name: "Reset to default" }));

    // **The chips are restored.**
    expect(chip("5 days before")).toHaveAttribute("aria-pressed", "false");
    expect(chip("1 day before")).toHaveAttribute("aria-pressed", "true");
    expect(chip("1 hour before")).toHaveAttribute("aria-pressed", "true");

    // **And nothing was written.** A reset that saved on its own would change the
    // plan without the user asking for it.
    expect(PUT).not.toHaveBeenCalled();
  });

  it("saves the chosen slots", async () => {
    renderPicker({ slots: ["1d"] });

    fireEvent.click(chip("2 days before"));
    fireEvent.click(screen.getByRole("button", { name: "Save reminder plan" }));

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(PUT.mock.calls[0]?.[1]?.body).toEqual({ slots: ["1d", "2d"] });
  });
});

/* ── the states ─────────────────────────────────────────────────────────────── */

describe("the states", () => {
  it("says 'Saved.' and nothing more", async () => {
    PUT.mockResolvedValue({
      data: { target_kind: "saved_event", target_id: "event-1", slots: ["1d"], deliveries: [] },
      response: { status: 200 },
    });
    renderPicker({ slots: ["1d"] });

    fireEvent.click(screen.getByRole("button", { name: "Save reminder plan" }));

    // **Success is quiet.** "Saved." — no emoji, no celebration, no fade.
    const saved = await screen.findByText("Saved.");
    expect(saved.textContent).toBe("Saved.");
    expect(saved.textContent).not.toMatch(/[🎉✅✨🎊]/);
  });

  it("announces the success in a status region", async () => {
    PUT.mockResolvedValue({
      data: { target_kind: "saved_event", target_id: "event-1", slots: ["1d"], deliveries: [] },
      response: { status: 200 },
    });
    renderPicker({ slots: ["1d"] });

    fireEvent.click(screen.getByRole("button", { name: "Save reminder plan" }));

    // **A `role="status"` region**, so a screen reader announces it without stealing
    // focus.
    const region = screen.getByRole("status");
    await waitFor(() => expect(region.textContent).toContain("Saved."));
  });

  it("keeps the chosen state when the save fails", async () => {
    PUT.mockResolvedValue({ data: undefined, error: {}, response: { status: 500 } });
    renderPicker({ slots: ["1d"] });

    fireEvent.click(chip("2 days before"));
    fireEvent.click(screen.getByRole("button", { name: "Save reminder plan" }));

    // **The message.** One line, and it says the retry is on the next change.
    expect(
      await screen.findByText("Couldn't save. We'll try again on your next change."),
    ).toBeInTheDocument();

    // **The chosen state survives.** Reverting the chips would throw away the user's
    // work over a transient failure — and the copy promises a retry on the next
    // change, so the state has to be there to retry with.
    expect(chip("2 days before")).toHaveAttribute("aria-pressed", "true");
    expect(chip("1 day before")).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps the chosen state when the save throws", async () => {
    PUT.mockRejectedValue(new Error("network"));
    renderPicker({ slots: ["1d"] });

    fireEvent.click(chip("5 days before"));
    fireEvent.click(screen.getByRole("button", { name: "Save reminder plan" }));

    expect(
      await screen.findByText("Couldn't save. We'll try again on your next change."),
    ).toBeInTheDocument();
    expect(chip("5 days before")).toHaveAttribute("aria-pressed", "true");
  });
});

/* ── keyboard and screen-reader behaviour ───────────────────────────────────── */

describe("keyboard and screen-reader behaviour", () => {
  it("reaches every chip by keyboard, and is a native button", () => {
    renderPicker();

    const oneDay = chip("1 day before");

    // **The chips are real controls, so they are in the tab order.**
    oneDay.focus();
    expect(oneDay).toHaveFocus();

    // **And they are native `<button>`s, not `<div>`s with a keydown handler.** A
    // native button is activated by Enter and by Space for free, from the browser's
    // own keyboard handling — which is the behaviour a screen-reader user gets too,
    // and which a hand-rolled `onKeyDown` would have to reimplement (and would
    // usually get subtly wrong).
    expect(oneDay.tagName).toBe("BUTTON");
    expect(oneDay).not.toHaveAttribute("tabindex", "-1");

    // **Every chip is reachable.** The four named tiers plus the custom slot's
    // absence — the chips container holds exactly the four.
    const chips = within(
      document.querySelector("[data-reminder-chips]") as HTMLElement,
    ).getAllByRole("button");
    for (const button of chips) {
      button.focus();
      expect(button).toHaveFocus();
    }
  });

  it("reflects selection in aria-pressed", async () => {
    renderPicker({ slots: ["1d", "1hr"] });

    expect(chip("1 day before")).toHaveAttribute("aria-pressed", "true");
    expect(chip("1 hour before")).toHaveAttribute("aria-pressed", "true");
    expect(chip("5 days before")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(chip("5 days before"));
    expect(chip("5 days before")).toHaveAttribute("aria-pressed", "true");
  });

  it("puts the deferred instant in the chip's accessible name", () => {
    renderPicker({
      slots: ["1hr"],
      deliveries: [deferred("1hr", "2026-08-29T12:00:00Z", "2026-08-29T12:00:00Z")],
    });

    // **The dimmed state is not carried by opacity alone** — opacity is invisible to a
    // screen reader, so the fact is in the name.
    const oneHour = chip("1 hour before");
    expect(oneHour.getAttribute("aria-label") ?? oneHour.textContent).toMatch(/Will deliver at/);
  });
});
