import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CardSkeletons } from "@/components/preview/card-skeleton";

describe("CardSkeletons", () => {
  it("shows three, parallel to the digest's loading state", () => {
    const { container } = render(<CardSkeletons />);

    expect(container.querySelectorAll("[aria-hidden='true']")).toHaveLength(3);
  });

  it("announces that something is loading, without describing the placeholders", () => {
    render(<CardSkeletons />);

    expect(screen.getByRole("status", { name: "Loading the preview" })).toBeInTheDocument();
  });

  it("uses no spinner and no animation class", () => {
    // "No spinners, anywhere" (EXPERIENCE.md), and `styles/motion.test.ts` fails the
    // suite on any animation other than the one `.fade-in` transition.
    const { container } = render(<CardSkeletons />);

    expect(container.innerHTML).not.toMatch(/animate-|spin/);
  });
});
