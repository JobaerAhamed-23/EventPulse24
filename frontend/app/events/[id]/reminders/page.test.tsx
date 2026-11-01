/**
 * `/events/:id/reminders` — the Reminder Plan editor's route.
 *
 * **The crumb, the shell and the states.** The route is a server component that reads
 * the plan, the default and the event, and renders the picker inside the A-8 shell.
 *
 * **The crumb is `Digest · {event name} · Edit reminders`.** The work item names it
 * exactly, and the event's name comes from the Detail Screen's own read — so the
 * crumb's name and the Detail Screen's title are the same string by construction,
 * rather than by coincidence.
 *
 * **Digest is the active sidenav item.** The picker hangs off Digest in the IA — Detail
 * is reached by tapping a Digest card, and the picker hangs off Detail — so the sidenav
 * marks Digest active on every path under `/events/`.
 */
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ReminderPickerPage from "@/app/events/[id]/reminders/page";

const readReminderPlan = vi.fn();
const readDefaultReminderSlots = vi.fn();
const readEventDetail = vi.fn();
const getSession = vi.fn();

vi.mock("@/lib/reminder-plan-read", () => ({
  readReminderPlan: (kind: string, id: string) => readReminderPlan(kind, id),
  readDefaultReminderSlots: () => readDefaultReminderSlots(),
}));

vi.mock("@/lib/event-detail-read", () => ({
  readEventDetail: (id: string) => readEventDetail(id),
}));

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/navigation", () => ({
  usePathname: () => "/events/event-1/reminders",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  onboarding: { completed: true, current_step: null },
};

/** The plan, as the server sends it. */
function plan(overrides: Record<string, unknown> = {}) {
  return {
    target_kind: "saved_event",
    target_id: "event-1",
    slots: ["1d", "1hr"],
    deliveries: [
      {
        slot: "1d",
        delivery_at: "2026-11-06T22:00:00Z",
        deferred: false,
        deferred_to: null,
      },
      {
        slot: "1hr",
        delivery_at: "2026-11-07T22:00:00Z",
        deferred: false,
        deferred_to: null,
      },
    ],
    ...overrides,
  };
}

/** The event, as the Detail Screen's read returns it. */
function detail(overrides: Record<string, unknown> = {}) {
  return {
    kind: "found",
    detail: {
      event: {
        canonical_url: "https://example.test/event",
        description: null,
        end_time_utc: null,
        event_version: 1,
        id: "event-1",
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
      },
      personal: {
        neighbor_bucket: "few",
        saved: true,
        why_this: null,
        conflict: null,
      },
    },
  };
}

beforeEach(() => {
  readReminderPlan.mockReset();
  readDefaultReminderSlots.mockReset();
  readEventDetail.mockReset();
  getSession.mockReset();

  readReminderPlan.mockResolvedValue({ kind: "found", plan: plan() });
  readDefaultReminderSlots.mockResolvedValue(["1d", "1hr"]);
  readEventDetail.mockResolvedValue(detail());
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
});

async function renderPage() {
  render(await ReminderPickerPage({ params: Promise.resolve({ id: "event-1" }) }));
}

describe("the route", () => {
  it("reads the plan for a saved event, with the default's slots", async () => {
    await renderPage();

    expect(readReminderPlan).toHaveBeenCalledWith("saved_event", "event-1");
    expect(readDefaultReminderSlots).toHaveBeenCalled();
  });

  it("renders the crumb Digest · {event} · Edit reminders", async () => {
    await renderPage();

    // **The crumb's own links, scoped to the crumb.** There are two "Digest" links on
    // the page — the sidenav's and the crumb's — and they mean different things, so
    // the query is scoped rather than ambiguous.
    const crumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumb).getByRole("link", { name: "Digest" })).toHaveAttribute("href", "/");
    expect(within(crumb).getByRole("link", { name: "Designing for Calm" })).toHaveAttribute(
      "href",
      "/events/event-1",
    );
    expect(within(crumb).getByText("Edit reminders")).toHaveAttribute("aria-current", "page");
  });

  it("marks Digest as the active sidenav item", async () => {
    await renderPage();

    // **The picker hangs off Digest in the IA**, so the sidenav's Digest row is the
    // active one — the same way it is on the Detail Screen.
    //
    // **The sidenav is the `Primary` rail.** There are two "Main" navigations on the
    // page — the sidenav's and the bottom-tab bar's — so the query is scoped to the
    // rail.
    const rail = screen.getByRole("complementary", { name: "Primary" });
    expect(within(rail).getByRole("link", { name: "Digest" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("renders the picker with the plan the server sent", async () => {
    await renderPage();

    expect(screen.getByRole("region", { name: "Reminder plan editor" })).toBeInTheDocument();
    expect(screen.getByText("Remind me:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1 day before/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("shows the event's name in the heading's line", async () => {
    await renderPage();

    expect(screen.getByText(/Reminders for Designing for Calm\./)).toBeInTheDocument();
  });
});

describe("the states", () => {
  it("says the event could not be found", async () => {
    readReminderPlan.mockResolvedValue({ kind: "missing" });

    await renderPage();

    expect(screen.getByText("We couldn't find that event.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Reminder plan editor" })).toBeNull();
  });

  it("says the reminders could not be loaded", async () => {
    readReminderPlan.mockResolvedValue({ kind: "unavailable" });

    await renderPage();

    expect(
      screen.getByText("Couldn't load your reminders. Back to Pulse Digest."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Reminder plan editor" })).toBeNull();
  });

  it("offers one way home from either failure", async () => {
    readReminderPlan.mockResolvedValue({ kind: "unavailable" });

    await renderPage();

    const home = screen.getByRole("link", { name: "Back to Pulse Digest" });
    expect(home).toHaveAttribute("href", "/");
  });
});
