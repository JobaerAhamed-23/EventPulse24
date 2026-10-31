import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AddEventButton } from "@/components/add-event-button";

/**
 * The **Add** nav affordance (EXPERIENCE.md `Component.BottomTab` / `Component.Sidenav.App`).
 *
 * The spine is explicit: the Add slot **opens `Sheet.PersonalEventCreate` in place**.
 * It does not route to an `/events/new` page — so this button opens a sheet and the
 * frontend has no `/add` route.
 *
 * **And it confirms the add inline.** The digest no longer shows personal events — the
 * Timeline does — so an add from here would look like nothing happened. The notice is a
 * `Text.Meta` line under the button with a link to the week the event landed on.
 */

const POST = vi.fn();

/** The panel refreshes the route after every successful write; the spy says it did. */
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
    PATCH: vi.fn(),
  },
}));

beforeEach(() => {
  POST.mockReset();
  refresh.mockReset();
  POST.mockResolvedValue({ data: { id: "77777777-7777-7777-7777-777777777777" } });
});

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

describe("the inline confirmation", () => {
  /** Fill the form and submit it, which is what a successful add looks like. */
  async function addAnEvent(): Promise<void> {
    fireEvent.click(screen.getByRole("button", { name: "Add personal event" }));
    fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "Dentist" } });
    fireEvent.change(screen.getByLabelText(/^Date/), { target: { value: "2026-11-06" } });
    fireEvent.change(screen.getByLabelText(/Start time/), { target: { value: "19:30" } });
    fireEvent.change(screen.getByLabelText(/Timezone/), {
      target: { value: "America/New_York" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));
    await waitFor(() => expect(POST).toHaveBeenCalled());
  }

  it("says the event was added, near the button", async () => {
    render(<AddEventButton />);

    await addAnEvent();

    await waitFor(() => expect(screen.getByText(/"Dentist" was added\./)).toBeInTheDocument());
  });

  it("links to the week the event landed on", async () => {
    render(<AddEventButton />);

    await addAnEvent();

    const link = await screen.findByRole("link", { name: "See it on your Timeline" });
    // The link names the week by the day the event starts on. The Timeline resolves
    // the week itself, so the day is enough — and the day is read in the event's own
    // zone, which is the day the user will see it on their calendar.
    expect(link).toHaveAttribute("href", expect.stringContaining("/timeline?week="));
    expect(link.getAttribute("href")).toMatch(/^\/timeline\?week=\d{4}-\d{2}-\d{2}$/);
  });

  it("is a live region, so the confirmation is announced", async () => {
    render(<AddEventButton />);

    await addAnEvent();

    const notice = await screen.findByText(/"Dentist" was added\./);
    expect(notice.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
  });

  it("is not terracotta, because a link is not one of the five sanctioned uses", async () => {
    render(<AddEventButton />);

    await addAnEvent();

    const link = await screen.findByRole("link", { name: "See it on your Timeline" });
    expect(link.className).not.toContain("terracotta");
  });

  it("is inline, not a toast and not a modal", async () => {
    render(<AddEventButton />);

    await addAnEvent();

    // The line is in the document beside the button — not in a dialog, and not in a
    // portal that floats over the page.
    const notice = await screen.findByText(/"Dentist" was added\./);
    expect(notice.closest('[role="dialog"]')).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says nothing before an add, so the header is quiet on arrival", () => {
    render(<AddEventButton />);

    expect(screen.queryByRole("link", { name: "See it on your Timeline" })).not.toBeInTheDocument();
    expect(screen.queryByText(/was added/)).not.toBeInTheDocument();
  });

  it("says nothing when the write failed", async () => {
    POST.mockResolvedValue({ error: { status: 500 } });
    render(<AddEventButton />);

    await addAnEvent();

    // A failed write is not an addition, and a link to a week with nothing in it would
    // be a lie about the user's calendar.
    await waitFor(() =>
      expect(screen.getByText("We couldn't save that. Try again.")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("link", { name: "See it on your Timeline" })).not.toBeInTheDocument();
  });

  it("clears the last notice when a new add starts", async () => {
    render(<AddEventButton />);

    await addAnEvent();
    await screen.findByRole("link", { name: "See it on your Timeline" });

    // A line that says "was added" beside a button that opens the sheet again would be
    // a claim about an attempt the user has not made yet.
    fireEvent.click(screen.getByRole("button", { name: "Add personal event" }));

    expect(screen.queryByRole("link", { name: "See it on your Timeline" })).not.toBeInTheDocument();
    expect(screen.queryByText(/was added\./)).not.toBeInTheDocument();
  });
});
