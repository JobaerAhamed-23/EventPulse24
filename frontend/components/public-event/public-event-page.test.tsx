import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PublicEventPage } from "@/components/public-event/public-event-page";
import type { PublicEventPageOut } from "@/lib/public-event-read";

/**
 * The public event page — the front door, open to a stranger.
 *
 * **The property this file exists to defend is that the page says the same thing twice,
 * in the same way.** The visible page and the structured data are two renderings of one
 * payload, and AD-12 requires the JSON-LD to be "emitted from the same data the page
 * renders". A page that rebuilt the Schema.org object would be a second source of
 * truth, and the two would eventually disagree.
 *
 * **The JSON-LD must be in the server-rendered markup.** A crawler that does not execute
 * JavaScript sees nothing otherwise, which defeats the entire FR — so the assertion is
 * on the document's own HTML, not on a hydrated tree.
 */

/** The payload the catalog's public read returns. */
function page(overrides: Record<string, unknown> = {}): PublicEventPageOut {
  return {
    canonical_url: "https://brooklynartscouncil.org/events/calm",
    description: "A short, opinionated panel on building products that respect attention.",
    end_time_utc: null,
    event_version: 3,
    id: "0196c3a4-5b6d-7e8f-9a0b-1c2d3e4f5061",
    is_sold_out: false,
    schema_org: {
      "@context": "https://schema.org",
      "@type": "Event",
      name: "Designing for Calm",
      startDate: "2026-08-28T18:30:00-04:00",
    },
    slug: "designing-for-calm-2026-08-28-a1b2c3",
    source_name: "Brooklyn Arts Council",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-08-28T22:30:00Z",
    status: "published",
    title: "Designing for Calm",
    tz_review_pending: false,
    venue_address: "27 Clinton Ave",
    venue_city: "Brooklyn",
    venue_country_code: "US",
    venue_name: "Brooklyn Arts Council",
    ...overrides,
  } as PublicEventPageOut;
}

/** The JSON-LD block's text, as the browser would parse it. */
function jsonLd(): Record<string, unknown> {
  const script = document.querySelector('script[type="application/ld+json"]');
  expect(script, "the JSON-LD block is not in the markup").not.toBeNull();
  return JSON.parse(script?.textContent ?? "{}") as Record<string, unknown>;
}

describe("the public event page", () => {
  it("shows the event's title", () => {
    render(<PublicEventPage page={page()} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Designing for Calm");
  });

  it("shows the event's description", () => {
    render(<PublicEventPage page={page()} />);

    expect(screen.getByText(/A short, opinionated panel on building products/)).toBeInTheDocument();
  });

  it("shows the time in the event's own zone", () => {
    render(<PublicEventPage page={page()} />);

    // **The event's zone, not the reader's.** The start is 22:30 UTC; in
    // `America/New_York` (UTC-4 in August) that is 6:30 PM. A page that formatted in
    // the browser's zone would print a different string on the server and in the
    // browser — and this page is statically generated, so there is no browser to ask.
    expect(screen.getByText(/6:30 PM EDT/)).toBeInTheDocument();
  });

  it("shows the venue", () => {
    render(<PublicEventPage page={page()} />);

    // **The venue appears twice** — once in the meta row and once in the "Where"
    // section — so the assertion is on the count, not on a single match.
    expect(screen.getAllByText(/Brooklyn Arts Council/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/27 Clinton Ave/).length).toBeGreaterThan(0);
  });

  it("shows the source", () => {
    render(<PublicEventPage page={page()} />);

    expect(screen.getAllByText("Brooklyn Arts Council").length).toBeGreaterThan(0);
  });

  it("links to the event's canonical listing", () => {
    render(<PublicEventPage page={page()} />);

    const link = screen.getByRole("link", { name: "Open the listing" });
    expect(link).toHaveAttribute("href", "https://brooklynartscouncil.org/events/calm");
  });

  it("prints the slug as this system's own path, not the mockup's", () => {
    render(<PublicEventPage page={page()} />);

    // **The mockup writes `/e/<slug>`; this system's event page is `/events/<slug>`**
    // (`domain/revalidation.EVENT_PATH_PREFIX`). A page that printed the mockup's path
    // would show a reader a URL that does not exist here.
    expect(screen.getByText(/\/events\/designing-for-calm-2026-08-28-a1b2c3/)).toBeInTheDocument();
    expect(screen.queryByText(/\/e\//)).not.toBeInTheDocument();
  });

  it("shows the structured-data badge, because the page really does emit it", () => {
    render(<PublicEventPage page={page()} />);

    // **The badge is a fact about the document, not a decoration.** The page embeds the
    // payload's own Schema.org `Event` object, so the claim is true — which is why it
    // is worth showing.
    expect(screen.getByText("schema.org/Event")).toBeInTheDocument();
  });

  /* ── the JSON-LD ──────────────────────────────────────────────────────────── */

  it("embeds the JSON-LD in the server-rendered markup", () => {
    render(<PublicEventPage page={page()} />);

    // **In the document, not in a hydrated tree.** A crawler that does not execute
    // JavaScript sees the markup; a crawler that does not see the structured data
    // sees a page with no event in it.
    expect(document.querySelector('script[type="application/ld+json"]')).not.toBeNull();
  });

  it("embeds the payload's own schema_org, verbatim", () => {
    const payload = page();
    render(<PublicEventPage page={payload} />);

    // **The same object, not a rebuilt one.** The backend projected it, and the page
    // carries it. A page that assembled its own Schema.org object would be a second
    // source of truth, and the two would eventually disagree.
    expect(jsonLd()).toEqual(payload.schema_org);
  });

  it("embeds a JSON-LD block that cannot break out of the script element", () => {
    // **The escape that matters.** A JSON-LD block is parsed as HTML, so the only
    // sequence that can end the element early is `</script>`. A title containing one
    // must not be able to close the block and inject markup.
    const payload = page({
      schema_org: {
        "@context": "https://schema.org",
        "@type": "Event",
        name: "A talk </script><script>alert(1)</script>",
      },
    });
    render(<PublicEventPage page={payload} />);

    const script = document.querySelector('script[type="application/ld+json"]');
    expect(script?.innerHTML).not.toContain("</script>");
    // And it is still valid JSON with the same meaning.
    expect(jsonLd()["name"]).toBe("A talk </script><script>alert(1)</script>");
  });

  it("injects no second script element, so the escaped title stays data", () => {
    // **The stronger form of the same claim.** Asserting on `innerHTML` reads the
    // element's *contents*; it does not say how many script elements the document
    // ended up with. If the escape failed, the parser would have closed the JSON-LD
    // block and opened a second `<script>` — so the count is the assertion that
    // actually distinguishes "escaped" from "broken out".
    const payload = page({
      schema_org: {
        "@context": "https://schema.org",
        "@type": "Event",
        name: "A talk </script><script>alert(1)</script>",
      },
    });
    render(<PublicEventPage page={payload} />);

    // **One JSON-LD block, and no injected script.** The count is the assertion that
    // distinguishes "escaped" from "broken out": a failed escape would close the
    // block and open a second `<script>`, so the document would hold two.
    expect(document.querySelectorAll('script[type="application/ld+json"]')).toHaveLength(1);
    expect(document.querySelectorAll("script")).toHaveLength(1);

    // **And the injected markup stayed *inside* the block, as text.** The title is
    // still there — the escape made the `<` inert, not the string disappear. This is
    // why the assertion is not "the document does not contain `alert(1)`": the title
    // legitimately says `alert(1)`, and a page that hid it would be hiding the
    // event's own name.
    const script = document.querySelector('script[type="application/ld+json"]');
    expect(script?.textContent).toContain(
      "A talk " +
        String.raw`\u003c` +
        "/script>" +
        String.raw`\u003c` +
        "script>alert(1)" +
        String.raw`\u003c` +
        "/script>",
    );
    // **And no element was created from it.**
    expect(document.querySelectorAll("script")).toHaveLength(1);
    expect(document.body.querySelectorAll("*:not(script)").length).toBeGreaterThan(0);
  });

  it("escapes the line separators, so the block survives being parsed as a script", () => {
    // **Cheap insurance.** U+2028 and U+2029 are legal in a JSON string but are line
    // terminators in JavaScript. This block is parsed as JSON, so they are not an
    // injection today — but a payload can carry them, and escaping them costs
    // nothing.
    const payload = page({
      schema_org: {
        "@context": "https://schema.org",
        "@type": "Event",
        name: "A talk with separators",
      },
    });
    render(<PublicEventPage page={payload} />);

    const script = document.querySelector('script[type="application/ld+json"]');
    expect(script?.textContent).not.toContain(" ");
    expect(script?.textContent).not.toContain(" ");
    // And the meaning survives: the JSON parser gives back the original characters.
    expect(jsonLd()["name"]).toBe("A talk with separators");
  });

  it("offers a Save to Pulse CTA that links to the sign-up", () => {
    render(<PublicEventPage page={page()} />);

    const cta = screen.getByRole("link", { name: /Save to Pulse/ });
    expect(cta).toHaveAttribute("href", "/signup");
  });

  it("does not gate the content behind the CTA", () => {
    render(<PublicEventPage page={page()} />);

    // **The soft wall's whole property.** The description — the content — is on the
    // page without an account. A CTA that hid the content until sign-up would be a
    // hard wall wearing a soft wall's clothes.
    expect(screen.getByText(/A short, opinionated panel on building products/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Designing for Calm");
  });

  /* ── the states ───────────────────────────────────────────────────────────── */

  it("says so when the event is sold out", () => {
    render(<PublicEventPage page={page({ is_sold_out: true })} />);

    expect(screen.getByText(/Sold out/)).toBeInTheDocument();
  });

  it("says so when the event is postponed", () => {
    // **The lifecycle state is a fact the payload carries, and the page renders it**
    // (AD-10). A reader who came to a postponed event's page needs to know it is not
    // happening as advertised — and the payload's `schema_org` already carries the same
    // fact as `eventStatus`, so the two cannot disagree.
    render(<PublicEventPage page={page({ status: "postponed" })} />);

    expect(screen.getByText(/Postponed/)).toBeInTheDocument();
  });

  it("says so when the event is cancelled", () => {
    render(<PublicEventPage page={page({ status: "cancelled" })} />);

    expect(screen.getByText(/Cancelled/)).toBeInTheDocument();
  });

  it("says nothing about a scheduled event", () => {
    // **A scheduled event is the ordinary case.** A line reading "Scheduled" tells a
    // reader nothing they did not already assume.
    render(<PublicEventPage page={page({ status: "scheduled" })} />);

    expect(document.querySelector("[data-public-status]")).toBeNull();
  });

  it("says nothing about a status it does not recognise", () => {
    // **A fact the frontend cannot put into words is not rendered.** Inventing an
    // "unknown" line would be claiming something about the world that nobody said
    // (ASSUMPTION-9).
    render(<PublicEventPage page={page({ status: "rescheduled_maybe" })} />);

    expect(document.querySelector("[data-public-status]")).toBeNull();
  });

  it("does not say sold out when it is not", () => {
    render(<PublicEventPage page={page({ is_sold_out: false })} />);

    expect(screen.queryByText(/Sold out/)).not.toBeInTheDocument();
  });

  it("renders a past event normally", () => {
    // **A past event stays addressable.** The public read keeps it resolving, and the
    // page renders it like any other event — the criteria require it, and a past event
    // that 404s would break every link ever shared. The time is the event's own: 18:30
    // UTC on a January day in New York is 1:30 PM EST.
    render(<PublicEventPage page={page({ start_time_utc: "2020-01-05T18:30:00Z" })} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Designing for Calm");
    expect(screen.getByText(/1:30 PM EST/)).toBeInTheDocument();
  });

  it("omits the time when the payload carries none", () => {
    // **A missing fact is omitted, never filled.** There is no "Time to be confirmed"
    // invented for a payload with no start time.
    render(<PublicEventPage page={page({ start_time_utc: "" })} />);

    expect(screen.queryByText(/When/)).not.toBeInTheDocument();
  });

  it("omits the venue section when the payload carries no venue", () => {
    render(
      <PublicEventPage page={page({ venue_name: null, venue_address: null, venue_city: null })} />,
    );

    expect(screen.queryByRole("heading", { name: "Where" })).not.toBeInTheDocument();
  });

  it("shows the time-zone review note when the payload says the zone is unreviewed", () => {
    render(<PublicEventPage page={page({ tz_review_pending: true })} />);

    expect(screen.getByText(/start time has not been checked/)).toBeInTheDocument();
  });

  it("shows no reliability score — the payload carries none", () => {
    // **The mockup draws a score; the projection does not send one.** A number that
    // was not measured is not shown, and a score a reader might act on is worse than
    // no score at all.
    render(<PublicEventPage page={page()} />);

    expect(screen.queryByText(/reliability/i)).not.toBeInTheDocument();
  });
});
