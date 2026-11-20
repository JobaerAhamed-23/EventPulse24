"use client";

/**
 * `Component.Modal.AccountDelete` — **the moment before the account goes.**
 *
 * Amendment A-16 puts this modal at `/settings/privacy` → Danger zone, and fixes its
 * anatomy exactly: a centred 480px dialog, three body paragraphs, a type-to-confirm
 * input, and two footer buttons. **The anatomy is not re-invented here** — the mockup
 * specifies it, and a second spelling of the same control is a second place to keep in
 * sync.
 *
 * ## It is a modal, and it is a real one
 *
 * **The house `Sheet` cannot carry it.** `components/sheets/sheet.tsx` is a native
 * `<dialog>`, and `components/digest/mute-prompt.tsx` records why that matters: *a
 * native `<dialog>` has no `aria-describedby` slot that this prompt can use*, because
 * its description is the element's own text content — and A-16's description is three
 * paragraphs, separate from the title. So this is its own `role="dialog"`, with
 * `aria-modal`, `aria-labelledby` and `aria-describedby`, and it follows `MutePrompt`'s
 * structure.
 *
 * **It has a focus trap, and nothing else in this repository does.** `MutePrompt` needs
 * none — it is a bottom sheet over a digest, and the digest behind it has nothing to
 * tab to. **This modal sits over the settings screen, which is full of interactive
 * controls**, so a Tab that walked out of the dialog would put a keyboard user into the
 * page behind it, editing settings they did not come to edit. The trap is not a
 * nicety here; it is the difference between a modal and a decoration.
 *
 * ## The gate is `=== "DELETE"`, and it is exactly that
 *
 * A-16 says case-sensitive, and says it in the mockup's own variant strip: *`input.value
 * === "DELETE"` (case-sensitive)*. **So the comparison is `=== "DELETE"`** — not
 * trimmed, not case-folded. A trimmed comparison would make the gate a suggestion, and
 * the gate is the last thing standing between an accident and a destroyed account.
 *
 * ## The two paragraphs come from the API, and the third is the promise
 *
 * **The API publishes what the deletion removes and what it survives** — the same two
 * constants the confirmation mail renders. The modal says what it is given, because a
 * second copy of the same sentence in the frontend is a second version of the same
 * story, and the two could drift.
 *
 * **The third paragraph is the only one written here**, and that is deliberate. The
 * other two describe *what the engine does* — a fact the server owns. **This one
 * describes what the product offers**: you can cancel, from this page or from the
 * email. Both of those exist — the cancel surface and the mail — and this modal is the
 * last thing that makes the sentence true.
 *
 * ## The label says "Start", and not "Delete"
 *
 * **The engine does not delete on this call. It schedules.** The label tells the truth
 * about what the button does, which is why it is "Start 30-day deletion" and not
 * "Delete account".
 *
 * ## A failed request keeps the modal open
 *
 **A request that failed did not start a deletion.** A modal that closed on failure
 * would tell the person their request landed when it did not — the same failure the
 * cancel surface refuses to make. **The API's own refusal is shown verbatim**, through
 * the project's `saveFailureMessage`.
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";

/**
 * The word the input has to match.
 *
 * **Case-sensitive, and written out rather than derived.** A-16 fixes the string, and a
 * constant that could be changed would be a constant that could be changed into
 * something weaker.
 */
const CONFIRM_WORD = "DELETE";

/**
 * The failure line for the **offline** case, where the API said nothing to quote.
 *
 * **Short, and it does not blame the person.** They pressed a button that was supposed
 * to work; saying their network is down is an excuse, not an answer.
 */
const FAILED = "Couldn't start that. Try again in a moment.";

export type AccountDeleteModalProps = {
  /**
   * Whether the modal is open.
   *
   * **The container decides.** The danger zone is the thing that knows whether a
   * deletion is pending, so it is the thing that knows whether the modal should be on
   * screen.
   */
  open: boolean;
  /**
   * What the deletion removes, in the product's own words.
   *
   * **This arrives from the API**, so the modal and the confirmation mail cannot tell
   * the person two different stories about the same destruction.
   */
  whatIsDeleted: string;
  /**
   * What survives the deletion, as anonymised aggregates.
   *
   * **Also from the API**, and for the same reason.
   */
  whatSurvives: string;
  /**
   * Called when the request lands, with the date the account will be destroyed.
   *
   * **The server's date, and the only date.** It was computed once, when the request
   * was first made, and a later request cannot move it — so the modal shows the date
   * the product promised rather than a duration it computes itself.
   */
  onRequested: (scheduledFor: string) => void;
  /** Called when the modal closes without a request landing. */
  onClose: () => void;
};

/**
 * The elements inside the panel that can hold the focus.
 *
 * **A focus trap needs to know where the edges are**, and the honest way to find out
 * is to ask the DOM — a hard-coded list would go stale the moment a button was added.
 */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function AccountDeleteModal({
  open,
  whatIsDeleted,
  whatSurvives,
  onRequested,
  onClose,
}: AccountDeleteModalProps) {
  const uid = useId();
  const titleId = `${uid}-title`;
  const bodyId = `${uid}-body`;
  const inputId = `${uid}-input`;
  const hintId = `${uid}-hint`;

  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  /** The message, not a flag — so the API's own refusal can be shown verbatim. */
  const [failure, setFailure] = useState<string | null>(null);

  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  /**
   * **The gate.** Exactly `=== "DELETE"` — not trimmed, not case-folded.
   *
   * A trimmed comparison would let " DELETE " through, which is a comparison that
   * *looks* strict and is not.
   */
  const matches = value === CONFIRM_WORD;

  /**
   * **Focus moves to the input when the modal opens, and comes back when it closes.**
   *
   * The input, and not the primary button: **the primary is disabled until the input
   * matches**, so focusing it would put a keyboard user on a control that does nothing.
   * The input is the first thing a person has to do.
   *
   * And the element that had the focus before is remembered, so closing the modal puts
   * the reader back on the "Delete account →" row rather than at the top of the
   * document.
   */
  useEffect(() => {
    if (!open) return;
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
    return () => {
      restoreFocusRef.current?.focus?.();
    };
  }, [open]);

  /**
   * **Escape closes the modal, and Tab stays inside it.**
   *
   * **The trap is the reason this modal is not a decoration.** The settings screen
   * behind it is full of interactive controls, so a Tab that walked out of the dialog
   * would put a keyboard user into the page behind it — editing settings they did not
   * come to edit, in a dialog about destroying their account.
   *
   * **The handler is on the document, not on the panel**, because the browser moves the
   * focus itself and the `keydown` still fires on whatever now has it — which may be
   * the body's last descendant rather than the panel. So the listener is on the
   * document, and it is removed when the modal closes, so it only runs while the panel
   * is mounted.
   */
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const panel = panelRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
      // **Nothing to trap around.** A panel with no focusable element cannot hold the
      // focus, and the browser would put it back on the body — which is behind the
      // modal. So the panel itself takes it.
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      // **Tab off the front wraps to the back, and Shift+Tab off the back wraps to
      // the front.** Anything in between is ordinary tabbing, which the browser does
      // on its own.
      if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  /** The request. */
  const start = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    try {
      const response = await api.POST("/api/auth/profile/deletion");
      if (response.error) {
        // **The modal stays open.** A request that failed did not start a deletion,
        // and a modal that closed on failure would say it had.
        setFailure(saveFailureMessage(response.error, FAILED));
        return;
      }
      // **The server's date, and the only one.** The container renders the pending
      // state from it — never a duration computed here, and never a hardcoded "30
      // days".
      onRequested(response.data.scheduled_for);
    } catch {
      // The request never reached the API, so there is nothing to quote.
      setFailure(FAILED);
    } finally {
      setBusy(false);
    }
  }, [onRequested]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-8" data-delete-backdrop>
      {/*
        **The backdrop is a sibling of the panel, not a wrapper of it**, so a click on
        the backdrop is a click *outside* the dialog — which is what closes it.

        **It is dimmed and blurred**, because this is an interruption and not a sheet:
        A-16 specifies `rgba(10,10,11,0.7)` and `backdrop-filter: blur(8px)`, and the
        settings screen behind it is full of controls a person must not reach.
      */}
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-surface-paper/70 backdrop-blur"
        data-delete-dim
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        // **`tabIndex={-1}`** so the panel itself can hold the focus when it has
        // nothing focusable inside it. It is not a tab stop.
        tabIndex={-1}
        className="relative w-full max-w-[480px] rounded-modal border border-border-subtle bg-surface-elevated p-6 shadow-floating"
        data-delete-modal
      >
        <h2 id={titleId} className="text-ink-primary [font:var(--type-scale-headline-md)]">
          Delete your account?
        </h2>

        {/*
          **The three paragraphs.**

          The first two are the API's, and they say what the engine does. The third is
          this screen's own promise, and it is the one the whole modal exists to make
          true: the cancellation surface and the mail both ship.
        */}
        <div id={bodyId} className="mt-3 text-ink-secondary [font:var(--type-scale-body-sm)]">
          <p className="mb-3">{whatIsDeleted}</p>
          <p className="mb-3">{whatSurvives}</p>
          <p>
            You can cancel anytime during the 30-day grace from this page or from the email we send.
          </p>
        </div>

        <div className="mt-6">
          <label
            htmlFor={inputId}
            className="block text-ink-muted [font:var(--type-scale-meta-sm)] uppercase"
          >
            Type DELETE to confirm
          </label>
          <input
            ref={inputRef}
            id={inputId}
            type="text"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Type DELETE to confirm"
            autoComplete="off"
            spellCheck={false}
            aria-describedby={hintId}
            disabled={busy}
            data-delete-confirm-input
            className="mt-2 w-full rounded-subtle border border-border-subtle bg-surface-elevated px-3 py-2 text-ink-primary [font:var(--type-scale-body-sm)]"
          />
          <p id={hintId} className="mt-2 text-ink-muted [font:var(--type-scale-meta-sm)]">
            Case-sensitive. The button activates once this matches.
          </p>
        </div>

        {/*
          **The failure is a `role="alert"`**, so a screen reader announces it without
          the focus moving — and it is *inside* the dialog, so the message and the
          control it belongs to cannot be separated.
        */}
        {failure ? (
          <p
            role="alert"
            className="mt-3 text-warn-amber [font:var(--type-scale-body-sm)]"
            data-delete-failed
          >
            {failure}
          </p>
        ) : null}

        <div className="mt-6 flex justify-end gap-3 border-t border-border-subtle pt-6">
          {/*
            **Cancel is never terracotta.** Terracotta is rationed, and A-16 says so
            explicitly: this is a `Button.Secondary`, and it is the *way out* of the
            dialog.
          */}
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="min-h-[44px] rounded-control border border-border-subtle px-4 py-2 text-ink-secondary [font:var(--type-scale-meta-md)] disabled:cursor-default"
            data-delete-cancel
          >
            Cancel
          </button>

          {/*
            **The primary is terracotta, and it says "Start".** The engine schedules;
            it does not delete on this call, and the label tells the truth about what
            the button does.

            **The disabled treatment has no precedent in this repository** — no
            existing primary button is ever disabled — so A-16's is the one written
            here: `surface-inset` fill, `ink-faint` text, `not-allowed` cursor.
          */}
          <button
            type="button"
            onClick={() => void start()}
            disabled={!matches || busy}
            aria-busy={busy}
            className="min-h-[44px] rounded-control bg-accent-terracotta px-4 py-2 text-ink-inverse [font:var(--type-scale-meta-md)] disabled:cursor-not-allowed disabled:bg-surface-inset disabled:text-ink-faint"
            data-delete-start
          >
            Start 30-day deletion
          </button>
        </div>
      </div>
    </div>
  );
}
