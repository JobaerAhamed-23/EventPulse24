import Link from "next/link";

/**
 * The Reminder Picker's two non-content states: the plan that is not there, and the
 * read that failed.
 *
 * **Two failures, kept apart.** `missing` is the server's 404 — the event does not
 * exist, is not this user's, or is of the other kind. `unavailable` is a failure to
 * answer. They are different facts about different things, and the page says different
 * things about them.
 *
 * **The copy carries its own instruction**, and the action matches it: one link home,
 * and nothing else. There is no retry on a screen whose retry would hit the same API.
 */
export function ReminderStates({ kind }: { kind: "missing" | "unavailable" }) {
  if (kind === "missing") {
    return (
      <div className="max-w-(--layout-container-reading)" data-reminder-missing>
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
          We couldn&apos;t find that event.
        </h1>
        <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-md)]">
          It may have been removed, or it may not be one of your events.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block rounded-control bg-accent-terracotta px-6 py-3 text-ink-inverse [font:var(--type-scale-meta-md)]"
        >
          Back to Pulse Digest
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-(--layout-container-reading)" data-reminder-unavailable>
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        Couldn&apos;t load your reminders. Back to Pulse Digest.
      </h1>
      <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-md)]">
        Your saved events are safe. This is on our side.
      </p>
      <Link
        href="/"
        className="mt-6 inline-block rounded-control bg-accent-terracotta px-6 py-3 text-ink-inverse [font:var(--type-scale-meta-md)]"
      >
        Back to Pulse Digest
      </Link>
    </div>
  );
}
