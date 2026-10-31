import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TimelineSkeleton } from "@/components/timeline/timeline-states";

/**
 * The Timeline's skeleton.
 *
 * **The skeleton is the week's shape, not its content.** Seven columns, each a stack
 * of rectangles — and **no day labels**. A skeleton that prints "Mon" and "Tue" is
 * half a rendering, and a half-rendering that then changes is worse than an empty
 * frame: the user reads the label, then watches it move.
 */
afterEach(() => {
  cleanup();
});

describe("the skeleton", () => {
  it("draws seven columns", () => {
    const { container } = render(<TimelineSkeleton />);

    const grid = container.firstElementChild;
    expect(grid?.children).toHaveLength(7);
  });

  it("draws no day labels", () => {
    render(<TimelineSkeleton />);

    expect(screen.queryByText("Mon")).toBeNull();
    expect(screen.queryByText("Tue")).toBeNull();
    expect(screen.queryByText("Sunday")).toBeNull();
  });

  it("is hidden from the screen reader, because it says nothing", () => {
    const { container } = render(<TimelineSkeleton />);

    expect(container.firstElementChild?.getAttribute("aria-hidden")).toBe("true");
  });
});
