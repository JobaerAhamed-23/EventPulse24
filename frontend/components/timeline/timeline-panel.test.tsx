import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { blockTime } from "@/components/timeline/timeline-block";
import { TimelinePanel } from "@/components/timeline/timeline-panel";
import type { TimelineBlock } from "@/lib/timeline-read";

/**
 * The Timeline's blocks — the thing a reader actually looks at.
 *
 * **Colour is never the sole carrier of meaning (WCAG 1.4.1).** Every block carries a
 * coloured stripe *and* a visible text label, so the two kinds tellable apart without
 * colour vision. These tests pin the pairing, because a stripe without its label is a
 * rule that fails silently and nobody notices until somebody cannot use the screen.
 *
 * **The server decides, the client draws.** The conflict indicator is already decided
 * in the payload; the block shows it or does not, and decides nothing itself.
 */

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/timeline",
}));

const PERSONAL_ID = "44444444-4444-4444-4444-444444444444";
const PUBLIC_ID = "55555555-5555-5555-5555-555555555555";

function block(overrides: Partial<TimelineBlock> = {}): TimelineBlock {
  return {
    conflict: false,
    end_time_utc: null,
    id: PERSONAL_ID,
    kind: "personal",
    name: "Dentist",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-11-02T14:00:00Z",
    ...overrides,
  };
}

/** The panel needs `next/link` to resolve a `<Link>` without a router. */
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

beforeEach(() => {
  refresh.mockReset();
});

afterEach(() => {
  cleanup();
});

/**
 * The desktop grid.
 *
 * **Both layouts are in the DOM** — the seven-column grid and the one-day stack — and
 * the CSS picks one. So a block is drawn twice, and these tests query the grid, where
 * there is exactly one copy of each.
 */
function grid(): HTMLElement {
  return screen.getByLabelText("Week grid");
}

describe("the block's category", () => {
  it("pairs a personal block's stripe with the word 'Personal'", () => {
    render(
      <TimelinePanel
        days={[{ blocks: [block()], date: "2026-11-02" }]}
        today="2026-11-02"
        mobileDay="2026-11-02"
      />,
    );

    const personal = within(grid()).getByRole("button", { name: /Dentist/ });
    expect(within(personal).getByText("Personal")).toBeInTheDocument();
    // The stripe is the second signal, and it is hidden from the screen reader —
    // the word beside it is what carries the meaning.
    expect(personal.querySelector('[aria-hidden="true"]')).not.toBeNull();
  });

  it("pairs a public block's stripe with the words 'Public event'", () => {
    render(
      <TimelinePanel
        days={[
          {
            blocks: [block({ id: PUBLIC_ID, kind: "public", name: "Concert" })],
            date: "2026-11-02",
          },
        ]}
        today="2026-11-02"
        mobileDay="2026-11-02"
      />,
    );

    const publicBlock = within(grid()).getByRole("link", { name: /Concert/ });
    expect(within(publicBlock).getByText("Public event")).toBeInTheDocument();
  });
});

describe("the conflict indicator", () => {
  it("appears when the API says the block is in conflict", () => {
    render(
      <TimelinePanel
        days={[{ blocks: [block({ conflict: true })], date: "2026-11-02" }]}
        today="2026-11-02"
        mobileDay="2026-11-02"
      />,
    );

    expect(screen.getAllByLabelText("Schedule conflict").length).toBeGreaterThan(0);
  });

  it("does not appear when the API says it is not", () => {
    render(
      <TimelinePanel
        days={[{ blocks: [block()], date: "2026-11-02" }]}
        today="2026-11-02"
        mobileDay="2026-11-02"
      />,
    );

    expect(screen.queryByLabelText("Schedule conflict")).toBeNull();
  });
});

describe("the block's accessible name", () => {
  it("is the name, the time, and the kind", () => {
    render(
      <TimelinePanel
        days={[{ blocks: [block()], date: "2026-11-02" }]}
        today="2026-11-02"
        mobileDay="2026-11-02"
      />,
    );

    const label = within(grid())
      .getByRole("button", { name: /Dentist/ })
      .getAttribute("aria-label");
    expect(label).toContain("Dentist");
    expect(label).toContain("Personal");
    expect(label).toMatch(/\d{1,2}:\d{2}/);
  });

  it("says 'Event no longer available' for a block with no name", () => {
    render(
      <TimelinePanel
        days={[{ blocks: [block({ name: null })], date: "2026-11-02" }]}
        today="2026-11-02"
        mobileDay="2026-11-02"
      />,
    );

    expect(screen.getAllByText("Event no longer available").length).toBeGreaterThan(0);
  });
});

describe("what a block does", () => {
  it("sends a public block to the event's detail page", () => {
    render(
      <TimelinePanel
        days={[
          {
            blocks: [block({ id: PUBLIC_ID, kind: "public", name: "Concert" })],
            date: "2026-11-02",
          },
        ]}
        today="2026-11-02"
        mobileDay="2026-11-02"
      />,
    );

    expect(within(grid()).getByRole("link", { name: /Concert/ })).toHaveAttribute(
      "href",
      `/events/${PUBLIC_ID}`,
    );
  });

  it("opens the edit sheet for a personal block", () => {
    render(
      <TimelinePanel
        days={[{ blocks: [block()], date: "2026-11-02" }]}
        today="2026-11-02"
        mobileDay="2026-11-02"
      />,
    );

    // The sheet is a native `<dialog>` — closed it takes no space, and it opens when
    // the block is clicked.
    const dialog = document.querySelector("dialog");
    expect(dialog).not.toBeNull();
    expect(dialog?.open).toBe(false);

    fireEvent.click(screen.getAllByRole("button", { name: /Dentist/ })[0] as HTMLElement);

    expect(document.querySelector("dialog")?.open).toBe(true);
  });
});

describe("the block's time line", () => {
  it("prints the start alone for an open-ended event", () => {
    const time = blockTime(block());

    expect(time).toContain("9:00 AM");
    expect(time).not.toContain("–");
  });

  it("prints the range, with the zone named once", () => {
    const time = blockTime(
      block({
        start_time_utc: "2026-11-02T14:00:00Z",
        end_time_utc: "2026-11-02T15:30:00Z",
      }),
    );

    expect(time).toBe("Mon, Nov 2 · 9:00 AM – 10:30 AM EST");
    // The zone's short name appears once, at the end.
    const zoneOccurrences = time?.match(/EST/g)?.length ?? 0;
    expect(zoneOccurrences).toBe(1);
  });

  it("renders the time in the event's own zone, not the viewer's", () => {
    // 2026-11-02T02:00:00Z is 21:00 on November 1 in New York (EST, UTC-5).
    const time = blockTime(
      block({
        start_time_utc: "2026-11-02T02:00:00Z",
        start_time_tz: "America/New_York",
      }),
    );

    expect(time).toBe("Sun, Nov 1 · 9:00 PM EST");
  });

  it("does not build a pattern from the zone's name", () => {
    // A zone's short name is a rendered string. If the range were built by stripping
    // the zone with a regex, a name carrying a metacharacter would either throw or
    // strip the wrong text. The zone is counted off the end instead.
    const time = blockTime(
      block({
        start_time_utc: "2026-11-02T14:00:00Z",
        end_time_utc: "2026-11-02T15:30:00Z",
      }),
    );

    expect(time).not.toBeNull();
    expect(time).not.toContain("undefined");
    expect(time).not.toContain("NaN");
  });
});
