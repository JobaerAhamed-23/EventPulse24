import Link from "next/link";

import { ReminderPicker } from "@/components/reminders/reminder-picker";
import { ReminderStates } from "@/components/reminders/reminder-states";
import { AppShell } from "@/components/shell/app-shell";
import { browserTimeZone } from "@/lib/detail-time";
import { displayName } from "@/lib/display-name";
import { readEventDetail } from "@/lib/event-detail-read";
import { readDefaultReminderSlots, readReminderPlan } from "@/lib/reminder-plan-read";
import { getSession } from "@/lib/session";

/**
 * `/events/:id/reminders` — the Reminder Plan editor.
 *
 * **A full route, not a sheet.** Amendment A-21's `reminder-picker-desktop.html` puts
 * this on its own page in the A-8 shell — the 240px sidenav, the brand-only topbar,
 * and the crumb `Digest · {event} · Edit reminders`. It is reached from "Edit reminders"
 * on the Event Detail screen.
 *
 * **Digest is the active sidenav item**, because the picker hangs off Digest in the IA
 * — Detail is reached by tapping a Digest card, and the picker hangs off Detail. The
 * sidenav's rule is widened to cover every path under `/events/`, so the Detail Screen
 * and the picker both mark Digest active.
 *
 * **The reads happen on the server, and the page renders what it was given.** The
 * plan's slots, its per-slot delivery times and the user's default plan are the
 * server's answers. The page does not compute a delivery time, does not compare
 * timestamps against a quiet window, and does not decide which chip dims (AD-10).
 *
 * **The crumb's event name comes from the Detail Screen's own read.** The plan payload
 * carries the slots and the deliveries and no title, so the page reads the event
 * separately — the same read the Detail Screen makes, for the same event.
 */
export const dynamic = "force-dynamic";

export default async function ReminderPickerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const session = await getSession();
  const name = session.kind === "signed-in" ? displayName(session.user) : "";
  const email = session.kind === "signed-in" ? session.user.email : "";

  // **The plan and the default are read together.** The default is what "Reset to
  // default" restores, and the picker needs both before it can render the chips.
  const [planRead, defaultSlots, detailRead] = await Promise.all([
    readReminderPlan("saved_event", id),
    readDefaultReminderSlots(),
    readEventDetail(id),
  ]);

  // **The event's name, for the crumb.** The plan payload does not carry a title, so
  // the page reads the event — and reads it through the Detail Screen's own read, so
  // the crumb's name and the Detail Screen's title are the same string by
  // construction rather than by coincidence.
  const eventName =
    detailRead.kind === "found" || detailRead.kind === "anonymous"
      ? detailRead.detail.event.title
      : "this event";

  const content =
    planRead.kind === "found" ? (
      <>
        <nav aria-label="Breadcrumb" className="text-ink-muted [font:var(--type-scale-meta-sm)]">
          <ol className="flex flex-wrap items-center gap-2">
            <li>
              <Link href="/" className="text-ink-secondary hover:text-ink-primary">
                Digest
              </Link>
            </li>
            <li aria-hidden="true">·</li>
            <li>
              <Link href={`/events/${id}`} className="text-ink-secondary hover:text-ink-primary">
                {eventName}
              </Link>
            </li>
            <li aria-hidden="true">·</li>
            <li aria-current="page" className="text-ink-primary">
              Edit reminders
            </li>
          </ol>
        </nav>

        <div className="mt-8 max-w-(--layout-container-reading)">
          <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
            When should we remind you?
          </h1>
          <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
            Reminders for {eventName}. Up to four per event.
          </p>

          <div className="mt-8">
            <ReminderPicker
              targetId={id}
              targetKind="saved_event"
              initialSlots={planRead.plan.slots}
              deliveries={planRead.plan.deliveries}
              defaultSlots={defaultSlots ?? []}
              timeZone={browserTimeZone() ?? "UTC"}
            />
          </div>
        </div>
      </>
    ) : (
      <ReminderStates kind={planRead.kind} />
    );

  return (
    <AppShell name={name} email={email}>
      {content}
    </AppShell>
  );
}

