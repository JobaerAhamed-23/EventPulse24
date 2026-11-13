"use client";

/**
 * FR-19's **personal-events opt-out** — the control a user actually touches.
 *
 * **What the control is about.** The Pulse Digest carries the user's own saved events
 * alongside the public ones. This is the switch for the first kind: turn it off and the
 * digest is public events only.
 *
 * ---
 *
 * ## The button is a button, and `aria-pressed` carries the state
 *
 * **Not a switch, not a checkbox.** The house pattern is a `<button>` with
 * `aria-pressed`, and it was decided and written down: `reminders/reminder-picker.tsx`
 * records that the Detail Screen used to use `role="switch"` and that the chips are
 * `<button>`s with `aria-pressed` instead. This follows that decision rather than
 * reopening it.
 *
 * **The accessible name is stable, and the visible text is not.** The name stays
 * *"Personal events in the Pulse Digest"* in both states, because a toggle whose name
 * changes with its state says both "press me" and "nothing to press" at once. The
 * *visible* text changes — *"Personal events are in your Pulse Digest"* /
 * *"Personal events are not in your Pulse Digest"* — so a sighted reader sees the state
 * in words rather than in the position of a widget. The state rides on `aria-pressed`
 * for assistive technology (WCAG 4.1.2), and the visible text carries it for everyone
 * else, so **colour is never the sole carrier of meaning** (WCAG 1.4.1).
 *
 * ---
 *
 * ## The save sends the schedule back with the flag
 *
 * **The endpoint has no "change one field" mode.** `DigestPreferenceIn.delivery_time`
 * is a `time` and `.timezone` is a `str` — both **required and non-nullable** — so a
 * request that sends only the flag is a request the API refuses. The schedule travels
 * with the flag, unchanged.
 *
 * **And the city does not.** The endpoint cannot clear a city (a `null` and an omitted
 * field are the same value there), so a client that sent one back would be relying on a
 * field this control does not own. The body is exactly three keys.
 *
 * ---
 *
 * ## The state after a save is the server's answer
 *
 * **The button moves at once** — it has to feel like a control, not a form that waits
 * for a round trip. **But the server's answer replaces the guess.** A user who has
 * never touched the setting has `true` from the server, and a client that decided
 * otherwise would be showing a state the server does not hold.
 *
 * **A failed save puts the state back.** The server did not record the opt-out, so the
 * personal events are still in the digest — and a control claiming otherwise would be
 * claiming something that did not happen.
 *
 * ---
 *
 * ## A user with no schedule has no save to make
 *
 * **The schedule is required, so a user without one cannot use this control at all.**
 * `delivery_time` is `null` for a user who has no `DigestPreference` row yet — a user
 * who has not finished onboarding. Sending `null` is a 422, not a save.
 *
 * **So the control is disabled and says why.** A control that can only fail is worse
 * than a control that is honestly unavailable, and "Set your delivery time first" is a
 * sentence the user can act on where a 422 is not. **The pressed state still reports
 * the server's value** — the server does believe the personal events are included — so
 * the button reads pressed while being unavailable, which is the truth.
 *
 * **And the schedule is one value, not two.** A half-schedule — a time with no zone —
 * is not a state the server produces and not one the endpoint accepts, so it is not
 * representable here: `schedule` is either a complete pair or `null`. That makes the
 * impossible request body unbuildable, rather than leaving it to a guard a refactor
 * could forget.
 */
import { useCallback, useState } from "react";

import { SaveFeedback } from "@/components/settings/save-feedback";
import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";

export type DigestPersonalEventsProps = {
  /**
   * Whether personal events are in the digest. **The server's answer.**
   *
   * The backend defaults this to `true`, so a user who has never touched the setting
   * has `true` — and the control shows what the server believes, not what this client
   * assumes a user who never opened the setting would want.
   */
  initialIncludePersonalEvents: boolean;
  /**
   * The stored schedule — **the time and its zone, together or not at all**.
   *
   * **`null` when the user has no schedule yet.** A user with no `DigestPreference`
   * row — one who has not finished onboarding — has no delivery time and no zone, and
   * the endpoint requires both, so there is nothing this control could send.
   *
   * **One value rather than two, and that is deliberate.** A half-schedule — a time
   * with no zone, or a zone with no time — is not a state the server can produce and
   * not a state the endpoint can accept, and modelling it as two independent nullable
   * fields would make it *representable*. Here it is not: `null` is the only way to
   * have no schedule, and a present schedule always has both halves. **The type makes
   * the impossible body unbuildable**, rather than leaving it to a guard that a
   * refactor could forget.
   */
  schedule: { deliveryTime: string; timezone: string } | null;
};

/**
 * The failure line, **verbatim** — and it is the **offline** line.
 *
 * *"Couldn't save."* — the same line the quiet-hours and delivery-time routes use,
 * because the same thing happened: the save did not take.
 *
 * **The API's own refusal is shown instead of this one, when the API made one.** A
 * refusal the server wrote for the user says what to change, and a generic line
 * throws that away.
 */
const FAILURE = "Couldn't save.";

/**
 * The button's stable accessible name.
 *
 * **It names the thing being controlled, not the action.** A name that changed with the
 * state would say both "press me" and "nothing to press" — and "Personal events are not
 * in your Pulse Digest" is a status dressed as a button label, so a reader who
 * believed it would have nothing to press.
 *
 * **So the name is fixed and the state rides on `aria-pressed`.** See
 * `detail-mute-control.tsx:92-104`, which is the same argument for the same rule.
 */
const ACCESSIBLE_NAME = "Personal events in the Pulse Digest";

/**
 * The two visible texts.
 *
 * **Two sentences, and both are statements about the world.** Neither is an
 * instruction — the instruction is the button's job, and the button's name says what
 * pressing it will do.
 */
const VISIBLE = {
  included: "Personal events are in your Pulse Digest",
  excluded: "Personal events are not in your Pulse Digest",
} as const;

/**
 * The line shown when the control cannot be used.
 *
 * **It says what to do, not what is wrong.** "Set your delivery time first" names the
 * next step. It is not a failure — nothing was attempted — so it is not the failure
 * line, and it is not shown in the failure region.
 */
const NO_SCHEDULE = "Set your delivery time first.";

/**
 * The body of the opt-out write — **or `null`, when there is nothing to send.**
 *
 * **This is where the "exactly three keys" rule lives**, and it is a pure function so
 * that the rule can be tested directly rather than inferred from a click.
 *
 * **A schedule of `null` produces no body at all.** The endpoint requires the delivery
 * time and the zone, so a request without them is a request the API refuses — and a
 * refusal the user can do nothing about is worse than not asking. Returning `null`
 * makes "there is nothing to send" a value the caller has to deal with, rather than a
 * body that quietly carries a `null` the server would reject.
 *
 * **The city is not here.** The endpoint cannot clear a city — a `null` and an omitted
 * field are the same value there — so a client that sent one back would be relying on
 * a field this control does not own.
 */
export function digestPreferenceBody(
  schedule: DigestPersonalEventsProps["schedule"],
  includePersonalEvents: boolean,
): { include_personal_events: boolean; delivery_time: string; timezone: string } | null {
  if (schedule === null) return null;
  return {
    include_personal_events: includePersonalEvents,
    // **The schedule travels with the flag, unchanged.** It is required, and it is not
    // this control's to change — the same rule the delivery-time control follows:
    // "Both or neither."
    //
    // **Both halves, because the schedule is one value.** A half-schedule is not
    // representable, so this body cannot be half-built.
    delivery_time: schedule.deliveryTime,
    timezone: schedule.timezone,
  };
}

export function DigestPersonalEvents({
  initialIncludePersonalEvents,
  schedule,
}: DigestPersonalEventsProps) {
  /**
   * The opt-out, as the user has it.
   *
   * **The server's answer is the starting state.** The control moves it locally so the
   * button feels like a control, and the server's answer replaces it afterwards.
   */
  const [included, setIncluded] = useState(initialIncludePersonalEvents);
  /** Whether a save is in flight, so the button cannot be pressed twice. */
  const [busy, setBusy] = useState(false);
  /**
   * The failure line to show, or `null`.
   *
   * **The message, not a flag** — so the API's own refusal can be shown verbatim.
   */
  const [failure, setFailure] = useState<string | null>(null);
  /** Whether the last save succeeded. */
  const [saved, setSaved] = useState(false);

  /**
   * Whether this control can save at all.
   *
   * **The schedule is the answer, and the answer is all-or-nothing.** A present
   * schedule has both halves, so this is not two checks — it is one.
   */
  const canSave = schedule !== null;

  const onToggle = useCallback(async () => {
    // **Without a schedule there is nothing to send.** The endpoint requires the
    // delivery time and the zone, so a request without them is a request the API
    // refuses — and a refusal the user can do nothing about is worse than not asking.
    //
    // **The button is disabled without a schedule, so this line is a second gate, not
    // the only one.** That is deliberate: the disable is the affordance, and this is
    // the guarantee. A keyboard shortcut, a queued click, or a future refactor that
    // re-enables the button cannot get past it.
    const body = digestPreferenceBody(schedule, !included);
    if (body === null) return;

    const next = !included;

    setBusy(true);
    setFailure(null);
    setSaved(false);
    // **The optimistic move — but only for the button.** It flips at once, so the
    // control feels like a control.
    setIncluded(next);

    try {
      const response = await api.PUT("/api/personal/onboarding/digest-preference", { body });
      if (response.error) {
        // **The API refused it, and it said why.**
        setFailure(saveFailureMessage(response.error, FAILURE));
        setIncluded(!next);
        return;
      }
      if (!response.data) {
        setFailure(FAILURE);
        setIncluded(!next);
        return;
      }
      // **The server's answer replaces the server's answer.**
      setIncluded(response.data.digest.include_personal_events);
      setSaved(true);
    } catch {
      // **The request never reached the API**, so there is nothing to quote.
      setFailure(FAILURE);
      setIncluded(!next);
    } finally {
      setBusy(false);
    }
  }, [included, schedule]);

  return (
    <section aria-label="Personal events" data-digest-personal-events>
      <button
        type="button"
        onClick={() => {
          void onToggle();
        }}
        disabled={busy || !canSave}
        /**
         * **`aria-pressed` carries the state to assistive technology.** The visible text
         * already says it in words; the attribute is what makes the button's *state*
         * announceable, which is the WCAG 4.1.2 rule this control is subject to.
         */
        aria-pressed={included}
        /**
         * **The accessible name is stable, and the state is `aria-pressed`'s.** See
         * `ACCESSIBLE_NAME` above.
         */
        aria-label={ACCESSIBLE_NAME}
        className="min-h-[44px] text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-md)] disabled:cursor-default"
      >
        {included ? VISIBLE.included : VISIBLE.excluded}
      </button>

      {/*
        The line under the control, when the control cannot be used.

        **It is a real element in the DOM**, not a pseudo-element — a helper a sighted
        user reads has to be one a screen reader reads too.
      */}
      {canSave ? null : (
        <p className="text-ink-muted [font:var(--type-scale-meta-sm)]" data-no-schedule>
          {NO_SCHEDULE}
        </p>
      )}

      <div className="mt-4">
        <SaveFeedback busy={busy} saved={saved} failure={failure} />
      </div>
    </section>
  );
}
