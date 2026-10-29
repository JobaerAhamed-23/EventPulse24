import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import HomePage from "@/app/page";

// The personal-events section is an async server component that reads through the API
// client. The page's own test is about the page's chrome, so the read is stubbed out.
vi.mock("@/components/personal-events-section", () => ({
  PersonalEventsSection: () => <p>Personal events section</p>,
}));

describe("HomePage", () => {
  it("renders the brand heading inside the fade-in container", () => {
    render(<HomePage />);

    const heading = screen.getByRole("heading", { level: 1, name: "EventPulse24" });
    expect(heading).toBeInTheDocument();
    expect(heading.closest("main")).toHaveClass("fade-in");
  });

  it("offers the Add affordance, which opens the create sheet in place", () => {
    render(<HomePage />);

    const add = screen.getByRole("button", { name: "Add personal event" });
    expect(add).toBeInTheDocument();
    expect(add).toHaveAttribute("aria-haspopup", "dialog");
  });

  it("hosts the personal-events section", () => {
    render(<HomePage />);

    expect(screen.getByText("Personal events section")).toBeInTheDocument();
  });

  it("is rendered per request, so the build never reads the user's events", async () => {
    // The page shows the signed-in user's own events, which is per-session state. A
    // statically prerendered page would be wrong for every user, and rendering it at
    // build time would need a live Django. So the route is dynamic.
    const page = await import("@/app/page");

    expect(page.dynamic).toBe("force-dynamic");
  });
});
