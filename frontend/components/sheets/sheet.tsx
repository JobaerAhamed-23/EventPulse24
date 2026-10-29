"use client";

/**
 * The `<dialog>` base: one overlay level, one open/close protocol.
 *
 * A native `<dialog>` opened with `showModal()` lives in the **top layer**, so the sheet
 * sits above the bottom-tab nav on mobile and above the sidenav on desktop without a
 * z-index token being invented for it. The backdrop is `::backdrop`, styled from the
 * existing surface tokens.
 *
 * **The dismissal rules are the whole point of this component.** A native modal is
 * Escape-dismissable and backdrop-click-dismissable *by default*. The create sheet is an
 * ordinary modal and wants both. The conflict sheet is a **forced choice** and wants
 * neither — FR-58: "no dismiss button, no X, no escape-key close, no outside-click close".
 *
 * So `dismissible={false}` turns off every escape hatch in one place, next to the code
 * that opens the dialog, where it cannot be forgotten by a second call site.
 */
import { useCallback, useEffect, useRef, type ReactNode } from "react";

export type SheetProps = {
  /** Whether the sheet is open. */
  open: boolean;
  /**
   * Whether the sheet can be dismissed without choosing.
   *
   * `false` is the forced-choice mode: no X button, the Escape key does nothing, and a
   * backdrop click does nothing.
   */
  dismissible?: boolean;
  /** Called when the sheet closes by an allowed route. */
  onClose: () => void;
  /** The dialog's accessible name. */
  label: string;
  /** The sheet's body. */
  children: ReactNode;
  /** Extra classes on the dialog element. */
  className?: string;
};

export function Sheet({
  open,
  dismissible = true,
  onClose,
  label,
  children,
  className,
}: SheetProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  // Open and close the dialog. `showModal()` puts it in the top layer; `close()` takes it
  // out. The `open` attribute alone would not — it would render the dialog in the normal
  // flow, below the page's other content, with no backdrop.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // `showModal` throws if the dialog is already open, and jsdom's support is uneven;
      // the `open` attribute is the fallback for a runtime that cannot do the top layer.
      if (typeof dialog.showModal === "function") {
        try {
          dialog.showModal();
        } catch {
          dialog.setAttribute("open", "");
        }
      } else {
        dialog.setAttribute("open", "");
      }
    } else if (!open && dialog.open) {
      // The mirror of the fallback above: a runtime without the top layer (jsdom, for
      // one) may have no `close()` either, so the `open` attribute is removed directly.
      if (typeof dialog.close === "function") {
        dialog.close();
      } else {
        dialog.removeAttribute("open");
      }
    }
  }, [open]);

  // The Escape key. The `cancel` event is the only way a native dialog learns that Escape
  // was pressed; preventing its default is what stops the dialog from closing.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || dismissible) return;
    const refuse = (event: Event): void => event.preventDefault();
    dialog.addEventListener("cancel", refuse);
    return () => dialog.removeEventListener("cancel", refuse);
  }, [dismissible]);

  // A click on the backdrop is a click whose target is the dialog element itself — the
  // dialog's box is the content, so a click that reaches the element and not a child is
  // outside the content. A forced sheet refuses even that.
  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLDialogElement>) => {
      if (!dismissible) return;
      if (event.target !== event.currentTarget) return;
      onClose();
    },
    [dismissible, onClose],
  );

  return (
    <dialog
      ref={dialogRef}
      aria-label={label}
      onClick={handleClick}
      onCancel={(event) => {
        if (!dismissible) event.preventDefault();
      }}
      className={[
        "m-auto w-full max-w-(--layout-container-form) rounded-modal border border-border-subtle",
        "bg-surface-elevated p-0 text-ink-primary shadow-floating backdrop:bg-surface-paper/70",
        className ?? "",
      ].join(" ")}
    >
      {children}
    </dialog>
  );
}
