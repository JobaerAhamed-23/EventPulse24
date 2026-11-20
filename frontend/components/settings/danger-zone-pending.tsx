"use client";

/**
 * The danger zone's pending state — **the way back.**
 *
 * ## What this is
 *
 * A person asks to delete their account, and then changes their mind. A-16 promises them
 * thirty days: *"You can cancel anytime during the 30-day grace."* **This is the button
 * that keeps that promise** — the surface for the `DELETE /api/auth/profile/deletion`
 * endpoint that already exists.
 *
 * ## Why it is a separate island, and not the whole section
 *
 * The danger zone itself is a server component, and it stays one. **The pending state
 * needs `useState` and a request**, so it cannot live in the container — but the container
 * is the thing the delete modal and this action both hang on, and making it a client
 * component would drag the whole section across the boundary for one button.
 *
 * **So the container decides which of two states to render, and this is the second one.**
 *
 * ## It is not terracotta
 *
 * The project's rule is that terracotta is reserved for destructive actions. **The
 * pending state is the way back *from* a destructive action**, so it wears the ordinary
 * treatment — spending the destructive colour on a button whose job is to prevent
 * destruction would spend the accent on the opposite of what it means.
 *
 * ## It names the server's date, and never computes one
 *
 * The date the account will be destroyed was computed once, by the server, when the
 * request was made. **This renders that moment**; it does not add thirty days to
 * anything, because a duration typed into a frontend is the mistake the mail templates
 * already made — *"a number that keeps saying '30 minutes' after the constant says
 * otherwise."*
 *
 * ## Cancelling is not an error, and it is not shown as one
 *
 * The endpoint answers the same way whether or not anything was pending: the caller
 * wanted no pending deletion and has none either way. **So a successful cancel is a
 * success**, and the surface says so plainly rather than apologising for cancelling
 * something that was already gone.
 *
 * **A failed cancel keeps the pending state.** A cancel that silently cleared the screen
 * would tell the user the deletion was stopped when it was not.
 */
import { useCallback, useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";

export type DangerZonePendingProps = {
  /**
   * When the account will be destroyed, ISO-8601.
   *
   * **The server's moment**, computed once when the request was made and never moved by
   * asking again.
   */
  scheduledFor: string;
  /**
   * When the deletion was requested, ISO-8601.
   *
   * **The screen says "you asked on the 3rd"** — and it can, because the server
   * computed it and it differs from the destruction date by exactly the grace period.
   */
  requestedAt: string;
  /**
   * Called when the cancellation lands.
   *
   * **The container needs to know, because the container decides which state shows.**
   * The section holds one state at a time, and a cancelled deletion means the request
   * row is back — so the state that changes has to be told.
   */
  onCancelled?: () => void;
};

/**
 * The failure line for the **offline** case, where the API said nothing to quote.
 *
 * **Short, and it does not blame the person.** They pressed a button that was supposed
 * to work; saying their network is down is an excuse, not an answer.
 */
const FAILED = "Couldn't cancel that. Try again in a moment.";

/**
 * The date, as a sentence a person can read.
 *
 * **The server's date, formatted.** `Date.parse` of an ISO-8601 string, then the
 * browser's own date rendering — and `null` for anything it cannot read, because an
 * unparseable date is not a reason to invent one.
 *
 * **The date is not the number of days left.** "How long do I have" is a question the
 * answer to "when" answers; computing a countdown in the browser would mean the browser
 * re-derives a deadline the server already computed, and the two could disagree.
 */
function destructionDate(iso: string): string | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return null;
  return new Date(at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

/**
 * The date the request was made, as a sentence — or `null`.
 *
 * **The same rule as the destruction date**: the server's moment, formatted, and
 * nothing invented.
 */
function requestedOn(iso: string): string | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return null;
  return new Date(at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function DangerZonePending({
  scheduledFor,
  requestedAt,
  onCancelled,
}: DangerZonePendingProps) {
  const [busy, setBusy] = useState(false);
  /** The message, not a flag — so the API's own refusal can be shown verbatim. */
  const [failure, setFailure] = useState<string | null>(null);

  const cancel = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    try {
      const response = await api.DELETE("/api/auth/profile/deletion");
      if (response.error) {
        // **The pending state stays.** A cancel that failed did not stop anything, and
        // a screen that says otherwise is lying.
        setFailure(saveFailureMessage(response.error, FAILED));
        return;
      }
      // **The container decides which state shows**, and the request row is back. The
      // reassurance belongs to the section rather than to this row — the row it
      // replaces is the row the person was reading a moment ago.
      onCancelled?.();
    } catch {
      // The request never reached the API, so there is nothing to quote.
      setFailure(FAILED);
    } finally {
      setBusy(false);
    }
  }, [onCancelled]);

  const when = destructionDate(scheduledFor);
  const asked = requestedOn(requestedAt);

  return (
    <div data-danger-pending>
      <p className="text-ink-primary [font:var(--type-scale-body-md)]" data-pending-line>
        {when ? (
          <>
            Your account will be deleted on <strong data-pending-date>{when}</strong>.
          </>
        ) : (
          <>Your account has a pending deletion.</>
        )}
        {asked ? (
          <>
            {" "}
            You asked on <span data-requested-date>{asked}</span>.
          </>
        ) : null}
      </p>

      <p className="mt-1 text-ink-secondary [font:var(--type-scale-body-sm)]">
        Nothing has been deleted yet. Cancel it and your account, your plan and your history all
        stay exactly as they are.
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void cancel()}
          disabled={busy}
          aria-busy={busy}
          data-keep-account
          // **The accessible name says what the button does, not just what it is
          // called.** "Keep it" out of context is ambiguous; this is not.
          aria-label="Keep my account. The pending deletion is cancelled."
          className="min-h-[44px] rounded-control border border-border-subtle px-3 py-2 text-ink-primary [font:var(--type-scale-body-sm)] disabled:cursor-default"
        >
          {busy ? "Keeping it…" : "Keep my account"}
        </button>
      </div>

      {/*
        **The failure region is a `role="alert"`**, so a screen reader announces it
        without the focus moving — and it is *inside* the section, so the message and
        the control it belongs to cannot be separated by a layout change.
      */}
      {failure ? (
        <p
          role="alert"
          className="mt-2 text-warn-amber [font:var(--type-scale-body-sm)]"
          data-keep-failed
        >
          {failure}
        </p>
      ) : null}
    </div>
  );
}
