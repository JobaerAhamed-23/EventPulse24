import Link from "next/link";

import { addDays, shortDate, weekdayLong, type LocalDate } from "@/lib/timeline-dates";

/**
 * The Timeline's navigators.
 *
 * **The visible week lives in the URL**, so reload, back and share all keep it. Both
 * navigators are therefore **links**, not buttons: a button would change the week in
 * place and leave the address bar describing the old one, and a shared link would open
 * a week the reader did not choose.
 *
 * **The desktop navigator moves a week; the mobile navigator moves a day.** They are
 * two different surfaces, and the AC asks for both.
 */

/**
 * The desktop week navigator: `←` / `Today` / `→`.
 *
 * **"Today" is a link to the current week** — the week the server would name for
 * today in the user's zone. The client sends the Monday it holds, so "Today" is the
 * Monday of the current week, computed on the calendar date the browser reports.
 */
export function WeekNavigator({
  weekStart,
  weekEnd,
  todayStart,
}: {
  /** The week's Monday, as the server named it. */
  weekStart: LocalDate;
  /** The week's Sunday, as the server named it. */
  weekEnd: LocalDate;
  /** The Monday of the current week. */
  todayStart: LocalDate;
}) {
  const previousStart = addDays(weekStart, -7);
  const nextStart = addDays(weekStart, 7);

  return (
    <nav
      aria-label="Week navigator"
      className="hidden items-center gap-2 md:flex md:rounded-timeline-cell md:border md:border-border-subtle md:bg-surface-elevated md:px-2 md:py-1"
    >
      <WeekLink href={`/timeline?week=${previousStart}`} label="Previous week">
        ←
      </WeekLink>
      <span className="px-2 [font:var(--type-scale-meta-md)] text-ink-primary">
        {shortDate(weekStart)} – {shortDate(weekEnd)}
      </span>
      <WeekLink href={`/timeline?week=${todayStart}`} label="This week">
        Today
      </WeekLink>
      <WeekLink href={`/timeline?week=${nextStart}`} label="Next week">
        →
      </WeekLink>
    </nav>
  );
}

/**
 * The mobile day navigator: `← {date} →`, centred, with a "Today" pill.
 *
 * **The arrows move one day and stay in the week.** The last day of the week does not
 * roll into the next week, and the first does not roll back into the previous one: the
 * URL names a *week*, and a day navigator that left the week would show a day the
 * server did not send. So the arrow at the week's edge is **inert** — a `<span>` with
 * `aria-disabled`, not a link to somewhere else.
 */
export function DayNavigator({
  weekStart,
  day,
  days,
  todayStart,
}: {
  /** The week's Monday, as the server named it. */
  weekStart: LocalDate;
  /** The day being shown. */
  day: LocalDate;
  /** The week's days, in the server's order. */
  days: LocalDate[];
  /** The Monday of the current week. */
  todayStart: LocalDate;
}) {
  const index = days.indexOf(day);
  const previous = index > 0 ? days[index - 1] : null;
  const next = index >= 0 && index < days.length - 1 ? days[index + 1] : null;

  const todayIndex = days.indexOf(todayStart);
  const todayDay = todayIndex >= 0 ? days[todayIndex] : null;

  return (
    <nav aria-label="Day navigator" className="flex items-center justify-between gap-2 md:hidden">
      {previous ? (
        <DayLink href={`/timeline?week=${weekStart}&day=${previous}`} label="Previous day">
          ←
        </DayLink>
      ) : (
        <span aria-disabled="true" className="px-2 text-ink-muted">
          ←
        </span>
      )}

      <span className="flex flex-col items-center gap-1 text-center">
        <span className="[font:var(--type-scale-headline-sm)] text-ink-primary">
          {weekdayLong(day)}
        </span>
        <span className="[font:var(--type-scale-meta-sm)] text-ink-muted">{shortDate(day)}</span>
        {todayDay === day ? (
          <span className="rounded-subtle border border-border-subtle px-3 py-1 [font:var(--type-scale-meta-sm)] text-ink-secondary">
            Today
          </span>
        ) : null}
      </span>

      {next ? (
        <DayLink href={`/timeline?week=${weekStart}&day=${next}`} label="Next day">
          →
        </DayLink>
      ) : (
        <span aria-disabled="true" className="px-2 text-ink-muted">
          →
        </span>
      )}
    </nav>
  );
}

/** One arrow in the week navigator. */
function WeekLink({
  href,
  label,
  children,
}: {
  href: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-label={label}
      className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-subtle px-2 [font:var(--type-scale-meta-md)] text-ink-secondary hover:bg-surface-subtle hover:text-ink-primary"
    >
      {children}
    </Link>
  );
}

/** One arrow in the day navigator. */
function DayLink({
  href,
  label,
  children,
}: {
  href: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-label={label}
      className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-subtle px-2 text-ink-secondary hover:bg-surface-subtle hover:text-ink-primary"
    >
      {children}
    </Link>
  );
}
