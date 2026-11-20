/**
 * The account-delete confirmation modal — **the moment before the account goes.**
 *
 * **What these tests hold.**
 *
 * 1. **The anatomy is A-16's**, and it is a real dialog: `role="dialog"`,
 *    `aria-modal`, a labelled title, a described body, 480px wide, three paragraphs, a
 *    type-to-confirm input and two footer buttons.
 * 2. **The gate is `=== "DELETE"`, case-sensitively.** A trimmed or case-folded
 *    comparison would *look* strict and would not be — and the gate is the last thing
 *    standing between an accident and a destroyed account.
 * 3. **The focus comes in, and goes back.** A keyboard user who opened the dialog
 *    lands on the input, and closing it puts them back on the row they came from.
 * 4. **The trap holds.** The settings screen behind the dialog is full of interactive
 *    controls, so a Tab that walked out of the dialog would put a keyboard user into
 *    the page behind it.
 * 5. **The request is literal**, so the endpoint-coverage test can see it, and it
 *    answers with the **server's date**.
 * 6. **A failed request keeps the modal open.** A request that failed did not start a
 *    deletion, and a modal that closed on failure would say it had.
 * 7. **No new tokens.**
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccountDeleteModal } from "@/components/settings/account-delete-modal";

const post = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => post(...args),
  },
}));

/** The two paragraphs, as the API publishes them. */
const WHAT_IS_DELETED =
  "Your personal events, your saved events, and your preference graph — the taste we built up about what you like.";
const WHAT_SURVIVES =
  "Anonymised aggregate figures survive — counts like 47 events saved in NYC on Aug 27. They are not linked to your account and cannot be traced back to you.";

/** The server's date. */
const SCHEDULED_FOR = "2026-12-20T00:00:00+00:00";

beforeEach(() => {
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

/** The serious and critical violations on the rendered dialog. */
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

/** The modal, open, with the two paragraphs the API would have published. */
function openModal(overrides: Partial<Parameters<typeof AccountDeleteModal>[0]> = {}) {
  const props = {
    open: true,
    whatIsDeleted: WHAT_IS_DELETED,
    whatSurvives: WHAT_SURVIVES,
    onRequested: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
  render(<AccountDeleteModal {...props} />);
  return props;
}

describe("the confirmation modal", () => {
  it("renders nothing when it is closed", () => {
    /** **A closed modal is not in the document.** Not hidden — absent, so it is not in
     * the tab order of the screen behind it. */
    openModal({ open: false });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is a real modal dialog", () => {
    /** **`role="dialog"` with `aria-modal`.** Not a `div` with a class, and not the
     * house `Sheet` — a native `<dialog>` has no `aria-describedby` slot, and A-16's
     * description is three paragraphs separate from the title. */
    openModal();

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("is labelled by its title and described by its body", () => {
    /** **The title names the dialog, and the body describes it.** A screen reader
     * announces both, and the description is the three paragraphs that say what is
     * about to happen. */
    openModal();

    const dialog = screen.getByRole("dialog");
    const titleId = dialog.getAttribute("aria-labelledby");
    const bodyId = dialog.getAttribute("aria-describedby");
    expect(titleId).toBeTruthy();
    expect(bodyId).toBeTruthy();
    if (!titleId || !bodyId) throw new Error("the dialog names no title and no body");
    expect(document.getElementById(titleId)?.textContent).toBe("Delete your account?");
    expect(document.getElementById(bodyId)).toBeTruthy();
  });

  it("is 480 pixels wide", () => {
    /** **A-16 fixes the width at 480px.** A dialog that grew would push its footer
     * buttons off a narrow screen, and the buttons are the only way out of it. */
    openModal();

    expect(screen.getByRole("dialog").className).toContain("max-w-[480px]");
  });

  it("says what the deletion removes and what it leaves behind", () => {
    /** **The two paragraphs are the API's**, and the modal renders what it was given
     * rather than its own copy of the sentence. */
    openModal();

    expect(screen.getByText(WHAT_IS_DELETED)).toBeInTheDocument();
    expect(screen.getByText(WHAT_SURVIVES)).toBeInTheDocument();
  });

  it("makes the third promise the product can keep", () => {
    /** **"You can cancel anytime during the 30-day grace from this page or from the
     * email we send."**
     *
     * The cancel surface and the mail both ship, so the sentence is true — and it is
     * the reason a person can agree to the deletion at all. */
    openModal();

    expect(screen.getByText(/you can cancel anytime during the 30-day grace/i)).toBeInTheDocument();
  });

  it("has exactly three body paragraphs", () => {
    /** **Three, and not four.**
     *
     * A-16 fixes the anatomy, and a fourth paragraph would be a fourth thing to keep in
     * step with the engine. */
    openModal();

    const bodyId = screen.getByRole("dialog").getAttribute("aria-describedby");
    if (!bodyId) throw new Error("the dialog describes nothing");
    const body = document.getElementById(bodyId);
    expect(body).toBeTruthy();
    expect(body?.querySelectorAll("p")).toHaveLength(3);
  });

  it("has a type-to-confirm input with the label A-16 fixes", () => {
    openModal();

    const input = screen.getByLabelText(/type delete to confirm/i);
    expect(input).toHaveAttribute("type", "text");
    expect(input).toHaveAttribute("autocomplete", "off");
    expect(input).toHaveAttribute("spellcheck", "false");
  });

  it("warns that the match is case-sensitive", () => {
    openModal();

    expect(screen.getByText(/case-sensitive/i)).toBeInTheDocument();
  });

  it("has a cancel button and a start button", () => {
    /** **Cancel is never terracotta** — it is the way out of the dialog, and A-16
     * says so explicitly. The primary is terracotta, and it says "Start", because the
     * engine schedules rather than deletes. */
    openModal();

    const cancel = screen.getByRole("button", { name: "Cancel" });
    const start = screen.getByRole("button", { name: /start 30-day deletion/i });
    expect(cancel.className).not.toContain("terracotta");
    expect(start.className).toContain("bg-accent-terracotta");
  });
});

describe("the confirmation gate", () => {
  it("is closed until the input matches", () => {
    openModal();

    expect(screen.getByRole("button", { name: /start 30-day deletion/i })).toBeDisabled();
  });

  it("opens on the exact word", () => {
    openModal();

    fireEvent.change(screen.getByLabelText(/type delete to confirm/i), {
      target: { value: "DELETE" },
    });

    expect(screen.getByRole("button", { name: /start 30-day deletion/i })).toBeEnabled();
  });

  it("stays closed for the wrong case", () => {
    /** **Case-sensitive, and this is the point of the test.**
     *
     * A case-folded comparison would let `delete` through, and the gate would be a
     * suggestion rather than a gate. */
    openModal();

    fireEvent.change(screen.getByLabelText(/type delete to confirm/i), {
      target: { value: "delete" },
    });

    expect(screen.getByRole("button", { name: /start 30-day deletion/i })).toBeDisabled();
  });

  it("stays closed for a padded word", () => {
    /** **Not trimmed either.** `" DELETE "` *looks* strict and is not — a trimmed
     * comparison would let a stray space through. */
    openModal();

    fireEvent.change(screen.getByLabelText(/type delete to confirm/i), {
      target: { value: " DELETE " },
    });

    expect(screen.getByRole("button", { name: /start 30-day deletion/i })).toBeDisabled();
  });
});

describe("the confirmation modal and the keyboard", () => {
  it("moves the focus to the input when it opens", () => {
    /** **The input, and not the primary button.** The primary is disabled until the
     * input matches, so focusing it would put a keyboard user on a control that does
     * nothing. The input is the first thing a person has to do. */
    openModal();

    expect(screen.getByLabelText(/type delete to confirm/i)).toHaveFocus();
  });

  it("closes on Escape", () => {
    const props = openModal();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(props.onClose).toHaveBeenCalled();
  });

  it("gives the focus back when it closes", async () => {
    /** **The reader goes back to where they were.** A person who opened the dialog and
     * closed it should land on the row they came from, not at the top of the document.
     */
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();

    const { rerender } = render(
      <AccountDeleteModal
        open
        whatIsDeleted={WHAT_IS_DELETED}
        whatSurvives={WHAT_SURVIVES}
        onRequested={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    rerender(
      <AccountDeleteModal
        open={false}
        whatIsDeleted={WHAT_IS_DELETED}
        whatSurvives={WHAT_SURVIVES}
        onRequested={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(trigger).toHaveFocus();
    });
    trigger.remove();
  });

  it("keeps the Tab inside the dialog", () => {
    /** **The trap is the reason this is a modal and not a decoration.**
     *
     * The settings screen behind it is full of interactive controls, so a Tab that
     * walked out of the dialog would put a keyboard user into the page behind it —
     * editing settings they did not come to edit, in a dialog about destroying their
     * account. */
    openModal();

    const dialog = screen.getByRole("dialog");
    const focusable = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    /** **Tab off the back wraps to the front.** */
    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(first).toHaveFocus();

    /** **Shift+Tab off the front wraps to the back.** */
    first.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(last).toHaveFocus();
  });

  it("lets an ordinary Tab pass through the middle of the dialog", () => {
    /** **The trap only holds the edges.** A Tab between two elements is ordinary
     * tabbing, and intercepting it would break the dialog rather than contain it.
     *
     * **The primary is disabled until the input matches**, so the dialog's focusable
     * elements are the input and the cancel button — the middle one is the input
     * itself, with the cancel button behind it and the (disabled) primary in front. */
    openModal();

    const dialog = screen.getByRole("dialog");
    const focusable = Array.from(
      dialog.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled])"),
    );
    /** **The input is first and the cancel button last, and the middle of the dialog
     * is between them.** */
    const first = focusable[0];
    first.focus();

    const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
  });
});

describe("the confirmation request", () => {
  it("calls the endpoint literally", async () => {
    /** **The method and the path are adjacent**, because the endpoint-coverage test
     * matches the call expression and a path in a variable is invisible to it. */
    openModal();

    fireEvent.change(screen.getByLabelText(/type delete to confirm/i), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start 30-day deletion/i }));

    expect(post).toHaveBeenCalledWith("/api/auth/profile/deletion");
  });

  it("tells the container the server's date", async () => {
    /** **The server's date, and the only one.** The container renders the pending
     * state from it — never a duration computed here, and never a hardcoded "30
     * days". */
    const props = openModal();

    fireEvent.change(screen.getByLabelText(/type delete to confirm/i), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start 30-day deletion/i }));

    await waitFor(() => {
      expect(props.onRequested).toHaveBeenCalledWith(SCHEDULED_FOR);
    });
  });

  it("keeps the modal open when the request fails", async () => {
    /** **A request that failed did not start a deletion.** A modal that closed on
     * failure would tell the person their request landed when it did not.
     *
     * **The modal does not close itself on a failure** — that is `onClose`, the
     * container's call, and this island does not make it. So the assertion is that
     * `onClose` was *not* called, and not merely that the dialog is still on screen —
     * a dialog that stayed on screen because the container refused to close it would
     * pass a weaker check and still be wrong. */
    post.mockResolvedValue({
      error: { code: "deletion_not_allowed", message: "Not allowed." },
    });
    const props = openModal();

    fireEvent.change(screen.getByLabelText(/type delete to confirm/i), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start 30-day deletion/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(props.onClose).not.toHaveBeenCalled();
    expect(props.onRequested).not.toHaveBeenCalled();
  });

  it("quotes the API's own refusal", async () => {
    /** **The API's words, verbatim.** The refusal says what is actually wrong; a
     * generic message would throw away the one line that says what to fix.
     *
     * **The body is the project's error shape** — a `code` and a `message` — because
     * that shape is what `readApiError` recognises. A body it does not recognise is
     * the offline case, and the offline line is shown instead. */
    post.mockResolvedValue({
      error: {
        code: "deletion_already_pending",
        message: "You already have a pending deletion.",
      },
    });
    openModal();

    fireEvent.change(screen.getByLabelText(/type delete to confirm/i), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start 30-day deletion/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain(
        "You already have a pending deletion.",
      );
    });
  });

  it("keeps the modal open when the request never lands", async () => {
    /** **The offline case.** There is nothing to quote, so the message is the
     * frontend's own — and it does not blame the person, who pressed a button that
     * was supposed to work. */
    post.mockRejectedValue(new Error("offline"));
    const props = openModal();

    fireEvent.change(screen.getByLabelText(/type delete to confirm/i), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start 30-day deletion/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(props.onClose).not.toHaveBeenCalled();
    expect(props.onRequested).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("the confirmation modal and the design tokens", () => {
  it("introduces no new token", () => {
    /** **A-16 says no new tokens, and the token test only governs `tokens.css` —
     * so an arbitrary value like `max-w-[480px]` does not close the scale.** What
     * this asserts is that the dialog uses the project's own tokens for the things
     * the project has tokens for. */
    openModal();

    const dialog = screen.getByRole("dialog");
    expect(dialog.className).toContain("rounded-modal");
    expect(dialog.className).toContain("bg-surface-elevated");
    expect(dialog.className).toContain("border-border-subtle");
    expect(dialog.className).toContain("shadow-floating");
  });

  it("has zero serious or critical axe-core violations", async () => {
    openModal();

    expect(await audit()).toEqual([]);
  });
});
