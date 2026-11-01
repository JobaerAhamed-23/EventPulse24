/**
 * The reminder chip's deferred state — **the frontend's half of the delivery proof.**
 *
 * **Why this file exists.** The work item's acceptance criterion asks for proof that
 * *"set quiet hours in `/settings/quiet-hours`, open `/events/:id/reminders`, and see the
 * affected chip rendered dim with its 'Will deliver at …' tooltip — proving the
 * server-computed flag reaches the UI."*
 *
 * **The flag's journey has two halves, and both are asserted here and in the backend
 * proof.** The server computes `deferred` and `deferred_to` (proved in
 * `backend/tests/e2e/test_delivery_proof.py`, in the real service, with a real quiet
 * window); the client renders it. **Neither half proves the other**: a flag the server
 * computes but the client ignores would pass both halves on their own, and a chip that
 * dims on a flag nobody sends would too.
 *
 * **The flag is not recomputed here.** The chip takes `deferred` and `note` as props and
 * renders them. A chip that reimplemented the Quiet Hours window in TypeScript would be
 * a second implementation of the shift — with DST and midnight rediscovered there — and
 * the two could disagree about the very instant the email goes out at.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReminderChip } from "@/components/reminders/reminder-chip";

/**
 * The note the picker builds for a deferred slot.
 *
 * **The exact shape EXPERIENCE.md's worked examples use.** The picker's own tests pin
 * the string it produces; this file pins that the chip *renders* what it is given, so
 * the two together cover the flag's whole journey from the server to the screen.
 */
const NOTE = "Will deliver at 8:00 am Saturday.";

/** A chip, with everything but the flag itself fixed. */
function chip(overrides: Partial<Parameters<typeof ReminderChip>[0]> = {}) {
  return (
    <ReminderChip
      slot="1hr"
      label="1hr"
      name="1 hour before"
      selected={false}
      deferred={false}
      note={null}
      custom={false}
      onToggle={vi.fn()}
      {...overrides}
    />
  );
}

describe("the chip", () => {
  it("dims when the server says the slot is deferred", () => {
    render(chip({ deferred: true, note: NOTE }));

    // **The dimming is the server's flag, applied.** 40% opacity, and the chip's class
    // list is where it shows.
    const button = screen.getByRole("button");
    expect(button.className).toContain("opacity-40");
  });

  it("does not dim when the server says the slot is not deferred", () => {
    render(chip({ deferred: false, note: null }));

    const button = screen.getByRole("button");
    expect(button.className).not.toContain("opacity-40");
  });

  it("shows the note as visible text, not only as a tooltip", () => {
    render(chip({ deferred: true, note: NOTE }));

    // **Opacity is invisible to a screen reader**, so the note is rendered as text under
    // the chip. A tooltip that only appears on hover would be unreachable by keyboard
    // and invisible to a screen reader.
    const note = document.querySelector("[data-reminder-chip-note]");
    expect(note?.textContent).toBe(NOTE);
  });

  it("carries the deferred instant in its accessible name", () => {
    render(chip({ deferred: true, note: NOTE }));

    // **The name is the label plus the note**, so the fact that this slot will deliver
    // later reaches a screen reader as well as the eye.
    expect(screen.getByRole("button").getAttribute("aria-label")).toBe(`1 hour before. ${NOTE}`);
  });

  it("stays selectable when it is deferred", () => {
    // **The dimmed state is still selectable.** It says what will happen; it does not
    // forbid it. A chip that could not be pressed would be a control that is present and
    // inert.
    const onToggle = vi.fn();
    render(chip({ deferred: true, note: NOTE, onToggle }));

    screen.getByRole("button").click();

    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("does not carry the note when the slot is not deferred", () => {
    // **A `deferred_to` on an un-deferred slot would be a time the picker showed that
    // the send was not going to happen at.** The note only appears with the flag.
    render(chip({ deferred: false, note: null }));

    expect(document.querySelector("[data-reminder-chip-note]")).toBeNull();
    expect(screen.getByRole("button").getAttribute("aria-label")).toBe("1 hour before");
  });

  it("carries no accent token, because selection is an ink inversion", () => {
    // **EXPERIENCE.md §4 `Input.ReminderSlot`**: *"no terracotta on this chip; selection
    // is communicated by ink inversion, not by accent."* The one sanctioned accent use
    // on this surface is the **focus ring**, which is a stroke and not a fill.
    render(chip({ selected: true }));

    const className = screen.getByRole("button").className;
    expect(className).toContain("bg-ink-primary");
    expect(className).toContain("text-ink-inverse");
    expect(className).not.toMatch(/bg-accent-terracotta/);
  });
});
