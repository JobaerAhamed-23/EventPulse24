import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PulseCard, categoryFor, MAX_WHY_THIS_TAGS } from "@/components/digest/pulse-card";
import type { Explanation } from "@/components/digest/pulse-card";
import type { components } from "@/lib/api/schema";

type DigestCard = components["schemas"]["DigestCardOut"];

/**
 * The Pulse Card.
 *
 * **The card is a projection.** Everything it shows was decided by the composition
 * service and persisted (AD-10), so the tests here are mostly about what the card does
 * *not* do: it does not re-bucket, does not re-sort, does not recompute an explanation,
 * and does not hide a trust signal.
 */

const CARD: DigestCard = {
  event_id: "11111111-1111-1111-1111-111111111111",
  slot: "nearby",
  event_kind: "public",
  title: "Brooklyn Symphony open rehearsal",
  canonical_url: "https://example.test/rehearsal",
  start_time_utc: "2026-11-07T23:00:00Z",
  end_time_utc: null,
  start_time_tz: "America/New_York",
  venue_name: "BAM Howard Gilman Opera House",
  venue_city: "Brooklyn",
  location: null,
  tags: ["nearby", "tonight", "matches_arts_culture"],
  bucket: 4,
  source_badge: "official_site",
  tz_review_pending: false,
  catalog_event_missing: false,
  conflict: false,
};

function renderCard(
  overrides: Partial<DigestCard> = {},
  explanation: Explanation = { kind: "relevance", value: 4 },
) {
  render(<PulseCard card={{ ...CARD, ...overrides }} explanation={explanation} />);
}

/**
 * The tag row.
 *
 * The row is the element that carries the micro-tag scale and holds the separator, and
 * each tag is a *span* inside it — so a query for the row has to find the paragraph, not
 * the span that happens to contain the word.
 */
function tagRow(): HTMLElement {
  const row = [...document.querySelectorAll("p")].find((element) =>
    element.className.includes("--type-scale-microtag"),
  );
  if (!row) throw new Error("no tag row on the card");
  return row;
}

/** The card's own text, lowercased — for the "never says" assertions. */
function cardText(): string {
  return (document.body.textContent ?? "").toLowerCase();
}

describe("the anatomy", () => {
  it("shows the headline in the headline type scale", () => {
    renderCard();

    const headline = screen.getByRole("heading", { level: 3 });
    expect(headline).toHaveTextContent("Brooklyn Symphony open rehearsal");
    expect(headline.className).toContain("--type-scale-headline-md");
  });

  it("shows the kicker in the meta scale, in muted ink", () => {
    renderCard();

    const kicker = screen.getByText("Public event");
    expect(kicker.className).toContain("--type-scale-meta-sm");
    expect(kicker.className).toContain("text-ink-muted");
  });

  it("shows the tags in the micro-tag scale — italic, and never bold", () => {
    renderCard();

    const row = tagRow();
    expect(row.className).toContain("--type-scale-microtag");
    // `type.scale.microtag` is the italic token; the card must not add a weight.
    expect(row.className).not.toContain("font-bold");
    expect(row.className).not.toContain("font-semibold");
  });

  it("shows the source-and-time row in the meta scale", () => {
    renderCard();

    const row = screen.getByText(/2026-11-07/);
    expect(row.className).toContain("--type-scale-meta-md");
  });

  it("sits on the elevated surface with a subtle border and the card radius", () => {
    renderCard();

    const card = screen.getByRole("article");
    expect(card.className).toContain("bg-surface-elevated");
    expect(card.className).toContain("border-border-subtle");
    expect(card.className).toContain("rounded-card");
  });

  it("pads with spacing 4 on mobile and spacing 6 on desktop", () => {
    renderCard();

    const card = screen.getByRole("article");
    expect(card.className).toContain("p-4");
    expect(card.className).toContain("md:p-6");
  });

  it("has a 3px left-edge stripe", () => {
    renderCard();

    const stripe = document.querySelector("span[aria-hidden='true'].w-\\[3px\\]");
    expect(stripe).not.toBeNull();
  });

  it("adds no shadow on hover, and no transition class", () => {
    renderCard();

    const card = screen.getByRole("article");
    expect(card.className).toContain("hover:bg-surface-subtle");
    expect(card.className).toContain("hover:border-border-strong");
    expect(card.className).not.toContain("shadow-");
    expect(card.className).not.toContain("transition");
  });

  it("fades in with the one motion class", () => {
    renderCard();

    expect(screen.getByRole("article").className).toContain("fade-in");
  });
});

describe("the category stripe", () => {
  it.each([
    ["must_know", "public", "Must-know", "bg-accent-amber"],
    ["nearby", "public", "Public event", "bg-accent-slate"],
    ["serendipity", "public", "Public event", "bg-accent-slate"],
    ["must_know", "personal", "Personal", "bg-warm-personal"],
  ])("maps slot %s / kind %s to the %s label", (slot, eventKind, label, stripe) => {
    renderCard({ slot, event_kind: eventKind });

    expect(screen.getByText(label)).toBeInTheDocument();
    const stripeElement = document.querySelector(`span.${stripe}`);
    expect(stripeElement).not.toBeNull();
  });

  it("gives a personal event the Personal tone, even when it fills the must-know slot", () => {
    // A personal event fills Slot 1 when it is eligible, so a slot-first mapping would
    // call every personal event "Must-know".
    renderCard({ slot: "must_know", event_kind: "personal" });

    expect(screen.getByText("Personal")).toBeInTheDocument();
    expect(screen.queryByText("Must-know")).toBeNull();
  });

  it("gives a discovery card the 0.85-opacity stripe", () => {
    renderCard({ slot: "serendipity" });

    const stripe = document.querySelector("span.bg-accent-slate");
    expect(stripe?.className).toContain("opacity-85");
  });

  it("does not give the plain public card the discovery opacity", () => {
    renderCard({ slot: "nearby" });

    const stripe = document.querySelector("span.bg-accent-slate");
    expect(stripe?.className).not.toContain("opacity-85");
  });

  it("never leaves a stripe without a visible text label", () => {
    // WCAG 1.4.1: colour is never the sole carrier of meaning.
    for (const [slot, eventKind] of [
      ["must_know", "public"],
      ["nearby", "public"],
      ["serendipity", "public"],
      ["must_know", "personal"],
    ] as const) {
      const { unmount } = render(
        <PulseCard
          card={{ ...CARD, slot, event_kind: eventKind }}
          explanation={{ kind: "relevance", value: 3 }}
        />,
      );
      const label = screen.getByText(/Public event|Must-know|Personal/);
      expect(label).toBeInTheDocument();
      unmount();
    }
  });

  it("renders the discovery micro-tag in the tag row", () => {
    renderCard({ slot: "serendipity", tags: ["discovery", "nearby"] });

    expect(tagRow()).toHaveTextContent("Discovery");
  });

  it("puts no stripe colour on an interactive surface", () => {
    // `color.accent.slate`, `color.accent.amber` and `color.warm.personal` are reserved
    // for the stripe and for the Personal label.
    renderCard({ slot: "must_know" });

    for (const button of screen.getAllByRole("button")) {
      expect(button.className).not.toContain("accent-amber");
      expect(button.className).not.toContain("accent-slate");
      expect(button.className).not.toContain("warm-personal");
    }
  });

  it("maps the categories through one function", () => {
    expect(categoryFor({ ...CARD, slot: "must_know", event_kind: "personal" }).label).toBe(
      "Personal",
    );
    expect(categoryFor({ ...CARD, slot: "must_know" }).label).toBe("Must-know");
  });
});

describe("the Why-this Tags", () => {
  it("labels the tags from their keys", () => {
    renderCard();

    expect(tagRow()).toHaveTextContent("Nearby, Tonight, Arts & culture");
  });

  it("separates the tags with a comma, as real text", () => {
    renderCard({ tags: ["nearby", "tonight"] });

    const row = tagRow();
    // The separator is a DOM character, not a CSS `::after` — a pseudo-element would be
    // visible to a sighted user and silent to a screen reader.
    expect(row.textContent).toContain("Nearby, Tonight");
    expect(row.textContent).not.toContain("·");
  });

  it("caps the tags at three", () => {
    renderCard({ tags: ["nearby", "tonight", "tomorrow", "weekend", "saved"] });

    expect(tagRow().textContent).toBe("Nearby, Tonight, Tomorrow");
    expect(MAX_WHY_THIS_TAGS).toBe(3);
  });

  it("renders no tag row when there are no tags", () => {
    renderCard({ tags: [] });

    expect(document.querySelector("p[class*='--type-scale-microtag']")).toBeNull();
  });

  it("renders an unknown tag from its slug rather than dropping it", () => {
    renderCard({ tags: ["a_brand_new_tag"] });

    expect(tagRow()).toHaveTextContent("A Brand New Tag");
  });
});

describe("the confidence indicator", () => {
  it("always draws five positions", () => {
    renderCard({ bucket: 1 }, { kind: "relevance", value: 1 });

    const trigger = screen.getByRole("button", { name: /Relevance 1 of 5/ });
    const dots = trigger.querySelectorAll("span[aria-hidden='true'] > span");
    expect(dots).toHaveLength(5);
  });

  it("fills exactly the persisted bucket", () => {
    renderCard({}, { kind: "relevance", value: 4 });

    const trigger = screen.getByRole("button", { name: "Relevance 4 of 5" });
    const dots = [...trigger.querySelectorAll("span[aria-hidden='true'] > span")];
    const filled = dots.filter((dot) => dot.className.includes("bg-ink-primary"));
    const empty = dots.filter((dot) => dot.className.includes("bg-ink-faint"));
    expect(filled).toHaveLength(4);
    expect(empty).toHaveLength(1);
  });

  it("shows no visible numeric", () => {
    renderCard({}, { kind: "relevance", value: 4 });

    // The number is in the accessible name, not on the card.
    expect(screen.getByRole("button", { name: "Relevance 4 of 5" })).toBeInTheDocument();
    // The *visible* text of the card carries no count — the accessible name does. The
    // tooltip is `invisible` until hovered, so it is not part of what a reader sees.
    const visible = screen.getByRole("article").textContent ?? "";
    expect(visible).not.toContain("4 of 5");
    expect(visible).not.toContain("4/5");
  });

  it("names the indicator visibly, without a number beside it", () => {
    renderCard({}, { kind: "relevance", value: 4 });

    // The dots alone would carry the meaning in shape and colour only.
    const label = screen.getByText("Relevance");
    expect(label).toBeVisible();
    expect(label.textContent).toBe("Relevance");
  });

  it("draws 6px round dots", () => {
    renderCard();

    const trigger = screen.getByRole("button", { name: /Relevance/ });
    const dot = trigger.querySelector("span[aria-hidden='true'] > span");
    expect(dot?.className).toContain("h-1.5");
    expect(dot?.className).toContain("w-1.5");
    expect(dot?.className).toContain("rounded-full");
  });

  it("names the indicator it is carrying", () => {
    renderCard({}, { kind: "event_fit", value: 3 });

    expect(screen.getByRole("button", { name: "Event Fit 3 of 5" })).toBeInTheDocument();
    expect(cardText()).not.toContain("relevance");
  });

  it("explains itself through a tooltip the trigger points at", () => {
    renderCard();

    const trigger = screen.getByRole("button", { name: /Relevance/ });
    const tooltipId = trigger.getAttribute("aria-describedby");
    expect(tooltipId).toBeTruthy();
    const tooltip = document.getElementById(tooltipId as string);
    expect(tooltip).toHaveAttribute("role", "tooltip");
  });

  it("takes the tooltip's contributing factors from the persisted tags", () => {
    // AD-10: an explanation is never generated at view time. The card cannot compute
    // "strong match on your top three interests" — it renders the persisted tags.
    renderCard({ tags: ["nearby", "tonight"] });

    const trigger = screen.getByRole("button", { name: /Relevance/ });
    const tooltip = document.getElementById(trigger.getAttribute("aria-describedby") as string);
    expect(tooltip).toHaveTextContent("Nearby");
    expect(tooltip).toHaveTextContent("Tonight");
    expect(tooltip?.textContent).not.toMatch(/km|neighbors|interests/i);
  });

  it("keeps the tooltip in the DOM and out of sight until hovered or focused", () => {
    renderCard();

    const trigger = screen.getByRole("button", { name: /Relevance/ });
    const tooltip = document.getElementById(trigger.getAttribute("aria-describedby") as string);

    expect(tooltip).toBeInTheDocument();
    expect(tooltip).toHaveClass("invisible");
    expect(tooltip?.className).toContain("group-hover/confidence:visible");
    expect(tooltip?.className).toContain("group-focus-within/confidence:visible");
    expect(tooltip).not.toHaveAttribute("hidden");
  });

  it("has a 44×44 hit area around the 6px dots", () => {
    renderCard();

    const trigger = screen.getByRole("button", { name: /Relevance/ });
    expect(trigger.className).toContain("min-h-11");
    expect(trigger.className).toContain("min-w-11");
  });

  it("clamps a value outside the range rather than drawing it", () => {
    renderCard({}, { kind: "relevance", value: 9 });

    expect(screen.getByRole("button", { name: "Relevance 5 of 5" })).toBeInTheDocument();
  });
});

describe("the Source Badge", () => {
  it.each([
    ["official_site", "Official"],
    ["community", "Community"],
    ["aggregator", "Listing site"],
    ["user_imported", "Forwarded"],
    ["crawled_html", "Unverified"],
  ])("shows %s with a visible inline label", (type, label) => {
    renderCard({ source_badge: type });

    expect(screen.getByRole("button", { name: new RegExp(label) })).toBeInTheDocument();
  });

  it("renders Official with the terracotta on the glyph — one of the four sanctioned uses", () => {
    renderCard({ source_badge: "official_site" });

    const badge = screen.getByRole("button", { name: /Official/ });

    // **The terracotta is on the glyph, and the label is ink.** `EXPERIENCE.md` §4
    // `Badge.Source` — the canonical list — specifies the terracotta as the *filled
    // checkmark icon*, with the label in `Text.Meta`. That is also the only way the
    // badge's text can meet AA: `#C4502B` is 4.37:1 on `color.surface.paper`, which is
    // a graphic's ratio and not a text's.
    const glyph = badge.querySelector('[aria-hidden="true"]');
    expect(glyph).not.toBeNull();
    expect(glyph?.className).toContain("text-accent-terracotta");

    // And the label itself — the button's own class — is in ink.
    expect(badge.className).toContain("text-ink-secondary");
    expect(badge.className).not.toContain("text-accent-terracotta");
  });

  it("does not render a badge at all for a personal event", () => {
    // `source_badge = null` means "there is no source", not "unknown".
    renderCard({ source_badge: null, event_kind: "personal" });

    expect(
      screen.queryByRole("button", {
        name: /Official|Community|Listing site|Forwarded|Unverified/,
      }),
    ).toBeNull();
  });

  it("shows the badge inline, never behind a tap", () => {
    renderCard();

    const badge = screen.getByRole("button", { name: /Official/ });
    expect(badge).toBeInTheDocument();
  });

  it("marks a crawled listing with the warning colour on the glyph, and its tooltip", () => {
    renderCard({ source_badge: "crawled_html" });

    const badge = screen.getByRole("button", { name: /Unverified/ });

    // **The amber is on the glyph and the label is ink** — the same treatment the
    // sold-out badge and the auth error row use. The amber is a signal colour, and a
    // source's provenance is not a state change.
    const glyph = badge.querySelector('[aria-hidden="true"]');
    expect(glyph).not.toBeNull();
    expect(glyph?.className).toContain("text-signal-warn");
    expect(badge.className).toContain("text-ink-secondary");
    expect(badge.className).not.toContain("text-signal-warn");

    const tooltip = document.getElementById(badge.getAttribute("aria-describedby") as string);
    expect(tooltip).toHaveTextContent("Read from a public page");
  });

  it("gives the badge a 44px-tall hit area", () => {
    renderCard();

    expect(screen.getByRole("button", { name: /Official/ }).className).toContain("min-h-11");
  });
});

describe("the conflict indicator", () => {
  it("appears only when the card is in conflict", () => {
    renderCard({ conflict: false });

    expect(screen.queryByLabelText("Schedule conflict")).toBeNull();
  });

  it("is labelled, not just coloured", () => {
    renderCard({ conflict: true });

    expect(screen.getByLabelText("Schedule conflict")).toBeInTheDocument();
  });

  it("is 6px, and distinct in shape from the confidence dots", () => {
    renderCard({ conflict: true });

    const dot = screen.getByLabelText("Schedule conflict").querySelector("span");
    expect(dot?.className).toContain("h-1.5");
    expect(dot?.className).toContain("w-1.5");
    expect(dot?.className).toContain("bg-warn-amber");
    // The ring is what tells it apart from an empty confidence dot.
    expect(dot?.className).toContain("ring-1");
  });

  it("is never red", () => {
    renderCard({ conflict: true });

    const dot = screen.getByLabelText("Schedule conflict").querySelector("span");
    expect(dot?.className).not.toContain("signal-error");
    expect(dot?.className).not.toContain("red");
  });
});

describe("the whole card is the tap target", () => {
  it("links to the event", () => {
    renderCard();

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/events/11111111-1111-1111-1111-111111111111");
  });

  it("covers the whole card, so the hit area is the card", () => {
    renderCard();

    expect(screen.getByRole("link").className).toContain("absolute");
    expect(screen.getByRole("link").className).toContain("inset-0");
  });

  it("has one focus ring, on the card, in terracotta", () => {
    renderCard();

    const link = screen.getByRole("link");
    expect(link.className).toContain("focus-visible:outline-accent-terracotta");
    expect(link.className).toContain("focus-visible:outline-2");
  });

  it("reads the full card content as its accessible name", () => {
    renderCard();

    const name = screen.getByRole("link").getAttribute("aria-label") ?? "";
    expect(name).toContain("Brooklyn Symphony open rehearsal");
    expect(name).toContain("Public event");
    expect(name).toContain("Official");
    expect(name).toContain("4 of 5");
    expect(name).toContain("Nearby, Tonight, Arts & culture");
  });

  it("renders the ▸ as decorative, not as a click target", () => {
    renderCard();

    const arrow = [
      ...screen.getByRole("article").querySelectorAll("span[aria-hidden='true']"),
    ].find((element) => element.textContent?.includes("▸"));
    expect(arrow).not.toBeUndefined();
    expect(arrow?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("reveals the ▸ on hover and on focus, so there is no hover-only affordance", () => {
    renderCard();

    const arrow = [
      ...screen.getByRole("article").querySelectorAll("span[aria-hidden='true']"),
    ].find((element) => element.textContent?.includes("▸"));
    expect(arrow?.className).toContain("group-hover:opacity-100");
    expect(arrow?.className).toContain("group-focus-within:opacity-100");
  });

  it("keeps the tooltip triggers above the stretched link, so they stay clickable", () => {
    // The link is `absolute inset-0` and comes *later* in the DOM, so it paints over
    // anything in the normal flow. The trust row must therefore be raised explicitly —
    // without this the confidence and badge buttons are covered and their tooltips can
    // never be opened, which would make the trust signals inert.
    renderCard();

    const link = screen.getByRole("link");
    expect(link.className).toContain("z-0");

    const row = screen.getByRole("button", { name: /Relevance 4 of 5/ }).closest("div");
    expect(row?.className).toContain("relative");
    expect(row?.className).toContain("z-10");

    // The tooltip itself is positioned and raised, so it is not clipped by the card.
    const tooltip = document.getElementById("confidence-11111111-1111-1111-1111-111111111111");
    expect(tooltip).not.toBeNull();
    expect(tooltip?.className).toContain("absolute");
    expect(tooltip?.className).toContain("z-10");
  });
});

describe("the trust signals never hide", () => {
  it("shows the tags, the confidence pulse and the badge together", () => {
    renderCard();

    expect(tagRow()).toHaveTextContent("Nearby");
    expect(screen.getByRole("button", { name: /Relevance 4 of 5/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Official/ })).toBeInTheDocument();
  });

  it("has no density prop that could hide one of them", () => {
    // The locked anti-pattern: "Adaptive density must not hide the trust signals … at
    // any density mode." The way to keep that promise is not to have a density mode.
    renderCard();

    const card = screen.getByRole("article");
    expect(card.className).not.toContain("hidden");
    expect(card.className).not.toContain("md:hidden");
    expect(card.className).not.toContain("lg:hidden");
  });

  it("keeps the conflict indicator visible, not collapsed into a density mode", () => {
    renderCard({ conflict: true });

    const indicator = screen.getByLabelText("Schedule conflict");
    expect(indicator.className).not.toContain("hidden");
  });
});

describe("what the card does not do", () => {
  it("does not re-sort the tags — the server's order is the order", () => {
    renderCard({ tags: ["tonight", "nearby"] });

    expect(tagRow().textContent).toBe("Tonight, Nearby");
  });

  it("does not re-bucket — it draws the value it was given", () => {
    renderCard({}, { kind: "relevance", value: 2 });

    expect(screen.getByRole("button", { name: "Relevance 2 of 5" })).toBeInTheDocument();
  });

  it("says nothing about price", () => {
    renderCard();

    expect(cardText()).not.toContain("free");
  });

  it("shows no attendee count, no share button and no description", () => {
    renderCard();

    expect(screen.queryByRole("button", { name: /share/i })).toBeNull();
    expect(cardText()).not.toMatch(/\d+ (neighbors|attendees|going)/);
  });

  it("renders the headline whole rather than truncating it", () => {
    // The 8-word cap is the server's obligation. A truncated headline is body copy
    // wearing a headline's clothes.
    const long = "One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve";
    renderCard({ title: long });

    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(long);
  });

  it("does not substitute one indicator for the other", () => {
    renderCard({}, { kind: "event_fit", value: 4 });

    expect(screen.getByRole("button", { name: "Event Fit 4 of 5" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Relevance/ })).toBeNull();
  });
});

describe("a card whose facts have moved on", () => {
  it("says the details are unavailable rather than rendering an empty headline", () => {
    renderCard({ title: null });

    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      "Event details unavailable",
    );
  });

  it("says the listing has changed", () => {
    renderCard({ catalog_event_missing: true });

    expect(screen.getByText(/listing has changed/)).toBeInTheDocument();
  });

  it("says the time is to be confirmed when there is no time", () => {
    renderCard({ start_time_utc: null });

    expect(screen.getByText(/Time to be confirmed/)).toBeInTheDocument();
  });

  it("marks an approximate time", () => {
    renderCard({ tz_review_pending: true });

    expect(screen.getByText(/Time approximate/)).toBeInTheDocument();
  });

  it("shows a personal event's place as free text", () => {
    renderCard({ event_kind: "personal", location: "2 Example Street", venue_name: null });

    expect(screen.getByText(/2 Example Street/)).toBeInTheDocument();
  });
});
