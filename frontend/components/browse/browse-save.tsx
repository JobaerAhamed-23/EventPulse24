"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

import { spentQuotaLabel } from "@/lib/browse-labels";
import type { BrowseQuota } from "@/lib/browse-read";
import { readCapDetails } from "@/lib/cap-details";
import { UPGRADE_HREF } from "@/components/upgrade/upgrade-prompt";
import { api } from "@/lib/backend-client";

/**
 * The inline Save button — `Component.Button.Save.Inline`.
 *
 * **The one element a Browse card adds to the digest card anatomy.** The card body is
 * not a button; Save is. It is a client island because it holds a state machine and
 * talks to the API, and the card it sits on is a server component.
 *
 * **It uses the endpoints that already exist.** `POST` and `DELETE
 * /api/personal/saved-events/{catalog_event_id}` — the same pair the Detail Screen's
 * action row uses, with the same call shape and no request body. **No new save endpoint
 * is added**, and the backend is untouched.
 *
 * **It decides nothing the server decided.** The two refusals are told apart by
 * `code`, never by a string match of the message: the backend owns the wording and will
 * change it, and a client that matched on prose would break on a reword.
 *
 * | Answer | What happened | What the button says |
 * |---|---|---|
 * | 2xx | The save happened. | "Saved ✓" |
 * | 409 `scheduling_conflict` | **The save row was written, and the pair is active.** The event *is* saved; there is a choice waiting at the detail screen. | "Saved ✓", plus a conflict line |
 * | 409 `save_cap_reached` | **The save did not happen.** The gate refused before any row existed. | "Save", plus an upgrade line |
 * | anything else | The request failed. | "Save", plus a quiet failure line |
 *
 * **A 409 clash is not a failed save.** The server writes the row and *then* finds the
 * clash (`api.py:398` — "the save row exists, the pair is active, and the flow is
 * waiting for a choice"). Saying "couldn't save that" would be false, and putting the
 * button back to "Save" would invite the reader to press it again and receive the same
 * 409.
 *
 * **A cap is final and is not retried.** The allowance does not come back from pressing
 * the button again; a button that keeps trying is the thing this surface avoids.
 *
 * **Both refusals are inline, in the normal flow, under the button.** No `role="dialog"`,
 * no `aria-modal`, no overlay, no portal, no toast. `save_cap.py` puts it plainly: *"A
 * cap that interrupts with a modal is a cap that trains people to dismiss prompts."* The
 * line is `role="status"`, not `role="alert"` — a refusal is information, not an
 * emergency, and an assertive region would interrupt a screen reader mid-sentence.
 *
 * **The quota wall is read from the payload, never re-derived.** `quota.cap` is `null`
 * for a Pro account, and `used >= cap` means the allowance is spent. The client never
 * refuses a save on the strength of a string it rendered: the server's gate is the gate,
 * and this is a sign above it — the same rule `lib/browse-labels.ts`'s `quotaNote()`
 * states for the hero's note.
 *
 * **`Esc` resets the label, and it does not promise the save did not happen.** There is
 * no server-side rollback: `save_event()` writes inside `transaction.atomic()` and the
 * transaction commits when it returns — no abort path, no compensating write, no
 * cancellation hook. So cancelling an in-flight save can honestly mean only "stop
 * showing Saving…" and "ignore the answer". Claiming the event was not saved would be a
 * guarantee the server does not make.
 */

/** How long the "Saved ✓" label stays put before the button accepts another press. */
const SAVED_LOCKOUT_MS = 1500;

export type BrowseSaveProps = {
  /** The **catalog** event id — the path parameter the endpoint takes. */
  eventId: string;
  /** The event's title, for the button's accessible name. */
  eventName: string;
  /** The event's public slug, for the "Open" link on a conflict refusal. */
  slug: string;
  /** Whether the user has already saved it. The **first paint's** state. */
  saved: boolean;
  /**
   * The save allowance, as the payload states it.
   *
   * **The generated type, not a hand-written copy.** `BrowseQuota` is
   * `components["schemas"]["BrowseQuotaOut"]` — the contract the server actually
   * published — so the shape here cannot drift from the payload that carries it.
   */
  quota: BrowseQuota;
};

/**
 * **The state machine's states.**
 *
 * `idle` — the ordinary "Save" button.
 * `saving` — a request is in flight.
 * `saved` — the event is saved.
 *
 * **The wall is not a fourth state.** "The allowance is spent" is a fact about the
 * payload, not a stage the machine reaches, so it is derived at render — a button that
 * became `blocked` by a state change could get stuck there when the allowance reset,
 * and a reset the payload never announces would leave it stuck forever.
 */
type SaveState = "idle" | "saving" | "saved";

export function BrowseSave({ eventId, eventName, slug, saved, quota }: BrowseSaveProps) {
  // **The first paint is the payload's.** `is_saved` comes from the API, so an
  // already-saved event renders "Saved ✓" on the first paint rather than flashing
  // "Save" and correcting itself a moment later.
  const [state, setState] = useState<SaveState>(saved ? "saved" : "idle");
  const [cap, setCap] = useState<number | null>(null);
  const [conflict, setConflict] = useState(false);
  const [failed, setFailed] = useState(false);
  // **The lockout is a flag, not a timestamp read during render.** `Date.now()` in a
  // render is a lie waiting to happen: the component does not re-render when the clock
  // passes the deadline, so the button would stay disabled forever. A flag, cleared by
  // a timer, re-renders exactly when the lockout ends.
  const [locked, setLocked] = useState(false);
  // **The generation counter abandons an answer the reader cancelled.** A request that
  // was in flight when `Esc` was pressed must not write its answer over the label the
  // reader asked for.
  const generation = useRef(0);
  // **The lockout's timer**, so it can be cleared when the island unmounts.
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current !== null) clearTimeout(timer.current);
    };
  }, []);

  /**
   * **Whether the allowance is spent.**
   *
   * **A Pro account has no wall.** `cap` is `null` for Pro — not a very large number —
   * and `is_pro` says so as well. **Both are read, and either one is enough**, because
   * Django Ninja omits the field when it is null and a missing `cap` is the same answer
   * arriving by two routes. `quotaNote()` in `lib/browse-labels.ts` reads the same two
   * facts the same way; two rules for one fact would be a rule that could drift.
   */
  const isPro = quota.is_pro || quota.cap === null || quota.cap === undefined;
  const capValue = quota.cap ?? 0;
  const spent = !isPro && quota.used >= capValue;

  /**
   * **The button's label, and its colour.**
   *
   * "Saving…" is in ink-muted — the request is in flight and nothing has happened yet.
   * "Saved ✓" is in `color.signal.success`. "Save" is in the ordinary ink.
   *
   * **Exactly one colour class, always.** A button that carried two colour utilities at
   * once would resolve them by CSS emission order rather than by intent — and Tailwind
   * sorts utilities by their own name, not by the order they appear in `className`. The
   * review measured it against the shipped CSS: `text-ink-faint` is emitted *before*
   * `text-ink-secondary`, so a button carrying both rendered in the ordinary ink and the
   * faint one was dead. The colour is chosen here, once, and it is the only one that
   * reaches the DOM.
   */
  const label = state === "saving" ? "Saving…" : state === "saved" ? "Saved ✓" : "Save";
  const labelColour =
    state === "saving"
      ? "text-ink-muted"
      : state === "saved"
        ? "text-signal-success"
        : "text-ink-secondary";

  /**
   * **Whether the button accepts a press.**
   *
   * **Three separate reasons, and they are not the same reason.** A request is in
   * flight; the label is inside its lockout; the allowance is spent. The first two are
   * transient and the third is not, and the spent one renders a *different* label — so
   * the button's appearance and its behaviour cannot drift apart.
   *
   * **A saved event still accepts a press.** The wall is about *new* saves; an
   * already-saved event can be un-saved whether or not the allowance is spent, and a
   * reader whose only option left is "un-save" must not be locked out of it.
   */
  const blocked = spent && state !== "saved" && state !== "saving";
  const disabled = state === "saving" || blocked || locked;

  /**
   * **The allowance, spent.**
   *
   * **The label is the payload's numbers.** `1 of 1 save used today` — the ceiling and
   * the count, as the API states them.
   */
  const spentLabel = spentQuotaLabel({ used: quota.used, cap: quota.cap });

  /**
   * **The lockout.**
   *
   * **The label stays "Saved ✓" for at least 1500ms.** The state moves to `saved`
   * immediately — that is the morph — and the *press* is what the lockout holds back.
   * A reader who taps twice quickly gets one save and one label, not a flicker.
   *
   * **The flag is cleared by a timer, not read from the clock during render.** A render
   * does not happen when the clock passes a deadline, so a `Date.now()` comparison would
   * leave the button disabled until something else re-rendered it.
   */
  function beginLockout() {
    setLocked(true);
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setLocked(false);
      timer.current = null;
    }, SAVED_LOCKOUT_MS);
  }

  const onSave = useCallback(async () => {
    // **The in-flight guard is here, in the handler.** A `<button disabled>` is not a
    // guarantee — a click dispatched in the same tick as the state change can still
    // arrive — and the save is idempotent server-side, so a duplicate is safe but
    // wasteful. The guard costs one line.
    if (state === "saving" || blocked) return;
    // **The lockout holds the press back, not the label.** The morph happened; this is
    // the 1500ms in which a second press would flicker the label and send a second
    // request.
    if (locked) return;

    setFailed(false);
    setCap(null);
    setConflict(false);

    // **Un-saving is the other half of the machine.** A second tap from "Saved ✓" is
    // the confirmation — there is no destructive dialog, and no undo toast. The label
    // change *is* the feedback, because the thing being removed is something the
    // reader put there themselves.
    if (state === "saved") {
      const mine = generation.current;
      setState("saving");
      try {
        const response = await api.DELETE("/api/personal/saved-events/{catalog_event_id}", {
          params: { path: { catalog_event_id: eventId } },
        });
        if (mine !== generation.current) return;
        if (response.response.status >= 200 && response.response.status < 300) {
          setState("idle");
        } else {
          setFailed(true);
          setState("saved");
        }
      } catch {
        if (mine !== generation.current) return;
        setFailed(true);
        setState("saved");
      }
      return;
    }

    const mine = generation.current;
    setState("saving");
    try {
      const response = await api.POST("/api/personal/saved-events/{catalog_event_id}", {
        params: { path: { catalog_event_id: eventId } },
      });
      // **A response the reader cancelled is not written to the label.** The generation
      // counter moved, so this answer belongs to a machine that no longer exists.
      if (mine !== generation.current) return;

      const status = response.response.status;
      const error = response.error;

      if (status >= 200 && status < 300) {
        setState("saved");
        beginLockout();
        return;
      }

      // **The 409 is one of two refusals, and the `code` says which.** `scheduling_conflict`
      // carries the pair; `save_cap_reached` carries the cap and an upgrade sentence.
      // They share a status code and nothing else.
      if (status === 409 && error?.code === "scheduling_conflict") {
        // **The save stands.** The row was written and the pair is active, so the button
        // says "Saved ✓" — and the line points at the detail screen, where the choice
        // can be made.
        setState("saved");
        setConflict(true);
        beginLockout();
        return;
      }

      // **The cap is a refusal, not a failure.** The save did not happen, so the button
      // goes back to "Save" — and it is not retried.
      const capDetails = readCapDetails(error);
      if (capDetails !== null) {
        setState("idle");
        setCap(capDetails.cap);
        return;
      }

      setState("idle");
      setFailed(true);
    } catch {
      if (mine !== generation.current) return;
      setState("idle");
      setFailed(true);
    }
  }, [blocked, eventId, locked, state]);

  /**
   * **`Esc` abandons an in-flight save.**
   *
   * **It resets the label, and it does not claim the save did not happen.** There is no
   * server-side rollback — `save_event()` commits inside `transaction.atomic()` and
   * there is no abort path — so the honest scope is the client-side label. The
   * generation counter moves, which makes the in-flight answer a no-op.
   *
   * **The listener is on the wrapper, not on the button.** The button is `disabled`
   * while a request is in flight — that is what the "Saving…" state means — and **a
   * disabled button fires no key events at all.** So a handler on the button would
   * never run in the one case it exists for: the cancel is only reachable *during* the
   * save. The wrapper is never disabled, and the event bubbles up to it.
   */
  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key !== "Escape") return;
      if (state !== "saving") return;
      generation.current += 1;
      setState("idle");
    },
    [state],
  );

  /**
   * **The button's accessible name.**
   *
   * **The visible label stays "Save"; the accessible name says which event.** A page of
   * a dozen cards each with a "Save" button gives a screen reader a dozen identical
   * controls, and the name is the only thing that tells them apart.
   */
  const accessibleName =
    state === "saved" ? `${eventName} is saved to your Pulse` : `Save ${eventName} to my Pulse`;

  return (
    <div className="flex flex-col items-end gap-1" data-browse-save onKeyDown={onKeyDown}>
      {/*
        **The button.**
        *
        **It is a real `<button>`, not a `<div role="button">`.** That is what makes
        **`Enter` and `Space` both trigger it** without a keydown handler, and what makes
        the focus ring and the disabled state the browser's own.
        *
        **The focus ring is 2px terracotta at AA**, the codebase's house idiom, and it
        * is `focus-visible` so it appears for a keyboard reader and not for a mouse
        * click.
      */}
      <button
        type="button"
        onClick={() => {
          void onSave();
        }}
        disabled={disabled}
        aria-label={accessibleName}
        // **The morph is announced, and the focus does not move.** The reader who
        // pressed the button is still on it, and the live region says what changed.
        aria-live="polite"
        title={blocked ? "Upgrade for unlimited saves" : undefined}
        className={[
          "rounded-control border border-border-subtle px-3 py-1",
          "[font:var(--type-scale-meta-md)]",
          // **The wall's own colour, chosen instead of the ordinary one.** A spent
          // allowance must *look* spent, and the muted ink is the design's word for
          // "available but not yours to take". This is a replacement, not an addition:
          // carrying both would leave the winner to CSS emission order, and Tailwind
          // emits `text-ink-faint` first — so the ordinary ink would have won and the
          // button would have looked live while refusing every press.
          blocked ? "text-ink-faint" : labelColour,
          // **No transition class.** The product's only transition is `.fade-in`, and
          // `tests/architecture.test.ts` bans every Tailwind `transition-*`/`duration-*`/
          // `ease-*` class in a `.tsx`.
          "fade-in",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-terracotta",
          "disabled:cursor-default",
        ].join(" ")}
        data-browse-save-button
      >
        {blocked ? spentLabel : label}
      </button>

      {/*
        **The two refusals, inline, under the button.**
        *
        **They are `role="status"`, not `role="alert"`.** A refusal is information, not
        an emergency; an assertive region would interrupt a screen reader mid-sentence.
        *
        **They are not modals and they are not toasts.** They render in the normal flow,
        in the card, under the button — no overlay, no portal, no dismissal.
      */}
      {cap !== null ? (
        <p
          role="status"
          className="max-w-[260px] text-right text-ink-muted [font:var(--type-scale-meta-sm)]"
          data-browse-save-cap
        >
          {`You've used your ${cap} free save today. `}
          {/*
            **The "Upgrade" link.** `Text.Meta` — a meta-sized link, not a button. The
            refusal is information and the link is the way out of it; a filled button
            would turn a quiet line into an interruption, which is what the item forbids.
            *
            **It points at the pricing page**, which is the one place in the product that
            sells anything — the same target `components/upgrade/upgrade-prompt.tsx`
            uses.
          */}
          <Link
            href={UPGRADE_HREF}
            className="text-accent-terracotta underline underline-offset-4"
            data-browse-save-upgrade
          >
            Upgrade
          </Link>
        </p>
      ) : null}

      {conflict ? (
        <p
          role="status"
          className="max-w-[260px] text-right text-ink-muted [font:var(--type-scale-meta-sm)]"
          data-browse-save-conflict
        >
          Conflicts with your saved dinner.{" "}
          <Link
            href={`/events/${slug}`}
            className="text-accent-terracotta underline underline-offset-4"
            data-browse-save-open
          >
            Open
          </Link>
        </p>
      ) : null}

      {failed ? (
        <p
          role="status"
          className="max-w-[260px] text-right text-ink-muted [font:var(--type-scale-meta-sm)]"
          data-browse-save-failed
        >
          Couldn&apos;t save that. Try again.
        </p>
      ) : null}
    </div>
  );
}
