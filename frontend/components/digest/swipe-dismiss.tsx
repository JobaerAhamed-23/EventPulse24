"use client";

/**
 * The swipe-to-dismiss control on the Pulse Card (FR-25).
 *
 * ## The swipe is the primary affordance, and it is not the only one
 *
 * The mockup's gesture is a swipe down: the user pushes the card away because they are
 * not interested in it. That gesture is the product's — a card that responds to the
 * push is what makes FR-25 feel like part of the digest rather than a form on it.
 *
 * **But a gesture-only control is invisible to a keyboard user and unreachable by a
 * screen reader.** The PRD's §11.5 gate runs `axe-core` over these surfaces, and no
 * automated check catches a missing gesture — but a human reviewer would, and a
 * keyboard user would not get the feature at all. So there is a **button with the same
 * action**, and it is deliberately the *secondary* affordance: quiet text, low contrast,
 * in the card's footer, where a thumb looking for the card's details will not find it
 * first.
 *
 * **The button says what it does in the product's words.** The card never says
 * "dismiss" — that is a word about the product's internals. It says **"Show me less of
 * this"**, which is the *question the prompt asks*, so the button and the prompt speak
 * the same language.
 *
 * ## The card does not decide what a dismissal means
 *
 * The client sends one event id and renders what comes back. Whether the dismissal
 * counted toward a cluster, whether three similar events have now been dismissed, and
 * what the prompt says are **all server facts** — the embedding cosine, the window, the
 * three-distinct-events rule and the rage-dismiss guard are the backend's arithmetic, and
 * a client that counted for itself would be answering the server's question with a
 * different number.
 *
 * **A failed write dismisses nothing.** The card stays where it is. A card that
 * vanished without a recorded dismissal would come back in the next digest with no
 * explanation.
 *
 * ## Why a swipe that fails does not leave the card broken
 *
 * The gesture is *provisional* until the server answers. The card follows the finger
 * while the user pushes it, and **springs back if the write fails** — because a card
 * stuck half off-screen with no way to restore it is the user having lost a card with
 * no way to get it back. There is no animation class for the spring: the product has
 * exactly one transition, `.fade-in`, and `styles/motion.test.ts` fails the suite on any
 * other.
 */
import { useCallback, useRef, useState } from "react";

import type { components } from "@/lib/api/schema";
import { recordDismissal } from "@/lib/dismissal-write";

export type SwipeDismissProps = {
  /** The catalog event's id — the only thing the server needs. */
  eventId: string;
  /** The event's title, for the button's accessible name. */
  title: string;
  /** Called when the server says a dismissal was recorded. */
  onDismissed: (eventId: string) => void;
  /**
   * Called when the server says the prompt is due.
   *
   * **The prompt's copy is the server's.** This callback carries the server's `prompt`
   * object and nothing else — the parent renders it, and the parent does not write a
   * word of it.
   */
  onPromptDue: (prompt: components["schemas"]["MutePromptOut"]) => void;
  /** The card itself. The gesture wraps it, so the card is what moves. */
  children: React.ReactNode;
};

/**
 * How far the card must be pushed down before the gesture counts, in pixels.
 *
 * **It is a threshold, not a hair-trigger.** A card that dismissed on a three-pixel
 * drag would dismiss on every scroll that started on it — and the user would lose
 * events they meant to read. The threshold is roughly a fifth of a card's height, and
 * the *vertical* distance is what counts: a horizontal drag is the reader's scroll.
 */
export const SWIPE_THRESHOLD_PX = 64;

/**
 * The most the card may travel while the finger is down.
 *
 * **The card follows the finger, but it does not follow it forever.** A card dragged
 * 600px down is a card that has left the viewport, and the card below it would jump
 * when the drag ends. So the travel is capped — the card moves far enough to say
 * "yes, this is a dismissal", and no further.
 */
export const MAX_TRAVEL_PX = 140;

export function SwipeDismiss({
  eventId,
  title,
  onDismissed,
  onPromptDue,
  children,
}: SwipeDismissProps) {
  const [dismissed, setDismissed] = useState(false);

  /**
   * **The gesture's own state lives in refs, not in state.**
   *
   * The pointer position changes on every frame of a drag, and a state update for each
   * one would re-render the whole card on every frame — which would fight the finger
   * and make the drag feel sticky. So the *travel* is written straight to the DOM
   * through a ref, and the state only ever holds the two things that are not per-frame:
   * whether the card has been dismissed, and whether a write is in flight.
   */
  const wrapRef = useRef<HTMLDivElement>(null);
  const startYRef = useRef(0);
  const travelRef = useRef(0);
  const draggingRef = useRef(false);
  const busyRef = useRef(false);

  /**
   * **The write.**
   *
   * **One path, for the gesture and the button alike.** The button does not synthesise
   * a swipe; it calls this, so there is exactly one implementation of "dismiss this
   * event" and exactly one place where the server's answer is read.
   */
  const dismiss = useCallback(async () => {
    // **A second swipe while the first is in flight is ignored.** The server is
    // idempotent per event, so a repeat would not corrupt anything — but it would
    // open the prompt twice, and a prompt that appears twice is the nag FR-25's guard
    // exists to prevent.
    if (busyRef.current) return;
    busyRef.current = true;
    setDismissed(true);

    const outcome = await recordDismissal(eventId);

    if (outcome === null) {
      // **The write failed, so nothing was dismissed.** The card comes back, because a
      // card the user cannot get back is worse than a card that stayed.
      busyRef.current = false;
      setDismissed(false);
      wrapRef.current?.style.removeProperty("transform");
      travelRef.current = 0;
      return;
    }

    onDismissed(eventId);
    if (outcome.prompt_due && outcome.prompt !== null) onPromptDue(outcome.prompt);
  }, [eventId, onDismissed, onPromptDue]);

  /**
   * **The gesture's start.**
   *
   * **A touch that begins on a control is not a swipe.** The card is covered in
   * buttons — the confidence pulse, the source badge, the share control — and a drag
   * that began on one of them would be swallowed by the button and the card would jump.
   * So the gesture refuses to start when the touch began on something interactive.
   */
  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (dismissed || busyRef.current) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("button, a, input, select, textarea")) return;
      startYRef.current = event.clientY;
      travelRef.current = 0;
      draggingRef.current = true;
    },
    [dismissed],
  );

  const onPointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!draggingRef.current || dismissed) return;
      const travel = event.clientY - startYRef.current;
      // **Only downward travel counts.** An upward drag is a scroll gesture, and the card
      // must not follow it — otherwise the card would chase the reader's scroll.
      if (travel <= 0) return;
      const capped = Math.min(travel, MAX_TRAVEL_PX);
      travelRef.current = capped;
      wrapRef.current?.style.setProperty("transform", `translateY(${capped}px)`);
    },
    [dismissed],
  );

  const onPointerUp = useCallback(() => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    if (travelRef.current >= SWIPE_THRESHOLD_PX) {
      void dismiss();
      return;
    }
    // **Not far enough: the card goes back.** There is no transition class for the
    // return — the product has exactly one transition, `.fade-in`.
    travelRef.current = 0;
    wrapRef.current?.style.removeProperty("transform");
  }, [dismiss]);

  return (
    <div
      ref={wrapRef}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      data-swipe-dismiss={eventId}
      className="flex flex-col"
    >
      {children}

      {/*
        **The button.**

        **It is quiet on purpose.** It is `text-ink-muted`, underlined like a text link,
        and it sits in the card's footer below the trust signals — so the swipe stays the
        thing a touch user reaches for first, and the button is the thing a keyboard
        user reaches for at all.

        **It is outside the card's stretched link.** The link is `absolute inset-0`
        inside the card, so a button inside the card's flow would be covered by it and
        could never be pressed — the same inertness the trust row's comment records.
        Here the button is a sibling of the card, so it is genuinely clickable.
      */}
      <div className="mt-2 flex justify-end">
        <button
          type="button"
          onClick={() => void dismiss()}
          disabled={dismissed}
          aria-label={`Show me less of this${title ? `: ${title}` : ""}`}
          data-dismiss-button={eventId}
          className="min-h-[44px] px-2 text-ink-muted underline underline-offset-4 [font:var(--type-scale-meta-sm)] disabled:opacity-60"
        >
          Show me less of this
        </button>
      </div>
    </div>
  );
}
