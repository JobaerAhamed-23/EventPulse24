import Link from "next/link";

/**
 * The Detail Screen's Reminder section — **a link to the Reminder Picker**.
 *
 * **This section used to display the plan's chips as `<span>`s.** Its own docstring
 * said why: *"nothing schedules sends"* — the delivery intent had not built the
 * scheduler, so a chip that toggled and persisted a plan would have been a control
 * that appeared to work and silently did nothing.
 *
 * **That reason is gone.** The plan is written through `PUT /api/reminders/…`, and the
 * Reminder Picker is where it is edited. So the section became a link, and the
 * display-only component was deleted — a `<span>` that looks like a control and is not
 * one is worse than a link that plainly is.
 *
 * **The section does not show the plan's slots.** The Detail payload carries the
 * event's public facts, the user's own `why_this` breakdown, their saved state and
 * their k-anonymous neighbour bucket — and **not** the reminder slots. So the section
 * says what it can say truthfully: that reminders exist and where they are set. The
 * picker reads the plan for itself, through the endpoint that owns it.
 *
 * **And the section makes no claim about what the plan contains.** An earlier version
 * said *"Reminders come by email the day before and the hour before."* That sentence
 * is **not true of every plan**: the user's default plan may be different, a custom
 * slot may replace a named one, and a plan with no reminders says nothing at all. The
 * Detail Screen cannot check, because the payload does not carry the slots — so a
 * sentence that asserts a specific plan is a sentence that can be wrong, and the page
 * has no way to know. The section now says only what is always true: reminders go by
 * email, and this is where you set them.
 */
export function DetailReminderLink({ eventId }: { eventId: string }) {
  return (
    <section aria-labelledby="detail-reminders" data-detail-reminder>
      <h2 id="detail-reminders" className="text-ink-primary [font:var(--type-scale-headline-sm)]">
        Reminders
      </h2>

      <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
        Reminders go by email. Choose when you&apos;ll hear from us about this event.
      </p>

      <Link
        href={`/events/${eventId}/reminders`}
        className="mt-3 inline-flex min-h-[44px] items-center text-ink-secondary underline underline-offset-4 hover:text-ink-primary [font:var(--type-scale-meta-md)]"
      >
        Edit reminders
      </Link>
    </section>
  );
}
