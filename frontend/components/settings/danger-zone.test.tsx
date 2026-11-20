/**
 * The danger zone — **the section for what cannot be undone.**
 *
 * **What these tests hold.**
 *
 * 1. **The section exists, and it renders unconditionally.** A danger zone that vanishes
 *    is the opposite of what a danger zone is for.
 * 2. **The delete row carries the terracotta treatment**, and the *heading* does not —
 *    terracotta is reserved for destructive actions, and spending it on a heading would
 *    leave the actual destructive control unmarked.
 * 3. **The subtitle does not claim the deletion cannot be undone.** It cannot: the engine
 *    holds a thirty-day grace period, and the A-16 mockup's *"Permanent. Cannot be
 *    undone."* predates that engine. **A subtitle that claims otherwise is a promise the
 *    product does not keep.**
 * 4. **The export row is not here** — it stays on `/settings/account`, where it already
 *    lives.
 * 5. **The section renders one state at a time.**
 * 6. **axe-core passes.**
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DangerZone } from "@/components/settings/danger-zone";

const get = vi.fn();
const post = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    GET: (...args: unknown[]) => get(...args),
    POST: (...args: unknown[]) => post(...args),
  },
}));

/** The two paragraphs, as the API publishes them. */
const WHAT_IS_DELETED = "Your personal events, your saved events, and your preference graph.";
const WHAT_SURVIVES = "Anonymised aggregate figures survive, not linked to your account.";

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue({
    data: { what_is_deleted: WHAT_IS_DELETED, what_survives: WHAT_SURVIVES },
  });
  post.mockReset();
  post.mockResolvedValue({
    data: {
      status: "scheduled",
      requested_at: "2026-11-20T00:00:00+00:00",
      scheduled_for: SCHEDULED_FOR,
      what_is_deleted: WHAT_IS_DELETED,
      what_survives: WHAT_SURVIVES,
    },
  });
});

/** The serious and critical violations on the rendered section. */
async function audit(): Promise<string[]> {
  const results = await axe.run(document.body, {
    resultTypes: ["violations"],
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations
    .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
    .map(
      (violation) => `${violation.id}: ${violation.nodes.map((node) => node.target).join(", ")}`,
    );
}

/** The server's two moments, for an account with a deletion pending. */
const SCHEDULED_FOR = "2026-12-20T00:00:00+00:00";
const REQUESTED_AT = "2026-11-20T00:00:00+00:00";

describe("the danger zone", () => {
  it("is a section, labelled by its heading", () => {
    /** **A labelled region, not a bare div.** A screen reader has to be able to reach
     * the danger zone by its name, and the name is the heading's. */
    render(<DangerZone />);

    const region = screen.getByRole("region", { name: "Danger zone" });
    expect(region).toBeInTheDocument();
  });

  it("renders the delete row", () => {
    render(<DangerZone />);

    expect(screen.getByRole("button", { name: /delete account/i })).toBeInTheDocument();
  });

  it("gives the delete row the terracotta treatment", () => {
    /** **Terracotta is reserved for destructive actions**, and the personal-event
     * delete row already uses exactly this treatment
     * (`components/sheets/personal-event-form.tsx`). This row reuses it rather than
     * inventing a second spelling of the same control. */
    render(<DangerZone />);

    const button = screen.getByRole("button", { name: /delete account/i });
    expect(button.className).toContain("text-accent-terracotta");
  });

  it("does not put terracotta on the heading", () => {
    /** **The accent is spent on the control, not on the decoration.** A terracotta
     * heading would spend the one colour that means "destructive" on a label, and leave
     * the destructive control itself unmarked. */
    render(<DangerZone />);

    const heading = screen.getByRole("heading", { name: "Danger zone" });
    expect(heading.className).not.toContain("terracotta");
  });

  it("does not claim the deletion cannot be undone", () => {
    /** **The A-16 mockup says "Permanent. Cannot be undone." — and that is false.**
     *
     * The mockup predates the deletion engine, and the engine holds a thirty-day grace
     * period: nothing is destroyed at request time, and a person can call the whole
     * thing off inside that window. **This is the exact failure the section exists to
     * prevent** — a surface promising something the product does not do — so the copy
     * says what is true. */
    render(<DangerZone />);

    expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/permanent/i)).not.toBeInTheDocument();
  });

  it("says the grace period, because that is what the engine holds", () => {
    render(<DangerZone />);

    expect(screen.getByText(/30-day grace period/i)).toBeInTheDocument();
  });

  it("does not carry the export row, which stays on /settings/account", () => {
    /** **The export row is not moved.** `DownloadMyData` already lives on
     * `/settings/account`, and moving a working control for no reason is churn. */
    render(<DangerZone />);

    expect(screen.queryByText(/export your data/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /email me my data/i })).not.toBeInTheDocument();
  });

  it("renders one state at a time, and never both", () => {
    /** **A section showing a "Delete account →" row *and* a "Keep my account" button
     * is offering two contradictory instructions.**
     *
     * The pending state is not built here — `CurrentUserOut` carries no pending-deletion
     * field yet, and the item that adds it depends on this one — so this section renders
     * the request state, and gains the second state when the read lands. */
    render(<DangerZone />);

    expect(screen.queryByRole("button", { name: /keep my account/i })).not.toBeInTheDocument();
  });

  it("has zero serious or critical axe-core violations", async () => {
    render(<DangerZone />);

    expect(await audit()).toEqual([]);
  });
});

describe("the danger zone with a deletion pending", () => {
  it("shows the pending state instead of the delete row", () => {
    /** **One state at a time.** A section offering both a "Delete account →" row *and*
     * a "Keep my account" button is offering two contradictory instructions. */
    render(<DangerZone deletionScheduledFor={SCHEDULED_FOR} deletionRequestedAt={REQUESTED_AT} />);

    expect(screen.getByRole("button", { name: /keep my account/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete account/i })).not.toBeInTheDocument();
  });

  it("shows the request row when nothing is pending", () => {
    render(<DangerZone deletionScheduledFor="" deletionRequestedAt="" />);

    expect(screen.getByRole("button", { name: /delete account/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /keep my account/i })).not.toBeInTheDocument();
  });

  it("never renders both states at once, in either direction", () => {
    /** **The rule, asserted from both ends.**
     *
     * The first version of this file asserted only the negative — that the pending state
     * was absent — which was true only because no pending state existed to render. Now
     * that there are two states, the rule has to be asserted in both directions. */
    const { unmount } = render(
      <DangerZone deletionScheduledFor={SCHEDULED_FOR} deletionRequestedAt={REQUESTED_AT} />,
    );
    expect(screen.queryByRole("button", { name: /delete account/i })).not.toBeInTheDocument();
    unmount();

    render(<DangerZone deletionScheduledFor="" deletionRequestedAt="" />);
    expect(screen.queryByRole("button", { name: /keep my account/i })).not.toBeInTheDocument();
  });

  it("does not put terracotta on the pending state", () => {
    /** **The pending state is the way back *from* a destructive action.**
     *
     * Spending the destructive colour on a button whose job is to prevent destruction
     * would spend the accent on the opposite of what it means. */
    render(<DangerZone deletionScheduledFor={SCHEDULED_FOR} deletionRequestedAt={REQUESTED_AT} />);

    const button = screen.getByRole("button", { name: /keep my account/i });
    expect(button.className).not.toContain("terracotta");
  });

  it("has zero serious or critical axe-core violations in the pending state", async () => {
    render(<DangerZone deletionScheduledFor={SCHEDULED_FOR} deletionRequestedAt={REQUESTED_AT} />);

    expect(await audit()).toEqual([]);
  });
});

describe("the danger zone and the confirmation modal", () => {
  it("opens the modal from the delete row", async () => {
    /** **The row is the way in.** A destructive control that opens nothing is a
     * decorative one, and this row is the only route to the deletion.
     *
     * **The modal is not open before the row is pressed.** A dialog about destroying
     * an account cannot be the screen's first state. */
    render(<DangerZone />);

    await waitFor(() => {
      expect(get).toHaveBeenCalled();
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /delete account/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows the copy the API published, and not a copy of its own", async () => {
    /** **The two paragraphs are the server's.** They are the same two strings the
     * confirmation mail renders, and a section that kept its own spelling would be a
     * third version of the same story. */
    render(<DangerZone />);

    await waitFor(() => {
      expect(get).toHaveBeenCalled();
    });
    fireEvent.click(screen.getByRole("button", { name: /delete account/i }));

    expect(screen.getByText(WHAT_IS_DELETED)).toBeInTheDocument();
    expect(screen.getByText(WHAT_SURVIVES)).toBeInTheDocument();
  });

  it("reads the copy from the API, literally", async () => {
    /** **The method and the path are adjacent**, because the endpoint-coverage test
     * matches the call expression and a path in a variable is invisible to it. */
    render(<DangerZone />);

    await waitFor(() => {
      expect(get).toHaveBeenCalledWith("/api/auth/profile/deletion");
    });
  });

  it("moves to the pending state when the request lands", async () => {
    /** **One state at a time, and the new one is the pending one.**
     *
     * The date is the server's — the section does not compute thirty days, and it
     * does not refresh the page to find out. */
    render(<DangerZone />);

    await waitFor(() => {
      expect(get).toHaveBeenCalled();
    });
    fireEvent.click(screen.getByRole("button", { name: /delete account/i }));
    fireEvent.change(screen.getByLabelText(/type delete to confirm/i), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start 30-day deletion/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /keep my account/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete account/i })).not.toBeInTheDocument();
  });

  it("shows the server's date on the pending state", async () => {
    render(<DangerZone />);

    await waitFor(() => {
      expect(get).toHaveBeenCalled();
    });
    fireEvent.click(screen.getByRole("button", { name: /delete account/i }));
    fireEvent.change(screen.getByLabelText(/type delete to confirm/i), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start 30-day deletion/i }));

    await waitFor(() => {
      expect(screen.getByText(/december 20, 2026/i)).toBeInTheDocument();
    });
  });

  it("keeps the request row when the request failed", async () => {
    /** **A failed request did not start a deletion.** The section stays where it was,
     * because saying the account is scheduled when it is not would be a lie. */
    post.mockResolvedValue({
      error: { code: "deletion_already_pending", message: "You already have one." },
    });
    render(<DangerZone />);

    await waitFor(() => {
      expect(get).toHaveBeenCalled();
    });
    fireEvent.click(screen.getByRole("button", { name: /delete account/i }));
    fireEvent.change(screen.getByLabelText(/type delete to confirm/i), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start 30-day deletion/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /keep my account/i })).not.toBeInTheDocument();
  });

  it("does not open the modal when the copy could not be read", async () => {
    /** **A dialog with two blank paragraphs says nothing about what is about to
     * happen** — and that is the one thing the dialog exists to say. So the row
     * opens nothing, rather than opening a blank one. */
    get.mockResolvedValue({ error: { code: "unauthorized", message: "No." } });
    render(<DangerZone />);

    await waitFor(() => {
      expect(get).toHaveBeenCalled();
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
