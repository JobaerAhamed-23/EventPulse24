"use client";

/**
 * FR-55's **per-event mute** — the control on the Detail Screen.
 *
 * **A mute silences the correction, not the event.** Reminders still fire on the user's
 * Reminder Plan and the event still places in the Pulse Digest; what stops is the
 * "this changed" message. The server's own contract says it, and the control's copy says
 * it too, because a user who thinks a mute turns their reminders off would be wrong
 * about the thing they care about.
 *
 * ---
 *
 * ## The off state is legible in words
 *
 * **The control is not a bare switch whose meaning is in its position.** Its *visible*
 * text changes:
 *
 * - **not muted** — "Mute updates about this event"
 * - **muted** — "Updates about this event are muted"
 *
 * **So a user can tell they have muted it without reading the state of a widget.** FR-55
 * asks for "a legible off state so a user can tell they have muted it", and a toggle
 * whose only signal is a filled circle fails that: the state is in the *shape*, and
 * WCAG 1.4.1 says colour is never the sole carrier of meaning. The visible text
 * carries it in words.
 *
 * **And `aria-pressed` carries it to assistive technology**, so the button's state is
 * announced rather than only shown.
 *
 * **The *accessible* name does not change, though.** A toggle button whose accessible
 * name changes with its state is a contradiction — `aria-pressed="true"` on a button
 * called "Mute updates about this event" says both "this is on" and "press me to turn
 * it on". So the accessible name is fixed at "Mute updates about this event" (it names
 * the action the control performs) and `aria-pressed` carries the state. The visible
 * text changes so a sighted reader sees the state too, and the explicit `aria-label`
 * keeps the two apart.
 *
 * ---
 *
 * ## The write, and what a failed write does
 *
 * **Muting is `PUT` and unmuting is `DELETE`** — a mute is a state with two values, so
 * setting it is `PUT` and clearing it is `DELETE`. There is no request body, so the
 * client cannot encode "clear this" as a field that could be confused with "leave it
 * alone".
 *
 * **A failed write puts the state back.** The server did not record the mute, so the
 * event is not muted, and a control claiming otherwise would be claiming something that
 * did not happen. **The banner does not move until the server confirms**, so a failed
 * write never leaves a hidden banner behind — the banner's disappearance is the
 * server's claim, not the client's (AD-10).
 *
 * **The endpoint is idempotent, and `changed` says whether *this call* moved it.** A
 * mute of an already-muted event answers 200 with `changed: false` — a success that
 * changed nothing. The control redraws either way, because the state it shows is the
 * state the server now holds.
 */
import { useCallback, useState } from "react";

import { api } from "@/lib/backend-client";

export type DetailMuteControlProps = {
  /** The event's id — the mute's own path parameter. */
  eventId: string;
  /** Whether the event's notices are muted. The server's fact. */
  muted: boolean;
  /** Called when the mute state changes, so the banner can leave. */
  onMuteChange?: (muted: boolean) => void;
};

/**
 * The two labels.
 *
 * **Two sentences, and they are different sentences.** The unmuted one names the action
 * the button will take; the muted one states the state the user is in. A user who has
 * muted an event must be able to tell that they did — which is why the muted state says
 * so in words rather than only drawing a different shape.
 *
 * **But the *accessible* name does not change.** A toggle button whose accessible name
 * changes with its state is a contradiction: `aria-pressed="true"` on a button called
 * "Mute updates about this event" says the button is pressed *and* offers to press it,
 * and "Updates about this event are muted" is not an action at all — it is a status
 * dressed as a button label, so a reader who believes it has nothing to press.
 *
 * **So the name is stable and the state rides on `aria-pressed`.** The accessible name
 * is always *"Mute updates about this event"*; `aria-pressed` says whether the mute is
 * on. The *visible* text changes, because a sighted user needs to see the state too —
 * but the visible text is a different string from the accessible name, and the button
 * carries an explicit `aria-label` so the two never collapse into each other.
 */
const LABELS = {
  unmuted: "Mute updates about this event",
  muted: "Updates about this event are muted",
} as const;

/**
 * The button's stable accessible name.
 *
 * **It names the action the button performs**, and it is the same in both states. The
 * state is `aria-pressed`'s job (WCAG 4.1.2), and the visible text's job is to let a
 * sighted reader see the state without reading the attribute.
 */
const ACCESSIBLE_NAME = "Mute updates about this event";

/**
 * The line under the control.
 *
 * **It says what a mute does, and what it does not.** A user who thinks "mute" means
 * "stop the reminders" would be badly wrong, and the cost of that mistake is a reminder
 * they expected and did not get. So the control says what it silences: *messages about
 * changes*, not reminders.
 *
 * **It is one line, and it is quiet.** It is `Text.Meta` in muted ink — a helper, not a
 * warning.
 */
const HINT = "Reminders are not affected.";

export function DetailMuteControl({ eventId, muted, onMuteChange }: DetailMuteControlProps) {
  /**
   * **The mute, in the island's own hands.**
   *
   * **The server's answer is the starting state**, and the control updates it locally
   * so the UI moves at once rather than after a round trip. The write still goes to the
   * server, and a failed write puts the state back — the event is not muted if the
   * server did not record it.
   */
  const [isMuted, setIsMuted] = useState(muted);
  /** Whether a write is in flight, so the control cannot be pressed twice. */
  const [busy, setBusy] = useState(false);
  /** Whether the last write failed, so the control can say so calmly. */
  const [failed, setFailed] = useState(false);

  const onToggle = useCallback(async () => {
    const next = !isMuted;

    setBusy(true);
    setFailed(false);
    // **The optimistic move — but only for the button.** The label flips at once, so the
    // control feels like a control and not a form that waits for a round trip.
    //
    // **The banner does NOT move yet.** `onMuteChange` is deliberately called *after*
    // the server confirms, and that is the point: the banner's disappearance is a claim
    // about the world ("you will not be told about changes to this event"), and a claim
    // the server has not agreed to is the client deciding the server's fact (AD-10). If
    // the write fails, the banner is still there — which is the truth — and the control
    // says so.
    setIsMuted(next);

    try {
      const response =
        next === true
          ? await api.PUT("/api/notices/events/{event_id}/mute", {
              params: { path: { event_id: eventId } },
            })
          : await api.DELETE("/api/notices/events/{event_id}/mute", {
              params: { path: { event_id: eventId } },
            });

      // **A 2xx is the server's answer**, and it is the authority on the state — even
      // when `changed` is false, which means the state was already what we asked for.
      if (response.response.status < 200 || response.response.status >= 300) {
        setIsMuted(!next);
        setFailed(true);
        return;
      }

      // **Now the banner moves** — the server has confirmed the mute, so the claim is
      // the server's and not the client's.
      onMuteChange?.(next);
    } catch {
      // **A failed write puts the state back.** The server did not record the mute, so
      // the event is not muted — and the banner never left.
      setIsMuted(!next);
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }, [eventId, isMuted, onMuteChange]);

  return (
    <div className="flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={() => {
          void onToggle();
        }}
        disabled={busy}
        /**
         * **`aria-pressed` carries the state to assistive technology.** The visible text
         * already says it in words; the attribute is what makes the button's *state*
         * announceable, which is the WCAG 4.1.2 rule this control is subject to.
         */
        aria-pressed={isMuted}
        /**
         * **The accessible name is stable, and the state is `aria-pressed`'s.** See
         * `ACCESSIBLE_NAME` above: a button whose name changes with its state says both
         * "press me" and "nothing to press" at once. The explicit `aria-label` is what
         * keeps the accessible name stable while the visible text changes.
         */
        aria-label={ACCESSIBLE_NAME}
        className="min-h-[44px] text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-md)] disabled:cursor-default"
      >
        {isMuted ? LABELS.muted : LABELS.unmuted}
      </button>

      {/*
        The hint. **It is a real element in the DOM**, not a pseudo-element — a helper
        a sighted user reads has to be one a screen reader reads too
        (`EXPERIENCE.md` §`Screen-Reader Specifics`).
      */}
      <p className="text-ink-muted [font:var(--type-scale-meta-sm)]">{HINT}</p>

      {/*
        The failure line. **A bare `aria-live="polite"`, never a second `role="status"`.**
        The Detail Screen's action row already owns this page's one status region — the
        conflict prompt's confirmation (`components/detail/detail-actions.tsx`) — and two
        status regions on a page would make "which one is the page talking?" a question the
        DOM cannot answer.

        **And it is always in the DOM.** A live region added to the page together with its
        text is not announced reliably; a region that is already there and then changes is.
        So the line is present and empty until a write fails, and the *change* to it is what
        gets announced.
      */}
      <p aria-live="polite" className="text-ink-muted [font:var(--type-scale-body-sm)]">
        {failed ? "Couldn't record that. Try again." : ""}
      </p>
    </div>
  );
}
