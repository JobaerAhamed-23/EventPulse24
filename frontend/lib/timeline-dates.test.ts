import { describe, expect, it } from "vitest";

import {
  addDays,
  dayOfMonth,
  isLocalDate,
  longDate,
  shortDate,
  today,
  weekRange,
  weekdayIndex,
  weekdayLong,
  weekdayShort,
} from "@/lib/timeline-dates";

/**
 * The Timeline's date arithmetic.
 *
 * **A calendar date is not an instant.** `new Date("2026-11-02")` is UTC midnight, and
 * reading its day-of-week gives the *server's* week, not the user's. The grid is
 * Monday–Sunday in the user's zone, so the weekday label has to come from the same
 * arithmetic the server used — the day-of-week of the **date**, read as a calendar
 * date. These tests pin that, because the failure is silent: the labels would simply
 * be shifted by one.
 *
 * **The day arithmetic is on calendar dates, not on instants.** Adding 86,400,000ms to
 * a UTC instant would give the same answer here, but it would not across a DST
 * boundary, and a day navigator that skipped a day would be a bug the user cannot
 * explain.
 */

describe("the weekday of a calendar date", () => {
  it("reads the date's own weekday, not the instant's", () => {
    // 2026-11-02 is a Monday.
    expect(weekdayIndex("2026-11-02")).toBe(0);
    expect(weekdayShort("2026-11-02")).toBe("Mon");
    expect(weekdayLong("2026-11-02")).toBe("Monday");
  });

  it("puts Sunday last, because the grid starts on Monday", () => {
    expect(weekdayIndex("2026-11-08")).toBe(6);
    expect(weekdayShort("2026-11-08")).toBe("Sun");
    expect(weekdayLong("2026-11-08")).toBe("Sunday");
  });

  it("does not slip when the date is the first of a month", () => {
    // 2026-11-01 is a Sunday, and the first of the month is where an off-by-one from
    // a month index would show up.
    expect(weekdayIndex("2026-11-01")).toBe(6);
    expect(weekdayIndex("2026-12-01")).toBe(1);
  });

  it("does not slip across a year boundary", () => {
    expect(weekdayIndex("2027-01-01")).toBe(4);
  });
});

describe("the day of the month", () => {
  it("is the date's day, zero-padded in the source and unpadded here", () => {
    expect(dayOfMonth("2026-11-02")).toBe(2);
    expect(dayOfMonth("2026-11-30")).toBe(30);
  });
});

describe("addDays", () => {
  it("adds a day on the calendar", () => {
    expect(addDays("2026-11-02", 1)).toBe("2026-11-03");
  });

  it("crosses a month boundary", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
  });

  it("crosses a year boundary", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("goes backwards", () => {
    expect(addDays("2026-11-02", -1)).toBe("2026-11-01");
    expect(addDays("2026-11-02", -7)).toBe("2026-10-26");
  });

  it("does not skip a day across a DST boundary", () => {
    // The US spring-forward is 2026-03-08 and the fall-back is 2026-11-01. Adding a
    // calendar day across either must land on the next calendar date.
    expect(addDays("2026-03-07", 1)).toBe("2026-03-08");
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
  });
});

describe("isLocalDate", () => {
  it("accepts a well-formed date", () => {
    expect(isLocalDate("2026-11-02")).toBe(true);
  });

  it("rejects a malformed value", () => {
    expect(isLocalDate("not-a-date")).toBe(false);
    expect(isLocalDate("2026-11")).toBe(false);
    expect(isLocalDate("")).toBe(false);
    expect(isLocalDate(null)).toBe(false);
    expect(isLocalDate(undefined)).toBe(false);
  });

  it("rejects a date that does not exist, rather than rolling it over", () => {
    // "2026-02-30" parses — it rolls into March — so the round trip is the real check.
    expect(isLocalDate("2026-02-30")).toBe(false);
    expect(isLocalDate("2026-13-01")).toBe(false);
  });
});

describe("the date's written forms", () => {
  it("writes the short date", () => {
    expect(shortDate("2026-11-02")).toBe("Nov 2");
  });

  it("writes the long date", () => {
    expect(longDate("2026-11-02")).toBe("November 2, 2026");
  });

  it("writes a week range within one month", () => {
    expect(weekRange("2026-11-02", "2026-11-08")).toBe("Nov 2 – 8");
  });

  it("names both months when the range crosses one", () => {
    expect(weekRange("2026-10-26", "2026-11-01")).toBe("Oct 26 – Nov 1");
  });
});

describe("today", () => {
  it("is a well-formed calendar date", () => {
    expect(isLocalDate(today())).toBe(true);
  });
});
