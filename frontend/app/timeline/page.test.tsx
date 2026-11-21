import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TimelinePage from "@/app/timeline/page";
import { addDays, todayIn } from "@/lib/timeline-dates";

/**
 * `/timeline` — the Unified Timeline.
 *
 * **The page is a server component that renders what the server sent.** These tests
 * pin the four things it is allowed to decide — the week in the URL, the seven days in
 * the server's order, today's column, and the mobile day — and the four states it
 * draws: the full week, the quiet day, the quiet week, and the failure.
 *
 * **A malformed week is a failure, not a guess.** The page refuses to guess which week
 * the reader meant, and this pins that: the malformed value is *not* forwarded to the
 * read as a week.
 *
 * **The fixture week is the current week, not a fixed one.** The page decides "today"
 * from the current date, so a fixture pinned to a date in the past would leave the
 * grid with no today column and the mobile view with no day. The week is built from
 * the current date so the fixture cannot rot.
 *
 * **"The current date" means: in the zone the fixture week names.** The page reads
 * today in the *reader's* zone — the one the server sent with the week — and not in
 * whatever zone the machine running this file happens to be set to. The two differ for
 * eleven hours of every day between, say, Dhaka and New York, so a fixture built from
 * the machine's date would pass or fail by the clock. `TODAY` is read the same way the
 * page reads it.
 */

const getSession = vi.fn();
const readTimeline = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/timeline-read", () => ({
  readTimeline: (week?: string | null) => readTimeline(week),
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  usePathname: () => "/timeline",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

/** The zone the fixture week is cut in — the reader's zone, as the server names it. */
const ZONE = "America/New_York";

/** Today, in the fixture's zone: the day the page will call today. */
const TODAY = todayIn(ZONE);

/** The seven days of the current week, Monday first. */
const DAYS = Array.from({ length: 7 }, (_, index) => addDays(mondayOf(TODAY), index));
const MONDAY = DAYS[0] as string;
const SUNDAY = DAYS[6] as string;

/** One block, as the API sends it. */
function block(overrides: Record<string, unknown> = {}) {
  return {
    conflict: false,
    end_time_utc: null,
    id: "44444444-4444-4444-4444-444444444444",
    kind: "personal" as const,
    name: "Dentist",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-11-02T14:00:00Z",
    ...overrides,
  };
}

/**
 * A Mon–Sun week.
 *
 * **One day carries a block, the rest are empty.** An empty *week* is a different
 * state — it replaces the grid altogether — so the default fixture has content and the
 * quiet-week test asks for an empty one explicitly.
 */
function week(overrides: Record<string, unknown> = {}) {
  return {
    days: DAYS.map((date, index) => ({
      blocks: index === 0 ? [block()] : [],
      date,
    })),
    timezone: ZONE,
    week_end: SUNDAY,
    week_start: MONDAY,
    ...overrides,
  };
}

/** A week with nothing in it — the quiet-week state. */
function emptyWeek() {
  return week({ days: DAYS.map((date) => ({ blocks: [], date })) });
}

/** The Monday of the calendar week the day falls in. */
function mondayOf(day: string): string {
  const parsed = new Date(`${day}T00:00:00Z`);
  const weekday = (parsed.getUTCDay() + 6) % 7;
  return addDays(day, -weekday);
}

/** The props Next passes the page. */
function props(query: Record<string, string | string[]> = {}): PageProps<"/timeline"> {
  return { params: Promise.resolve({}), searchParams: Promise.resolve(query) };
}

beforeEach(() => {
  getSession.mockReset();
  redirect.mockReset();
  readTimeline.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readTimeline.mockResolvedValue({ kind: "week", week: week() });
});

afterEach(() => {
  cleanup();
});

describe("the routing decision", () => {
  it("sends an anonymous visitor to the public preview", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    await TimelinePage(props());

    expect(redirect).toHaveBeenCalledWith("/preview");
  });

  it("sends a signed-in user who hasn't finished onboarding to /onboarding", async () => {
    getSession.mockResolvedValue({
      kind: "signed-in",
      user: { ...USER, onboarding: { completed: false, current_step: 1 } },
    });

    await TimelinePage(props());

    expect(redirect).toHaveBeenCalledWith("/onboarding");
  });

  it("does not redirect when the API is unreachable, because a blip is not a logout", async () => {
    readTimeline.mockResolvedValue({ kind: "unavailable" });

    render(await TimelinePage(props()));

    expect(redirect).not.toHaveBeenCalled();
    expect(screen.getByText("Couldn't reach Timeline. Try again.")).toBeInTheDocument();
  });
});

describe("the week in the URL", () => {
  it("sends the week it was given to the read", async () => {
    await TimelinePage(props({ week: MONDAY }));

    expect(readTimeline).toHaveBeenCalledWith(MONDAY);
  });

  it("asks for no particular week when the URL names none", async () => {
    await TimelinePage(props());

    expect(readTimeline).toHaveBeenCalledWith(null);
  });

  it("does not forward a malformed week, because guessing would be a lie", async () => {
    await TimelinePage(props({ week: "not-a-date" }));

    expect(readTimeline).toHaveBeenCalledWith(null);
  });

  it("keeps the previous and next week in the URL", async () => {
    render(await TimelinePage(props({ week: MONDAY })));

    const nav = screen.getByRole("navigation", { name: "Week navigator" });
    expect(within(nav).getByLabelText("Previous week")).toHaveAttribute(
      "href",
      `/timeline?week=${addDays(MONDAY, -7)}`,
    );
    expect(within(nav).getByLabelText("Next week")).toHaveAttribute(
      "href",
      `/timeline?week=${addDays(MONDAY, 7)}`,
    );
  });
});

describe("the header", () => {
  it("names the week's range, the zone, and that the view is read-only", async () => {
    render(await TimelinePage(props()));

    expect(screen.getByRole("heading", { level: 1, name: "This week" })).toBeInTheDocument();
    // The range, the zone and the read-only note are one line — one `<p>`.
    const subtitle = screen.getByText(/Read-only/);
    expect(subtitle).toHaveTextContent(/America\/New_York/);
    expect(subtitle).toHaveTextContent(/Read-only/);
  });
});

/**
 * The mobile day's section.
 *
 * **Both layouts are in the DOM** — the page draws the seven-column grid and the
 * one-day stack, and the CSS picks one — so a day carries its `aria-label` twice.
 * The mobile one is the `<section>` that is not inside the grid.
 */
function mobileDay(date: string): HTMLElement {
  const section = screen
    .getAllByLabelText(date)
    .find((element) => element.tagName === "SECTION" && element.className.includes("md:hidden"));
  if (!section) throw new Error(`no mobile section for ${date}`);
  return section;
}

describe("the desktop grid", () => {
  it("draws seven columns in the server's order", async () => {
    render(await TimelinePage(props()));

    const grid = screen.getByLabelText("Week grid");
    const columns = within(grid).getAllByRole("region");
    expect(columns.map((column) => column.getAttribute("aria-label"))).toEqual(DAYS);
  });

  it("marks today's column with aria-current, not with colour alone", async () => {
    render(await TimelinePage(props()));

    const grid = screen.getByLabelText("Week grid");
    const marked = grid.querySelectorAll('[aria-current="date"]');
    expect(marked).toHaveLength(1);
    expect(marked[0]?.getAttribute("aria-label")).toBe(TODAY);
  });

  it("says 'Quiet day.' in a day with no events", async () => {
    render(await TimelinePage(props()));

    const grid = screen.getByLabelText("Week grid");
    // Six of the seven days are empty; the first carries a block.
    expect(within(grid).getAllByText("Quiet day.").length).toBe(6);
  });
});

describe("the quiet week", () => {
  it("replaces the grid with the quiet line and one link to the digest", async () => {
    readTimeline.mockResolvedValue({ kind: "week", week: emptyWeek() });

    render(await TimelinePage(props()));

    expect(screen.queryByLabelText("Week grid")).toBeNull();
    expect(
      screen.getByText("Your week is quiet. Pulse Digest is the place to discover."),
    ).toBeInTheDocument();
    const links = screen
      .getAllByRole("link")
      .filter((link) => link.textContent === "Open Pulse Digest");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/");
  });
});

describe("the mobile day", () => {
  it("shows the day the URL names", async () => {
    render(await TimelinePage(props({ week: MONDAY, day: DAYS[4] as string })));

    expect(mobileDay(DAYS[4] as string)).toBeInTheDocument();
  });

  it("falls back to today when the URL names no day", async () => {
    render(await TimelinePage(props({ week: MONDAY })));

    expect(mobileDay(TODAY)).toBeInTheDocument();
  });

  it("does not roll the last day into the next week", async () => {
    render(await TimelinePage(props({ week: MONDAY, day: SUNDAY })));

    const nav = screen.getByRole("navigation", { name: "Day navigator" });
    expect(within(nav).getByLabelText("Previous day")).toHaveAttribute(
      "href",
      `/timeline?week=${MONDAY}&day=${DAYS[5]}`,
    );
    // The forward arrow at the week's edge is inert — there is no day the server did
    // not send.
    expect(within(nav).queryByLabelText("Next day")).toBeNull();
    expect(nav.querySelector('[aria-disabled="true"]')).not.toBeNull();
  });

  it("does not roll the first day back into the previous week", async () => {
    render(await TimelinePage(props({ week: MONDAY, day: MONDAY })));

    const nav = screen.getByRole("navigation", { name: "Day navigator" });
    expect(within(nav).queryByLabelText("Previous day")).toBeNull();
    expect(within(nav).getByLabelText("Next day")).toHaveAttribute(
      "href",
      `/timeline?week=${MONDAY}&day=${DAYS[1]}`,
    );
  });
});

describe("the failure state", () => {
  it("says it could not reach the Timeline and offers a retry", async () => {
    readTimeline.mockResolvedValue({ kind: "unavailable" });

    render(await TimelinePage(props()));

    expect(screen.getByText("Couldn't reach Timeline. Try again.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /try again/i })).toHaveAttribute("href", "/timeline");
  });

  it("keeps the week in the retry link", async () => {
    readTimeline.mockResolvedValue({ kind: "unavailable" });

    render(await TimelinePage(props({ week: MONDAY })));

    expect(screen.getByRole("link", { name: /try again/i })).toHaveAttribute(
      "href",
      `/timeline?week=${MONDAY}`,
    );
  });
});

/**
 * **Which zone decides what day it is.**
 *
 * The page is a server component, so anything it reads from the environment is read on
 * the *server* — UTC on a deployed box. The week, though, was cut in the reader's own
 * zone and the server named that zone in the response. These two pin that the page
 * reads today in the named zone: the clock is frozen at an instant where the server's
 * date and the reader's date are two different days, in both directions, and the
 * highlighted column has to follow the reader.
 */
describe("the zone today is read in", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** The column the grid marked `aria-current="date"`. */
  function markedColumn(): string | null | undefined {
    const grid = screen.getByLabelText("Week grid");
    const marked = grid.querySelectorAll('[aria-current="date"]');
    expect(marked).toHaveLength(1);
    return marked[0]?.getAttribute("aria-label");
  }

  it("marks the reader's day when the reader is a day ahead of UTC", async () => {
    // 2026-11-18 20:00 UTC is already Thursday the 19th in Dhaka (UTC+6).
    vi.setSystemTime(new Date("2026-11-18T20:00:00Z"));
    const days = Array.from({ length: 7 }, (_, index) => addDays("2026-11-16", index));
    readTimeline.mockResolvedValue({
      kind: "week",
      week: {
        days: days.map((date) => ({ blocks: [block()], date })),
        timezone: "Asia/Dhaka",
        week_end: days[6],
        week_start: days[0],
      },
    });

    render(await TimelinePage(props({ week: days[0] as string })));

    expect(markedColumn()).toBe("2026-11-19");
  });

  it("marks the reader's day when the reader is a day behind UTC", async () => {
    // 2026-11-19 02:00 UTC is still Wednesday the 18th in New York (UTC-5).
    vi.setSystemTime(new Date("2026-11-19T02:00:00Z"));
    const days = Array.from({ length: 7 }, (_, index) => addDays("2026-11-16", index));
    readTimeline.mockResolvedValue({
      kind: "week",
      week: {
        days: days.map((date) => ({ blocks: [block()], date })),
        timezone: "America/New_York",
        week_end: days[6],
        week_start: days[0],
      },
    });

    render(await TimelinePage(props({ week: days[0] as string })));

    expect(markedColumn()).toBe("2026-11-18");
  });

  it("points 'Today' at the reader's own week, not the renderer's", async () => {
    // 2026-11-22 20:00 UTC is Monday the 23rd in Dhaka — a different week, not just a
    // different day. The "Today" link has to name the reader's Monday.
    vi.setSystemTime(new Date("2026-11-22T20:00:00Z"));
    const days = Array.from({ length: 7 }, (_, index) => addDays("2026-11-16", index));
    readTimeline.mockResolvedValue({
      kind: "week",
      week: {
        days: days.map((date) => ({ blocks: [block()], date })),
        timezone: "Asia/Dhaka",
        week_end: days[6],
        week_start: days[0],
      },
    });

    render(await TimelinePage(props({ week: days[0] as string })));

    const nav = screen.getByRole("navigation", { name: "Week navigator" });
    expect(within(nav).getByLabelText("This week")).toHaveAttribute(
      "href",
      "/timeline?week=2026-11-23",
    );
  });
});
