"use client";

/**
 * The Detail Screen's tooltip: a `<button>` trigger with `aria-describedby` pointing at
 * a sibling `role="tooltip"`.
 *
 * **Why this is a component and not the card's CSS-only tooltip.** The card's tooltip is
 * a sibling `<span>` revealed by `group-hover`/`group-focus-within` — which covers hover
 * and keyboard focus, and opens on tap as a side effect of the tap focusing the button.
 * But `EXPERIENCE.md` §12 and `DESIGN.md` also ask for the tooltip to dismiss on an
 * outside-tap and on `Esc`, and **CSS cannot do either**. So the Detail Screen gets its
 * own, and the card's is left exactly as it is (the card is a completed work item, and
 * changing it here would be a change to something that is already shipped and tested).
 *
 * **"No hover-only tooltips on touch."** The tooltip is always **in the DOM** — it is
 * revealed by `hidden`/`aria-hidden` rather than by `display: none` — so:
 *
 *   - `aria-describedby` always resolves to a live element;
 *   - a test can assert its *content* without simulating hover;
 *   - a screen reader that reads the description reads it whether or not the tooltip is
 *     currently visible.
 *
 * A CSS-hover-only tooltip has to be `display: none` to be hidden, and a
 * `display: none` element is not a description target. That is the whole reason this
 * component exists.
 */
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";

export type TriggerTipProps = {
  /** The trigger's content — the dot row, the badge label. */
  children: ReactNode;
  /** The tooltip's content. */
  tip: ReactNode;
  /** The trigger's accessible name. */
  label: string;
  /** Extra classes on the trigger button. */
  className?: string;
};

export function TriggerTip({ children, tip, label, className }: TriggerTipProps) {
  const [open, setOpen] = useState(false);
  const tipId = useId();
  const rootRef = useRef<HTMLSpanElement>(null);

  const close = useCallback(() => setOpen(false), []);

  /**
   * **Escape closes it.** The keydown listener is on the document, because the focus may
   * be anywhere — on the trigger, or inside the tooltip if the tooltip ever holds a
   * focusable thing.
   */
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, close]);

  /**
   * **An outside tap closes it.** The listener is on the document and checks the
   * trigger's own container, so a tap on the trigger itself is not an outside tap — the
   * button's own `onClick` handles that.
   */
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent): void => {
      const root = rootRef.current;
      if (root && event.target instanceof Node && root.contains(event.target)) return;
      close();
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open, close]);

  return (
    <span ref={rootRef} className="relative inline-flex items-center">
      <button
        type="button"
        aria-label={label}
        aria-describedby={tipId}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={close}
        onFocus={() => setOpen(true)}
        onBlur={close}
        onClick={() => setOpen((was) => !was)}
        className={[
          "inline-flex min-h-[44px] items-center justify-center rounded-control",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-terracotta",
          className ?? "",
        ].join(" ")}
      >
        {children}
      </button>

      {/*
        The tooltip stays in the DOM. `hidden` takes it out of the accessibility tree
        and out of the layout, and `aria-describedby` still resolves — so the
        description is available to anything that asks for it, and the content is
        assertable without a browser.
      */}
      <span
        role="tooltip"
        id={tipId}
        hidden={!open}
        className="absolute top-full left-0 z-20 mt-1 block max-w-[260px] rounded-card border border-border-subtle bg-surface-elevated px-3 py-2 shadow-floating [font:var(--type-scale-meta-sm)] text-ink-secondary"
      >
        {tip}
      </span>
    </span>
  );
}
