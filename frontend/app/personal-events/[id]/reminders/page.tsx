import Link from "next/link";

import { ReminderPicker } from "@/components/reminders/reminder-picker";
import { ReminderStates } from "@/components/reminders/reminder-states";
import { AppShell } from "@/components/shell/app-shell";
import { browserTimeZone } from "@/lib/detail-time";
import { displayName } from "@/lib/display-name";
import { readPersonalEvent } from "@/lib/personal-event-read";
import { readDefaultReminderSlots, readReminderPlan } from "@/lib/reminder-plan-read";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/personal-events/:id/reminders` — FR-20's screen.
 *
 * **The endpoint took `personal_event` from the day it was written; nothing ever sent
 * it.** `GET`/`PUT /api/reminders/{target_kind}/{target_id}` accept `personal_event` or
 * `saved_event` (`delivery/api.py:81`), and `ReminderPicker` has always taken
 * `targetKind` as a prop — but it was mounted exactly once, at
 * `/events/:id/reminders`, hard-coded to `saved_event`. So a personal event could not
 * carry a reminder plan, and FR-20 had no reachable surface.
 *
 * **This is a second route rather than a branch on the existing one.** `/events/:id`
 * serves catalog events: a minted slug renders the public page and everything else is
 * the signed-in Detail Screen, read through `readEventDetail`. A personal event id is
 * not a catalog event id and does not resolve there — so a branch would mean teaching
 * that route about a second kind of thing, on a segment that already carries two
 * surfaces and a documented rendering-mode conflict.
 *
 * **Timeline is the active sidenav item, not Digest.** `personal-event-reminders-desktop.html`
 * says so and gives the reason: *"a Personal Event is reached from the Timeline / Add
 * surfaces, where personal events live, rather than from the public Pulse Digest."*
 *
 * **FR-20 is about defaults, and the mockup is the authority on them.** The plan is
 * attached silently at creation — `personal-event-form.tsx` contains no mention of
 * reminders — so this surface is where the inherited plan first becomes visible. The
 * mockup records that as a deliberate divergence from the PRD's text, not an omission:
 * FR-20 requires that the user *can edit*, not that creation *must disclose*.
 */
export const dynamic = "force-dynamic";

export default async function PersonalEventRemindersPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) {
    const { redirect } = await import("next/navigation");
    redirect(destination);
  }

  const name = session.kind === "signed-in" ? displayName(session.user) : "";
  const email = session.kind === "signed-in" ? session.user.email : "";
  const avatarUrl = session.kind === "signed-in" ? session.user.avatar_url : "";

  // **The plan, the default and the event's name are read together.** The default is
  // what "Reset to default" restores; the name is for the crumb, and the plan payload
  // carries no title — the same split the saved-event route works to.
  const [planRead, defaultSlots, eventRead] = await Promise.all([
    readReminderPlan("personal_event", id),
    readDefaultReminderSlots(),
    readPersonalEvent(id),
  ]);

  const eventName = eventRead.kind === "found" ? eventRead.event.name : "this event";

  const content =
    planRead.kind === "found" ? (
      <>
        <nav aria-label="Breadcrumb" className="text-ink-muted [font:var(--type-scale-meta-sm)]">
          <ol className="flex flex-wrap items-center gap-2">
            <li>
              <Link href="/timeline" className="text-ink-secondary hover:text-ink-primary">
                Timeline
              </Link>
            </li>
            <li aria-hidden="true">·</li>
            <li aria-current="page" className="text-ink-primary">
              {eventName} · Edit reminders
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
              targetKind="personal_event"
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
    <AppShell name={name} email={email} avatarUrl={avatarUrl}>
      {content}
    </AppShell>
  );
}
