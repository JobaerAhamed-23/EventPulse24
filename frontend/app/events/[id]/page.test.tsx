import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EventDetailPage from "@/app/events/[id]/page";

/**
 * `/events/:id` — the Detail Screen.
 *
 * **The property this file exists to defend is the absence.** The Detail Screen is
 * where a plausible explanation is most tempting, and the screen's correctness is
 * mostly about what it *refuses* to show:
 *
 *   - an event the user was never shown gets **no explanation at all** — not an empty
 *     section, not a placeholder, not an Event Fit standing in for it;
 *   - an anonymous visitor gets **nothing personal**;
 *   - fewer than five neighbors gets **silence**, and no number anywhere.
 *
 * So most of the assertions below are about the *absence* of a thing, and several of
 * them assert that an element is not in the DOM rather than that its text is empty —
 * because an empty `<section>` with a heading is exactly the placeholder the criterion
 * forbids.
 */

const readEventDetail = vi.fn();
const getSession = vi.fn();

vi.mock("@/lib/event-detail-read", () => ({
  readEventDetail: (id: string) => readEventDetail(id),
}));

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/components/detail/detail-actions", () => ({
  DetailActions: (props: { saved: boolean }) => (
    <div data-detail-actions-stub data-saved={String(props.saved)}>
      <button type="button">Save to Pulse</button>
      <button type="button">Share</button>
    </div>
  ),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  onboarding: { completed: true, current_step: null },
};

/** The event's public facts — the payload every case shares. */
function facts(overrides: Record<string, unknown> = {}) {
  return {
    canonical_url: "https://example.test/event",
    description: "A short panel on building products that respect attention.",
    end_time_utc: null,
    event_version: 1,
    id: "22222222-2222-2222-2222-222222222222",
    is_sold_out: false,
    slug: "designing-for-calm",
    source_name: "Brooklyn Arts Council",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-11-07T23:00:00Z",
    status: "published",
    title: "Designing for Calm",
    tz_review_pending: false,
    venue_city: "Brooklyn",
    venue_country_code: "US",
    venue_name: "Brooklyn Arts Council",
    ...overrides,
  };
}

/** The persisted composition's breakdown. */
function whyThis(overrides: Record<string, unknown> = {}) {
  return {
    bucket: 4,
    composed_at: "2026-11-07T08:00:00Z",
    slot: "nearby",
    source_badge: "official_site",
    tags: ["nearby", "tonight", "matches_arts_culture"],
    ...overrides,
  };
}

function personal(overrides: Record<string, unknown> = {}) {
  return {
    neighbor_bucket: "few",
    saved: false,
    why_this: whyThis(),
    conflict: null,
    ...overrides,
  };
}

/**
 * The caller's **active** conflict pair for this event, as the payload carries it.
 *
 * **`saved_side_id` is the save row's id**, not the catalog event's — the pair stores a
 * `SavedEvent` by that row's id, and a `skip_public` releases the save by the same id.
 */
function conflict(overrides: Record<string, unknown> = {}) {
  return {
    pair_id: "33333333-3333-3333-3333-333333333333",
    kind: "time",
    saved_side_id: "44444444-4444-4444-4444-444444444444",
    other_side: {
      kind: "personal_event",
      id: "55555555-5555-5555-5555-555555555555",
      name: "Dentist",
      start_time_utc: "2026-11-07T23:30:00Z",
      end_time_utc: null,
    },
    actions: ["keep_both", "edit_new", "skip_public"],
    ...overrides,
  };
}

function found(personalBlock: Record<string, unknown> | null) {
  return { event: facts(), personal: personalBlock };
}

beforeEach(() => {
  readEventDetail.mockReset();
  getSession.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
});

async function renderPage() {
  render(await EventDetailPage({ params: Promise.resolve({ id: "event-1" }) }));
}

/**
 * The text of an element, with its children's text joined.
 *
 * **The tags and the date line are split across `<span>`s**, so a string matcher on
 * `textContent` of one node does not find them. This walks the element and joins the
 * text it actually contains — which is what a screen reader reads, and what the
 * assertions are about.
 */
function textOf(element: Element | null): string {
  return (element?.textContent ?? "").replace(/\s+/g, " ").trim();
}

/* ── the read ─────────────────────────────────────────────────────────────────── */

describe("the read", () => {
  it("reads the event by its id", async () => {
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    expect(readEventDetail).toHaveBeenCalledWith("event-1");
  });

  it("renders the removed state for a 404, and says the event is gone", async () => {
    readEventDetail.mockResolvedValue({ kind: "removed" });

    await renderPage();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "This event is no longer available.",
    );
    expect(screen.getByRole("link", { name: "Back to Pulse Digest" })).toBeInTheDocument();
  });

  it("renders the error state when the API cannot be reached", async () => {
    readEventDetail.mockResolvedValue({ kind: "unavailable" });

    await renderPage();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Couldn't load this event. Back to Pulse Digest.",
    );
  });

  it("tells the removed state and the error state apart", async () => {
    // The two failures are different facts: one about the world, one about us. Folding
    // them together would either lie about the event or lie about our infrastructure.
    readEventDetail.mockResolvedValue({ kind: "removed" });
    await renderPage();
    const removed = screen.getByRole("heading", { level: 1 }).textContent;

    screen.getByRole("heading", { level: 1 });
    readEventDetail.mockResolvedValue({ kind: "unavailable" });
    const { unmount } = render(await EventDetailPage({ params: Promise.resolve({ id: "e" }) }));
    const error = screen.getAllByRole("heading", { level: 1 })[1]?.textContent;
    unmount();

    expect(removed).not.toBe(error);
  });

  it("gives the error state exactly one action home", async () => {
    readEventDetail.mockResolvedValue({ kind: "unavailable" });

    await renderPage();

    // The action is inside the error state itself — the public footer carries links of
    // its own, and those are chrome rather than actions.
    const error = document.querySelector("[data-detail-error]");
    expect(error).not.toBeNull();
    expect(error?.querySelectorAll("a")).toHaveLength(1);
  });
});

/* ── the locked order ─────────────────────────────────────────────────────────── */

describe("the locked element order", () => {
  it("renders the trust row, the name, the when·where, then the content", async () => {
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    // **The order is read from the document's own sequence**, not from the component
    // tree — the locked order is a statement about what a reader sees first.
    const article = screen.getByRole("article");
    const markers: Array<[string, string]> = [
      ["tags", "[data-detail-tags]"],
      ["reminder", "[data-detail-reminder]"],
      ["actions", "[data-detail-actions-stub]"],
      ["breakdown", "[data-detail-breakdown]"],
      ["neighbors", "[data-detail-neighbors]"],
    ];
    const positions = markers.map(([name, selector]) => {
      const node = article.querySelector(selector);
      expect(node, name).not.toBeNull();
      const container = node?.parentElement ?? null;
      return { name, index: container ? Array.from(article.children).indexOf(container) : -1 };
    });

    // The header comes first (it holds the badge, the pulse and the name), then the
    // tags, then the description, then the picker, the actions, the breakdown, and the
    // neighbor count last.
    const index = (name: string): number =>
      positions.find((position) => position.name === name)?.index ?? -1;
    expect(index("tags")).toBeGreaterThan(-1);
    expect(index("tags")).toBeLessThan(index("reminder"));
    expect(index("reminder")).toBeLessThan(index("actions"));
    expect(index("actions")).toBeLessThan(index("breakdown"));
    expect(index("breakdown")).toBeLessThan(index("neighbors"));
  });

  it("puts the source badge before the confidence pulse", async () => {
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    // The Detail Screen's own header, not the shell's topbar — there are two `<header>`
    // elements on the page and the trust row lives in this one.
    const header = document.querySelector("article header");
    const buttons = Array.from(header?.querySelectorAll("button") ?? []);
    expect(buttons[0]).toHaveAccessibleName("Official");
    expect(buttons[1]).toHaveAccessibleName("Relevance 4 of 5");
  });
});

/* ── the conflict mark ────────────────────────────────────────────────────────── */

describe("the conflict mark", () => {
  it("is absent when the payload names no pair", async () => {
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    expect(screen.queryByRole("button", { name: /Schedule conflict/ })).not.toBeInTheDocument();
  });

  it("is present when the payload names an active pair", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ conflict: conflict() })),
    });

    await renderPage();

    expect(
      screen.getByRole("button", { name: "Schedule conflict. Choose how to handle it." }),
    ).toBeInTheDocument();
  });

  it("sits in the trust row, after the badge and the pulse", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ conflict: conflict() })),
    });

    await renderPage();

    // The mark is a fact about this event, and the trust row is where this screen puts
    // its facts about the event.
    const header = document.querySelector("article header");
    const buttons = Array.from(header?.querySelectorAll("button") ?? []);
    expect(buttons[0]).toHaveAccessibleName("Official");
    expect(buttons[1]).toHaveAccessibleName("Relevance 4 of 5");
    expect(buttons[2]).toHaveAccessibleName("Schedule conflict. Choose how to handle it.");
  });

  it("is absent for an anonymous reader", async () => {
    // The anonymous reader has nothing personal, and a conflict is the most personal
    // thing there is.
    readEventDetail.mockResolvedValue({ kind: "anonymous", detail: found(null) });

    await renderPage();

    expect(screen.queryByRole("button", { name: /Schedule conflict/ })).not.toBeInTheDocument();
  });

  it("does not open the prompt by itself", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ conflict: conflict() })),
    });

    await renderPage();

    // The payload says "there is a choice" — not "show the choice now". The user came
    // to read an event.
    expect(screen.queryByRole("dialog", { name: "Schedule conflict" })).not.toBeInTheDocument();
  });
});

/* ── the tags ─────────────────────────────────────────────────────────────────── */

describe("the why-this tags", () => {
  it("renders the persisted tags, in the persisted order", async () => {
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    expect(textOf(document.querySelector("[data-detail-tags]"))).toBe(
      "Nearby, Tonight, Arts & culture",
    );
  });

  it("renders the same labels the card renders for the same keys", async () => {
    // FR-21's third consequence: the tags are "consistent on the Pulse Card and on the
    // Detail Screen". The strongest form of consistency is equality — and the reason
    // they are equal is that both surfaces read the same `tagLabel`.
    const { tagLabel } = await import("@/lib/digest-labels");
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    expect(textOf(document.querySelector("[data-detail-tags]"))).toBe(
      ["nearby", "tonight", "matches_arts_culture"].map(tagLabel).join(", "),
    );
  });

  it("renders no tags at all when there is no composition", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ why_this: null })),
    });

    await renderPage();

    expect(document.querySelector("[data-detail-tags]")).toBeNull();
  });
});

/* ── the absence ──────────────────────────────────────────────────────────────── */

describe("no composition, no breakdown", () => {
  it("renders no breakdown section at all — not an empty one", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ why_this: null })),
    });

    await renderPage();

    // **The section element is not in the DOM.** An assertion on empty text would pass
    // on a screen that rendered an empty `<section>` with a heading — which is the
    // placeholder the criterion forbids.
    expect(document.querySelector("[data-detail-breakdown]")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Why this?" })).not.toBeInTheDocument();
  });

  it("renders no confidence pulse when there is no composition", async () => {
    // The pulse's value is the persisted Relevance Pulse bucket. There is no other
    // source for it, and the Event Fit's bucket belongs to the anonymous preview — so a
    // signed-in user who was never shown this event sees no five-dot indicator.
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ why_this: null })),
    });

    await renderPage();

    expect(screen.queryByRole("button", { name: /Relevance \d of 5/ })).not.toBeInTheDocument();
  });

  it("renders no source badge when there is no composition", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ why_this: null })),
    });

    await renderPage();

    expect(screen.queryByRole("button", { name: "Official" })).not.toBeInTheDocument();
  });

  it("still renders the public facts", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ why_this: null })),
    });

    await renderPage();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Designing for Calm");
    expect(
      screen.getByText("A short panel on building products that respect attention."),
    ).toBeInTheDocument();
  });
});

/* ── the anonymous case ───────────────────────────────────────────────────────── */

describe("the anonymous case", () => {
  beforeEach(() => {
    readEventDetail.mockResolvedValue({ kind: "anonymous", detail: found(null) });
  });

  it("renders the public facts", async () => {
    await renderPage();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Designing for Calm");
    expect(
      screen.getByText("A short panel on building products that respect attention."),
    ).toBeInTheDocument();
  });

  it("renders no breakdown, no confidence pulse and no source badge", async () => {
    await renderPage();

    expect(document.querySelector("[data-detail-breakdown]")).toBeNull();
    expect(screen.queryByRole("button", { name: /Relevance \d of 5/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Official" })).not.toBeInTheDocument();
  });

  it("renders no neighbor count", async () => {
    await renderPage();

    expect(document.querySelector("[data-detail-neighbors]")).toBeNull();
  });

  it("renders no save button and no reminder picker", async () => {
    await renderPage();

    expect(document.querySelector("[data-detail-actions-stub]")).toBeNull();
    expect(document.querySelector("[data-detail-reminder]")).toBeNull();
  });

  it("does not read the session — the API's own answer is the authority", async () => {
    // The read says "anonymous" because the API sent `personal: null`. A client that
    // inferred it from its own session cookie could render the personal surface to a
    // caller the API refused.
    await renderPage();

    expect(getSession).not.toHaveBeenCalled();
  });
});

/* ── the breakdown ────────────────────────────────────────────────────────────── */

describe("the why-this breakdown", () => {
  it("renders one factor per line", async () => {
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    // The breakdown's own list, not the reminder chips' list.
    const list = document.querySelector("[data-detail-breakdown] ul");
    expect(list?.querySelectorAll("li")).toHaveLength(3);
  });

  it("renders a line for each persisted tag, and nothing else", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ why_this: whyThis({ tags: ["nearby"] }) })),
    });

    await renderPage();

    const list = document.querySelector("[data-detail-breakdown] ul");
    const items = list?.querySelectorAll("li") ?? [];
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent("It's in your city.");
  });

  it("states no reliability score, no distance and no attendance", async () => {
    // The mockup's factors — "Source reliability 0.91 (Bayesian-smoothed)", "It's four
    // blocks from your office" — are drift: FR-16 is unbuilt and there are no
    // coordinates. A factor line stating a number we never computed is worse than no
    // line at all.
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/reliability/i);
    expect(text).not.toMatch(/bayesian/i);
    expect(text).not.toMatch(/\d+\s*km/i);
    expect(text).not.toMatch(/blocks from/i);
    expect(text).not.toMatch(/attended/i);
  });

  it("falls back to the tag's own label for a tag it does not know", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ why_this: whyThis({ tags: ["brand_new_tag"] }) })),
    });

    await renderPage();

    // A new server tag appears as a plain line rather than vanishing or acquiring a
    // fabricated reason.
    const list = document.querySelector("[data-detail-breakdown] ul");
    expect(textOf(list?.querySelector("li") ?? null)).toBe("Brand New Tag");
  });
});

/* ── the neighbor count ───────────────────────────────────────────────────────── */

describe("the neighbor count", () => {
  it.each([
    ["few", "A few neighbors saved this."],
    ["some", "Some neighbors saved this."],
    ["many", "Many neighbors saved this."],
    ["a_lot", "A lot of neighbors saved this."],
  ])("renders the %s bucket as prose", async (bucket, line) => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ neighbor_bucket: bucket })),
    });

    await renderPage();

    expect(screen.getByText(line)).toBeInTheDocument();
  });

  it("renders nothing at all when the bucket is null", async () => {
    // The suppression is silence — no row, no "0 neighbors", and no field saying the
    // count was suppressed.
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: found(personal({ neighbor_bucket: null })),
    });

    await renderPage();

    expect(document.querySelector("[data-detail-neighbors]")).toBeNull();
    expect(screen.queryByText(/neighbor/i)).not.toBeInTheDocument();
  });

  it("renders no exact number, in any bucket", async () => {
    for (const bucket of ["few", "some", "many", "a_lot"]) {
      readEventDetail.mockResolvedValue({
        kind: "found",
        detail: found(personal({ neighbor_bucket: bucket })),
      });
      const { unmount } = render(await EventDetailPage({ params: Promise.resolve({ id: "e" }) }));
      const text = screen.getByText(/neighbors saved this/).textContent ?? "";
      expect(text, bucket).not.toMatch(/\d/);
      unmount();
    }
  });

  it("renders no emoji prefix", async () => {
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    expect(document.body.textContent).not.toContain("👥");
  });
});

/* ── the actions and the picker ───────────────────────────────────────────────── */

describe("the action row and the reminder picker", () => {
  it("offers Save and Share to a signed-in reader", async () => {
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    expect(screen.getByRole("button", { name: "Save to Pulse" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Share" })).toBeInTheDocument();
  });

  it("offers no Dismiss button, because there is no dismissal endpoint", async () => {
    // FR-25's dismissal is a swipe on the Pulse Card. A "Dismiss" button here would be
    // a control that silently does nothing.
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    expect(
      screen.queryByRole("button", { name: /dismiss|less like this/i }),
    ).not.toBeInTheDocument();
  });

  it("names the channel and the choice, without claiming a particular plan", async () => {
    // **The section must not assert what the plan contains.** The Detail payload does
    // not carry the reminder slots, so a sentence like "the day before and the hour
    // before" is a claim the page cannot check — and it is false for a user whose
    // plan is the default, carries a custom slot, or is empty.
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    expect(
      screen.getByText("Reminders go by email. Choose when you'll hear from us about this event."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/day before and the hour before/i)).not.toBeInTheDocument();
  });

  it("links to the Reminder Picker, and holds no control of its own", async () => {
    // **The section used to render the plan's chips as `<span>`s**, because "nothing
    // schedules sends" — the delivery intent had not built the scheduler. That reason
    // is gone: the plan is written through `PUT /api/reminders/…`, and the picker is
    // where it is edited.
    //
    // **So the section links out and holds no control.** A `<span>` that looks like a
    // control and is not one is worse than a link that plainly is — and a button here
    // would be a second, redundant route into the picker.
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    const link = screen.getByRole("link", { name: "Edit reminders" });
    expect(link).toHaveAttribute("href", expect.stringContaining("/reminders"));
    expect(document.querySelector("[data-detail-reminder] button")).toBeNull();
  });
});

/* ── the sold-out state ───────────────────────────────────────────────────────── */

describe("the sold-out state", () => {
  it("says so, calmly, in one line", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts({ is_sold_out: true }), personal: personal() },
    });

    await renderPage();

    expect(screen.getByText("Sold out — tickets no longer available.")).toBeInTheDocument();
  });

  it("replaces the save and reminder actions", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts({ is_sold_out: true }), personal: personal() },
    });

    await renderPage();

    expect(screen.queryByRole("button", { name: /Save to Pulse/ })).not.toBeInTheDocument();
    expect(document.querySelector("[data-detail-reminder]")).toBeNull();
  });

  it("still renders the breakdown — a sold-out event is still an event the user was shown", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts({ is_sold_out: true }), personal: personal() },
    });

    await renderPage();

    expect(document.querySelector("[data-detail-breakdown]")).not.toBeNull();
  });
});

/* ── the time ─────────────────────────────────────────────────────────────────── */

describe("the time", () => {
  it("shows the event's date and time", async () => {
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    // **The instant is rendered, whichever zone the reader is in.** The event starts at
    // 23:00 UTC on Nov 7; in New York that is 6:00 PM on Nov 7, and in London it is
    // 11:00 PM on Nov 7. The assertion is on the shape, because the zone the test
    // machine is in is not the zone the reader is in.
    const meta = textOf(document.querySelector("article header p"));
    expect(meta).toMatch(/\w+day, Nov \d+ · \d{1,2}:\d{2} (AM|PM)/);
  });

  it("shows the venue's local time too, when the reader is in another zone", async () => {
    // The venue is in New York; the reader is wherever the browser says. When the two
    // clocks differ, both are shown — and the venue's is in parentheses beside its own
    // zone.
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    const meta = textOf(document.querySelector("article header p"));
    expect(meta).toMatch(/\(\d{1,2}:\d{2} (AM|PM) [A-Z]{2,4}\)/);
  });

  it("shows one clock when the reader and the venue agree", async () => {
    // Two different zones can show the same clock face. When they do, showing both is
    // noise rather than information — so the venue's time is withheld.
    const { detailTimes } = await import("@/lib/detail-time");
    const times = detailTimes("2026-11-07T23:00:00Z", "America/New_York", "America/New_York");

    expect(times?.venueTime).toBeNull();
    expect(times?.time).toBe("6:00 PM");
  });

  it("shows the venue's time when the zones differ", async () => {
    const { detailTimes } = await import("@/lib/detail-time");
    const times = detailTimes("2026-11-07T23:00:00Z", "America/New_York", "Europe/London");

    expect(times?.time).toBe("11:00 PM");
    expect(times?.venueTime).toBe("6:00 PM");
    expect(times?.venueZone).toBe("EST");
  });

  it("marks the time approximate when the source's time is under review", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts({ tz_review_pending: true }), personal: personal() },
    });

    await renderPage();

    expect(screen.getByText("Time approximate")).toBeInTheDocument();
  });

  it("says the time is to be confirmed when there is no time", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts({ start_time_utc: null }), personal: personal() },
    });

    await renderPage();

    expect(screen.getByText("Time to be confirmed")).toBeInTheDocument();
  });
});

/* ── the absent sections ──────────────────────────────────────────────────────── */

describe("the sections that do not ship", () => {
  it("renders no reviews, no similar events and no report link", async () => {
    readEventDetail.mockResolvedValue({ kind: "found", detail: found(personal()) });

    await renderPage();

    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/review/i);
    expect(text).not.toMatch(/similar events/i);
    expect(text).not.toMatch(/report this event/i);
    expect(text).not.toMatch(/attended/i);
  });
});
