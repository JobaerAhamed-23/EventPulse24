import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MutePrompt } from "@/components/digest/mute-prompt";
import type { components } from "@/lib/api/schema";

/**
 * The "less of this" prompt (FR-25).
 *
 * **The prompt is a question, and the copy is the server's.** The title and description
 * arrive on the dismissal response, because the category the cluster agreed on is a
 * fact the server computed (AD-10). These tests assert that the component *renders*
 * the server's words and writes none of its own — and that the copy the user reads is
 * never built out of an event's title, which is untrusted scraped text (AD-9).
 *
 * **The prompt is dismissible, and that is the point.** A prompt the user cannot walk
 * away from is a dark pattern — the exact thing FR-25's guard exists to prevent. So
 * Escape works, the X works, and the backdrop works.
 */

const PROMPT: components["schemas"]["MutePromptOut"] = {
  title: "Less arts & culture in your next digest?",
  description:
    "You've swiped past 3 similar events. Want us to deprioritize this category for a while? You can undo anytime in Settings → Taste.",
  category_key: "arts_culture",
};

function renderPrompt(
  overrides: {
    open?: boolean;
    prompt?: components["schemas"]["MutePromptOut"] | null;
    onAccept?: (prompt: components["schemas"]["MutePromptOut"]) => void;
    onDismiss?: () => void;
  } = {},
) {
  const onAccept = overrides.onAccept ?? vi.fn();
  const onDismiss = overrides.onDismiss ?? vi.fn();
  render(
    <MutePrompt
      open={overrides.open ?? true}
      prompt={overrides.prompt === undefined ? PROMPT : overrides.prompt}
      onAccept={onAccept}
      onDismiss={onDismiss}
    />,
  );
  return { onAccept, onDismiss };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the prompt's structure", () => {
  it("is a dialog, named by its title and described by its description", () => {
    // **The mockup's own accessibility line.** `role="dialog"` + `aria-labelledby` +
    // `aria-describedby` — and the mockup is explicit that the description is a
    // *separate* element from the title, which is why the prompt is its own component
    // rather than the house `Sheet` (a native `<dialog>` has no `aria-describedby`
    // slot, because its description is the element's own text content).
    renderPrompt();

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");

    const labelledBy = dialog.getAttribute("aria-labelledby");
    const describedBy = dialog.getAttribute("aria-describedby");
    expect(labelledBy).toBeTruthy();
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(labelledBy as string)).toHaveTextContent(PROMPT.title);
    expect(document.getElementById(describedBy as string)).toHaveTextContent(PROMPT.description);
  });

  it("renders the server's title and description verbatim", () => {
    // **The copy is the server's** (AD-10). A client that paraphrased would be
    // re-deciding a persisted fact at render.
    renderPrompt();

    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(PROMPT.title);
    expect(screen.getByText(/You can undo anytime in Settings → Taste/)).toBeInTheDocument();
  });

  it("renders nothing when there is no prompt to ask", () => {
    // `null` means "no cluster completed" — the state after the server has said the
    // prompt is due and the client has shown it.
    renderPrompt({ prompt: null });

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders nothing when it is closed", () => {
    renderPrompt({ open: false });

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("is a bottom-anchored sheet, not a modal that blacks out the page", () => {
    // **The mockup says so in as many words**: "bottom-anchored sheet, NOT a modal.
    // The user can close it without choosing." So the sheet hugs the bottom edge and
    // the digest stays readable behind it.
    renderPrompt();

    const container = document.querySelector("[data-mute-prompt]");
    expect(container?.className).toContain("bottom-0");
    expect(container?.className).not.toContain("items-center");
    expect(container?.className).not.toContain("bg-surface-paper");
  });

  it("points at the settings screen the mockup names", () => {
    // **The reversal surface is `Settings → Taste`, and the mockup says so twice.**
    // A prompt that pointed at the wrong screen would send the user to a control that
    // cannot express what they just asked for.
    renderPrompt();

    expect(document.body.textContent).toContain("Settings → Taste");
  });
});

describe("the prompt's focus", () => {
  it("moves focus to the affirmative button when it opens", () => {
    // **The mockup's own accessibility line**: "Focus moves to 'Mute for 30 days' on
    // open (the affirmative — calm default)." A keyboard user who presses Enter gets
    // the answer the screen is asking for.
    renderPrompt();

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Show me less" }));
  });

  it("gives the focus back when it closes", () => {
    // The reader goes back where they were, not to the top of the document.
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const { rerender } = render(
      <MutePrompt open prompt={PROMPT} onAccept={vi.fn()} onDismiss={vi.fn()} />,
    );
    rerender(<MutePrompt open={false} prompt={PROMPT} onAccept={vi.fn()} onDismiss={vi.fn()} />);

    waitFor(() => expect(document.activeElement).toBe(trigger));
    trigger.remove();
  });
});

describe("the prompt is dismissible", () => {
  it("closes on Escape", async () => {
    // **A prompt the user cannot walk away from is a dark pattern** — the exact thing
    // FR-25's guard exists to prevent.
    const { onDismiss } = renderPrompt();

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(onDismiss).toHaveBeenCalled());
  });

  it("closes on the X", () => {
    const { onDismiss } = renderPrompt();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(onDismiss).toHaveBeenCalled();
  });

  it("closes on a click outside the sheet", () => {
    const { onDismiss } = renderPrompt();

    fireEvent.click(document.querySelector("[data-mute-backdrop]") as HTMLElement);

    expect(onDismiss).toHaveBeenCalled();
  });

  it("offers a dismissive path in words, not only as an escape", () => {
    // The mockup's own button is "Keep as is". The product's wording is "Not now" —
    // and the point is that it is a *named button*, so a reader who does not know the
    // keyboard can still decline.
    renderPrompt();

    expect(screen.getByRole("button", { name: "Not now" })).toBeInTheDocument();
  });
});

describe("answering the prompt", () => {
  it("hands the server's prompt back when the user accepts", () => {
    // **The accept path writes a mute**, and the mute's subject is the server's
    // category key. So the server's prompt object is what the caller receives.
    const { onAccept } = renderPrompt();

    fireEvent.click(screen.getByRole("button", { name: "Show me less" }));

    expect(onAccept).toHaveBeenCalledWith(PROMPT);
  });

  it("does not accept when the user declines", () => {
    const { onAccept } = renderPrompt();

    fireEvent.click(screen.getByRole("button", { name: "Not now" }));

    expect(onAccept).not.toHaveBeenCalled();
  });

  it("names the affirmative button in the product's words", () => {
    renderPrompt();

    expect(screen.getByRole("button", { name: "Show me less" })).toBeInTheDocument();
  });
});

describe("the prompt's announcement", () => {
  it("announces itself assertively, because it interrupts", () => {
    // The prompt appears over the digest without being asked for, so a screen reader
    // has to be told — the same calm copy the title uses.
    renderPrompt();

    const live = document.querySelector("[aria-live='assertive']");
    expect(live).not.toBeNull();
    expect(live?.textContent).toContain(PROMPT.title);
  });
});
