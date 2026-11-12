/**
 * Browse's *words* — the translation from the server's numbers to the reader's language.
 *
 * **These are pure functions, so they are tested as pure functions.** `lib/browse-labels.ts`
 * is the only place in the Browse surface that turns a number into a sentence, and every
 * one of those sentences is a claim the reader will believe. A rounding bug here is a
 * wrong number on the page, and a timezone bug here is a wrong *day* on the page.
 *
 * **The two hard cases are the ones a rendering test cannot reach.**
 *
 * 1. **The window's date is the window's first day *in the user's own zone*.** Read in
 *    UTC, a window that opens at 7pm Eastern on Thursday names *Wednesday* — and the
 *    window is a local idea, so naming the previous day for anyone west of Greenwich is
 *    the bug this file exists to prevent.
 * 2. **A malformed timezone must not take the page down.** `Intl` throws a `RangeError`
 *    on a zone it does not know, and the zone is a string the server wrote.
 */
import { describe, expect, it } from "vitest";

import {
  eventCountLabel,
  quotaNote,
  resetPhrase,
  stripeColour,
  stripeLabel,
  windowDateLabel,
} from "@/lib/browse-labels";

describe("the reset phrase", () => {
  it("says seconds for a window shorter than a minute", () => {
    expect(resetPhrase(0)).toBe("0s");
    expect(resetPhrase(45)).toBe("45s");
  });

  it("says minutes for a window shorter than an hour", () => {
    expect(resetPhrase(60)).toBe("1m");
    expect(resetPhrase(59 * 60)).toBe("59m");
  });

  it("says hours for the quota's own 24-hour window", () => {
    // **The quota window is exactly 24 hours, and every user sees the same number.**
    // "1d" would be the phrase for every one of them, and would hide the number the
    // payload carries.
    expect(resetPhrase(24 * 60 * 60)).toBe("24h");
  });

  it("rounds down, so it never promises more time than there is", () => {
    // 90 minutes is 1.5 hours. Saying "2h" would over-promise by half an hour, and the
    // reader would wait for a reset that has not happened.
    expect(resetPhrase(90 * 60)).toBe("1h");
    expect(resetPhrase(119 * 60)).toBe("1h");
  });

  it("says days only past a day", () => {
    expect(resetPhrase(25 * 60 * 60)).toBe("1d");
    expect(resetPhrase(48 * 60 * 60)).toBe("2d");
  });

  it("never says a negative duration", () => {
    expect(resetPhrase(-100)).toBe("0s");
  });
});

describe("the quota note", () => {
  it("reports the allowance the API stated", () => {
    const note = quotaNote({
      used: 3,
      cap: 10,
      is_pro: false,
      resets_in_seconds: 86400,
    });

    expect(note.text).toBe("Free plan: 3 of 10 saves used today · resets in 24h");
    expect(note.isPro).toBe(false);
  });

  it("says a Pro account has no limit", () => {
    // **A Pro account has `cap: null`, not a very large number.** A cap of "infinity"
    // is a number a client would eventually render into the hero.
    const note = quotaNote({
      used: 99,
      cap: null,
      is_pro: true,
      resets_in_seconds: 0,
    });

    expect(note.text).toBe("Pro plan · no save limit");
    expect(note.isPro).toBe(true);
  });

  it("treats an absent cap as a null one", () => {
    // Django Ninja omits the field when it is null, so "absent" and "explicitly null"
    // are the same answer arriving by two routes.
    const note = quotaNote({
      used: 0,
      is_pro: false,
      resets_in_seconds: 3600,
    });

    expect(note.isPro).toBe(true);
  });

  it('says "save" when the cap is one', () => {
    const note = quotaNote({
      used: 1,
      cap: 1,
      is_pro: false,
      resets_in_seconds: 3600,
    });

    expect(note.text).toContain("1 of 1 save used today");
  });
});

describe("the event count", () => {
  it('says "event" for one and "events" for more', () => {
    expect(eventCountLabel(1)).toBe("1 event");
    expect(eventCountLabel(0)).toBe("0 events");
    expect(eventCountLabel(147)).toBe("147 events");
  });
});

describe("the window's date", () => {
  it("names the window's first day in the user's own zone", () => {
    // 7pm Eastern on Saturday 7 November 2026. Read in UTC this is 23:00 on the 7th —
    // the *same* date, but only because the window opens late in the evening. The
    // point of the local zone is the reader's Saturday, not Greenwich's.
    const label = windowDateLabel("2026-11-07T23:00:00Z", "America/New_York");
    expect(label).toBe("Sat, Nov 7");
  });

  it("names the reader's day, not Greenwich's, when the window opens late", () => {
    // 2am Eastern on Sunday 8 November is 07:00 UTC — still Sunday. But 11pm Eastern
    // on Saturday 7 November is 04:00 UTC on *Sunday* the 8th, so a UTC reading
    // names tomorrow for a reader whose tonight is tonight.
    const label = windowDateLabel("2026-11-08T04:00:00Z", "America/New_York");
    expect(label).toBe("Sat, Nov 7");
  });

  it("names the same instant on different sides of the Atlantic", () => {
    const label = windowDateLabel("2026-11-08T02:00:00Z", "Europe/London");
    expect(label).toBe("Sun, Nov 8");
  });

  it("survives a timezone the runtime does not know", () => {
    // **An unusable zone is not a crash.** `Intl` throws a `RangeError` on a malformed
    // `timeZone`, and the zone is a string the server wrote — a typo would otherwise
    // take the whole page down over a label.
    expect(() => windowDateLabel("2026-11-07T23:00:00Z", "Not/AZone")).not.toThrow();
    expect(windowDateLabel("2026-11-07T23:00:00Z", "Not/AZone")).toBe("Sat, Nov 7");
  });

  it("returns nothing for an unreadable date", () => {
    expect(windowDateLabel("not-a-date", "America/New_York")).toBe("");
  });
});

describe("the stripe", () => {
  it("names the two stripes in words", () => {
    // Colour is never the only carrier (WCAG 1.4.1).
    expect(stripeLabel("public")).toBe("Public");
    expect(stripeLabel("must_know")).toBe("Must-know");
  });

  it("falls back to the public treatment for an unrecognised stripe", () => {
    // Amendment A-12 caps the stripes at two. An unrecognised stripe is a public card,
    // not a card in a third colour.
    expect(stripeLabel("discovery")).toBe("Public");
    expect(stripeColour("discovery")).toBe(stripeColour("public"));
  });

  it("uses slate for public and amber for must-know, and nothing else", () => {
    expect(stripeColour("public")).toBe("bg-accent-slate");
    expect(stripeColour("must_know")).toBe("bg-accent-amber");
  });
});
