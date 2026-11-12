/**
 * The notification settings' pure helpers.
 *
 * **The weekday numbering is the one worth a test of its own.** A client that started its
 * week on Sunday would send Sunday's window as Monday's; the request would be perfectly
 * valid, nothing would raise, and the user would simply be quiet on the wrong night. That
 * failure is invisible to every other test in the suite, so it is pinned here.
 */
import { describe, expect, it } from "vitest";

import {
  DEFAULT_QUIET_HOURS,
  WEEKDAYS,
  clockForInput,
  clockLabel,
  crossesMidnight,
  windowLabel,
} from "@/lib/notification-settings";

describe("WEEKDAYS", () => {
  it("runs Monday 0 through Sunday 6, the server's numbering", () => {
    // `QuietHoursOverrideIn.weekday`: "Monday 0 through Sunday 6" — Python's
    // `date.weekday()`, which `domain/quiet_hours.py` indexes its week by.
    expect(WEEKDAYS.map((day) => day.long)).toEqual([
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
      "Sunday",
    ]);
    expect(WEEKDAYS.map((day) => day.index)).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });
});

describe("clockLabel", () => {
  it("drops the minutes when they are zero", () => {
    expect(clockLabel("22:00:00")).toBe("10pm");
    expect(clockLabel("08:00:00")).toBe("8am");
  });

  it("keeps the minutes when there are any", () => {
    expect(clockLabel("22:30:00")).toBe("10:30pm");
    expect(clockLabel("06:05:00")).toBe("6:05am");
  });

  it("says 12am at midnight and 12pm at noon", () => {
    // The two values a naive `% 12` prints as "0am" and "0pm".
    expect(clockLabel("00:00:00")).toBe("12am");
    expect(clockLabel("12:00:00")).toBe("12pm");
  });

  it("is empty for a missing clock", () => {
    expect(clockLabel("")).toBe("");
  });
});

describe("windowLabel", () => {
  it("joins the two clocks with an en dash", () => {
    expect(windowLabel("22:00:00", "08:00:00")).toBe("10pm–8am");
  });
});

describe("crossesMidnight", () => {
  it("is true when the end is earlier in the day than the start", () => {
    expect(crossesMidnight("22:00:00", "08:00:00")).toBe(true);
  });

  it("is false for a window inside one day", () => {
    expect(crossesMidnight("01:00:00", "10:00:00")).toBe(false);
  });

  it("is false for two equal clocks", () => {
    // The server refuses `start == end` outright, so it never reaches a stored window.
    // Calling it a crossing would put "reaches into tomorrow" under a broken window.
    expect(crossesMidnight("22:00:00", "22:00:00")).toBe(false);
  });

  it("is false when either clock is missing", () => {
    expect(crossesMidnight("22:00:00", "")).toBe(false);
    expect(crossesMidnight("", "08:00:00")).toBe(false);
  });
});

describe("the server's default window", () => {
  it("is 22:00–08:00, stored-shaped", () => {
    // The backend's `DEFAULT_QUIET_HOURS_START`/`END`. The locked label — "10pm–8am.
    // Nothing during this window." — says the same, and the two have to agree.
    expect(DEFAULT_QUIET_HOURS).toEqual({ start: "22:00:00", end: "08:00:00" });
    expect(clockForInput(DEFAULT_QUIET_HOURS.start)).toBe("22:00");
    expect(windowLabel(DEFAULT_QUIET_HOURS.start, DEFAULT_QUIET_HOURS.end)).toBe("10pm–8am");
  });
});
