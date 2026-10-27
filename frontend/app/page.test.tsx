import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "@/app/page";

describe("HomePage", () => {
  it("renders the brand heading inside the fade-in container", () => {
    render(<HomePage />);

    const heading = screen.getByRole("heading", { level: 1, name: "EventPulse24" });
    expect(heading).toBeInTheDocument();
    expect(heading.closest("main")).toHaveClass("fade-in");
  });
});
