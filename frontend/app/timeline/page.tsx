import { redirect } from "next/navigation";

import { AppShell } from "@/components/shell/app-shell";
import { DayNavigator, WeekNavigator } from "@/components/timeline/timeline-navigator";
import { TimelinePanel } from "@/components/timeline/timeline-panel";
import { QuietWeek, TimelineError } from "@/components/timeline/timeline-states";
import { displayName } from "@/lib/display-name";
import { getSession, homeRoute } from "@/lib/session";
import { addDays, isLocalDate, today, weekRange } from "@/lib/timeline-dates";
import { readTimeline } from "@/lib/timeline-read";

/**
 * `/timeline` — the Unified Timeline (FR-32, `Surface.Timeline`).
 *
 * **A read-only view of the week.** The page renders what the server sent: seven local
 * days, each a time-ordered list of blocks, with the conflict indicator already
 * decided. It buckets nothing, sorts nothing, and decides no conflict (AD-10, applied
 * to the Timeline).
 *
 * **The visible week lives in the URL.** `?week=YYYY-MM-DD` names the week, and
 * `&day=YYYY-MM-DD` names the day within it on mobile. Reload, back and share all
 * keep it — which is the point of putting it in the address bar rather than in state.
 *
 * **Two layouts, one read.** The desktop draws all seven days side by side; the mobile
 * draws one day at a time. Both are in the DOM and the CSS picks — so the page stays a
 * **server component** and never measures the viewport.
 *
 * **The week is a local week.** The server cut it at local midnight in the user's own
 * zone, and it named that week's Monday and Sunday. The client sends the Monday it was
 * given, which keeps the URL canonical: the same week always has the same address.
 */
export const dynamic = "force-dynamic";

export default async function TimelinePage({ searchParams }: PageProps<"/timeline">) {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  // **The Timeline is a signed-in surface.** `homeRoute` has already sent an anonymous
  // visitor to the preview and a half-onboarded one to `/onboarding`; what is left is
  // a signed-in user, or a session the API could not answer — and an unreadable
  // session is not a reason to show somebody else's week.
  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="" avatarUrl="">
        <TimelineError href="/timeline" />
      </AppShell>
    );
  }

  const query = await searchParams;
  const weekParam = firstValue(query.week);
  const dayParam = firstValue(query.day);

  // **A malformed week is not a week.** The API answers 422 for one, and the page
  // treats that as the read it is — a failure — rather than guessing which week the
  // reader meant. Guessing would be a lie about what was asked for.
  const week = isLocalDate(weekParam) ? weekParam : null;

  const read = await readTimeline(week);

  if (read.kind === "unavailable") {
    return (
      <AppShell
        name={displayName(session.user)}
        email={session.user.email}
        avatarUrl={session.user.avatar_url}
      >
        <TimelineError href={week ? `/timeline?week=${week}` : "/timeline"} />
      </AppShell>
    );
  }

  const timeline = read.week;
  const days = timeline.days;
  const currentDay = today();

  // **The current week's Monday, for the "Today" control.** The client computes it
  // from the browser's own date, on the calendar — the same rule the server uses to
  // cut the week. The alternative — asking the server for "the current week" and
  // reading its Monday — would be a second request for a fact the browser knows.
  const todayStart = mondayOf(currentDay);

  // **A quiet week replaces the grid.** Seven empty columns saying "Quiet day." seven
  // times says less than the week does, so the whole grid goes and the week's own line
  // takes its place. The navigators stay: the user can still go to another week, and
  // the error state would be a lie about a week nobody read.
  const quiet = days.every((day) => day.blocks.length === 0);

  // **Which day the mobile view shows.** The URL names it; otherwise today if today is
  // in this week, and otherwise the week's first day. The server's `days` array is the
  // authority — a day the server did not send is not a day the client can show.
  const dayDates = days.map((day) => day.date);
  const requestedDay = isLocalDate(dayParam) ? dayParam : null;
  const mobileDay =
    (requestedDay && dayDates.includes(requestedDay) ? requestedDay : null) ??
    (dayDates.includes(currentDay) ? currentDay : null) ??
    dayDates[0] ??
    null;

  return (
    <AppShell
        name={displayName(session.user)}
        email={session.user.email}
        avatarUrl={session.user.avatar_url}
      >
      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">This week</h1>
        <p className="text-ink-muted [font:var(--type-scale-meta-md)]">
          {weekRange(timeline.week_start, timeline.week_end)} · {timeline.timezone} · Read-only ·
          Personal and public events in one view.
        </p>
      </header>

      <div className="mt-6">
        <WeekNavigator
          weekStart={timeline.week_start}
          weekEnd={timeline.week_end}
          todayStart={todayStart}
        />
      </div>

      <div className="mt-4 md:hidden">
        <DayNavigator
          weekStart={timeline.week_start}
          day={mobileDay ?? timeline.week_start}
          days={dayDates}
          todayStart={todayStart}
        />
      </div>

      {quiet ? (
        <div className="mt-8">
          <QuietWeek />
        </div>
      ) : (
        <div className="mt-6">
          <TimelinePanel days={days} today={currentDay} mobileDay={mobileDay} />
        </div>
      )}
    </AppShell>
  );
}

/** A query parameter's first value, or `null`. */
function firstValue(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

/**
 * The Monday of the calendar week the day falls in.
 *
 * **The arithmetic is on the calendar date**, not on an instant — the same rule the
 * server's `timeline_days.week_start_for` follows. The client's own idea of "this
 * week's Monday" would be the server's if it were computed from a UTC midnight.
 */
function mondayOf(day: string): string {
  const parts = new Date(`${day}T00:00:00Z`);
  const weekday = (parts.getUTCDay() + 6) % 7;
  return addDays(day, -weekday);
}

