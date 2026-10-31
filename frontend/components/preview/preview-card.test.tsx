import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PreviewCard } from "@/components/preview/preview-card";
import type { components } from "@/lib/api/schema";

/** The fixture is typed from the generated contract, so it cannot drift from it. */
type Card = components["schemas"]["PreviewCardOut"];

/**
 * One preview card.
 *
 * The card's job is to state the server's facts without borrowing meaning the server did
 * not send: the 1–5 is the **Event Fit**, not the Confidence Pulse and not a Relevance
 * Pulse (AD-10), there is no category because the preview has none, and there is no price
 * because the catalog has no price field.
 */

const CARD: Card = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "brooklyn-symphony-open-rehearsal",
  title: "Brooklyn Symphony open rehearsal",
  start_time_utc: "2026-11-07T23:00:00Z",
  start_time_tz: "America/New_York",
  venue_name: "BAM Howard Gilman Opera House",
  city: "Brooklyn",
  score: 4,
  tags: ["tonight", "in_brooklyn"],
  source_name: "Brooklyn Symphony",
  source_badge: "official_site",
};

function renderCard(overrides: Partial<Card> = {}, savedNote: string | null = null) {
  const onSave = vi.fn();
  render(<PreviewCard card={{ ...CARD, ...overrides }} onSave={onSave} savedNote={savedNote} />);
  return onSave;
}

describe("the facts on the card", () => {
  it("shows the title, the venue and a link to the event", () => {
    renderCard();

    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      "Brooklyn Symphony open rehearsal",
    );
    expect(screen.getByText("BAM Howard Gilman Opera House")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Brooklyn Symphony open rehearsal/ })).toHaveAttribute(
      "href",
      "/events/brooklyn-symphony-open-rehearsal",
    );
  });

  it("shows the local start time in the event's own zone, and names the zone", () => {
    // The server sends an instant plus an IANA zone and does not guess a locale (AD-6).
    // 23:00 UTC is 6:00 PM in New York on that date, after the clocks went back: EST.
    renderCard();

    expect(screen.getByText("Sat, Nov 7 · 6:00 PM EST")).toBeInTheDocument();
  });

  it("survives a card with no venue", () => {
    renderCard({ venue_name: null });

    expect(screen.getByRole("heading", { level: 3 })).toBeInTheDocument();
  });

  it("labels the tags from their keys", () => {
    renderCard();

    expect(screen.getByText("Tonight")).toBeInTheDocument();
    expect(screen.getByText("In Brooklyn")).toBeInTheDocument();
  });

  it("renders no tag row when there are no tags", () => {
    renderCard({ tags: [] });

    expect(screen.queryByText("Tonight")).toBeNull();
  });
});

describe("the Event Fit", () => {
  it("has a text alternative, not just dots to count", () => {
    renderCard({ score: 4 });

    expect(screen.getByRole("button", { name: "Event Fit 4 of 5" })).toBeInTheDocument();
    expect(screen.getByText("Event Fit")).toBeInTheDocument();
  });

  it("explains what it measures through a tooltip the trigger points at", () => {
    renderCard();

    const trigger = screen.getByRole("button", { name: "Event Fit 4 of 5" });
    const tooltipId = trigger.getAttribute("aria-describedby");
    expect(tooltipId).toBeTruthy();
    const tooltip = document.getElementById(tooltipId as string);
    expect(tooltip).toHaveAttribute("role", "tooltip");
    expect(tooltip).toHaveTextContent(/How soon it is/);
  });

  it("keeps the tooltip out of sight until its trigger is hovered or focused", () => {
    // `DESIGN.md`'s pattern is a tooltip, not a caption: two permanently visible
    // explanations would crowd a card whose whole point is calm.
    renderCard();

    const trigger = screen.getByRole("button", { name: "Event Fit 4 of 5" });
    const tooltip = document.getElementById(trigger.getAttribute("aria-describedby") as string);

    expect(tooltip).toHaveClass("invisible");
    expect(tooltip?.className).toContain("group-hover:visible");
    expect(tooltip?.className).toContain("group-focus-within:visible");
    // `hidden` is `display: none`, which no amount of hovering undoes — it would make
    // the tooltip unreachable rather than merely out of sight.
    expect(tooltip).not.toHaveAttribute("hidden");
  });

  it("keeps the tooltip in the DOM, because the description is read from it", () => {
    // Removing it would leave `aria-describedby` pointing at nothing, and the trigger's
    // accessible description — the part that says what the number means — would vanish.
    renderCard();

    const trigger = screen.getByRole("button", { name: "Event Fit 4 of 5" });
    const tooltip = document.getElementById(trigger.getAttribute("aria-describedby") as string);

    expect(tooltip).toBeInTheDocument();
    expect(tooltip).toHaveTextContent(/How soon it is/);
  });

  it("puts the tooltip inside its trigger's group, or the reveal never fires", () => {
    renderCard();

    const trigger = screen.getByRole("button", { name: "Event Fit 4 of 5" });
    const tooltip = document.getElementById(trigger.getAttribute("aria-describedby") as string);
    const group = tooltip?.closest(".group");

    expect(group).not.toBeNull();
    expect(group?.contains(trigger)).toBe(true);
  });

  it("clamps a score outside the server's range rather than drawing it", () => {
    renderCard({ score: 9 });

    expect(screen.getByRole("button", { name: "Event Fit 5 of 5" })).toBeInTheDocument();
  });

  it("never calls the number a Confidence Pulse or a Relevance Pulse", () => {
    // AD-10: the two indicators look identical on screen, so the words are what keep them
    // apart. This page has only the session-free one.
    renderCard();

    const text = (document.body.textContent ?? "").toLowerCase();
    expect(text).not.toContain("confidence");
    expect(text).not.toContain("relevance");
    expect(text).not.toContain("sources confirm");
  });
});

describe("the Source Badge", () => {
  it.each([
    ["official_site", "Official", "Verified venue or organizer."],
    ["community", "Community", "Posted by a community member."],
    ["aggregator", "Listing site", "Aggregated from a public listing."],
  ])("shows %s with a visible label and its tooltip", (type, label, tooltip) => {
    renderCard({ source_badge: type });

    const trigger = screen.getByRole("button", { name: new RegExp(label) });
    const tooltipId = trigger.getAttribute("aria-describedby") as string;
    expect(document.getElementById(tooltipId)).toHaveTextContent(tooltip);
  });

  it("names the source, so the badge is attributable", () => {
    renderCard();

    expect(screen.getByText(/Brooklyn Symphony\./)).toBeInTheDocument();
  });

  it("marks a crawled listing as unverified", () => {
    renderCard({ source_badge: "crawled_html" });

    expect(screen.getByRole("button", { name: /Unverified/ })).toBeInTheDocument();
  });
});

describe("what the card deliberately does not say", () => {
  it("shows no category, because the preview has none", () => {
    renderCard();

    const text = document.body.textContent ?? "";
    for (const category of ["Must-know", "Nearby", "Discovery"]) {
      expect(text).not.toContain(category);
    }
  });

  it("says nothing about price, because the catalog has no price", () => {
    renderCard();

    expect((document.body.textContent ?? "").toLowerCase()).not.toContain("free");
  });
});

describe("Save", () => {
  it("offers the locked helper line", () => {
    renderCard();

    expect(screen.getByText("We'll hold your seat.")).toBeInTheDocument();
  });

  it("reports the tap", () => {
    const onSave = renderCard();

    screen.getByRole("button", { name: "Save" }).click();

    expect(onSave).toHaveBeenCalled();
  });

  it("shows the note the section gives it once saved", () => {
    renderCard({}, "Saved for this visit. Sign up to keep it.");

    expect(screen.getByText("Saved for this visit. Sign up to keep it.")).toBeInTheDocument();
  });
});
