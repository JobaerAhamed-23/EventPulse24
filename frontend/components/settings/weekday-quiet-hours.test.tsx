/**
 * The per-weekday Quiet Hours picker (FR-51, Pro).
 *
 * **What is worth proving here is what a screenshot cannot show:**
 *
 * 1. **One request carries the whole week.** Changing Thursday sends all seven entries,
 *    because `replace_quiet_hours_overrides` is a replace — a Thursday-shaped payload
 *    would delete the other six days.
 * 2. **A full-day window never leaves the component.** `start == end` is withheld, not
 *    sent and refused, because the acceptance criterion asks that the UI cannot produce
 *    the form at all.
 * 3. **A lapsed Pro user reads their week and cannot write it.**
 * 4. **"Same as usual" is a real state**, distinct from a window, and going back to it
 *    removes the day rather than storing something.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WeekdayQuietHours } from "@/components/settings/weekday-quiet-hours";

const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

/** A whole week of windows, Monday 0 through Sunday 6. */
function wholeWeek() {
  return [
    { weekday: 0, start: "22:00:00", end: "08:00:00" },
    { weekday: 1, start: "22:30:00", end: "08:00:00" },
    { weekday: 2, start: "23:00:00", end: "07:00:00" },
    { weekday: 3, start: "22:00:00", end: "06:30:00" },
    { weekday: 4, start: "23:30:00", end: "09:00:00" },
    { weekday: 5, start: "01:00:00", end: "10:00:00" },
    { weekday: 6, start: "21:00:00", end: "08:00:00" },
  ];
}

/** The server's answer to a successful save. */
function answer(overrides: ReturnType<typeof wholeWeek>) {
  return {
    data: {
      default_reminder_slots: ["1d"],
      quiet_hours: { start: "22:00:00", end: "08:00:00" },
      quiet_hours_overrides: overrides,
      digest: { delivery_time: "09:00:00", timezone: "UTC" },
    },
    response: { status: 200 },
  };
}

/** The body of the one `PUT` that was made. */
function sentBody(): Record<string, unknown> {
  expect(PUT).toHaveBeenCalledTimes(1);
  const [, options] = PUT.mock.calls[0] as [string, { body: Record<string, unknown> }];
  return options.body;
}

/** Open one day's row. */
function openDay(name: string): void {
  fireEvent.click(screen.getByRole("button", { name: new RegExp(`^${name}`) }));
}

function renderPicker(props: Partial<React.ComponentProps<typeof WeekdayQuietHours>> = {}) {
  return render(
    <WeekdayQuietHours
      initialOverrides={props.initialOverrides ?? []}
      baseStart={props.baseStart ?? "22:00:00"}
      baseEnd={props.baseEnd ?? "08:00:00"}
      canEdit={props.canEdit ?? true}
    />,
  );
}

beforeEach(() => {
  PUT.mockReset();
  PUT.mockResolvedValue(answer(wholeWeek()));
});

describe("the week", () => {
  it("shows all seven days, Monday first", () => {
    renderPicker();

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(7);
    expect(rows.map((row) => row.textContent?.startsWith("Monday"))[0]).toBe(true);
    expect(rows.map((row) => row.textContent?.startsWith("Sunday"))[6]).toBe(true);
  });

  it("shows a stored window as a chip, and an untouched day as 'Same as usual'", () => {
    renderPicker({ initialOverrides: [{ weekday: 2, start: "23:00:00", end: "07:00:00" }] });

    expect(screen.getByText("11pm–7am")).toBeTruthy();
    // The other six days have no window of their own.
    expect(screen.getAllByText("Same as usual")).toHaveLength(6);
  });

  it("never renders more than one day's clocks, which is what makes a phone work", () => {
    renderPicker({ initialOverrides: wholeWeek() });

    // **Seven windows is fourteen time inputs**, which fits no phone and reads on no
    // desktop. The accordion is the mobile layout, not a decoration on top of one.
    expect(screen.queryAllByDisplayValue(/^\d\d:\d\d$/)).toHaveLength(0);

    openDay("Wednesday");
    expect(screen.queryAllByDisplayValue(/^\d\d:\d\d$/)).toHaveLength(2);

    openDay("Saturday");
    expect(screen.queryAllByDisplayValue(/^\d\d:\d\d$/)).toHaveLength(2);
  });

  it("opens one day at a time", () => {
    renderPicker({ initialOverrides: wholeWeek() });

    const monday = screen.getByRole("button", { name: /^Monday/ });
    const tuesday = screen.getByRole("button", { name: /^Tuesday/ });

    fireEvent.click(monday);
    expect(monday).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(tuesday);
    // **Opening Tuesday closes Monday** — seven open rows is the layout this avoids.
    expect(monday).toHaveAttribute("aria-expanded", "false");
    expect(tuesday).toHaveAttribute("aria-expanded", "true");
  });
});

describe("saving", () => {
  it("sends the whole week in one request when one day changes", async () => {
    renderPicker({ initialOverrides: wholeWeek() });

    openDay("Thursday");
    fireEvent.change(screen.getByLabelText("Thursday starts"), { target: { value: "21:15" } });

    await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));

    const body = sentBody();
    const sent = body.quiet_hours_overrides as { weekday: number; start: string }[];
    // **All seven, not just Thursday.** The command is a replace: a one-day payload
    // would delete the other six.
    expect(sent).toHaveLength(7);
    expect(sent.map((entry) => entry.weekday)).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(sent.find((entry) => entry.weekday === 3)?.start).toBe("21:15");
  });

  it("sends the week in weekday order, whatever order it arrived in", async () => {
    // **The fixture is deliberately shuffled.** With a Monday-first fixture the payload
    // comes out sorted whether or not anything sorts it, so the earlier test cannot see
    // the sort at all — mutation testing said so by deleting it and staying green.
    renderPicker({
      initialOverrides: [
        { weekday: 5, start: "01:00:00", end: "10:00:00" },
        { weekday: 0, start: "22:00:00", end: "08:00:00" },
        { weekday: 3, start: "22:00:00", end: "06:30:00" },
      ],
    });

    openDay("Saturday");
    fireEvent.change(screen.getByLabelText("Saturday ends"), { target: { value: "09:30" } });

    await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));

    const sent = sentBody().quiet_hours_overrides as { weekday: number }[];
    expect(sent.map((entry) => entry.weekday)).toEqual([0, 3, 5]);
  });

  it("sends only the weekday field, leaving the base window and the slots alone", async () => {
    renderPicker({ initialOverrides: wholeWeek() });

    openDay("Monday");
    fireEvent.change(screen.getByLabelText("Monday ends"), { target: { value: "07:45" } });

    await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));

    const body = sentBody();
    // **The absence matters.** `quiet_hours` is the field where `null` is a value, so a
    // payload that carried it could turn the base window off by accident.
    expect(Object.keys(body)).toEqual(["quiet_hours_overrides"]);
  });

  it("gives a day its own window, seeded from the usual one", async () => {
    renderPicker();

    openDay("Friday");
    fireEvent.click(screen.getByRole("button", { name: "Give Friday its own" }));

    await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));

    const sent = sentBody().quiet_hours_overrides as { weekday: number; start: string }[];
    expect(sent).toEqual([{ weekday: 4, start: "22:00", end: "08:00" }]);
  });

  it("returns a day to the usual window by removing it from the week", async () => {
    renderPicker({
      initialOverrides: [
        { weekday: 0, start: "23:00:00", end: "07:00:00" },
        { weekday: 1, start: "23:00:00", end: "07:00:00" },
      ],
    });

    openDay("Monday");
    fireEvent.click(screen.getByRole("button", { name: "Use my usual window on Monday" }));

    await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));

    const sent = sentBody().quiet_hours_overrides as { weekday: number }[];
    // **Absence is how a day says "the usual window applies here".**
    expect(sent.map((entry) => entry.weekday)).toEqual([1]);
  });
});

describe("the windows it refuses to send", () => {
  it("does not send a window whose clocks are the same", async () => {
    renderPicker({ initialOverrides: [{ weekday: 0, start: "22:00:00", end: "08:00:00" }] });

    openDay("Monday");
    fireEvent.change(screen.getByLabelText("Monday ends"), { target: { value: "22:00" } });

    // **The acceptance criterion asks that the UI cannot produce the form**, so this is
    // withheld rather than sent and refused.
    await waitFor(() =>
      expect(screen.getByText("A quiet window needs a start and an end that differ.")).toBeTruthy(),
    );
    expect(PUT).not.toHaveBeenCalled();
  });

  it("does not send a half-filled window", async () => {
    renderPicker({ initialOverrides: [{ weekday: 0, start: "22:00:00", end: "08:00:00" }] });

    openDay("Monday");
    fireEvent.change(screen.getByLabelText("Monday starts"), { target: { value: "" } });

    expect(PUT).not.toHaveBeenCalled();
  });
});

describe("a window that crosses midnight", () => {
  it("says which morning it reaches into", () => {
    renderPicker({ initialOverrides: [{ weekday: 4, start: "22:00:00", end: "08:00:00" }] });

    openDay("Friday");

    // **Two clocks do not say this.** 22:00 → 08:00 owns Saturday's small hours.
    expect(screen.getByText("Reaches into Saturday morning.")).toBeTruthy();
  });

  it("wraps from Sunday to Monday", () => {
    renderPicker({ initialOverrides: [{ weekday: 6, start: "21:00:00", end: "08:00:00" }] });

    openDay("Sunday");

    expect(screen.getByText("Reaches into Monday morning.")).toBeTruthy();
  });

  it("says nothing for a window inside one day", () => {
    renderPicker({ initialOverrides: [{ weekday: 5, start: "01:00:00", end: "10:00:00" }] });

    openDay("Saturday");

    expect(screen.queryByText(/Reaches into/)).toBeNull();
  });
});

describe("a lapsed Pro user", () => {
  it("reads their seven windows", () => {
    renderPicker({ initialOverrides: wholeWeek(), canEdit: false });

    // **The rows are kept on purpose.** The API refuses the write, never the read.
    expect(screen.getAllByRole("listitem")).toHaveLength(7);
    expect(screen.getByText("11pm–7am")).toBeTruthy();
  });

  it("cannot change them", () => {
    renderPicker({ initialOverrides: wholeWeek(), canEdit: false });

    openDay("Monday");

    expect(screen.getByLabelText("Monday starts")).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Use my usual window/ })).toBeNull();
  });

  it("is not offered a day's own window", () => {
    renderPicker({ initialOverrides: [], canEdit: false });

    openDay("Monday");

    expect(screen.queryByRole("button", { name: /Give Monday its own/ })).toBeNull();
  });
});

describe("when the server refuses on tier", () => {
  it("shows the server's own upgrade sentence, and no modal", async () => {
    PUT.mockResolvedValue({
      error: {
        code: "quiet_hours_pro_required",
        message: "Setting a different window for each day is part of Pro.",
        details: { cap: 1, upgrade_hint: "Set a different window for each day with Pro." },
      },
      response: { status: 409 },
    });

    renderPicker({ initialOverrides: wholeWeek() });

    openDay("Monday");
    fireEvent.change(screen.getByLabelText("Monday ends"), { target: { value: "07:15" } });

    await waitFor(() =>
      expect(screen.getByText("Set a different window for each day with Pro.")).toBeTruthy(),
    );
    // **Inline, never an interruption** — the posture `frontend-upgrade-prompts` locked.
    expect(screen.queryByRole("dialog")).toBeNull();
    // Scoped to the prompt itself: `SaveFeedback` is also a `role="status"` region, so
    // the sentence is what identifies this one.
    const prompt = screen
      .getByText("Set a different window for each day with Pro.")
      .closest('[role="status"]') as HTMLElement;
    expect(within(prompt).getByRole("link", { name: "Upgrade" })).toHaveAttribute(
      "href",
      "/pricing",
    );
  });
});
