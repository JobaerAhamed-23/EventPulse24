/**
 * The Timeline block's revealed place (FR-32, `EXPERIENCE.md` §13).
 *
 * §13's density table says a desktop event-block **adds** location on hover or focus.
 * Three things are worth pinning, and none of them is "the CSS class is present":
 *
 * 1. **The place is in the accessible name.** `aria-label` overrides inner text, so a
 *    screen-reader user would otherwise never hear the revealed line — and "reveal on
 *    hover" means nothing to a reader who cannot hover.
 * 2. **Nothing is removed.** §13's locked anti-pattern is that adaptive density must not
 *    hide a trust signal, so the name, the time, the category label and the conflict
 *    indicator survive untouched.
 * 3. **Nothing is rendered when there is nothing to show**, so a block with no place
 *    holds open no gap.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TimelineBlockView } from "@/components/timeline/timeline-block";
import type { TimelineBlock } from "@/lib/timeline-read";

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

const PUBLIC_ID = "55555555-5555-5555-5555-555555555555";

function block(overrides: Partial<TimelineBlock> = {}): TimelineBlock {
  return {
    conflict: false,
    end_time_utc: null,
    id: PUBLIC_ID,
    kind: "public",
    name: "Hackathon",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-11-02T14:00:00Z",
    place: "Barbican",
    ...overrides,
  };
}

describe("the place the server sent", () => {
  it("is rendered in the block", () => {
    render(<TimelineBlockView block={block()} />);

    expect(screen.getByText("Barbican")).toBeInTheDocument();
  });

  it("is part of the accessible name, so a screen reader gets it without hovering", () => {
    render(<TimelineBlockView block={block()} />);

    // `aria-label` overrides inner text: if the place were not named here, the revealed
    // line would be invisible to assistive technology entirely.
    const link = screen.getByRole("link");
    expect(link.getAttribute("aria-label")).toContain("Barbican");
    expect(link.getAttribute("aria-label")).toContain("Hackathon");
  });

  it("renders nothing when the server sent none", () => {
    render(<TimelineBlockView block={block({ place: null })} />);

    expect(screen.queryByText("Barbican")).toBeNull();
    // And the name is still the first thing in the block — no empty element in between.
    expect(screen.getByRole("link").getAttribute("aria-label")).toContain("Hackathon");
  });

  it("renders nothing for a personal block with no location", () => {
    const onEditPersonal = vi.fn();
    render(
      <TimelineBlockView
        block={block({ kind: "personal", name: "Dentist", place: null })}
        onEditPersonal={onEditPersonal}
      />,
    );

    const button = screen.getByRole("button");
    const label = button.getAttribute("aria-label") ?? "";
    // The name, its time and its kind — and no place segment, because there is none.
    expect(label).toContain("Dentist");
    expect(label).toContain("Personal");
    expect(label).not.toContain("Blue Bottle");
    expect(label).not.toContain("Barbican");
  });

  it("carries a personal block's own location", () => {
    render(
      <TimelineBlockView
        block={block({ kind: "personal", name: "Coffee", place: "Blue Bottle" })}
        onEditPersonal={vi.fn()}
      />,
    );

    expect(screen.getByText("Blue Bottle")).toBeInTheDocument();
    expect(screen.getByRole("button").getAttribute("aria-label")).toContain("Blue Bottle");
  });
});

describe("the reveal adds and never removes", () => {
  it("keeps the name, the category label and the conflict indicator", () => {
    render(<TimelineBlockView block={block({ conflict: true })} />);

    const link = screen.getByRole("link");
    // Everything the idle block showed is still here — §13's locked anti-pattern is that
    // adaptive density must not hide a trust signal.
    expect(within(link).getByText("Hackathon")).toBeInTheDocument();
    expect(within(link).getByText("Public event")).toBeInTheDocument();
    expect(within(link).getByRole("img", { name: "Schedule conflict" })).toBeInTheDocument();
    expect(within(link).getByText("Barbican")).toBeInTheDocument();
  });

  it("reveals on focus as well as on hover", () => {
    render(<TimelineBlockView block={block()} />);

    // The pairing is what matters: a hover-only reveal is a detail a keyboard user can
    // never reach. Both utilities must be present on the same element.
    const place = screen.getByText("Barbican");
    expect(place.className).toContain("group-hover:block");
    expect(place.className).toContain("group-focus-within:block");
  });

  it("hangs the reveal off the block, not off itself", () => {
    render(<TimelineBlockView block={block()} />);

    // A `<span>` is not focusable, so without `group` on the block the reveal could
    // never match either state.
    expect(screen.getByRole("link").className).toContain("group");
  });
});
