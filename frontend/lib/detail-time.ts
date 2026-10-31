/**
 * The Detail Screen's time display.
 *
 * **The primary time is the user's local time**, and the venue's local time is shown
 * beside it **when the two differ**. The payload carries the instant
 * (`start_time_utc`) and the event's own IANA zone (`start_time_tz`); the user's zone
 * comes from the browser, because a Detail Screen is a navigation — it renders in a
 * browser, and the browser knows the user's zone exactly. There is no second round trip
 * for a zone the client already has (AD-6: display-time conversion happens at the
 * presentation edge).
 *
 * **"When they differ" is a comparison of the two wall-clocks, not of the two zone
 * names.** `America/New_York` and `America/Toronto` are different zones that show the
 * same clock face. A screen that read "6:30 PM EDT · 6:30 PM Toronto" would be noise,
 * so the venue time is shown only when the **rendered time text** differs.
 */

/** One zone's wall-clock for an instant, as the parts the screen needs. */
type WallClock = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

/**
 * The wall-clock `zone` shows for `instant`.
 *
 * Read through `formatToParts` rather than by parsing a formatted string: the formatted
 * shape is locale-dependent, and this has to be exact.
 */
function wallClockIn(instant: Date, zone: string): WallClock {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(instant);
  const value = (type: Intl.DateTimeFormatPartTypes): number =>
    Number(parts.find((part) => part.type === type)?.value);
  return {
    year: value("year"),
    month: value("month"),
    day: value("day"),
    hour: value("hour"),
    minute: value("minute"),
  };
}

/** The zone's short name, as the screen shows it beside a time. */
function zoneLabel(instant: Date, zone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    timeZoneName: "short",
  }).formatToParts(instant);
  return parts.find((part) => part.type === "timeZoneName")?.value ?? zone;
}

/** The month names, for the "Aug 28" form the card uses. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** The day names, for the "Thursday" form. */
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/**
 * The wall-clock a zone shows, formatted.
 *
 * **`hourCycle: "h23"` and a 12-hour label are two different things.** The parts are
 * read in 24-hour form (so "00:30" is hour 0, not hour 24), and the label is built by
 * hand from them — which is why the display can say "6:30 PM" while the arithmetic
 * stays exact.
 */
function formatted(clock: WallClock): { date: string; time: string; day: string } {
  const suffix = clock.hour >= 12 ? "PM" : "AM";
  const hour12 = clock.hour % 12 === 0 ? 12 : clock.hour % 12;
  const minute = String(clock.minute).padStart(2, "0");
  // The weekday and the month are read from the *same* wall-clock the time comes from,
  // so a time that straddles midnight in the user's zone cannot show Tuesday's date
  // beside Monday's time.
  const dayIndex = new Date(Date.UTC(clock.year, clock.month - 1, clock.day)).getUTCDay();

  return {
    date: `${MONTHS[clock.month - 1]} ${clock.day}`,
    time: `${hour12}:${minute} ${suffix}`,
    day: WEEKDAYS[dayIndex] ?? "",
  };
}

/**
 * The times the Detail Screen shows.
 *
 * `user` is the browser's own zone. `venue` is the event's zone.
 */
export type DetailTimes = {
  /** "Thursday, Aug 28" — the user's local date. */
  date: string;
  /** "6:30 PM" — the user's local time. */
  time: string;
  /** The user's zone's short name, when the venue's time is also shown. */
  zone: string;
  /** The venue's local time, or `null` when it matches the user's. */
  venueTime: string | null;
  /** The venue's zone's short name, when its time is shown. */
  venueZone: string | null;
};

/**
 * The event's times, in the user's zone and — when it differs — the venue's.
 *
 * **`null` in, `null` out.** An event with no start time has no time to show, and the
 * screen says "Time to be confirmed" rather than rendering a wrong one.
 */
export function detailTimes(
  startTimeUtc: string | null | undefined,
  venueZone: string | null | undefined,
  userZone: string | null | undefined,
): DetailTimes | null {
  if (!startTimeUtc) return null;
  const instant = new Date(startTimeUtc);
  if (Number.isNaN(instant.getTime())) return null;

  // The user's zone, when the browser named one we can use. Without it the event's own
  // zone is the best we have — which is honest: we are showing the venue's clock and
  // saying so.
  const zone = userZone ?? venueZone ?? "UTC";

  const local = formatted(wallClockIn(instant, zone));
  const date = `${local.day}, ${local.date}`;

  const venue = venueZone ? wallClockIn(instant, venueZone) : null;
  const venueText = venue ? formatted(venue) : null;

  // **The wall-clock comparison, not the zone-name comparison.** Two different zones can
  // show the same clock face; showing both would be noise, not information.
  const differs = venueText !== null && venueText.time !== local.time;

  return {
    date,
    time: local.time,
    zone: zoneLabel(instant, zone),
    venueTime: differs ? (venueText?.time ?? null) : null,
    venueZone: differs && venueZone ? zoneLabel(instant, venueZone) : null,
  };
}

/**
 * The browser's own IANA zone.
 *
 * **Read at the presentation edge.** `Intl` is available in the browser and in Node, so
 * this works in a server component too — but the *browser's* zone is only truly the
 * user's when it is read in the browser. The page reads it on the server and passes it
 * down; that is the same server-rendered-hydration boundary the rest of the app uses.
 */
export function browserTimeZone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone ?? null;
  } catch {
    return null;
  }
}
