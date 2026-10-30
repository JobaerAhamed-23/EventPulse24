import { describe, expect, it } from "vitest";

import { EVENT_FIT_TOOLTIP, eventFitLabel, sourceBadge, tagLabel } from "@/lib/preview-labels";

/**
 * The words for the server's facts.
 *
 * The server sends keys and types; the labels are the frontend's, by the backend's own
 * instruction. The one rule worth guarding is that an unfamiliar key still renders — a
 * translation table that silently drops what it does not recognise loses data nobody sees
 * go.
 */

describe("tagLabel", () => {
  it.each([
    ["tonight", "Tonight"],
    ["tomorrow", "Tomorrow"],
    ["this_weekend", "This weekend"],
  ])("labels the %s time tag", (key, label) => {
    expect(tagLabel(key)).toBe(label);
  });

  it.each([
    ["in_brooklyn", "In Brooklyn"],
    ["in_san_francisco", "In San Francisco"],
    ["in_nyc", "In Nyc"],
  ])("labels the %s place tag", (key, label) => {
    expect(tagLabel(key)).toBe(label);
  });

  it("renders an unknown key from its slug rather than dropping it", () => {
    // A tag the backend adds later should appear as soon as it exists, looking plain,
    // rather than vanish from the card.
    expect(tagLabel("free_entry")).toBe("Free Entry");
  });
});

describe("sourceBadge", () => {
  it.each([
    ["official_site", "Official", "Verified venue or organizer."],
    ["community", "Community", "Posted by a community member."],
    ["aggregator", "Listing site", "Aggregated from a public listing."],
  ])("gives %s its locked label and tooltip", (type, label, tooltip) => {
    expect(sourceBadge(type)).toMatchObject({ label, tooltip });
  });

  it("marks the crawled badge as unverified, which is what carries the warning glyph", () => {
    const badge = sourceBadge("crawled_html");

    expect(badge.unverified).toBe(true);
    expect(badge.label).toBe("Unverified");
  });

  it("falls back to a plain label for a type it does not know", () => {
    expect(sourceBadge("something_new").label).toBe("Listed");
  });

  it("gives every badge a visible text label, never an icon alone", () => {
    for (const type of ["official_site", "community", "aggregator", "crawled_html", "???"]) {
      expect(sourceBadge(type).label.trim().length).toBeGreaterThan(0);
    }
  });
});

describe("the Event Fit's words", () => {
  it("says what the number is, out of five", () => {
    expect(eventFitLabel(4)).toBe("Event Fit 4 of 5");
  });

  it("explains what it measures, and says it is not personal", () => {
    // AD-10: the Event Fit and the Relevance Pulse look identical on screen and must
    // never be substituted. The tooltip is where this page says which one it is.
    expect(EVENT_FIT_TOOLTIP).toContain("How soon it is");
    expect(EVENT_FIT_TOOLTIP).toContain("not a personal recommendation");
  });

  it("never borrows the Confidence Pulse's meaning", () => {
    const words = `${EVENT_FIT_TOOLTIP} ${eventFitLabel(3)}`.toLowerCase();

    expect(words).not.toContain("confidence");
    expect(words).not.toContain("sources confirm");
    expect(words).not.toContain("relevance");
  });
});
