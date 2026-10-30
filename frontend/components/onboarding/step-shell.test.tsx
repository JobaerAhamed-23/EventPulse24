import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StepShell, type StepShellProps } from "@/components/onboarding/step-shell";

/**
 * The shared step frame: the progress, the actions' home, and where focus goes.
 *
 * The **topbar-quiet rule** (ASSUM-11) puts Back, Skip and Continue in the footer; the
 * mockups draw them there and `EXPERIENCE.md` calls an inversion a bug. The frame is also
 * where the step change is announced and where focus lands, so a keyboard user is not
 * left on a button that has just been replaced.
 */

/** Everything the shell needs except the body, which is passed as a child. */
type ShellProps = Omit<StepShellProps, "children">;

function renderShell(step = 2, overrides: Partial<ShellProps> = {}) {
  const props: ShellProps = {
    step,
    title: "What kinds of things?",
    lede: "Pick up to three.",
    continueLabel: "Continue →",
    busy: false,
    onBack: vi.fn(),
    onSkipStep: vi.fn(),
    onSkipAll: vi.fn(),
    onContinue: vi.fn(),
    ...overrides,
  };
  render(
    <StepShell {...props}>
      <p>Step body</p>
    </StepShell>,
  );
  return props;
}

describe("StepShell", () => {
  it("announces which step this is", () => {
    renderShell(2);

    expect(screen.getByRole("status")).toHaveTextContent("Step 2 of 3 · Optional");
  });

  it("labels each progress dot with its state, so colour is not the only signal", () => {
    renderShell(2);

    const progress = screen.getByRole("group", { name: "Onboarding progress" });
    expect(progress).toBeInTheDocument();
    expect(screen.getByLabelText("Step 1 of 3 — done")).toBeInTheDocument();
    expect(screen.getByLabelText("Step 2 of 3 — current")).toBeInTheDocument();
    expect(screen.getByLabelText("Step 3 of 3 — pending")).toBeInTheDocument();
  });

  it("moves focus to the step heading, so the new step is where the user lands", () => {
    renderShell(2);

    expect(screen.getByRole("heading", { level: 1 })).toHaveFocus();
  });

  it("keeps every action in the footer, below the step body", () => {
    renderShell(2);

    const body = screen.getByText("Step body");
    for (const name of ["← Back", "Skip all", "Skip for now", "Continue →"]) {
      const action = screen.getByRole("button", { name });
      // DOCUMENT_POSITION_FOLLOWING: the action comes after the step body in the document.
      expect(body.compareDocumentPosition(action) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("wires each action", () => {
    const props = renderShell(2);

    fireEvent.click(screen.getByRole("button", { name: "← Back" }));
    fireEvent.click(screen.getByRole("button", { name: "Skip for now" }));
    fireEvent.click(screen.getByRole("button", { name: "Skip all" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue →" }));

    expect(props.onBack).toHaveBeenCalled();
    expect(props.onSkipStep).toHaveBeenCalled();
    expect(props.onSkipAll).toHaveBeenCalled();
    expect(props.onContinue).toHaveBeenCalled();
  });

  it("omits Back when there is nowhere to go back to", () => {
    renderShell(1, { onBack: null });

    expect(screen.queryByRole("button", { name: "← Back" })).toBeNull();
  });

  it("shows the step's own note beside the label", () => {
    renderShell(2, { note: "2 of 3 picked" });

    expect(screen.getByText("2 of 3 picked")).toBeInTheDocument();
  });

  it("disables the actions while a call is in flight, so nothing is double-sent", () => {
    renderShell(2, { busy: true });

    expect(screen.getByRole("button", { name: "Continue →" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Continue →" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Skip for now" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Skip all" })).toBeDisabled();
  });
});
