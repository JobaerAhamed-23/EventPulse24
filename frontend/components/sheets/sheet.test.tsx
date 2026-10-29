import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Sheet } from "@/components/sheets/sheet";

/**
 * The `<dialog>` base's two dismissal regimes (D60).
 *
 * A native modal is Escape-dismissable and backdrop-click-dismissable **by default**,
 * and FR-58 forbids both on the conflict sheet. These tests prove the base turns each
 * escape hatch off in one place — and that the ordinary sheet keeps both.
 */

describe("Sheet", () => {
  it("renders its label as the dialog's accessible name", () => {
    render(
      <Sheet open onClose={() => {}} label="Add personal event">
        <p>Body</p>
      </Sheet>,
    );

    expect(screen.getByRole("dialog", { name: "Add personal event" })).toBeInTheDocument();
  });

  it("is not rendered as an open dialog when closed", () => {
    render(
      <Sheet open={false} onClose={() => {}} label="Add personal event">
        <p>Body</p>
      </Sheet>,
    );

    expect(screen.queryByRole("dialog", { name: "Add personal event" })).not.toBeInTheDocument();
  });

  describe("when dismissible", () => {
    it("closes on a backdrop click", async () => {
      const onClose = vi.fn();
      render(
        <Sheet open onClose={onClose} label="Add personal event">
          <p>Body</p>
        </Sheet>,
      );

      const dialog = screen.getByRole("dialog", { name: "Add personal event" });
      fireEvent.click(dialog);

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("closes on the Escape key", () => {
      const onClose = vi.fn();
      render(
        <Sheet open onClose={onClose} label="Add personal event">
          <p>Body</p>
        </Sheet>,
      );

      const dialog = screen.getByRole("dialog", { name: "Add personal event" });
      const event = new Event("cancel", { cancelable: true });
      dialog.dispatchEvent(event);

      // The `cancel` event is not cancelled, so the native dialog would close.
      expect(event.defaultPrevented).toBe(false);
    });

    it("does not close on a click inside the content", () => {
      const onClose = vi.fn();
      render(
        <Sheet open onClose={onClose} label="Add personal event">
          <p>Body</p>
        </Sheet>,
      );

      fireEvent.click(screen.getByText("Body"));

      expect(onClose).not.toHaveBeenCalled();
    });
  });

  describe("when not dismissible", () => {
    it("ignores a backdrop click", () => {
      const onClose = vi.fn();
      render(
        <Sheet open dismissible={false} onClose={onClose} label="Schedule conflict">
          <p>Body</p>
        </Sheet>,
      );

      fireEvent.click(screen.getByRole("dialog", { name: "Schedule conflict" }));

      expect(onClose).not.toHaveBeenCalled();
    });

    it("refuses the Escape key", () => {
      render(
        <Sheet open dismissible={false} onClose={() => {}} label="Schedule conflict">
          <p>Body</p>
        </Sheet>,
      );

      const dialog = screen.getByRole("dialog", { name: "Schedule conflict" });
      const event = new Event("cancel", { cancelable: true });
      dialog.dispatchEvent(event);

      // The `cancel` event's default is prevented, so the dialog stays open.
      expect(event.defaultPrevented).toBe(true);
    });
  });
});
