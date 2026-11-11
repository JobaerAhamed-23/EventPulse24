/**
 * The Detail Screen's **axe-core gate**.
 *
 * **"axe-core reports zero serious or critical violations on this surface."** The work
 * item's acceptance criteria say so, and this file is the gate.
 *
 * **The gate runs over every state, not just the happy one.** A page can be accessible
 * when it is full and inaccessible when it is empty. The found, anonymous, removed and
 * error documents are four different documents with four different sets of rules — an
 * anonymous document with no buttons, an error document whose action is a link, a
 * removed document that is a heading and a paragraph.
 *
 * **Serious and critical only.** `minor` and `moderate` findings are advisory, and a
 * gate that fails on a moderate finding is a gate that gets disabled.
 *
 * **`color-contrast` is disabled explicitly.** jsdom computes no layout, so axe has no
 * boxes to compare and the rule reports false positives rather than findings. The
 * contrast requirement belongs to a real browser.
 */
import { render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EventDetailPage from "@/app/events/[id]/page";

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

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  onboarding: { completed: true, current_step: null },
};

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

beforeEach(() => {
  readEventDetail.mockReset();
  getSession.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
});

/**
 * Run axe over the rendered page.
 *
 * **The container is the whole document.** axe walks the DOM it is given, so auditing
 * `main` alone would miss the shell — and the shell is part of the surface.
 */
async function audit() {
  const results = await axe.run(document.body, {
    resultTypes: ["violations"],
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
}

async function renderPage() {
  render(await EventDetailPage({ params: Promise.resolve({ id: "event-1" }) }));
}

describe("the Detail Screen's axe-core gate", () => {
  it("has zero serious or critical violations in the found state", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts(), personal: personal() },
    });

    await renderPage();

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the anonymous state", async () => {
    readEventDetail.mockResolvedValue({
      kind: "anonymous",
      detail: { event: facts(), personal: null },
    });

    await renderPage();

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the removed state", async () => {
    readEventDetail.mockResolvedValue({ kind: "removed" });

    await renderPage();

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the error state", async () => {
    readEventDetail.mockResolvedValue({ kind: "unavailable" });

    await renderPage();

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations in the sold-out state", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts({ is_sold_out: true }), personal: personal() },
    });

    await renderPage();

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations with an active conflict", async () => {
    // **The mark is a button**, and a button with an accessible name is a thing axe
    // checks — a mark that was only a coloured dot would fail the "button name" rule,
    // and a mark with no name would fail the "colour is not the sole carrier" rule.
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts(), personal: personal({ conflict: conflict() }) },
    });

    await renderPage();

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations with the prompt open", async () => {
    // **The prompt is a modal sheet with its own content** — a heading, two cards and
    // three choices. It is the surface where an accessibility failure would hurt most,
    // because it is a forced choice the user cannot walk away from.
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts(), personal: personal({ conflict: conflict() }) },
    });

    await renderPage();

    screen.getByRole("button", { name: "Schedule conflict. Choose how to handle it." }).click();

    await waitFor(() =>
      expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument(),
    );

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("has zero serious or critical violations with the report modal open", async () => {
    // **The report modal (FR-59) is a modal sheet with its own content** — a heading,
    // a radio group of four options, and two buttons. It is a surface where an
    // accessibility failure would hurt: the reader came here to say something is
    // wrong, and the control that lets them say it must not be the one that traps
    // them.
    //
    // **The radio group is the thing axe checks here.** A group of buttons with
    // `role="radio"` and `aria-checked` is a composite widget, and axe has rules for
    // one — a radio with no checked sibling, or a group with no accessible name, would
    // both be reported.
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts(), personal: personal() },
    });

    await renderPage();

    screen.getByRole("button", { name: "Report this event" }).click();

    await waitFor(() =>
      expect(screen.getByRole("dialog", { name: "Report this event" })).toBeInTheDocument(),
    );

    const violations = await audit();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`)).toEqual(
      [],
    );
  });

  it("audits a document with the real landmarks in place", async () => {
    // A gate that passed because the page rendered nothing would pass forever.
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts(), personal: personal() },
    });

    await renderPage();

    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("article")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});

/**
 * The report flag's **presence**, and where it is and is not.
 *
 * **This file renders the *real* action row.** `app/events/[id]/page.test.tsx` stubs
 * `DetailActions` out — it tests the page's contribution to the row — so it cannot see
 * the flag at all. So the flag's presence is pinned here, where the row is the real one.
 *
 * **The pair is the claim.** The flag is there for a signed-in reader and absent for an
 * anonymous one — the same rule Save follows, because the whole row is behind one
 * `personal` gate (`app/events/[id]/page.tsx:477`).
 */
describe("the report flag", () => {
  it("is there for a signed-in reader", async () => {
    readEventDetail.mockResolvedValue({
      kind: "found",
      detail: { event: facts(), personal: personal() },
    });

    await renderPage();

    expect(screen.getByRole("button", { name: "Report this event" })).toBeInTheDocument();
  });

  it("is absent for an anonymous reader", async () => {
    // **The flag matches what Save does on the same screen.** Save is absent for an
    // anonymous reader, and the flag is absent in the same render — because they are
    // behind the same gate, not because each has its own rule.
    readEventDetail.mockResolvedValue({
      kind: "anonymous",
      detail: { event: facts(), personal: null },
    });

    await renderPage();

    expect(screen.queryByRole("button", { name: "Report this event" })).not.toBeInTheDocument();
  });

  it("is gone for an anonymous reader in the same way Save is", async () => {
    // **The two absences are the same absence.** If the flag were routed to sign-in
    // while Save were hidden, this would fail — and the criterion is that they match.
    readEventDetail.mockResolvedValue({
      kind: "anonymous",
      detail: { event: facts(), personal: null },
    });

    await renderPage();

    expect(screen.queryByRole("button", { name: /Save to Pulse/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Report this event" })).not.toBeInTheDocument();
  });
});
