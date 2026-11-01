/**
 * The Reminder Picker's **axe-core gate**.
 *
 * **"axe-core reports zero serious or critical violations on this surface."** The work
 * item's acceptance criteria ask for keyboard and screen-reader behaviour, and this
 * file is the mechanical half of that.
 *
 * **The gate runs over every state, not just the happy one.** A picker can be
 * accessible when it is full and inaccessible when it is empty — and the empty state
 * is a *different document*, with a different set of rules: no chips pressed, one
 * paragraph, and the custom-slot input and its button.
 *
 * **The dimmed state is audited too.** That is the state most likely to fail: a chip
 * at 40% opacity with a dimmed label, where the only thing carrying the fact is text
 * that is also dimmed. axe's `color-contrast` rule is disabled (jsdom computes no
 * layout, so the rule reports false positives), but the *other* rules — the ones about
 * names, roles and structure — still apply, and a chip whose note was reachable only
 * by hover would fail them.
 *
 * **Serious and critical only.** `minor` and `moderate` findings are advisory, and a
 * gate that fails on a moderate finding is a gate that gets disabled.
 */
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";

import { ReminderPicker } from "@/components/reminders/reminder-picker";

const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    PUT: (...args: unknown[]) => PUT(...args),
  },
}));

/**
 * Run axe over the rendered picker.
 *
 * **The container is the whole document.** axe walks the DOM it is given, so auditing
 * the picker alone would miss the shell — and the shell is part of the surface.
 */
async function audit() {
  const results = await axe.run(document.body, {
    resultTypes: ["violations"],
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
}

/** The picker, with a plan and its deliveries. */
function renderPicker({
  slots = [] as string[],
  deliveries = [] as Array<{
    slot: string;
    delivery_at: string | null;
    deferred: boolean;
    deferred_to: string | null;
  }>,
} = {}) {
  return render(
    <ReminderPicker
      targetId="event-1"
      targetKind="saved_event"
      initialSlots={slots}
      deliveries={deliveries}
      defaultSlots={["1d", "1hr"]}
      timeZone="America/New_York"
    />,
  );
}

describe("the Reminder Picker's axe-core gate", () => {
  it("has zero serious or critical violations with a plan", async () => {
    renderPicker({
      slots: ["1d", "1hr"],
      deliveries: [
        {
          slot: "1d",
          delivery_at: "2026-11-06T22:00:00Z",
          deferred: false,
          deferred_to: null,
        },
        {
          slot: "1hr",
          delivery_at: "2026-11-07T22:00:00Z",
          deferred: false,
          deferred_to: null,
        },
      ],
    });

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the empty state", async () => {
    // **The empty state is a different document.** No chips pressed, one paragraph, and
    // the custom-slot input and its button — and the input's `aria-describedby` points
    // at a hint that has to exist.
    renderPicker({ slots: [] });

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations with a deferred chip", async () => {
    // **The dimmed chip, with its note.** The chip is at 40% opacity and the note is
    // visible text beneath it; axe's structural rules still apply, and a note that
    // existed only as a hover title would be the failure this catches.
    renderPicker({
      slots: ["1hr"],
      deliveries: [
        {
          slot: "1hr",
          delivery_at: "2026-08-29T12:00:00Z",
          deferred: true,
          deferred_to: "2026-08-29T12:00:00Z",
        },
      ],
    });

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations with a custom slot", async () => {
    // **The custom chip.** Its label is a sentence rather than an abbreviation, and it
    // has the same structure as every other chip.
    renderPicker({
      slots: ["1d", "custom:30"],
      deliveries: [
        {
          slot: "1d",
          delivery_at: "2026-11-06T22:00:00Z",
          deferred: false,
          deferred_to: null,
        },
        {
          slot: "custom:30",
          delivery_at: "2026-11-07T22:30:00Z",
          deferred: false,
          deferred_to: null,
        },
      ],
    });

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations after a failed save", async () => {
    // **The failed state.** The error message is a `<p>` in `color.warn.amber` — a real
    // element with real text, and not a `role="alert"` (which would be a live region
    // announcing a message the user did not ask for).
    PUT.mockResolvedValue({ data: undefined, error: {}, response: { status: 500 } });

    renderPicker({ slots: ["1d"] });
    screen.getByRole("button", { name: "Save reminder plan" }).click();

    await screen.findByText("Couldn't save. We'll try again on your next change.");

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("audits a document with the real landmarks in place", async () => {
    // A gate that passed because the picker rendered nothing would pass forever.
    //
    // **The picker is a labelled region, not a page.** The `<h1>` belongs to the route's
    // page, and the island is audited on its own here — so the landmarks checked are
    // the island's own: the fieldset's group, the legend, and the chips.
    renderPicker({ slots: ["1d"] });

    expect(screen.getByRole("region", { name: "Reminder plan editor" })).toBeInTheDocument();
    expect(screen.getByRole("group")).toBeInTheDocument();
    expect(screen.getByText("Remind me:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1 day before/ })).toBeInTheDocument();
  });
});
