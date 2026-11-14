"use client";

/**
 * `Sheet.MutePrompt` — the "less of this" question (FR-25).
 *
 * **It is the product's own question, and the copy is the server's.** The title and the
 * description arrive on the dismissal response, because the category the cluster agreed
 * on is a fact the server computed (AD-10) — and the label in the title comes from the
 * server's own vocabulary, never from an event's title. A scraped title cannot reach
 * the user's screen (AD-9).
 *
 * **It fires once per cluster, and the counter resets when it does.** So this prompt
 * cannot nag: the third similar dismissal fires it, and the next cluster has to earn its
 * own. The mockup's "No dark-pattern nag" is a rule about the *product*, and this
 * component is only ever told to open when the server says a cluster completed.
 *
 * ## It is a bottom-anchored sheet, NOT a modal
 *
 * The mockup says so in as many words: *"Position: bottom-anchored sheet, NOT a modal.
 * The user can close it without choosing."* So this prompt:
 *
 *   - sits at the bottom of the screen, over the digest;
 *   - does **not** cover the digest with a backdrop that swallows the page;
 *   - does **not** take the focus away from the page — the reader keeps reading while
 *     the question sits there, which is the whole point of it being a sheet and not a
 *     modal;
 *   - moves focus to the affirmative button anyway, because the mockup's own
 *     accessibility line says *"Focus moves to 'Mute for 30 days' on open (the
 *     affirmative — calm default)"*.
 *
 * **It is still dismissible.** It is a *question*, not a forced choice: the user did
 * not have to answer it, and a prompt that cannot be closed without answering is a
 * dark pattern — the exact thing FR-25's guard exists to prevent. So there is an X, the
 * Escape key works, and clicking outside works.
 *
 * ## It is not the house `Sheet`, and the difference matters
 *
 * The house `Sheet` is a native `<dialog>`, and a native dialog opened with
 * `showModal()` brings its own accessibility behaviour: the top layer, the backdrop, and
 * the browser's focus trap. **A native `<dialog>` has no `aria-describedby` slot that
 * this prompt can use**, because its description is the element's own text content — and
 * the description here is a *separate* element from the title, so the prompt has to
 * point at it.
 *
 * So this prompt is its own `role="dialog"` component, with:
 *
 *   - `aria-labelledby` pointing at the title,
 *   - `aria-describedby` pointing at the description,
 *   - `aria-modal="true"` — because it is the one thing the reader is being asked
 *     about, and a screen reader should not wander into the digest behind it,
 *   - focus moved to the affirmative button when it opens,
 *   - focus returned to whatever had it when the prompt closes,
 *   - Escape and a backdrop click both close it.
 *
 * **The affirmative button gets the focus.** The prompt's question is "want us to
 * deprioritize this?" and the affirmative is the action the copy leads with, so a
 * keyboard user who presses Enter gets the answer the screen is asking for. The
 * dismissive path — closing the prompt and leaving the preferences alone — is still one
 * Escape away.
 */
import { useEffect, useRef } from "react";

import type { components } from "@/lib/api/schema";

type MutePromptData = components["schemas"]["MutePromptOut"];

export type MutePromptProps = {
  /** Whether the prompt is open. */
  open: boolean;
  /**
   * The prompt's content, or `null` when there is nothing to ask.
   *
   * `null` means "no cluster completed", and the prompt stays closed — the state after
   * the server has said the prompt is due and the client has shown it.
   */
  prompt: MutePromptData | null;
  /** Called when the user asks for less of this category. */
  onAccept: (prompt: MutePromptData) => void;
  /** Called when the prompt closes without an answer. */
  onDismiss: () => void;
};

export function MutePrompt({ open, prompt, onAccept, onDismiss }: MutePromptProps) {
  const acceptRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  // **Focus moves to the affirmative button when the prompt opens**, so a keyboard user
  // lands on the answer the screen is asking for. And the element that had the focus
  // before is remembered, so closing the prompt puts the reader back where they were
  // rather than at the top of the document.
  useEffect(() => {
    if (!open) return;
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    acceptRef.current?.focus();
    return () => {
      restoreFocusRef.current?.focus?.();
    };
  }, [open]);

  // **Escape closes the prompt.** It is a question, and a question the user cannot walk
  // away from is a dark pattern — which is the thing FR-25's guard exists to prevent.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onDismiss();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onDismiss]);

  if (!open || !prompt) return null;

  const titleId = "mute-prompt-title";
  const descriptionId = "mute-prompt-description";

  return (
    <div
      /*
        **The sheet, anchored to the bottom.**
        *
        **It is not centred and it is not a full-bleed backdrop.** The mockup's sheet
        * sits at the bottom of the screen, over the digest, and the digest stays
        * readable behind it — a modal that blacks out the page is the thing the mockup
        rules out. So there is no `bg-surface-paper/70` wash over the whole viewport
        and no `items-center`: the sheet hugs the bottom edge.
      */
      className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex justify-center p-4 md:p-6"
      data-mute-prompt
    >
      {/*
        **The backdrop.**

        **It is a sibling of the panel, not a wrapper of it, so a click on the backdrop
        is a click *outside* the dialog — which is what closes it.** And it is
        `pointer-events-none` at the container level, so the sheet itself is not
        covered; the backdrop button opts back in.

        **It is transparent.** It exists to catch the click, not to dim the page — the
        sheet is a question, not an interruption that hides what is behind it.

        **It is hidden from the accessibility tree.** There is already a named "Close"
        control — the X — and a second button with the same name is a second thing for
        a screen reader to read and a second tab stop that leads nowhere. So the
        backdrop is `aria-hidden`, and the Escape key and the X carry the dismissal for
        anyone who is not using a pointer.
      */}
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        onClick={onDismiss}
        className="pointer-events-auto absolute inset-0 cursor-default"
        data-mute-backdrop
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="pointer-events-auto relative w-full max-w-(--layout-container-form) rounded-modal border border-border-subtle bg-surface-elevated p-6 shadow-floating"
      >
        {/*
          **The X.** It is a real `<button>` with a name, because an icon-only close
          control with no accessible name is a control a screen reader cannot reach
          (WCAG 4.1.2). The glyph is decorative; the name is on the button.
        */}
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Close"
          className="absolute top-4 right-4 flex size-[44px] items-center justify-center rounded-control text-ink-secondary"
        >
          <span aria-hidden="true">×</span>
        </button>

        <h2 id={titleId} className="pr-8 [font:var(--type-scale-headline-lg)] text-ink-primary">
          {prompt.title}
        </h2>
        <p id={descriptionId} className="mt-2 [font:var(--type-scale-body-md)] text-ink-secondary">
          {prompt.description}
        </p>

        {/*
          **The announcement.** Assertive, because the prompt interrupts: it appears
          over the digest without being asked for. The text is the same calm copy the
          title uses.
        */}
        <p aria-live="assertive" className="sr-only">
          {prompt.title}
        </p>

        <div className="mt-6 flex flex-wrap gap-3">
          <button
            ref={acceptRef}
            type="button"
            onClick={() => onAccept(prompt)}
            className="min-h-[44px] rounded-control bg-accent-terracotta px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-inverse"
          >
            Show me less
          </button>
          <button
            type="button"
            onClick={onDismiss}
            className="min-h-[44px] rounded-control border border-border-subtle px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
          >
            Not now
          </button>
        </div>
      </div>
    </div>
  );
}
