import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConflictResolution, type Conflict } from "@/components/sheets/conflict-resolution";

/**
 * The forced three-action prompt (FR-58).
 *
 * The properties proved here are the ones FR-58 names and the ones a reviewer would
 * check by hand: three actions, the right labels, no way out, and a delete that does
 * not happen until it is confirmed.
 */

const NEW_EVENT = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Anniversary dinner with Rahul",
  start_time_utc: "2026-11-06T23:30:00Z",
};

/** A time conflict: the server's closed set is keep / edit / delete. */
const TIME_CONFLICT: Conflict = {
  pair_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  kind: "time",
  actions: ["keep_both", "edit_new", "delete_new"],
  other: {
    id: "22222222-2222-2222-2222-222222222222",
    name: "Free tech meetup — Designing for Calm",
    start_time_utc: "2026-11-06T22:30:00Z",
    end_time_utc: "2026-11-06T23:30:00Z",
  },
};

/** A duplicate: the second action is relabelled and targets the other side. */
const DUPLICATE_CONFLICT: Conflict = {
  pair_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  kind: "duplicate",
  actions: ["keep_both", "update_existing", "delete_new"],
  other: {
    id: "33333333-3333-3333-3333-333333333333",
    name: "Designing for Calm",
    start_time_utc: "2026-11-06T23:30:00Z",
    end_time_utc: null,
  },
};

function renderSheet(overrides: Partial<React.ComponentProps<typeof ConflictResolution>> = {}): {
  onResolve: ReturnType<typeof vi.fn>;
} {
  const onResolve = vi.fn();
  render(
    <ConflictResolution
      open
      conflict={TIME_CONFLICT}
      newEvent={NEW_EVENT}
      onResolve={onResolve}
      {...overrides}
    />,
  );
  return { onResolve };
}

describe("ConflictResolution", () => {
  it("renders nothing when there is no conflict to answer", () => {
    render(<ConflictResolution open conflict={null} newEvent={null} onResolve={() => {}} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  describe("the three actions", () => {
    it("offers exactly the server's set, and nothing else", () => {
      renderSheet();

      const group = screen.getByRole("group", { name: "Conflict resolution" });
      expect(within(group).getAllByRole("button")).toHaveLength(3);
    });

    it("labels them with the PRD's words", () => {
      renderSheet();

      expect(screen.getByText("Keep both — I'll manage")).toBeInTheDocument();
      expect(screen.getByText("Edit the new one")).toBeInTheDocument();
      expect(screen.getByText("Delete the new one")).toBeInTheDocument();
    });

    it("does not offer a resolution the kind does not allow", () => {
      // A time conflict cannot be resolved by updating the existing event.
      renderSheet();

      expect(screen.queryByText("Update the existing one")).not.toBeInTheDocument();
    });

    it("relabels the second action for a duplicate", () => {
      renderSheet({ conflict: DUPLICATE_CONFLICT });

      expect(screen.getByText("Update the existing one")).toBeInTheDocument();
      expect(screen.queryByText("Edit the new one")).not.toBeInTheDocument();
    });

    it("omits an action the server did not send", () => {
      // A server that sends two actions renders two — the sheet does not invent a third.
      renderSheet({
        conflict: { ...TIME_CONFLICT, actions: ["keep_both", "delete_new"] },
      });

      const group = screen.getByRole("group", { name: "Conflict resolution" });
      expect(within(group).getAllByRole("button")).toHaveLength(2);
    });
  });

  describe("the choice", () => {
    it("reports the chosen resolution", () => {
      const { onResolve } = renderSheet();

      fireEvent.click(screen.getByText("Keep both — I'll manage"));

      expect(onResolve).toHaveBeenCalledWith("keep_both");
    });

    it("reports the relabelled duplicate resolution", () => {
      const { onResolve } = renderSheet({ conflict: DUPLICATE_CONFLICT });

      fireEvent.click(screen.getByText("Update the existing one"));

      expect(onResolve).toHaveBeenCalledWith("update_existing");
    });
  });

  describe("the absence of a dismiss path", () => {
    it("renders no X button and no dismiss button", () => {
      renderSheet();

      expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /dismiss/i })).not.toBeInTheDocument();
    });

    it("refuses the Escape key", () => {
      renderSheet();

      const dialog = screen.getByRole("dialog", { name: "Schedule conflict" });
      const event = new Event("cancel", { cancelable: true });
      dialog.dispatchEvent(event);

      expect(event.defaultPrevented).toBe(true);
    });

    it("ignores a backdrop click", () => {
      renderSheet();

      fireEvent.click(screen.getByRole("dialog", { name: "Schedule conflict" }));

      expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument();
    });

    it("says so, so the absence is not a mystery", () => {
      renderSheet();

      expect(
        screen.getByText("No dismiss button — conflict must be resolved before continuing."),
      ).toBeInTheDocument();
    });
  });

  describe("the copy", () => {
    it("uses the time-conflict header", () => {
      renderSheet();

      expect(
        screen.getByRole("heading", { name: "This overlaps with another event." }),
      ).toBeInTheDocument();
    });

    it("uses the duplicate header", () => {
      renderSheet({ conflict: DUPLICATE_CONFLICT });

      expect(screen.getByRole("heading", { name: "These overlap." })).toBeInTheDocument();
    });

    it("names the event that was already saved in the subhead", () => {
      renderSheet();

      expect(
        screen.getByText(
          `You've already saved ${TIME_CONFLICT.other.name}. Choose how to handle it.`,
        ),
      ).toBeInTheDocument();
    });

    it("has no exclamation marks and no alarm words in the copy", () => {
      renderSheet();

      // The amber circle's "!" is a decorative glyph (it is `aria-hidden` and the mockup
      // draws it too), so the calm voice is a property of the *prose* — the headings, the
      // subhead, the action labels and their hints.
      const copy = [
        screen.getByRole("heading", { name: "This overlaps with another event." }).textContent,
        screen.getByText(/You've already saved/).textContent,
        screen.getByText("Keep both — I'll manage").textContent,
        screen.getByText("Edit the new one").textContent,
        screen.getByText("Delete the new one").textContent,
        screen.getByText(/Both events stay on your timeline/).textContent,
        screen.getByText(/Open the event in edit mode/).textContent,
        screen.getByText(/Removes the new event/).textContent,
        screen.getByText(/No dismiss button/).textContent,
      ].join(" ");

      expect(copy).not.toContain("!");
      expect(copy.toLowerCase()).not.toMatch(/error|warning|urgent|critical|failed|danger/);
    });

    it("hides the amber circle's glyph from assistive technology", () => {
      renderSheet();

      const glyph = screen
        .getByRole("dialog", { name: "Schedule conflict" })
        .querySelector('[aria-hidden="true"]');
      expect(glyph?.textContent).toBe("!");
    });
  });

  describe("the two cards", () => {
    it("shows both events, marking the new one NEW", () => {
      renderSheet();

      expect(screen.getByText("Anniversary dinner with Rahul")).toBeInTheDocument();
      expect(screen.getByText("Free tech meetup — Designing for Calm")).toBeInTheDocument();
      expect(screen.getByText("NEW")).toBeInTheDocument();
    });

    it("gives each card the amber conflict dot, labelled", () => {
      renderSheet();

      const dots = screen.getAllByRole("img", { name: "Schedule conflict" });
      expect(dots).toHaveLength(2);
      for (const dot of dots) {
        expect(dot).toHaveClass("bg-warn-amber");
      }
    });

    it("does not use the signal-warn token for the conflict dot", () => {
      renderSheet();

      const dot = screen.getAllByRole("img", { name: "Schedule conflict" })[0];
      expect(dot).not.toHaveClass("bg-signal-warn");
    });

    it("renders a location it was not given", () => {
      // `ConflictSideOut` carries no location, so the card must not invent one.
      renderSheet();

      const dialog = screen.getByRole("dialog", { name: "Schedule conflict" });
      expect(dialog.textContent).not.toMatch(/Brooklyn|Williamsburg/i);
    });
  });

  describe("the announcement and the focus", () => {
    it("announces the conflict assertively", () => {
      renderSheet();

      const live = screen.getByText("Schedule conflict. Three choices.");
      expect(live).toHaveAttribute("aria-live", "assertive");
    });

    it("moves focus to the header", () => {
      renderSheet();

      expect(
        screen.getByRole("heading", { name: "This overlaps with another event." }),
      ).toHaveFocus();
    });
  });

  describe("the aria-labels", () => {
    it("names each action and its consequence", () => {
      renderSheet();

      expect(
        screen.getByRole("button", {
          name: "Keep both events. The conflict indicator remains on both.",
        }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", {
          name: "Edit the new event. Its start time is highlighted so you can move it.",
        }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", {
          name: "Delete the new event. You will be asked to confirm before it is removed.",
        }),
      ).toBeInTheDocument();
    });
  });

  describe("the delete confirmation", () => {
    it("does not delete until the confirmation is answered", () => {
      const { onResolve } = renderSheet();

      fireEvent.click(screen.getByText("Delete the new one"));

      expect(onResolve).not.toHaveBeenCalled();
      expect(screen.getByText("Delete “Anniversary dinner with Rahul”?")).toBeInTheDocument();
      expect(screen.getByText("This can't be undone.")).toBeInTheDocument();
    });

    it("deletes once the confirmation is given", () => {
      const { onResolve } = renderSheet();

      fireEvent.click(screen.getByText("Delete the new one"));
      fireEvent.click(screen.getByRole("button", { name: /^Delete / }));

      expect(onResolve).toHaveBeenCalledWith("delete_new");
    });

    it("returns to the three choices when the deletion is called off", () => {
      const { onResolve } = renderSheet();

      fireEvent.click(screen.getByText("Delete the new one"));
      fireEvent.click(screen.getByRole("button", { name: /Keep the new event/ }));

      expect(onResolve).not.toHaveBeenCalled();
      expect(screen.getByText("Keep both — I'll manage")).toBeInTheDocument();
    });
  });
});
