/**
 * Timezones: the curated list the form offers, and the conversion from a local wall-clock
 * time in one of those zones to the UTC instant the API takes.
 *
 * **The backend does not reinterpret a wall-clock time in a zone.** `start_time_utc` is an
 * absolute instant and `start_time_tz` is the zone the event is *displayed* in (AD-6). So
 * the browser has to do the conversion, and it does it with `Intl.DateTimeFormat` and an
 * explicit `timeZone` — exact, and no timezone database in the bundle.
 */

/** One zone in the selector: the IANA name the API takes, and the city shown beside it. */
export type ZoneChoice = {
  /** The IANA name. The backend's `canonical_zone` accepts exactly these. */
  value: string;
  /** The city label, so the list reads as places rather than as identifiers. */
  label: string;
};

/**
 * The zones the form offers.
 *
 * A curated list, not the full IANA set. The full set is around four hundred unlabelled
 * entries — complete, and unpleasant to choose from. Every entry here is one the backend
 * accepts, and they cover the cities the product's audience actually lives in.
 *
 * `UTC` is last: it is a legitimate choice, but it is the one a person makes
 * deliberately rather than by accident.
 */
export const ZONE_CHOICES: readonly ZoneChoice[] = [
  { value: "America/New_York", label: "New York" },
  { value: "America/Chicago", label: "Chicago" },
  { value: "America/Denver", label: "Denver" },
  { value: "America/Los_Angeles", label: "Los Angeles" },
  { value: "America/Phoenix", label: "Phoenix" },
  { value: "America/Anchorage", label: "Anchorage" },
  { value: "Pacific/Honolulu", label: "Honolulu" },
  { value: "Europe/London", label: "London" },
  { value: "Europe/Dublin", label: "Dublin" },
  { value: "Europe/Paris", label: "Paris" },
  { value: "Europe/Berlin", label: "Berlin" },
  { value: "Europe/Madrid", label: "Madrid" },
  { value: "Europe/Athens", label: "Athens" },
  { value: "Asia/Jerusalem", label: "Jerusalem" },
  { value: "Asia/Dubai", label: "Dubai" },
  { value: "Asia/Kolkata", label: "Kolkata" },
  { value: "Asia/Dhaka", label: "Dhaka" },
  { value: "Asia/Singapore", label: "Singapore" },
  { value: "Asia/Shanghai", label: "Shanghai" },
  { value: "Asia/Tokyo", label: "Tokyo" },
  { value: "Australia/Sydney", label: "Sydney" },
  { value: "Pacific/Auckland", label: "Auckland" },
  { value: "UTC", label: "UTC" },
] as const;

/**
 * The browser's own zone, when it is one of the offered choices.
 *
 * The form pre-selects this, but it is never *inferred* — the zone stays a field the user
 * can see and change, because a floating local time is a time the backend would have to
 * guess at. `null` means the browser's zone is not on the list, and the user picks.
 */
export function browserZone(): string | null {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return ZONE_CHOICES.some((choice) => choice.value === zone) ? zone : null;
}

/** A local wall-clock time, as the form collects it. */
export type LocalTime = {
  /** `YYYY-MM-DD`. */
  date: string;
  /** `HH:MM`, 24-hour. */
  time: string;
};

/** The wall-clock the zone shows for an instant, as its parts. */
type WallClock = { year: number; month: number; day: number; hour: number; minute: number };

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

/** The offset of `zone` at `instant`, in milliseconds east of UTC. */
function zoneOffsetMs(instant: Date, zone: string): number {
  const shown = wallClockIn(instant, zone);
  const asUtc = Date.UTC(shown.year, shown.month - 1, shown.day, shown.hour, shown.minute);
  return asUtc - instant.getTime();
}

/**
 * The UTC instant of a local wall-clock time in `zone`.
 *
 * `null` when the local time does not exist — the hour that a daylight-saving jump skips
 * (2:30 AM on a spring-forward morning). The backend would refuse such a time anyway, so
 * the form says so rather than posting something that comes back as an error.
 *
 * The offset is taken from **two probes**: one before and one after the guessed instant.
 * Around a transition the two differ, and the smaller magnitude is the one that describes
 * the instant *after* the transition — the instant the user meant when they typed a time
 * that exists. When they agree, the answer is exact.
 */
export function localToUtcInstant(local: LocalTime, zone: string): Date | null {
  const date = /^(\d{4})-(\d{2})-(\d{2})$/.exec(local.date);
  const time = /^(\d{2}):(\d{2})$/.exec(local.time);
  if (!date || !time) return null;

  const year = Number(date[1]);
  const month = Number(date[2]);
  const day = Number(date[3]);
  const hour = Number(time[1]);
  const minute = Number(time[2]);
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59) return null;

  const asUtc = Date.UTC(year, month - 1, day, hour, minute, 0, 0);
  if (Number.isNaN(asUtc)) return null;

  const before = zoneOffsetMs(new Date(asUtc - 24 * 60 * 60 * 1000), zone);
  const after = zoneOffsetMs(new Date(asUtc + 24 * 60 * 60 * 1000), zone);
  const offset = Math.abs(before) <= Math.abs(after) ? before : after;
  const instant = new Date(asUtc - offset);

  // Does the zone actually show the time the user typed? If it shows something else, the
  // local time fell in a gap — the hour the clock jumped over.
  const shown = wallClockIn(instant, zone);
  if (
    shown.year !== year ||
    shown.month !== month ||
    shown.day !== day ||
    shown.hour !== hour ||
    shown.minute !== minute
  ) {
    return null;
  }

  return instant;
}

/** The instant as the API takes it: UTC, with a `Z` and no fractional seconds. */
export function toApiInstant(instant: Date): string {
  return instant.toISOString().replace(/\.\d{3}Z$/, "Z");
}

/**
 * The local wall-clock time an instant falls on in `zone`.
 *
 * The inverse of {@link localToUtcInstant}, used to pre-fill the edit sheet.
 */
export function utcInstantToLocal(instant: Date, zone: string): LocalTime {
  const shown = wallClockIn(instant, zone);
  const pad = (value: number): string => String(value).padStart(2, "0");
  return {
    date: `${shown.year}-${pad(shown.month)}-${pad(shown.day)}`,
    time: `${pad(shown.hour)}:${pad(shown.minute)}`,
  };
}

/** The time of day an instant falls on in `zone`, as `HH:MM`. */
export function formatLocalTime(instant: Date, zone: string): string {
  const shown = wallClockIn(instant, zone);
  return `${String(shown.hour).padStart(2, "0")}:${String(shown.minute).padStart(2, "0")}`;
}

/** The date an instant falls on in `zone`, as `YYYY-MM-DD`. */
export function formatLocalDate(instant: Date, zone: string): string {
  const shown = wallClockIn(instant, zone);
  return `${shown.year}-${String(shown.month).padStart(2, "0")}-${String(shown.day).padStart(2, "0")}`;
}
