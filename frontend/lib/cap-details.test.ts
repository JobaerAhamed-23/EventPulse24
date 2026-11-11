import { describe, expect, it } from "vitest";

import { readCapDetails } from "@/lib/cap-details";

/** The save cap's refusal, exactly as `save_cap.py` builds it. */
const SAVE_CAP = {
  code: "save_cap_reached",
  message: "You've used your free save for today.",
  details: { cap: 1, upgrade_hint: "You saved one event today. Save more with Pro." },
};

/** The calendar cap's refusal, exactly as `calendar_connections.py` builds it. */
const CALENDAR_CAP = {
  code: "calendar_cap_reached",
  message: "You've connected the calendars your plan allows.",
  details: { cap: 1, upgrade_hint: "Save more with Pro." },
};

describe("readCapDetails", () => {
  it("reads the save cap", () => {
    expect(readCapDetails(SAVE_CAP)).toEqual({
      cap: 1,
      upgradeHint: "You saved one event today. Save more with Pro.",
    });
  });

  it("reads the calendar cap, which is the same shape from a different endpoint", () => {
    expect(readCapDetails(CALENDAR_CAP)).toEqual({ cap: 1, upgradeHint: "Save more with Pro." });
  });

  it("reads the hint verbatim, whatever the backend changes it to", () => {
    // The acceptance criterion: backend copy changes need no frontend change. Nothing
    // here matches on, trims or rewrites the sentence.
    const reworded = {
      ...SAVE_CAP,
      details: { cap: 3, upgrade_hint: "Three saves a day is the free plan. Pro has no limit." },
    };
    expect(readCapDetails(reworded)).toEqual({
      cap: 3,
      upgradeHint: "Three saves a day is the free plan. Pro has no limit.",
    });
  });

  describe("is not a cap", () => {
    it("the other 409 on the save endpoint", () => {
      // `scheduling_conflict` shares the status code and nothing else. If this read
      // ever returned a cap for it, the Detail Screen would show an upgrade prompt
      // instead of opening the conflict sheet.
      expect(
        readCapDetails({
          code: "scheduling_conflict",
          message: "That clashes with something you've saved.",
          details: { conflicts: [{ id: "c1" }] },
        }),
      ).toBeNull();
    });

    it("a non-cap code that happens to carry cap-shaped fields", () => {
      // **The `code` decides, not the fields.** Without this the narrowing would be
      // untested: `scheduling_conflict` carries no `cap`/`upgrade_hint`, so the field
      // checks alone already reject it, and removing the code check breaks nothing.
      // This is the case that makes the code check load-bearing — a refusal that is not
      // a cap must not render an upgrade prompt merely because its payload grew the
      // right-looking fields.
      expect(
        readCapDetails({
          code: "scheduling_conflict",
          message: "That clashes with something you've saved.",
          details: { cap: 1, upgrade_hint: "Save more with Pro." },
        }),
      ).toBeNull();
    });

    it("an ordinary error", () => {
      expect(readCapDetails({ code: "invalid_credentials", message: "No." })).toBeNull();
    });

    it("a cap code with no details", () => {
      expect(readCapDetails({ code: "save_cap_reached", message: "No." })).toBeNull();
    });

    it("a cap code with an empty or missing hint", () => {
      // A bare "Upgrade" link with no sentence explaining it is worse than the
      // surface's ordinary refusal line, so this falls back to that.
      expect(
        readCapDetails({ code: "save_cap_reached", details: { cap: 1, upgrade_hint: "" } }),
      ).toBeNull();
      expect(readCapDetails({ code: "save_cap_reached", details: { cap: 1 } })).toBeNull();
    });

    it("a cap whose `cap` is not a number", () => {
      expect(
        readCapDetails({ code: "save_cap_reached", details: { cap: "1", upgrade_hint: "Pro." } }),
      ).toBeNull();
    });

    it("something that is not an error body at all", () => {
      expect(readCapDetails(null)).toBeNull();
      expect(readCapDetails(undefined)).toBeNull();
      expect(readCapDetails("save_cap_reached")).toBeNull();
      expect(readCapDetails(new Error("network"))).toBeNull();
    });
  });

  it("never reads a modal-shaped field, even if the payload grows one", () => {
    // Both backends state that the payload carries no `modal`, `title`, `actions` or
    // `dismissable` *by design*. This pins the frontend half: a payload that grew them
    // could not turn the prompt into an interruption without someone editing the
    // component on purpose.
    const withModalFields = {
      ...SAVE_CAP,
      details: {
        ...SAVE_CAP.details,
        modal: true,
        title: "Upgrade now!",
        actions: [{ label: "Not now" }],
        dismissable: true,
      },
    };
    const read = readCapDetails(withModalFields);
    expect(read).toEqual({
      cap: 1,
      upgradeHint: "You saved one event today. Save more with Pro.",
    });
    expect(Object.keys(read ?? {})).toEqual(["cap", "upgradeHint"]);
  });
});
