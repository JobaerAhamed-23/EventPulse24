import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceTrustLegend } from "@/components/settings/source-trust-legend";

/**
 * The **reliability legend** (FR-16).
 *
 * **What these tests hold.**
 *
 * 1. **All three readings are on the screen.** The mockup ships them
 *    (`mockups/settings-sources-desktop.html:224-227`), and a legend missing one of them
 *    leaves a band uninterpretable.
 * 2. **The dots are the reading's own.** Each item draws the number of filled dots its
 *    reading names — 5 on for "trusted", 3 on for "ok", 1 on for "low coverage" — so the
 *    legend teaches the same vocabulary the rows use.
 * 3. **The dots are decorative and the words carry the meaning.** A screen reader reads
 *    "5 = trusted" as text; it does not hear fifteen anonymous circles.
 * 4. **The dots are ink, not terracotta.** The terracotta belongs to the Confidence
 *    Pulse, and borrowing it here would make two different things look like one.
 */
describe("SourceTrustLegend", () => {
  it("shows every reading the mockup names", () => {
    render(<SourceTrustLegend />);

    expect(screen.getByText("5 = trusted")).toBeDefined();
    expect(screen.getByText("3 = ok")).toBeDefined();
    expect(screen.getByText("1 = low coverage")).toBeDefined();
  });

  it("is labelled so it reads as a legend", () => {
    render(<SourceTrustLegend />);

    expect(screen.getByRole("list", { name: "Reliability legend" })).toBeDefined();
  });

  it("draws each reading's own number of filled dots", () => {
    render(<SourceTrustLegend />);

    const filled = (label: string) => {
      const item = screen.getByText(label).closest("li");
      if (!item) throw new Error(`expected an item for ${label}`);
      return item.querySelectorAll(".bg-ink-primary").length;
    };

    expect(filled("5 = trusted")).toBe(5);
    expect(filled("3 = ok")).toBe(3);
    expect(filled("1 = low coverage")).toBe(1);
  });

  it("draws five dots for every reading", () => {
    const { container } = render(<SourceTrustLegend />);

    // Each reading is a five-dot row, so a band is always read against the same scale.
    expect(container.querySelectorAll("[aria-hidden='true']")).toHaveLength(3);
    expect(
      container.querySelectorAll(".bg-ink-faint").length +
        container.querySelectorAll(".bg-ink-primary").length,
    ).toBe(15);
  });

  it("hides the dots from assistive technology", () => {
    const { container } = render(<SourceTrustLegend />);

    for (const row of container.querySelectorAll("[aria-hidden='true']")) {
      expect(row.getAttribute("aria-hidden")).toBe("true");
    }
  });

  it("does not use the terracotta confidence pulse", () => {
    const { container } = render(<SourceTrustLegend />);

    // The Confidence Pulse's colour is reserved for a card's own confidence.
    expect(container.querySelector(".bg-signal-warm")).toBeNull();
    expect(container.querySelector(".text-signal-warm")).toBeNull();
  });
});
