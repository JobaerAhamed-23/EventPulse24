/**
 * The Detail Screen's two vocabularies: the breakdown's factor lines and the neighbor
 * count's bucketed prose.
 *
 * **These are the arithmetic of the screen**, and they are where a wrong number or a
 * made-up reason would hide. So they are pinned directly rather than only through a
 * render.
 */
import { describe, expect, it } from "vitest";

import { factorLine, neighborLine } from "@/lib/detail-labels";

describe("the breakdown's factor lines", () => {
  it("gives each known tag its own line", () => {
    expect(factorLine("nearby")).toBe("It's in your city.");
    expect(factorLine("tonight")).toBe("It starts tonight.");
    expect(factorLine("tomorrow")).toBe("It starts tomorrow.");
    expect(factorLine("weekend")).toBe("It starts this weekend.");
  });

  it("names the interest a chip tag matched", () => {
    // The chip's own label, from the same table the card uses, so the breakdown and the
    // card name the interest identically.
    expect(factorLine("matches_arts_culture")).toBe(
      "It matches an interest you picked: Arts & culture.",
    );
  });

  it("falls back to the tag's own label for a tag it does not know", () => {
    // A new server tag appears as a plain line rather than vanishing or acquiring a
    // fabricated reason.
    expect(factorLine("brand_new_tag")).toBe("Brand New Tag");
  });

  it("states no reliability, no distance, no price and no attendance", () => {
    // FR-16 is unbuilt, there are no coordinates, there is no price field and there is
    // no attendance model. A line claiming any of them would be stating something
    // nobody computed.
    for (const tag of ["nearby", "tonight", "tomorrow", "weekend", "discovery", "saved"]) {
      const line = factorLine(tag);
      expect(line).not.toMatch(/reliability/i);
      expect(line).not.toMatch(/bayesian/i);
      expect(line).not.toMatch(/\d/);
      expect(line).not.toMatch(/\bkm\b/i);
      expect(line).not.toMatch(/free/i);
      expect(line).not.toMatch(/attended/i);
    }
  });

  it("gives two different tags two different lines", () => {
    const lines = new Set(
      ["nearby", "tonight", "tomorrow", "weekend", "discovery", "saved"].map(factorLine),
    );
    expect(lines.size).toBe(6);
  });
});

describe("the neighbor count's prose", () => {
  it.each([
    ["few", "A few neighbors saved this."],
    ["some", "Some neighbors saved this."],
    ["many", "Many neighbors saved this."],
    ["a_lot", "A lot of neighbors saved this."],
  ])("renders the %s bucket", (bucket, line) => {
    expect(neighborLine(bucket)).toBe(line);
  });

  it("renders nothing for a suppressed count", () => {
    // The suppression is silence. There is no "0 neighbors" and no "not enough yet" —
    // a line that says the count was withheld is itself a signal about how many people
    // are near this event.
    expect(neighborLine(null)).toBeNull();
    expect(neighborLine(undefined)).toBeNull();
    expect(neighborLine("")).toBeNull();
  });

  it("renders nothing for a bucket it does not know", () => {
    // A server that grew a fifth bucket should not have the client invent prose for it.
    expect(neighborLine("a_great_many")).toBeNull();
  });

  it("states no number in any bucket", () => {
    for (const bucket of ["few", "some", "many", "a_lot"]) {
      expect(neighborLine(bucket)).not.toMatch(/\d/);
    }
  });

  it("carries no emoji prefix", () => {
    for (const bucket of ["few", "some", "many", "a_lot"]) {
      expect(neighborLine(bucket)).not.toContain("👥");
    }
  });
});
