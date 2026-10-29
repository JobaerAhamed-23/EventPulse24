/**
 * The timezone conversion: a local wall-clock time in a zone becomes the UTC instant the
 * API takes, and back again.
 *
 * The backend does not reinterpret a wall-clock time in a zone — `start_time_utc` is an
 * absolute instant — so this conversion is the form's responsibility, and it has to be
 * right in both daylight-saving states.
 */
import { describe, expect, it } from "vitest";

import {
  ZONE_CHOICES,
  browserZone,
  formatLocalDate,
  formatLocalTime,
  localToUtcInstant,
  toApiInstant,
  utcInstantToLocal,
} from "@/lib/timezones";

describe("the zone list", () => {
  it("offers only zones the backend accepts", () => {
    // The backend's `canonical_zone` accepts a zone under a primary area, or UTC.
    for (const choice of ZONE_CHOICES) {
      if (choice.value === "UTC") continue;
      expect(choice.value).toMatch(/^[A-Za-z]+\/[A-Za-z_]+$/);
    }
  });

  it("gives every zone a city label", () => {
    for (const choice of ZONE_CHOICES) {
      expect(choice.label.length).toBeGreaterThan(0);
    }
  });

  it("offers no zone twice", () => {
    const values = ZONE_CHOICES.map((choice) => choice.value);
    expect(new Set(values).size).toBe(values.length);
  });

  it("is a curated list, not the full IANA set", () => {
    expect(ZONE_CHOICES.length).toBeGreaterThan(5);
    expect(ZONE_CHOICES.length).toBeLessThan(50);
  });
});

describe("the browser's own zone", () => {
  it("is offered when it is one of the choices", () => {
    const zone = browserZone();
    if (zone === null) return;
    expect(ZONE_CHOICES.some((choice) => choice.value === zone)).toBe(true);
  });
});

describe("local time to a UTC instant", () => {
  it("converts a winter evening in New York", () => {
    // EST is five hours behind UTC, so 7:30 PM is half past midnight the next day.
    const instant = localToUtcInstant({ date: "2026-11-06", time: "19:30" }, "America/New_York");
    expect(instant?.toISOString()).toBe("2026-11-07T00:30:00.000Z");
  });

  it("converts a summer evening in New York", () => {
    // EDT is four hours behind UTC — the same wall clock, a different instant.
    const instant = localToUtcInstant({ date: "2026-07-06", time: "19:30" }, "America/New_York");
    expect(instant?.toISOString()).toBe("2026-07-06T23:30:00.000Z");
  });

  it("converts a winter noon in London", () => {
    const instant = localToUtcInstant({ date: "2026-11-06", time: "12:00" }, "Europe/London");
    expect(instant?.toISOString()).toBe("2026-11-06T12:00:00.000Z");
  });

  it("converts a summer noon in London", () => {
    // BST is one hour ahead of UTC.
    const instant = localToUtcInstant({ date: "2026-07-06", time: "12:00" }, "Europe/London");
    expect(instant?.toISOString()).toBe("2026-07-06T11:00:00.000Z");
  });

  it("converts a morning in Tokyo", () => {
    const instant = localToUtcInstant({ date: "2026-11-06", time: "09:00" }, "Asia/Tokyo");
    expect(instant?.toISOString()).toBe("2026-11-06T00:00:00.000Z");
  });

  it("converts a half-hour offset zone", () => {
    // India is five and a half hours ahead of UTC.
    const instant = localToUtcInstant({ date: "2026-11-06", time: "12:00" }, "Asia/Kolkata");
    expect(instant?.toISOString()).toBe("2026-11-06T06:30:00.000Z");
  });

  it("converts UTC to itself", () => {
    const instant = localToUtcInstant({ date: "2026-11-06", time: "12:00" }, "UTC");
    expect(instant?.toISOString()).toBe("2026-11-06T12:00:00.000Z");
  });

  it("refuses a local time that the clock jumps over", () => {
    // 2:30 AM on a spring-forward morning does not exist in New York.
    expect(localToUtcInstant({ date: "2026-03-08", time: "02:30" }, "America/New_York")).toBeNull();
  });

  it("refuses a malformed date", () => {
    expect(localToUtcInstant({ date: "06-11-2026", time: "12:00" }, "UTC")).toBeNull();
  });

  it("refuses a malformed time", () => {
    expect(localToUtcInstant({ date: "2026-11-06", time: "7pm" }, "UTC")).toBeNull();
  });

  it("refuses an impossible hour", () => {
    expect(localToUtcInstant({ date: "2026-11-06", time: "25:00" }, "UTC")).toBeNull();
  });
});

describe("the API's instant format", () => {
  it("is UTC with a Z and no fractional seconds", () => {
    const instant = localToUtcInstant({ date: "2026-07-06", time: "19:30" }, "America/New_York");
    expect(instant).not.toBeNull();
    expect(toApiInstant(instant as Date)).toBe("2026-07-06T23:30:00Z");
  });
});

describe("a UTC instant back to local time", () => {
  it("round-trips", () => {
    const instant = localToUtcInstant({ date: "2026-11-06", time: "19:30" }, "America/New_York");
    expect(instant).not.toBeNull();
    expect(utcInstantToLocal(instant as Date, "America/New_York")).toEqual({
      date: "2026-11-06",
      time: "19:30",
    });
  });

  it("round-trips across a half-hour offset zone", () => {
    const instant = localToUtcInstant({ date: "2026-11-06", time: "12:00" }, "Asia/Kolkata");
    expect(instant).not.toBeNull();
    expect(utcInstantToLocal(instant as Date, "Asia/Kolkata")).toEqual({
      date: "2026-11-06",
      time: "12:00",
    });
  });

  it("renders the date and time separately", () => {
    const instant = new Date("2026-11-06T23:30:00Z");
    expect(formatLocalDate(instant, "America/New_York")).toBe("2026-11-06");
    expect(formatLocalTime(instant, "America/New_York")).toBe("18:30");
  });
});
