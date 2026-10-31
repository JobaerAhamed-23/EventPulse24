import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ConflictSideView } from "@/components/conflicts/conflict-side";
import type { ConflictSide } from "@/lib/conflict-wording";

/**
 * One side of a conflict pair.
 *
 * **Colour is never the sole carrier of meaning (WCAG 1.4.1).** Every side carries a
 * coloured stripe *and* a visible text label, so the two kinds are tellable apart
 * without colour vision. These tests pin the pairing, because a stripe without its
 * label is a rule that fails silently and nobody notices until somebody cannot use the
 * screen.
 *
 * **An unavailable side says so.** A side whose record cannot be read has no title to
 * show, and the state has to be explicit rather than looking like an event with no name.
 */

const PERSONAL_ID = "11111111-1111-1111-1111-111111111111";
const SAVED_ID = "22222222-2222-2222-2222-222222222222";

function personal(overrides: Partial<ConflictSide> = {}): ConflictSide {
  return {
    available: true,
    end_time_utc: null,
    id: PERSONAL_ID,
    kind: "personal_event",
    name: "Work standup",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-09-08T13:00:00Z",
    ...overrides,
  };
}

function saved(overrides: Partial<ConflictSide> = {}): ConflictSide {
  return {
    available: true,
    end_time_utc: null,
    id: SAVED_ID,
    kind: "saved_event",
    name: "Designers coffee chat",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-09-08T13:15:00Z",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("the side's category", () => {
  it("pairs a personal side's stripe with the word 'Personal'", () => {
    render(<ConflictSideView side={personal()} />);

    expect(screen.getByText("Personal")).toBeInTheDocument();
    // The stripe is the second signal, and it is hidden from the screen reader — the
    // word beside it is what carries the meaning.
    expect(document.querySelector('[aria-hidden="true"]')).not.toBeNull();
  });

  it("pairs a saved side's stripe with the words 'Public event'", () => {
    render(<ConflictSideView side={saved()} />);

    expect(screen.getByText("Public event")).toBeInTheDocument();
  });

  it("never says 'Public' on its own — the label is 'Public event'", () => {
    render(<ConflictSideView side={saved()} />);

    expect(screen.queryByText("Public")).toBeNull();
  });
});

describe("the side's time", () => {
  it("renders the time in the side's own zone", () => {
    render(<ConflictSideView side={personal()} />);

    // 13:00 UTC on Sep 8 is 9:00 AM in New York (EDT, UTC-4).
    expect(screen.getByText(/9:00 AM EDT/)).toBeInTheDocument();
  });

  it("renders each side's own clock when the two zones differ", () => {
    const { container } = render(
      <>
        <ConflictSideView side={personal()} />
        <ConflictSideView side={saved({ start_time_tz: "Europe/London" })} />
      </>,
    );

    // 13:00 UTC is 9:00 AM in New York and 2:00 PM in London. Two records, two
    // different zones — both clocks are true. (`Intl` renders London's September
    // offset as "GMT+1" rather than "BST", so the assertion pins the clock and not
    // the platform's choice of zone label.)
    const text = container.textContent ?? "";
    expect(text).toContain("9:00 AM EDT");
    expect(text).toContain("2:15 PM");
  });
});

describe("the unavailable side", () => {
  it("says the event is no longer available", () => {
    render(<ConflictSideView side={saved({ available: false, name: null })} />);

    expect(screen.getByText("Event no longer available")).toBeInTheDocument();
  });

  it("still says which kind of thing it was", () => {
    // The kind label is independent of the name — an unreadable public event is still a
    // public event, and the user needs to know what they are looking at.
    render(<ConflictSideView side={saved({ available: false, name: null })} />);

    expect(screen.getByText("Public event")).toBeInTheDocument();
  });
});
