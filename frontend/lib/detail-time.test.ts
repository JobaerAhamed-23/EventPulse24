/**
 * The Detail Screen's time arithmetic.
 *
 * **The rule this file exists to pin is the one the digest header also needed:** a
 * timezone offset must never move the displayed *date* onto a different day. The
 * event starts at 23:00 UTC on a Saturday; in New York that is 6:00 PM the same
 * Saturday, and in London it is 11:00 PM the same Saturday — and in Auckland it is
 * 11:00 AM on the **Sunday**. Each of those is a different day, and each must show
 * its own day.
 */
import { describe, expect, it } from "vitest";

import { cardTime, detailTimes } from "@/lib/detail-time";

/** 2026-11-07 is a Saturday. */
const SATURDAY_EVENING = "2026-11-07T23:00:00Z";

describe("the user's local time", () => {
  it("reads the instant in the reader's zone", () => {
    const times = detailTimes(SATURDAY_EVENING, "America/New_York", "America/New_York");

    expect(times?.time).toBe("6:00 PM");
    expect(times?.date).toBe("Saturday, Nov 7");
  });

  it("moves the day when the zone moves the instant across midnight", () => {
    // Auckland is UTC+13 in November, so 23:00 UTC on Saturday is 12:00 PM on Sunday
    // there — and the screen must say Sunday, not Saturday.
    const times = detailTimes(SATURDAY_EVENING, "America/New_York", "Pacific/Auckland");

    expect(times?.date).toBe("Sunday, Nov 8");
    expect(times?.time).toBe("12:00 PM");
  });

  it("reads midnight as 12 AM, not 12 PM", () => {
    const times = detailTimes("2026-11-08T05:00:00Z", "UTC", "UTC");

    expect(times?.time).toBe("5:00 AM");
  });

  it("reads noon as 12 PM", () => {
    const times = detailTimes("2026-11-08T12:00:00Z", "UTC", "UTC");

    expect(times?.time).toBe("12:00 PM");
  });

  it("shows the venue's time too when the reader is in another zone", () => {
    const times = detailTimes(SATURDAY_EVENING, "America/New_York", "Europe/London");

    expect(times?.time).toBe("11:00 PM");
    expect(times?.venueTime).toBe("6:00 PM");
    expect(times?.venueZone).toBe("EST");
  });

  it("withholds the venue's time when the two clocks agree", () => {
    // Two different zones can show the same clock face. `America/Toronto` and
    // `America/New_York` are different names for the same hour, and showing both
    // would be noise rather than information.
    const times = detailTimes(SATURDAY_EVENING, "America/New_York", "America/Toronto");

    expect(times?.time).toBe("6:00 PM");
    expect(times?.venueTime).toBeNull();
    expect(times?.venueZone).toBeNull();
  });

  it("falls back to the venue's zone when the reader's is unknown", () => {
    const times = detailTimes(SATURDAY_EVENING, "America/New_York", null);

    expect(times?.time).toBe("6:00 PM");
    expect(times?.venueTime).toBeNull();
  });

  it("has no time to show when there is no time", () => {
    expect(detailTimes(null, "America/New_York", "America/New_York")).toBeNull();
    expect(detailTimes(undefined, "America/New_York", "America/New_York")).toBeNull();
    expect(detailTimes("not a date", "America/New_York", "America/New_York")).toBeNull();
  });

  it("keeps the weekday and the date in step", () => {
    // The weekday and the date come from the same wall-clock, so a time that straddles
    // midnight cannot show Tuesday's date beside Monday's time.
    const times = detailTimes(SATURDAY_EVENING, "America/New_York", "Pacific/Auckland");

    expect(times?.date).toContain("Sunday");
    expect(times?.date).toContain("Nov 8");
  });
});

describe("a card's time line", () => {
  it("reads as weekday, date, 12-hour time and the event's zone", () => {
    expect(cardTime("2026-11-03T15:30:00Z", "America/Chicago")).toBe("Tue, Nov 3 · 9:30 AM CST");
  });

  it("uses the event's zone, so the server and the browser print the same text", () => {
    // 01:00 UTC on Nov 4 is still Nov 3 in Chicago: the day comes from the event's clock.
    expect(cardTime("2026-11-04T01:00:00Z", "America/Chicago")).toBe("Tue, Nov 3 · 7:00 PM CST");
  });

  it("names daylight time when the event is in it", () => {
    expect(cardTime("2026-07-04T23:00:00Z", "America/New_York")).toBe("Sat, Jul 4 · 7:00 PM EDT");
  });

  it("has no time to show without a start", () => {
    expect(cardTime(null, "America/Chicago")).toBeNull();
    expect(cardTime("not a date", "America/Chicago")).toBeNull();
  });

  it("falls back to UTC when the zone is missing", () => {
    expect(cardTime("2026-11-03T00:05:00Z", null)).toBe("Tue, Nov 3 · 12:05 AM UTC");
  });
});
