import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PulseCard } from "@/components/digest/pulse-card";
import type { components } from "@/lib/api/schema";

type DigestCard = components["schemas"]["DigestCardOut"];

/**
 * The Pulse Card's **state treatment** (FR-53, FR-54).
 *
 * **The card used to render a cancelled event exactly as it rendered a live one.** It
 * read neither `status` nor `is_sold_out`, so a card whose event had been cancelled —
 * or sold out, or postponed — gave the reader no sign that anything had happened. The
 * card now shows the state, and this file is what holds it to that.
 *
 * **Four things are being tested, and they are four different claims.**
 *
 * 1. **The state is shown, and it is shown in words.** Colour is never the sole carrier
 *    of meaning (WCAG 1.4.1), so the state carries a visible label.
 * 2. **The state is distinct from the conflict indicator.** Both are in the card's trust
 *    row, and the conflict indicator's amber and the badge's amber are *the same hex* —
 *    so they have to be told apart by shape and position.
 * 3. **The card's affordances match the state.** A cancelled event has nothing to offer
 *    the reader, so it offers nothing — and the control is *removed*, not greyed.
 * 4. **An unknown state shows nothing.** The vocabulary is the backend's, and a status
 *    the frontend has no word for must not be guessed at (ASSUMPTION-9).
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
  tags: ["nearby", "tonight"],
  bucket: 4,
  source_badge: "official_site",
  tz_review_pending: false,
  catalog_event_missing: false,
  conflict: false,
  public_slug: "brooklyn-symphony-open-rehearsal-2026-11-07-a1b2c3",
};

function renderCard(overrides: Partial<DigestCard> = {}) {
  render(
    <PulseCard
      card={{ ...CARD, ...overrides }}
      explanation={{ kind: "relevance", value: 4 }}
      shareOrigin="https://eventpulse24.test"
    />,
  );
}

/** The card's own text, lowercased — for the "never says" assertions. */
function cardText(): string {
  return (document.body.textContent ?? "").toLowerCase();
}

describe("a card whose event is sold out", () => {
  it("says so, in words", () => {
    renderCard({ is_sold_out: true });

    // **The label, not just the colour.** `DESIGN.md` is explicit: "Color is paired
    // with the visible text label 'Sold out' so the chromatic signal is never the sole
    // carrier of meaning (WCAG 1.4.1)."
    expect(screen.getByText("Sold out")).toBeInTheDocument();
  });

  it("shows the badge the design specifies", () => {
    renderCard({ is_sold_out: true });

    const badge = screen.getByText("Sold out");
    // `component.badge.soldout`: a subtle fill, a strong stroke, a 6px radius.
    expect(badge.className).toContain("bg-surface-subtle");
    expect(badge.className).toContain("border-border-strong");
    expect(badge.className).toContain("rounded-subtle");
    // The label is in ink, not in the signal colour.
    expect(badge.className).toContain("text-ink-secondary");
    expect(badge.className).not.toContain("text-signal-warn");
  });

  it("puts the chromatic signal on the glyph alone", () => {
    renderCard({ is_sold_out: true });

    const badge = screen.getByText("Sold out");
    const glyph = badge.querySelector('[aria-hidden="true"]');
    expect(glyph).not.toBeNull();
    expect(glyph?.className).toContain("text-signal-warn");
  });

  it("hides the glyph from a screen reader, so the label carries the meaning", () => {
    renderCard({ is_sold_out: true });

    // `DESIGN.md`: "The glyph is aria-hidden; the label carries the meaning."
    const glyph = screen.getByText("Sold out").querySelector('[aria-hidden="true"]');
    expect(glyph?.getAttribute("aria-hidden")).toBe("true");
  });

  it("names the state in the card's accessible name", () => {
    renderCard({ is_sold_out: true });

    // The card's link is the tap target, so its `aria-label` is what a link-navigating
    // reader hears — and it has to carry the state too.
    const name = screen.getByRole("link").getAttribute("aria-label") ?? "";
    expect(name).toContain("Sold out");
  });

  it("keeps its share control", () => {
    // **A sold-out event is still published and still has a public page.** What it has
    // lost is its tickets, not its page — and the Detail screen's own comment says the
    // Pulse Card offers a share for a sold-out event, so the Detail Screen must too.
    renderCard({ is_sold_out: true });

    expect(screen.getByRole("button", { name: /share/i })).toBeInTheDocument();
  });
});

describe("a card whose event is cancelled", () => {
  it("says so, in words", () => {
    renderCard({ status: "cancelled" });

    expect(screen.getByText("Cancelled")).toBeInTheDocument();
  });

  it("names the state in the card's accessible name", () => {
    renderCard({ status: "cancelled" });

    const name = screen.getByRole("link").getAttribute("aria-label") ?? "";
    expect(name).toContain("Cancelled");
  });

  it("keeps its share control, because the server still publishes it", () => {
    // **The share control is rendered from `public_slug`, never from the state.**
    //
    // The catalog's public read excludes only `superseded` events, so a **cancelled**
    // event is still published and still has a public page — and the server sends its
    // slug. A reader who wants to tell a friend that an event was cancelled needs a
    // link to the page that says so, so the control stays.
    //
    // The fixture below carries the slug the server actually sends. If the catalog ever
    // stops publishing cancelled events, the server sends `public_slug: null` and the
    // control disappears on its own — **with no frontend change**, because the card
    // never guesses the server's publishing policy (AD-10).
    renderCard({ status: "cancelled" });

    expect(screen.getByRole("button", { name: /share/i })).toBeInTheDocument();
  });

  it("drops the share control when the server sends no public page", () => {
    // **The control is removed, not greyed** — but only when there is genuinely
    // nothing to share. `public_slug: null` is the server saying the event has no
    // public page (a personal event, an event the catalog no longer holds publicly),
    // and a share control there would produce a link that 404s for the friend who
    // opened it.
    renderCard({ status: "cancelled", public_slug: null });

    expect(screen.queryByRole("button", { name: /share/i })).toBeNull();
  });

  it("keeps its own link to the Detail screen, so the reader can read why", () => {
    // The card's link stays whatever the state: a reader who sees "Cancelled" may want
    // to read why, and the Detail screen is where the explanation is.
    renderCard({ status: "cancelled" });

    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "/events/11111111-1111-1111-1111-111111111111",
    );
  });

  it("does not say the event is merely sold out", () => {
    renderCard({ status: "cancelled" });

    expect(cardText()).not.toContain("sold out");
  });
});

describe("a card whose event is postponed", () => {
  it("says so, in words", () => {
    renderCard({ status: "postponed" });

    expect(screen.getByText("Postponed")).toBeInTheDocument();
  });

  it("names the state in the card's accessible name", () => {
    renderCard({ status: "postponed" });

    const name = screen.getByRole("link").getAttribute("aria-label") ?? "";
    expect(name).toContain("Postponed");
  });

  it("keeps its share control, because the event still has a page", () => {
    // A postponed event is still happening, on another date. It is not a dead event.
    renderCard({ status: "postponed" });

    expect(screen.getByRole("button", { name: /share/i })).toBeInTheDocument();
  });
});

describe("a card that is both sold out and cancelled", () => {
  it("shows the cancellation, not the sold-out", () => {
    // **The lifecycle state wins.** The backend keeps sold-out as a *separate boolean*
    // precisely because an event can be `scheduled` and sold out at the same time —
    // and `DigestCardOut`'s own docstring says the two "are not collapsed into one
    // 'state' enum". The frontend keeps **both** fields and only the *badge* picks one.
    //
    // **It picks the cancellation**, because a badge reading "Sold out" on a cancelled
    // event would invite a reader to wait for tickets for an event that is not
    // happening.
    renderCard({ status: "cancelled", is_sold_out: true });

    expect(screen.getByText("Cancelled")).toBeInTheDocument();
    expect(screen.queryByText("Sold out")).toBeNull();
  });

  it("names the cancellation in the card's accessible name", () => {
    renderCard({ status: "cancelled", is_sold_out: true });

    const name = screen.getByRole("link").getAttribute("aria-label") ?? "";
    expect(name).toContain("Cancelled");
    expect(name).not.toContain("Sold out");
  });

  it("shows the postponement, not the sold-out", () => {
    // The same rule, the other lifecycle state.
    renderCard({ status: "postponed", is_sold_out: true });

    expect(screen.getByText("Postponed")).toBeInTheDocument();
    expect(screen.queryByText("Sold out")).toBeNull();
  });

  it("shows the sold-out when there is no lifecycle state to show", () => {
    // A `scheduled` event that is sold out is the ordinary case the flag exists for.
    renderCard({ status: "scheduled", is_sold_out: true });

    expect(screen.getByText("Sold out")).toBeInTheDocument();
  });
});

describe("a card in no state", () => {
  it("shows no badge for a scheduled event", () => {
    renderCard({ status: "scheduled" });

    expect(screen.queryByText("Sold out")).toBeNull();
    expect(screen.queryByText("Cancelled")).toBeNull();
    expect(screen.queryByText("Postponed")).toBeNull();
  });

  it("shows no badge when the server sends no status", () => {
    // `null` is the server saying it has no lifecycle to report — a personal event, or
    // a card whose catalog event is gone.
    renderCard({ status: null });

    expect(screen.queryByText("Sold out")).toBeNull();
    expect(screen.queryByText("Cancelled")).toBeNull();
    expect(screen.queryByText("Postponed")).toBeNull();
  });

  it("shows no badge for a status the frontend has no word for", () => {
    // ASSUMPTION-9: a status this system has never heard of is a fact the frontend
    // cannot put into words, and rendering one as "unknown" would be inventing a claim
    // about the world.
    renderCard({ status: "rescheduled_for_tuesday" });

    expect(screen.queryByText("Sold out")).toBeNull();
    expect(screen.queryByText("Cancelled")).toBeNull();
    expect(screen.queryByText("Postponed")).toBeNull();
    expect(cardText()).not.toContain("unknown");
  });

  it("shows no badge for a personal event", () => {
    // The server sends `null` for a personal event's status and `null` for its sold-out
    // flag — the user's own agenda row has no lifecycle and no tickets.
    renderCard({ event_kind: "personal", status: null, is_sold_out: null });

    expect(screen.queryByText("Sold out")).toBeNull();
  });
});

describe("the state and the conflict indicator together", () => {
  it("shows both when a sold-out event is also in conflict", () => {
    // **This is the case the work item names**: two indicators that must coexist
    // legibly. They are both in the card's upper region, and the conflict indicator's
    // amber and the badge's amber are *the same hex* — so they have to be told apart by
    // shape and position, not by colour.
    renderCard({ is_sold_out: true, conflict: true });

    expect(screen.getByText("Sold out")).toBeInTheDocument();
    expect(screen.getByLabelText("Schedule conflict")).toBeInTheDocument();
  });

  it("tells the two apart by shape", () => {
    renderCard({ is_sold_out: true, conflict: true });

    // The conflict indicator is a 6px dot.
    const dot = screen.getByLabelText("Schedule conflict").querySelector("span");
    expect(dot?.className).toContain("size-[6px]");

    // The state badge is a pill, with a border and a fill.
    const badge = screen.getByText("Sold out");
    expect(badge.className).toContain("border-border-strong");
    expect(badge.className).not.toContain("size-[6px]");
  });

  it("tells the two apart by position", () => {
    renderCard({ is_sold_out: true, conflict: true });

    // **They are in different places, and the assertion is about the places, not about
    // a class name.** The conflict indicator lives in the trust row — the strip at the
    // top of the card that holds the conflict mark, the confidence pulse and the
    // source badge. The badge lives in its own row above the title. So the two are
    // not in the same parent, and the badge is not among the trust row's children.
    const conflict = screen.getByLabelText("Schedule conflict");
    const badge = screen.getByText("Sold out");

    expect(conflict).not.toBe(badge);
    expect(badge.closest("article")).not.toBeNull();
    expect(conflict.closest("article")).toBe(badge.closest("article"));
    // **Not siblings, and not in the same row.** The badge is right-aligned in its own
    // row; the conflict mark is in the row above it, beside the confidence pulse.
    expect(conflict.parentElement).not.toBe(badge.parentElement);
  });

  it("gives the two different glyphs", () => {
    // The badge's glyph is a shape, and it is not the conflict indicator's dot.
    renderCard({ is_sold_out: true, conflict: true });

    const glyph = screen.getByText("Sold out").querySelector('[aria-hidden="true"]');
    // A hollow circle, where the conflict indicator is a solid one.
    expect(glyph?.textContent).toBe("⊘");
    // The conflict indicator's dot is a 6px circle with a ring; the badge's glyph is a
    // character in a span with no size of its own.
    expect(glyph?.className).not.toContain("size-[6px]");
    expect(glyph?.className).not.toContain("rounded-full");
  });

  it("shows a cancelled card's state and its conflict together", () => {
    renderCard({ status: "cancelled", conflict: true });

    expect(screen.getByText("Cancelled")).toBeInTheDocument();
    expect(screen.getByLabelText("Schedule conflict")).toBeInTheDocument();
  });
});

describe("the badge's own shape", () => {
  it("is not a control", () => {
    // There is nothing to dismiss and nothing to do about a cancelled event, so the
    // badge is a `<span>` — never a focus stop, never in the tab order.
    renderCard({ status: "cancelled" });

    const badge = screen.getByText("Cancelled");
    expect(badge.tagName).toBe("SPAN");
    expect(badge.getAttribute("role")).toBeNull();
    expect(badge.getAttribute("tabindex")).toBeNull();
  });

  it("is hidden from assistive technology, because the card's link already names it", () => {
    // **The same fact must not be announced twice in one card.** The card's link
    // carries the state's name in its `aria-label`, and the link is the tap target —
    // so a browse-mode reader who reaches the badge and then the link would hear
    // "Cancelled" twice. The badge is therefore `aria-hidden`.
    //
    // **The visible label stays.** It is what makes the state legible at a glance and
    // what satisfies WCAG 1.4.1 — colour is never the sole carrier of meaning.
    renderCard({ status: "cancelled" });

    const badge = screen.getByText("Cancelled");
    expect(badge.getAttribute("aria-hidden")).toBe("true");
  });

  it("gives each state its own glyph", () => {
    // Three states, three shapes. The colour cannot do this — the badge's amber and
    // the conflict indicator's amber are the same hex — so the glyph has to.
    const glyphFor = (overrides: Partial<DigestCard>) => {
      const { unmount } = render(
        <PulseCard
          card={{ ...CARD, ...overrides }}
          explanation={{ kind: "relevance", value: 4 }}
        />,
      );
      const glyph = screen
        .getByText(/Sold out|Cancelled|Postponed/)
        .querySelector('[aria-hidden="true"]')?.textContent;
      unmount();
      return glyph;
    };

    expect(glyphFor({ is_sold_out: true })).toBe("⊘");
    expect(glyphFor({ status: "cancelled" })).toBe("✕");
    expect(glyphFor({ status: "postponed" })).toBe("↦");
  });
});
