import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AddEventButton } from "@/components/add-event-button";

/**
 * The **Add** nav affordance (EXPERIENCE.md `Component.BottomTab` / `Component.Sidenav.App`).
 *
 * The spine is explicit: the Add slot **opens `Sheet.PersonalEventCreate` in place**.
 * It does not route to an `/events/new` page — so this button opens a sheet and the
 * frontend has no `/add` route.
 */

const POST = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
    PATCH: vi.fn(),
  },
}));

describe("AddEventButton", () => {
  it("is a dialog-triggering control, not a link", () => {
    render(<AddEventButton />);

    const add = screen.getByRole("button", { name: "Add personal event" });
    expect(add).toHaveAttribute("aria-haspopup", "dialog");
    expect(add.tagName).toBe("BUTTON");
  });

  it("does not carry the terracotta fill", () => {
    // The spine reserves the terracotta fill for actions inside a decision moment; on a
    // tap-anytime nav control it would burn the accent.
    render(<AddEventButton />);

    expect(screen.getByRole("button", { name: "Add personal event" })).not.toHaveClass(
      "bg-accent-terracotta",
    );
  });

  it("opens the create sheet when tapped", () => {
    render(<AddEventButton />);

    fireEvent.click(screen.getByRole("button", { name: "Add personal event" }));

    expect(screen.getByRole("dialog", { name: "Add personal event" })).toBeInTheDocument();
  });

  it("closes the create sheet again", () => {
    render(<AddEventButton />);

    fireEvent.click(screen.getByRole("button", { name: "Add personal event" }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByRole("dialog", { name: "Add personal event" })).not.toBeInTheDocument();
  });
});
