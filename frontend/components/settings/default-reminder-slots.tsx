"use client";

/**
 * The Default Reminder Plan editor — the four chips, saved inline.
 *
 * **This is the same chip the per-event picker uses.** `ReminderChip` is reused rather
 * than copied, so the ink-inversion treatment is the picker's treatment by
 * construction and not by agreement — the work item says so explicitly.
 *
 * **The chips here have no deferred state.** There is no target event here, so there
 * are no delivery times and nothing to defer — the settings payload carries
 * `default_reminder_slots` and nothing per-slot. The dimming belongs to a plan that
 * knows when it will send.
 *
 * **The save is inline, and it sends one field.** `NotificationSettingsIn` is a patch:
 * an omitted field is left alone. So a chip change sends
 * `{ default_reminder_slots: [...] }` and **not** the quiet window — and that matters,
 * because the patch's `quiet_hours` field is the one where `null` is a value. A payload
 * that re-sent the window on every chip change could turn quiet hours off by accident.
 *
 * **The save happens on change, not on a button.** There is no Save button on this
 * page; the work item rules one out, and a settings screen with a Save button for a
 * control the user just pressed is a screen that asks for a confirmation it does not
 * need.
 */
import { useCallback, useState } from "react";

import { ReminderChip } from "@/components/reminders/reminder-chip";
import { SaveFeedback } from "@/components/settings/save-feedback";
import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";
import { SLOT_IDS, SLOT_LABELS, SLOT_NAMES } from "@/lib/reminder-slots";

export type DefaultReminderSlotsProps = {
  /** The user's current default slots, as the server stores them. */
  initialSlots: string[];
};

/**
 * The failure line, **verbatim** — and it is the **offline** line.
 *
 * *The work item's own words:* "Couldn't save. We'll try again on your next change."
 *
 * **The API's own refusal is shown instead of this one, when the API made one.** The
 * server validates the plan with the same validator the per-event picker uses, so it
 * can refuse a plan — and it says why in a message written for the user. A generic
 * "we'll try again" would send them round the loop again with the same plan.
 */
const FAILURE = "Couldn't save. We'll try again on your next change.";

export function DefaultReminderSlots({ initialSlots }: DefaultReminderSlotsProps) {
  /** The chips the user has chosen. */
  const [selected, setSelected] = useState<string[]>(initialSlots);
  /** Whether a save is in flight. */
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
   * Saving the chosen slots.
   *
   * **The narrow patch.** Only the slots go up; the quiet window and the digest
   * schedule are omitted, and an omitted field is left alone.
   */
  const save = useCallback(async (slots: string[]) => {
    setBusy(true);
    setFailure(null);
    setSaved(false);
    try {
      const response = await api.PUT("/api/settings/notifications", {
        body: { default_reminder_slots: slots },
      });
      if (response.error) {
        // **The API refused the plan, and it said why** — the same validator the
        // per-event picker uses, with a message written for the user.
        setFailure(saveFailureMessage(response.error, FAILURE));
        return;
      }
      if (!response.data) {
        setFailure(FAILURE);
        return;
      }
      // **The server's answer replaces the server's answer.** The response carries the
      // whole settings surface, and its slots are what was actually saved.
      setSelected(response.data.default_reminder_slots);
      setSaved(true);
    } catch {
      // **The request never reached the API**, so there is nothing to quote.
      setFailure(FAILURE);
    } finally {
      setBusy(false);
    }
  }, []);

  /**
   * The chip's toggle: choose, then save.
   *
   * **The choice is applied locally first and saved after.** The chip is a control the
   * user pressed; it should show the press immediately, and the save happens behind it.
   * If the save fails, **the choice stays** — the failure line says the next change
   * will be retried, and that promise is only true if the state survived.
   *
   * **The save carries the choice the user just made**, not the state before it —
   * so the computed next state is what goes up. Two rapid presses would race, but the
   * control is `disabled` while a save is in flight, so they cannot.
   */
  const onToggle = useCallback(
    (slot: string) => {
      setFailure(null);
      setSaved(false);
      const next = selected.includes(slot)
        ? selected.filter((item) => item !== slot)
        : [...selected, slot];
      setSelected(next);
      void save(next);
    },
    [save, selected],
  );

  return (
    <section aria-label="Default reminder plan" data-default-slots>
      {/*
        **The non-retroactivity sentence.** The opposite is the natural assumption — that
        changing a default rewrites the plans already set — and getting that wrong
        silently rewrites the user's choices. So it is said plainly, above the chips.
      */}
      <p
        className="text-ink-secondary [font:var(--type-scale-body-md)]"
        data-default-slots-nonretroactive
      >
        This is the default for newly saved events. It does not change reminders you have already
        set.
      </p>

      <fieldset className="mt-6 border-0 p-0">
        <legend className="text-ink-primary [font:var(--type-scale-headline-sm)]">
          Remind me:
        </legend>

        <div className="mt-4 flex flex-wrap gap-2" data-default-slots-chips>
          {SLOT_IDS.map((id) => (
            <ReminderChip
              key={id}
              slot={id}
              label={SLOT_LABELS[id]}
              name={SLOT_NAMES[id]}
              selected={selected.includes(id)}
              // **No target event, so no deliveries and nothing to defer.**
              deferred={false}
              note={null}
              custom={false}
              onToggle={() => onToggle(id)}
            />
          ))}
        </div>
      </fieldset>

      <div className="mt-4">
        <SaveFeedback busy={busy} saved={saved} failure={failure} />
      </div>
    </section>
  );
}
