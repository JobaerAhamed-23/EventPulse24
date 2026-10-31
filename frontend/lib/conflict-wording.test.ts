import { describe, expect, it } from "vitest";

import {
  actionSide,
  asResolution,
  movableSide,
  resolutionPhrase,
  reviewActionAria,
  reviewActionLabel,
  type ConflictSide,
} from "@/lib/conflict-wording";

/**
 * The conflict wording, shared by the prompt and the review screen.
 *
 * **The rules these tests pin are the rules the two surfaces could disagree on.** A
 * drift between a prompt's button and the review screen's button would be a bug the
 * user finds by clicking, so the wording is built once and tested once.
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

describe("narrowing a server action name", () => {
  it("accepts the five resolutions the API owns", () => {
    expect(asResolution("keep_both")).toBe("keep_both");
    expect(asResolution("edit_new")).toBe("edit_new");
    expect(asResolution("update_existing")).toBe("update_existing");
    expect(asResolution("delete_new")).toBe("delete_new");
    expect(asResolution("skip_public")).toBe("skip_public");
  });

  it("rejects a name outside the closed set", () => {
    // A choice the surface cannot explain is not a choice it offers.
    expect(asResolution("dismiss")).toBeNull();
    expect(asResolution("")).toBeNull();
  });
});

describe("the review screen's label", () => {
  it("names the event a move acts on", () => {
    expect(reviewActionLabel("edit_new", "Work standup")).toBe("Move Work standup");
    expect(reviewActionLabel("update_existing", "Work standup")).toBe("Move Work standup");
  });

  it("names the event a skip acts on", () => {
    expect(reviewActionLabel("skip_public", "Designers coffee chat")).toBe(
      "Skip Designers coffee chat",
    );
  });

  it("names the event a delete acts on", () => {
    expect(reviewActionLabel("delete_new", "Work standup")).toBe("Delete Work standup");
  });

  it("says 'Keep both' for the one action that is about neither side", () => {
    expect(reviewActionLabel("keep_both", "Work standup")).toBe("Keep both — I'll manage");
  });

  it("falls back to the kind's noun when the name is missing", () => {
    // "Move " with nothing after it would be a broken label.
    expect(reviewActionLabel("edit_new", null)).toBe("Move the personal event");
    expect(reviewActionLabel("edit_new", "   ")).toBe("Move the personal event");
    expect(reviewActionLabel("skip_public", undefined)).toBe("Skip the public event");
  });
});

describe("the review screen's accessible name", () => {
  it("says the action and its consequence", () => {
    const aria = reviewActionAria("edit_new", "Work standup");
    expect(aria).toContain("Move Work standup");
    // The consequence — what actually happens when the button is pressed.
    expect(aria).toMatch(/highlight/i);
  });

  it("says the consequence for keep both", () => {
    expect(reviewActionAria("keep_both", "Work standup")).toBe(
      "Keep both events. The conflict indicator remains on both.",
    );
  });

  it("says the consequence for a skip", () => {
    expect(reviewActionAria("skip_public", "Designers coffee chat")).toContain("released");
  });
});

describe("the side a resolution acts on", () => {
  it("moves the personal side", () => {
    const side = actionSide("edit_new", personal(), saved());
    expect(side).toEqual({ kind: "personal_event", id: PERSONAL_ID });
  });

  it("releases the saved side", () => {
    const side = actionSide("skip_public", personal(), saved());
    expect(side).toEqual({ kind: "saved_event", id: SAVED_ID });
  });

  it("deletes the personal side", () => {
    const side = actionSide("delete_new", personal(), saved());
    expect(side).toEqual({ kind: "personal_event", id: PERSONAL_ID });
  });

  it("updates the personal side", () => {
    // The backend's `_target_side_kind` maps **every** resolution but `skip_public` to
    // the personal side — including `update_existing`. Naming the saved side here
    // would be refused with `IllegalResolutionError`.
    const side = actionSide("update_existing", personal(), saved());
    expect(side).toEqual({ kind: "personal_event", id: PERSONAL_ID });
  });

  it("acts on neither side for keep both", () => {
    expect(actionSide("keep_both", personal(), saved())).toBeNull();
  });

  it("does not depend on which side the row happens to have stored first", () => {
    // The pair row stores its sides sorted by id, so `left` is not "the personal one".
    const side = actionSide("edit_new", saved(), personal());
    expect(side).toEqual({ kind: "personal_event", id: PERSONAL_ID });
  });

  it("answers deterministically for a pair with two personal sides", () => {
    // Both sides are the same kind, so "the personal side" and "the other side" are the
    // same claim — and the rule falls back to the row's own order.
    const other = personal({ id: "33333333-3333-3333-3333-333333333333", name: "Yoga" });
    expect(actionSide("edit_new", other, personal())).toEqual({
      kind: "personal_event",
      id: other.id,
    });
    expect(actionSide("update_existing", other, personal())).toEqual({
      kind: "personal_event",
      id: PERSONAL_ID,
    });
  });
});

describe("the side a move opens in the edit sheet", () => {
  it("is the personal event", () => {
    const side = movableSide("edit_new", personal(), saved());
    expect(side?.id).toBe(PERSONAL_ID);
  });

  it("is nothing for an action that does not move", () => {
    expect(movableSide("keep_both", personal(), saved())).toBeNull();
    expect(movableSide("skip_public", personal(), saved())).toBeNull();
    expect(movableSide("delete_new", personal(), saved())).toBeNull();
  });

  it("is nothing when the side is a saved event", () => {
    // The edit sheet edits personal events; a saved public event is edited on its own
    // detail screen.
    expect(movableSide("edit_new", saved(), saved())).toBeNull();
  });
});

describe("the resolution phrase", () => {
  it("is the past tense of the decision", () => {
    expect(resolutionPhrase("skip_public")).toBe("Skipped public");
    expect(resolutionPhrase("keep_both")).toBe("Kept both");
    expect(resolutionPhrase("edit_new")).toBe("Moved personal");
    expect(resolutionPhrase("delete_new")).toBe("Deleted personal");
  });

  it("says something honest for a pair with no resolution recorded", () => {
    expect(resolutionPhrase(null)).toBe("Decided");
    expect(resolutionPhrase(undefined)).toBe("Decided");
  });
});
