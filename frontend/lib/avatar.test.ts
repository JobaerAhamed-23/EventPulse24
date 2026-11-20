/**
 * The initials rule — **the fallback for an account with no picture.**
 *
 * ## Why this file exists
 *
 * **The rule was going to be pasted into three places** — the sidenav's account row, the
 * bottom bar's More sheet and the account sheet — and each of them draws the disc. A
 * rule with three copies is a rule that can differ from itself in three places, and the
 * difference would be visible: one rail with two letters and another with one.
 *
 * **This file pins the one copy.** The cases below are the cases the rule makes, written
 * down, so the next reader does not have to re-derive them from the source.
 *
 * ## The property that matters most
 *
 * **The initials never blank the name.** The name is rendered as text beside the disc
 * whatever the disc shows, and the disc falls back to initials rather than to nothing —
 * so an account with no picture still looks like an account.
 */
import { describe, expect, it } from "vitest";

import { initials } from "@/lib/avatar";

describe("the initials of a display name", () => {
  it("are one letter per word, at most two", () => {
    expect(initials("Maya Ahmed")).toBe("MA");
  });

  it("are one letter when the name is one word", () => {
    expect(initials("Maya")).toBe("M");
  });

  it("are the first two words, not the first two characters", () => {
    // **The distinction the rule is about.** "Mary-Jane Watson" is two words — the
    // hyphen is inside one of them — so the initials are "MW".
    //
    // A rule that took the first two *characters* would say "MA", which are the first
    // two letters of one word and say nothing about the second word at all.
    expect(initials("Mary-Jane Watson")).toBe("MW");
    expect(initials("Mary-Jane")).toBe("M");
  });

  it("ignore a third word", () => {
    // **A disc is 32px across.** Three letters do not fit legibly, and a rule that grew
    // to fit the widest name would be a rule nobody could predict.
    expect(initials("Ada Byron King Lovelace")).toBe("AB");
  });

  it("are upper-case", () => {
    // **The disc is a small, quiet mark.** A name's own casing is not what it is there
    // to show.
    expect(initials("maya ahmed")).toBe("MA");
  });

  it("do not re-case a capital that is not the first", () => {
    // **The rule upper-cases the first letter and leaves the rest of the word alone** —
    // it never shows the rest of the word, so this is only about not lower-casing it
    // on the way past.
    expect(initials("mcDonald vanDerBerg")).toBe("MV");
  });

  it("ignore surrounding whitespace", () => {
    expect(initials("  Maya Ahmed  ")).toBe("MA");
  });

  it("treat a run of whitespace as one break", () => {
    expect(initials("Maya   Ahmed")).toBe("MA");
  });

  it("are empty for a blank name, rather than a broken letter", () => {
    // **A disc with nothing in it is a hole in the rail.** The product never asks this
    // of an empty name — `displayName` derives one from the address — but the function
    // answers for one anyway: the absence of letters is stated rather than rendered.
    expect(initials("")).toBe("");
    expect(initials("   ")).toBe("");
  });

  it("never produce a letter from nowhere", () => {
    // **The failure this pins is a `charAt(0)` on an empty word** — a run of
    // whitespace split without filtering leaves empty words behind, and `"".charAt(0)`
    // is `""`, which would put a stray separator in the disc.
    expect(initials("Maya  Ahmed")).toBe("MA");
    expect(initials(" Maya Ahmed ")).toBe("MA");
  });
});
