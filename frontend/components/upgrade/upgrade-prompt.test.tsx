import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UpgradePrompt } from "@/components/upgrade/upgrade-prompt";

const HINT = "You saved one event today. Save more with Pro.";

describe("UpgradePrompt", () => {
  it("renders the server's sentence verbatim", () => {
    render(<UpgradePrompt hint={HINT} />);
    expect(screen.getByText(HINT)).toBeInTheDocument();
  });

  it("renders whatever sentence the server sends, with no frontend change", () => {
    // Acceptance criterion 4: the prompt does not hard-code the sentence.
    render(<UpgradePrompt hint="Save more with Pro." />);
    expect(screen.getByText("Save more with Pro.")).toBeInTheDocument();
  });

  it("points Upgrade at /pricing", () => {
    render(<UpgradePrompt hint={HINT} />);
    expect(screen.getByRole("link", { name: "Upgrade" })).toHaveAttribute("href", "/pricing");
  });

  describe("is never a modal", () => {
    it("has no dialog role, no aria-modal, and no overlay", () => {
      const { container } = render(<UpgradePrompt hint={HINT} />);
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(screen.queryByRole("alertdialog")).toBeNull();
      expect(container.querySelector("[aria-modal]")).toBeNull();
      expect(container.querySelector("dialog")).toBeNull();
      // An interstitial is a fixed/absolute full-bleed layer. The prompt is in flow.
      expect(container.querySelector(".fixed, .absolute, .inset-0")).toBeNull();
    });

    it("does not block the surface behind it", () => {
      // Nothing is hidden from assistive tech or pointer events on its account.
      const { container } = render(
        <div>
          <button type="button">Save to Pulse</button>
          <UpgradePrompt hint={HINT} />
        </div>,
      );
      expect(screen.getByRole("button", { name: "Save to Pulse" })).toBeInTheDocument();
      expect(container.querySelector("[aria-hidden='true']")).toBeNull();
      expect(container.querySelector("[inert]")).toBeNull();
    });

    it("does not steal focus", () => {
      const previous = document.createElement("button");
      document.body.append(previous);
      previous.focus();
      render(<UpgradePrompt hint={HINT} />);
      expect(document.activeElement).toBe(previous);
      previous.remove();
    });

    it("announces politely, not assertively", () => {
      // `role="alert"` interrupts a screen reader mid-sentence. A tier ceiling is
      // information, not an emergency.
      render(<UpgradePrompt hint={HINT} />);
      expect(screen.getByRole("status")).toBeInTheDocument();
      expect(screen.queryByRole("alert")).toBeNull();
    });
  });

  it("offers no dismissal to persist", () => {
    // The payload carries no `dismissable` field by design, so there is no dismissal
    // state to invent and nothing to write to a setting.
    render(<UpgradePrompt hint={HINT} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText(/not now/i)).toBeNull();
    expect(screen.queryByRole("link", { name: /dismiss|close/i })).toBeNull();
  });

  it("takes no tier prop, which is why a Pro user can never see it", () => {
    // Entitlement is not an input: the component renders a refusal the server sent, and
    // the server does not refuse a Pro user. There is no client-side flag to go stale —
    // including immediately after an upgrade, with no reload.
    const props = { hint: HINT, className: "mt-4" };
    expect(Object.keys(props)).toEqual(["hint", "className"]);
    // @ts-expect-error — there is no tier prop to pass.
    render(<UpgradePrompt hint={HINT} isPro={true} />);
    expect(screen.getByText(HINT)).toBeInTheDocument();
  });
});
