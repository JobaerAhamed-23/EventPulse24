/**
 * The Timeline's dates.
 *
 * **The server cut the week; the client only reads it.** The API sends
 * `week_start`, `week_end` and seven days with their own dates. Those are the
 * authority — the client never computes a Monday, because a week is cut at local
 * midnight and the client's idea of "this week's Monday" would be the server's.
 *
 * **The dates are plain `YYYY-MM-DD` strings, not `Date` objects.** A `Date` parsed
 * from `"2026-11-02"` is **UTC midnight**, and reading its day-of-week gives the
 * *server's* week, not the user's. The week grid is Monday–Sunday in the *user's*
 * zone, so the weekday label has to come from the same arithmetic the server used —
 * which is: the day-of-week of the **date**, computed as if it were a calendar date.
 *
 * That arithmetic is what `Intl.DateTimeFormat` with `timeZone: "UTC"` gives, and it is
 * the same rule the backend's `timeline_days.week_days` follows. So the client's
 * weekday labels and the server's day order cannot disagree.
 */

/** A calendar date, as the API sends it: `"2026-11-02"`. */
export type LocalDate = string;

/** The seven day names, Monday first — the grid's column order. */
export const WEEKDAY_LONG = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

/** The short day names, Monday first — the grid's column headers. */
export const WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

/** The month names, for the "Sep 7" form. */
const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

/**
 * A date's parts, read as a **calendar** date.
 *
 * **Read through `formatToParts` in UTC, not by parsing.** `new Date("2026-11-02")` is
 * an instant — UTC midnight — and `getDay()` on it is the server's week. The date the
 * server named is a calendar day in the *user's* zone, so its weekday is the weekday of
 * that calendar day, wherever the reader is. `timeZone: "UTC"` says exactly that: read
 * these parts as a calendar date, not as an instant.
 */
function parts(date: LocalDate): { year: number; month: number; day: number } {
  const pieces = new Intl.DateTimeFormat("en-US", {
    timeZone: "UTC",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(`${date}T00:00:00Z`));
  const value = (type: Intl.DateTimeFormatPartTypes): number =>
    Number(pieces.find((piece) => piece.type === type)?.value);
  return {
    year: value("year"),
    month: value("month"),
    day: value("day"),
  };
}

/**
 * A date's weekday, Monday first.
 *
 * `Date.UTC(...)` on the calendar parts gives the weekday of **that calendar day**,
 * with no zone involved at all — which is the point.
 */
export function weekdayIndex(date: LocalDate): number {
  const { year, month, day } = parts(date);
  // `getUTCDay()` is Sunday-first; the grid is Monday-first.
  return (new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7;
}

/** A date's short weekday name — "Mon". */
export function weekdayShort(date: LocalDate): string {
  return WEEKDAY_SHORT[weekdayIndex(date)] ?? "";
}

/** A date's long weekday name — "Monday". */
export function weekdayLong(date: LocalDate): string {
  return WEEKDAY_LONG[weekdayIndex(date)] ?? "";
}

/** A date's day-of-month, as a number — "7" for `2026-09-07`. */
export function dayOfMonth(date: LocalDate): number {
  return parts(date).day;
}

/** A date's "Sep 7" form. */
export function shortDate(date: LocalDate): string {
  const { month, day } = parts(date);
  return `${MONTHS[month - 1] ?? ""} ${day}`;
}

/** A date's "September 7, 2026" form. */
export function longDate(date: LocalDate): string {
  const { year, month, day } = parts(date);
  const name = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ][month - 1];
  return `${name ?? ""} ${day}, ${year}`;
}

/**
 * A date's "Sep 7 – Sep 13" form, for the week's range.
 *
 * **The end's month is shown when it differs from the start's.** "Sep 28 – Oct 4" names
 * two months; "Sep 7 – Sep 13" names one. A range that silently dropped the month
 * would say "28 – 4".
 */
export function weekRange(start: LocalDate, end: LocalDate): string {
  const startParts = parts(start);
  const endParts = parts(end);
  const startMonth = MONTHS[startParts.month - 1] ?? "";
  const endMonth = MONTHS[endParts.month - 1] ?? "";
  if (startMonth === endMonth) return `${startMonth} ${startParts.day} – ${endParts.day}`;
  return `${startMonth} ${startParts.day} – ${endMonth} ${endParts.day}`;
}

/**
 * The date `days` away from `date`.
 *
 * **The arithmetic is on calendar dates, not on instants.** Adding a day to
 * `"2026-11-02"` gives `"2026-11-03"` — the next calendar day — which is what a day
 * navigator means. Adding 86,400,000ms would give the same answer here, but it would
 * not across a DST boundary, and a day navigator that skipped a day would be a bug the
 * user cannot explain.
 */
export function addDays(date: LocalDate, days: number): LocalDate {
  const { year, month, day } = parts(date);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  const iso = shifted.toISOString().slice(0, 10);
  return iso;
}

/** Today's date in the browser's own zone — "2026-11-04". */
export function today(): LocalDate {
  try {
    const formatter = new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
    // `en-CA` formats as `YYYY-MM-DD`, which is the shape the API uses.
    return formatter.format(new Date());
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

/**
 * Today's date **in a named zone** — "2026-11-21" in `Asia/Dhaka`.
 *
 * **The reader's zone, not the renderer's.** `today()` reads whatever zone the
 * environment running it is set to. On a server component that environment is the
 * *server* — typically UTC — so a reader six hours east of it is told "today" is
 * yesterday for the last six hours of their day. The week itself is already cut in the
 * reader's own zone (the backend's `timeline_days.week_start_for`), and the server
 * names that zone in the response; so the day that week highlights has to be read in
 * the same zone, or the highlight and the grid disagree about what day it is.
 *
 * **An unusable zone falls back to `today()`.** A zone the runtime does not know
 * throws; the environment's own date is a worse answer than the reader's, but it is a
 * far better one than a crashed page.
 */
export function todayIn(zone: string | null | undefined): LocalDate {
  if (!zone) return today();
  try {
    // `en-CA` formats as `YYYY-MM-DD`, which is the shape the API uses.
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  } catch {
    return today();
  }
}

/** Whether a date is a well-formed `YYYY-MM-DD` calendar date. */
export function isLocalDate(value: string | null | undefined): value is LocalDate {
  if (!value) return false;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return false;
  // "2026-02-30" parses (it rolls into March), so the round trip is the real check.
  return parsed.toISOString().slice(0, 10) === value;
}
