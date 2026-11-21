import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DayNavigator, WeekNavigator } from "@/components/timeline/timeline-navigator";

/**
 * The Timeline's navigators (FR-32, `Surface.Timeline`).
 *
 * **Both navigators are links, and the week is in the URL.** So every assertion here
 * is about an `href`: a button that moved the week in place would leave the address
 * bar describing the old one, and a shared link would open a week the reader did not
 * choose.
 *
 * **The "Today" pill marks a day, not a week.** The mobile navigator is handed today's
 * date and the day it is showing; the pill is on when those are the same day. It was
 * once handed the current week's *Monday* and looked that up in the week's days, which
 * put the pill under Monday every day of the week — on the current week it was always
 * there, and on any other week it was always absent, so neither state ever looked
 * obviously wrong. The two "pill" tests below are that bug, from both sides.
 */

/** A Mon–Sun week: 2026-11-16 … 2026-11-22. */
const DAYS = [
  "2026-11-16",
  "2026-11-17",
  "2026-11-18",
  "2026-11-19",
  "2026-11-20",
  "2026-11-21",
  "2026-11-22",
];
const MONDAY = DAYS[0] as string;
const SATURDAY = DAYS[5] as string;
const SUNDAY = DAYS[6] as string;

afterEach(() => {
  cleanup();
});

describe("the week navigator", () => {
  it("steps a week back and a week forward from the week it is shown", () => {
    render(<WeekNavigator weekStart={MONDAY} weekEnd={SUNDAY} todayStart={MONDAY} />);

    const nav = screen.getByRole("navigation", { name: "Week navigator" });
    expect(within(nav).getByLabelText("Previous week")).toHaveAttribute(
      "href",
      "/timeline?week=2026-11-09",
    );
    expect(within(nav).getByLabelText("Next week")).toHaveAttribute(
      "href",
      "/timeline?week=2026-11-23",
    );
  });

  it("points 'Today' at the current week, which is not always the shown one", () => {
    render(<WeekNavigator weekStart="2026-12-07" weekEnd="2026-12-13" todayStart={MONDAY} />);

    const nav = screen.getByRole("navigation", { name: "Week navigator" });
    expect(within(nav).getByLabelText("This week")).toHaveAttribute(
      "href",
      `/timeline?week=${MONDAY}`,
    );
  });

  it("names both months when the week crosses one", () => {
    render(<WeekNavigator weekStart="2026-09-28" weekEnd="2026-10-04" todayStart={MONDAY} />);

    expect(screen.getByText("Sep 28 – Oct 4")).toBeInTheDocument();
  });
});

describe("the day navigator", () => {
  it("shows the 'Today' pill on the day that is today", () => {
    render(<DayNavigator weekStart={MONDAY} day={SATURDAY} days={DAYS} today={SATURDAY} />);

    const nav = screen.getByRole("navigation", { name: "Day navigator" });
    expect(within(nav).getByText("Today")).toBeInTheDocument();
  });

  it("does not show it on another day of the same week", () => {
    render(<DayNavigator weekStart={MONDAY} day={MONDAY} days={DAYS} today={SATURDAY} />);

    const nav = screen.getByRole("navigation", { name: "Day navigator" });
    expect(within(nav).queryByText("Today")).toBeNull();
  });

  it("does not show it on a week that does not contain today", () => {
    render(
      <DayNavigator
        weekStart="2026-12-07"
        day="2026-12-09"
        days={["2026-12-07", "2026-12-08", "2026-12-09"]}
        today={SATURDAY}
      />,
    );

    const nav = screen.getByRole("navigation", { name: "Day navigator" });
    expect(within(nav).queryByText("Today")).toBeNull();
  });

  it("names the day it is showing", () => {
    render(<DayNavigator weekStart={MONDAY} day={SATURDAY} days={DAYS} today={SATURDAY} />);

    expect(screen.getByText("Saturday")).toBeInTheDocument();
    expect(screen.getByText("Nov 21")).toBeInTheDocument();
  });

  it("steps a day back and a day forward inside the week", () => {
    render(
      <DayNavigator weekStart={MONDAY} day={DAYS[3] as string} days={DAYS} today={SATURDAY} />,
    );

    const nav = screen.getByRole("navigation", { name: "Day navigator" });
    expect(within(nav).getByLabelText("Previous day")).toHaveAttribute(
      "href",
      `/timeline?week=${MONDAY}&day=2026-11-18`,
    );
    expect(within(nav).getByLabelText("Next day")).toHaveAttribute(
      "href",
      `/timeline?week=${MONDAY}&day=2026-11-20`,
    );
  });

  it("leaves the arrow at the week's edge inert rather than leaving the week", () => {
    render(<DayNavigator weekStart={MONDAY} day={SUNDAY} days={DAYS} today={SATURDAY} />);

    const nav = screen.getByRole("navigation", { name: "Day navigator" });
    expect(within(nav).queryByLabelText("Next day")).toBeNull();
    expect(nav.querySelector('[aria-disabled="true"]')).not.toBeNull();
  });
});
