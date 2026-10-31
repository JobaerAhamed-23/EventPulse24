/**
 * The Pulse Digest's header: the eyebrow, the h1 and the lede.
 *
 * **The words are locked.** `EXPERIENCE.md` §3's microcopy contract gives the headline
 * exactly — "Today, three things matter." — and the desktop mockup agrees. The mobile
 * mockup's inverted "Three things matter today." is drift, and the spine wins.
 *
 * **The date line is the server's.** `local_date` is the user's local day and
 * `timezone` is the zone the digest was composed in. The page does not compute "today"
 * from the browser clock: the server already decided which day this is, and a browser
 * in another zone computing its own "today" would disagree with the digest it is about
 * to render.
 *
 * **The `Indicator.Today` dot is the first sanctioned terracotta use** — a single 6px
 * `radius.full` dot with the sanctioned glow. It is `aria-hidden`, because the date
 * beside it already says what day it is; the dot is a glance, not a fact.
 */
export function DigestHeader({
  localDate,
  timezone,
  city,
}: {
  /** The user's local day, `YYYY-MM-DD`, from the API. */
  localDate: string;
  /** The IANA zone the digest was composed in. */
  timezone: string;
  /** The city the server resolved. */
  city: string | null;
}) {
  return (
    <header>
      <p className="flex items-center gap-2 text-ink-secondary [font:var(--type-scale-meta-md)]">
        {/* The today indicator: a single glowing terracotta dot, inline with the date.
            `aria-hidden` — the words beside it carry the meaning. */}
        <span
          aria-hidden="true"
          className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent-terracotta"
          style={{ boxShadow: "var(--glow-today)" }}
        />
        <span>
          {weekdayOf(localDate, timezone)}
          {" · "}
          {readableDate(localDate)}
          {city ? ` · ${city}` : ""}
        </span>
      </p>

      <h1 className="mt-3 text-ink-primary [font:var(--type-scale-display-lg)]">
        Today, three things matter.
      </h1>

      <p className="mt-3 max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-lg)]">
        Your morning brief, kept short on purpose. Open one, save one, or close the app and let it
        go.
      </p>
    </header>
  );
}

/**
 * The weekday the local date falls on, read in the digest's own zone.
 *
 * **The date is parsed as UTC and then formatted in the zone**, which is the only way
 * to get the right weekday for a date that is already local. `new Date("2026-08-27")`
 * is midnight **UTC**, and formatting that in a western zone would give the *previous*
 * day — so the zone is passed explicitly and the date is pinned to midday in it before
 * the weekday is read.
 */
function weekdayOf(localDate: string, timezone: string): string {
  return new Intl.DateTimeFormat("en-US", { weekday: "long", timeZone: timezone }).format(
    localMidday(localDate, timezone),
  );
}

/** The date, as the mockup writes it: "Aug 27, 2026". */
function readableDate(localDate: string): string {
  const [year, month, day] = localDate.split("-").map(Number);
  const months = [
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
  ];
  if (!year || !month || !day) return localDate;
  return `${months[month - 1]} ${day}, ${year}`;
}

/**
 * Noon on the local date, in the local zone.
 *
 * Noon rather than midnight because the local date *is* a calendar day, and noon is the
 * one instant on it that no timezone offset can move onto a different day.
 */
function localMidday(localDate: string, timezone: string): Date {
  const noonUtc = new Date(`${localDate}T12:00:00Z`);
  if (Number.isNaN(noonUtc.getTime())) return noonUtc;

  // The offset at that instant, and the local date it implies.
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(noonUtc);
  const value = (type: Intl.DateTimeFormatPartTypes): number =>
    Number(parts.find((part) => part.type === type)?.value);
  const shown = Date.UTC(
    value("year"),
    value("month") - 1,
    value("day"),
    value("hour"),
    value("minute"),
  );
  const offsetMs = shown - noonUtc.getTime();
  return new Date(noonUtc.getTime() - offsetMs);
}
