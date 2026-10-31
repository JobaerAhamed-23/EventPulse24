/**
 * The reminder picker — **display-only**.
 *
 * **FR-9's picker belongs to the delivery intent.** `ReminderPlan` exists as a model, but
 * **nothing schedules sends**: the delivery intent has not built the scheduler, and
 * FR-11's email delivery is not wired. A chip that toggles and persists a plan would be
 * a control that appears to work and silently does nothing — worse than no control.
 *
 * **So the chips are `<span>`s, not `<button>`s.** A button that does nothing is a
 * broken control, and a screen reader announcing "5 days before, button" for something
 * unpressable is worse than silence.
 *
 * **The label is FR-9's own default (1d + 1hr) and FR-9's own channel.** ASSUM-3: push
 * is Phase 2, and email is the MVP channel.
 *
 * **The selected chip is an ink inversion, never terracotta.** `EXPERIENCE.md` §4
 * `Input.ReminderSlot`: "no terracotta on this chip; selection is communicated by ink
 * inversion, not by accent".
 */
export function DetailReminder() {
  return (
    <section aria-labelledby="detail-reminders" data-detail-reminder>
      <h2 id="detail-reminders" className="text-ink-primary [font:var(--type-scale-headline-sm)]">
        Reminders
      </h2>

      <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
        Reminders come by email the day before and the hour before.
      </p>

      <ul className="mt-3 flex flex-wrap gap-2" data-detail-reminder-slots>
        {REMINDER_SLOTS.map((slot) => {
          const selected = slot.selected;
          return (
            <li
              key={slot.label}
              className={[
                "rounded-control px-3 py-2 [font:var(--type-scale-meta-sm)]",
                selected
                  ? "bg-ink-primary text-ink-inverse"
                  : "bg-surface-subtle text-ink-secondary",
              ].join(" ")}
            >
              {slot.label}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/**
 * The four slots, and which two are the default.
 *
 * **FR-9's default is 1d + 1hr**, and these are the four slots it offers.
 */
const REMINDER_SLOTS = [
  { label: "5 days before", selected: false },
  { label: "2 days before", selected: false },
  { label: "1 day before", selected: true },
  { label: "1 hour before", selected: true },
] as const;
