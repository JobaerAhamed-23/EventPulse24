"use client";

/**
 * The Reminder Plan editor — the picker island.
 *
 * **Four chips, and the one that dims.** The chips are the four named tiers — `5d`,
 * `2d`, `1d`, `1hr` — and a plan may carry one custom slot as well. The chip whose
 * delivery would land inside the user's Quiet Hours **dims to 40% opacity and says when
 * it will actually go out**, and it **stays selectable**: selecting it queues the
 * deferred send.
 *
 * **The dimmed state is the server's flag, never the client's arithmetic.** The plan
 * read carries each slot's `deferred` flag and the instant it was deferred to. The
 * picker renders that flag. It does **not** know the user's quiet window, does not
 * compare timestamps, and does not implement the shift — that would be a second
 * implementation of the Quiet Hours window in TypeScript, with DST and the
 * midnight-crossing case rediscovered there and got wrong differently from the server.
 *
 * **The chips are real controls.** They are `<button>`s inside a `<fieldset>` with an
 * `aria-pressed`, not the mockup's `role="switch"` toggles and not the display-only
 * `<span>`s the Detail Screen used to carry. The Detail Screen's component said out
 * loud that "nothing schedules sends" — **that is no longer true**, and the picker is
 * where the plan is actually written.
 *
 * **The selection is an ink inversion, never a terracotta fill.** See
 * `reminder-chip.tsx` for why.
 *
 * **A zero-slot save is a normal save.** It says *"No reminders. You'll still see this
 * event in Pulse Digest."* — not a warning, not an error. FR-9: "0 slots = no reminders
 * (still in feed)". The plan row survives the save, so "the user chose no reminders"
 * stays distinguishable from "the user never configured a plan".
 *
 * **A failed save keeps the chosen state.** The chips stay as the user left them, and
 * one calm line says *"Couldn't save. We'll try again on your next change."* Reverting
 * the chips would throw away the user's work over a transient failure — and the copy
 * promises a retry on the next change, so the state has to be there to retry with.
 */
import { useCallback, useState } from "react";

import { ReminderChip } from "@/components/reminders/reminder-chip";
import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import {
  CUSTOM_SLOT_MAX_MINUTES,
  CUSTOM_SLOT_MIN_MINUTES,
  MAX_SLOTS,
  SLOT_IDS,
  SLOT_LABELS,
  SLOT_NAMES,
  customMinutes,
  customSlotLabel,
  isCustomSlot,
} from "@/lib/reminder-slots";

export type ReminderPickerProps = {
  /** The target's id — the event's id. */
  targetId: string;
  /** The target's kind — `saved_event` for a saved public event. */
  targetKind: "personal_event" | "saved_event";
  /** The plan's slots, as the server stores them. */
  initialSlots: string[];
  /**
   * The plan's deliveries, as the server computed them.
   *
   * **Each slot's `deferred` flag and the instant it was deferred to.** The picker
   * renders these; it never derives them.
   */
  deliveries: components["schemas"]["ReminderSlotDeliveryOut"][];
  /** The user's default slots, for "Reset to default". */
  defaultSlots: string[];
  /** The browser's own zone — the deferred instants are rendered in it. */
  timeZone: string;
};

export function ReminderPicker({
  targetId,
  targetKind,
  initialSlots,
  deliveries,
  defaultSlots,
  timeZone,
}: ReminderPickerProps) {
  /** The chips the user has chosen. */
  const [selected, setSelected] = useState<string[]>(initialSlots);
  /** The custom slot's minutes, as typed. */
  const [customValue, setCustomValue] = useState("");
  /** The server's refusal of the custom slot, when there was one. */
  const [customError, setCustomError] = useState<string | null>(null);
  /**
   * The plan's slot bound, when the user has hit it.
   *
   * **Its own line, because it is a different kind of refusal.** The custom slot's
   * message is about the *interval* the user typed; this one is about how many
   * reminders a plan may carry. They read the same way to a reader and mean different
   * things to the user, so they are kept apart.
   */
  const [slotError, setSlotError] = useState<string | null>(null);
  /** Whether a save is in flight. */
  const [busy, setBusy] = useState(false);
  /** Whether the last save failed. */
  const [failed, setFailed] = useState(false);
  /** Whether a save succeeded — the quiet "Saved." */
  const [saved, setSaved] = useState(false);
  /**
   * **The deliveries, as the server last described them.**
   *
   * **The server's answer replaces the server's answer.** After a save, the `PUT`'s own
   * response carries the recomputed delivery times — and those are *newer* than the
   * `GET`'s, because the plan's slots may have changed. A picker that kept the
   * original deliveries would show a stale dimmed state for a slot the user has just
   * changed. So the save replaces them wholesale, and the reset clears them, because
   * a reset's chips carry no delivery times of their own.
   */
  const [slotDeliveries, setSlotDeliveries] = useState(deliveries);

  /**
   * The delivery for a slot, if the server described one.
   *
   * **A lookup, not a recomputation.** The server sent one delivery per slot, in the
   * same order as the slots; the picker reads them by slot id.
   */
  const deliveryFor = useCallback(
    (slot: string) => slotDeliveries.find((delivery) => delivery.slot === slot),
    [slotDeliveries],
  );

  /**
   * The note under a deferred chip.
   *
   * **The instant, rendered in the user's own zone.** The server sends a UTC instant;
   * the browser knows the user's zone, and the product's rule is that display-time
   * conversion happens at the presentation edge (AD-6).
   */
  const deferredNote = useCallback(
    (slot: string): string | null => {
      const delivery = deliveryFor(slot);
      if (!delivery?.deferred) return null;
      const instant = delivery.deferred_to ?? delivery.delivery_at;
      if (!instant) return null;
      return `Will deliver at ${formatDeferredInstant(instant, timeZone)}.`;
    },
    [deliveryFor, timeZone],
  );

  /**
   * Whether a chip is selected.
   *
   * **The selected set is the source of truth.** The chips are the four named tiers
   * plus the plan's custom slot, and selection is membership of the set.
   */
  const isSelected = useCallback((slot: string) => selected.includes(slot), [selected]);

  /**
   * Turning a chip on or off.
   *
   * **Selecting a deferred chip is allowed, and queues the deferred send.** The chip is
   * the one that explains itself; refusing to let the user select it would be a control
   * that is present and inert.
   */
  const toggle = useCallback(
    (slot: string) => {
      setSaved(false);
      setFailed(false);

      // **Turning a chip off always makes room**, so the bound message goes with it.
      if (selected.includes(slot)) {
        setSlotError(null);
        setSelected((current) => current.filter((item) => item !== slot));
        return;
      }

      // **The plan's bound, checked before the fifth slot joins it.** The picker knows
      // the plan may carry at most four slots, and it says so rather than letting the
      // save fail for a reason the user would never be told.
      if (selected.length >= MAX_SLOTS) {
        setSlotError(`You can keep up to ${MAX_SLOTS} reminders. Turn one off to add another.`);
        return;
      }

      setSlotError(null);
      setSelected((current) => [...current, slot]);
    },
    [selected],
  );

  /**
   * Adding the custom slot.
   *
   * **The value is sent as typed, and the server decides.** The bound — 15 minutes to
   * 30 days — is the server's, and this does not clamp into it. A silent clamp would
   * save something the user did not ask for; instead the server's refusal is shown
   * inline and the input keeps what was typed, so the fix is one edit away.
   */
  const addCustom = useCallback(() => {
    setSaved(false);
    setFailed(false);
    setSlotError(null);

    const trimmed = customValue.trim();
    if (trimmed === "") {
      setCustomError("Enter how many minutes before the event.");
      return;
    }
    if (!/^\d+$/.test(trimmed)) {
      setCustomError("Enter a whole number of minutes.");
      return;
    }

    const minutes = Number(trimmed);
    if (minutes < CUSTOM_SLOT_MIN_MINUTES || minutes > CUSTOM_SLOT_MAX_MINUTES) {
      setCustomError(
        `Choose between ${CUSTOM_SLOT_MIN_MINUTES} minutes and ${CUSTOM_SLOT_MAX_MINUTES} minutes (30 days) before the event.`,
      );
      return;
    }

    // **A second custom slot is not offered.** The server refuses it, so the picker
    // does not offer it — the existing custom slot has to be turned off first.
    if (selected.some((slot) => isCustomSlot(slot))) {
      setCustomError("You already have a custom reminder. Turn it off to add another.");
      return;
    }

    // **The plan's own bound is checked here, not left to the server.** A plan may
    // carry at most four slots. The picker knows that number — `MAX_SLOTS` — and it
    // refuses the fifth *before* the save, so the user is told which bound they hit
    // instead of pressing Save and getting a bare "Couldn't save."
    //
    // **The alternative is a save that fails for a reason the user cannot see.** The
    // failure copy is deliberately calm and generic; a refusal the picker could have
    // prevented would be a failure it caused. The server still validates — this is the
    // client being honest about a bound it knows, not a second implementation of it.
    if (selected.length >= MAX_SLOTS) {
      setCustomError(null);
      setSlotError(`You can keep up to ${MAX_SLOTS} reminders. Turn one off to add another.`);
      return;
    }

    const slot = customMinutes(minutes);
    setCustomError(null);
    setCustomValue("");
    setSelected((current) => [...current, slot]);
  }, [customValue, selected]);

  /**
   * Turning the custom chip off.
   *
   * **The custom chip is removed from the selected set**, and the input is cleared —
   * otherwise the input would still hold the value that is no longer in the plan.
   *
   * **This is the one toggle that also clears the input.** The named chips have no
   * input to clear; the custom chip does, and a stale number in it would be a value the
   * user thought they had already chosen.
   */
  const clearCustom = useCallback((slot: string) => {
    setSaved(false);
    setFailed(false);
    setSlotError(null);
    setCustomError(null);
    setCustomValue("");
    setSelected((current) => current.filter((item) => item !== slot));
  }, []);

  /**
   * Resetting to the default plan.
   *
   * **The reset restores the chips; it does not save.** The user looks at what the
   * default is and then presses Save, because a reset that wrote on its own would
   * change the plan without being asked to.
   *
   * **The reset clears the deliveries.** The default-plan read returns slot ids and
   * nothing else — there is no per-slot delivery time in it — so the chips it restores
   * carry no dimmed state. The dimming reappears when the save's own response comes
   * back with the server's recomputed times, which is the only honest source for them.
   */
  const reset = useCallback(() => {
    setSaved(false);
    setFailed(false);
    setSlotError(null);
    setCustomError(null);
    setCustomValue("");
    setSelected(defaultSlots);
    setSlotDeliveries([]);
  }, [defaultSlots]);

  /**
   * Saving the plan.
   *
   * **The save sends the chips the user chose, in the order they are shown.** The
   * server validates them, reschedules the pending sends in the same transaction, and
   * answers with the saved plan and its recomputed delivery times.
   */
  const save = useCallback(async () => {
    setBusy(true);
    setFailed(false);
    setSaved(false);
    try {
      const response = await api.PUT("/api/reminders/{target_kind}/{target_id}", {
        params: { path: { target_kind: targetKind, target_id: targetId } },
        body: { slots: selected },
      });

      if (!response.data) {
        setFailed(true);
        return;
      }

      // **The server's answer replaces the server's answer.** The response's slots are
      // what was saved, and its deliveries are the recomputed times for those slots.
      setSelected(response.data.slots);
      setSlotDeliveries(response.data.deliveries);
      setSaved(true);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }, [selected, targetId, targetKind]);

  /**
   * **The custom slot the user has chosen.**
   *
   * **The selected one, saved or not.** A custom slot the user has just added is in
   * `selected`, and it appears as a chip immediately — the user sees their choice
   * before they save it, and turning the chip off takes it back out. The input is
   * offered only when there is no custom slot chosen, so a second one is never
   * offered.
   */
  const selectedCustom = selected.find((slot) => isCustomSlot(slot)) ?? null;

  return (
    <section aria-label="Reminder plan editor" data-reminder-picker>
      <fieldset className="border-0 p-0">
        {/*
          **The legend is the locked microcopy.** "Remind me:" — the work item names it
          as locked, so it is a constant and not a prop.
        */}
        <legend className="text-ink-primary [font:var(--type-scale-headline-sm)]">
          Remind me:
        </legend>

        {/*
          **The empty state.** No chips selected reads "No reminders. You'll still see
          this event in Pulse Digest." — a statement of fact, not a warning. A zero-slot
          plan is a legitimate choice.
        */}
        {selected.length === 0 ? (
          <p
            className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]"
            data-reminder-empty
          >
            No reminders. You&apos;ll still see this event in Pulse Digest.
          </p>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2" data-reminder-chips>
          {SLOT_IDS.map((id) => (
            <ReminderChip
              key={id}
              slot={id}
              label={SLOT_LABELS[id]}
              name={SLOT_NAMES[id]}
              selected={isSelected(id)}
              deferred={deliveryFor(id)?.deferred === true}
              note={deferredNote(id)}
              custom={false}
              onToggle={() => toggle(id)}
            />
          ))}

          {/*
            **The custom chip, when the plan carries one.** It is a chip like any other —
            it can be turned off, and it can be dimmed — because a custom slot is a slot.
          */}
          {selectedCustom ? (
            <ReminderChip
              slot={selectedCustom}
              label={customSlotLabel(selectedCustom)}
              name={customSlotLabel(selectedCustom)}
              selected={isSelected(selectedCustom)}
              deferred={deliveryFor(selectedCustom)?.deferred === true}
              note={deferredNote(selectedCustom)}
              custom
              onToggle={() => clearCustom(selectedCustom)}
            />
          ) : null}
        </div>

        {/*
          **The custom slot's input.**

          **It is offered only when there is no custom slot already.** A second custom
          slot is refused by the server, so the picker does not offer one — and the
          refusal is stated when it is reached, not hidden behind a disabled button
          whose reason is invisible.
        */}
        {selectedCustom === null ? (
          <div className="mt-4 flex flex-wrap items-end gap-3" data-reminder-custom>
            <label className="flex flex-col gap-1">
              <span className="text-ink-secondary [font:var(--type-scale-meta-sm)]">
                Custom reminder
              </span>
              <input
                type="number"
                inputMode="numeric"
                min={CUSTOM_SLOT_MIN_MINUTES}
                max={CUSTOM_SLOT_MAX_MINUTES}
                value={customValue}
                onChange={(event) => {
                  setCustomValue(event.target.value);
                  setCustomError(null);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addCustom();
                  }
                }}
                aria-describedby="reminder-custom-hint"
                className="min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-3 py-2 text-ink-primary [font:var(--type-scale-body-md)]"
              />
            </label>
            <button
              type="button"
              onClick={addCustom}
              className="min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-4 py-2 text-ink-secondary [font:var(--type-scale-meta-md)] hover:text-ink-primary"
            >
              Add slot
            </button>
            <p
              id="reminder-custom-hint"
              className="text-ink-muted [font:var(--type-scale-meta-sm)]"
            >
              Minutes before the event ({CUSTOM_SLOT_MIN_MINUTES}–{CUSTOM_SLOT_MAX_MINUTES}).
            </p>
          </div>
        ) : null}

        {/*
          **The custom slot's inline message.**

          **The bound is surfaced, not clamped.** When the value is out of range the
          input keeps what was typed and one line says why — so the user's own number
          is still there to correct, and the plan is never quietly changed to something
          they did not ask for.
        */}
        {customError ? (
          <p className="mt-2 text-warn-amber [font:var(--type-scale-meta-sm)]" data-reminder-error>
            {customError}
          </p>
        ) : null}

        {/*
          **The plan's slot bound.** A plan may carry at most four reminders, and the
          picker says so when the user reaches the fifth — rather than accepting it
          and failing the save with a message that does not name the reason.
        */}
        {slotError ? (
          <p
            className="mt-2 text-warn-amber [font:var(--type-scale-meta-sm)]"
            data-reminder-slot-error
          >
            {slotError}
          </p>
        ) : null}
      </fieldset>

      {/*
        **The action bar.**

        **"Reset to default" is a ghost button and "Save reminder plan" is the primary
        one** — the mockup's order and the work item's words. The primary is terracotta:
        this is a real, consequential primary action on its own screen, and the accent's
        sanctioned uses include a primary button.
      */}
      <div className="mt-8 flex flex-wrap gap-3" data-reminder-actions>
        <button
          type="button"
          onClick={reset}
          disabled={busy}
          className="min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-4 py-2 text-ink-secondary [font:var(--type-scale-meta-md)] hover:text-ink-primary disabled:cursor-default"
        >
          Reset to default
        </button>
        <button
          type="button"
          onClick={save}
          disabled={busy}
          className="min-h-[44px] rounded-control bg-accent-terracotta px-6 py-2 text-ink-inverse [font:var(--type-scale-meta-md)] disabled:cursor-default"
        >
          Save reminder plan
        </button>
      </div>

      {/*
        **The two messages, and they are both quiet.**

        **Success is "Saved."** — no emoji, no celebration, no fade (EXPERIENCE.md §3).
        It is a `role="status"` region, so a screen reader announces it without stealing
        focus.

        **Failure keeps the chosen state.** The chips are exactly as the user left them,
        and the message says the retry is on their next change — which is only true if
        the state survives.
      */}
      <div role="status" aria-live="polite" className="mt-3">
        {saved ? (
          <p className="text-ink-secondary [font:var(--type-scale-body-sm)]" data-reminder-saved>
            Saved.
          </p>
        ) : null}
      </div>

      {failed ? (
        <p className="mt-3 text-warn-amber [font:var(--type-scale-body-sm)]" data-reminder-failed>
          Couldn&apos;t save. We&apos;ll try again on your next change.
        </p>
      ) : null}
    </section>
  );
}

/**
 * The deferred instant, as the tooltip says it.
 *
 * **"Will deliver at 8:00 am Saturday."** — the exact shape EXPERIENCE.md's worked
 * examples use. The instant is rendered in the user's own zone, because the user's zone
 * is the browser's, and because a time without a zone is not a time the user can act on.
 *
 * **The weekday is included only when it is not today.** "Will deliver at 8:00 am
 * Saturday" is the example; for a delivery later today the weekday would be noise, and
 * the same sentence reads "Will deliver at 8:00 am.".
 */
function formatDeferredInstant(instant: string, timeZone: string): string {
  const date = new Date(instant);
  if (Number.isNaN(date.getTime())) return instant;

  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour: "numeric",
    minute: "2-digit",
    hourCycle: "h23",
    weekday: "long",
  }).formatToParts(date);
  const read = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((part) => part.type === type)?.value ?? "";

  const hour = Number(read("hour"));
  const minute = read("minute");
  const suffix = hour >= 12 ? "pm" : "am";
  const hour12 = hour % 12 === 0 ? 12 : hour % 12;
  const clock = `${hour12}:${minute} ${suffix}`;

  // **The same day, in the user's own zone.** The weekday of the delivery and the
  // weekday of today are compared as zone-local calendar days, not as UTC instants.
  const dayKey = (value: Date): string =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(value);

  if (dayKey(date) === dayKey(now)) return clock;

  return `${clock} ${read("weekday")}`;
}
