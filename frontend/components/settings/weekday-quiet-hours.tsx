"use client";

/**
 * The **per-weekday** Quiet Hours picker — seven rows, one open at a time (FR-51, Pro).
 *
 * **This sits beside the base window; it does not replace it.** `QuietHoursWindow` still
 * owns the one window that means *"this window, every day"*, and that is still what a
 * Free user has and what every day falls back to. A row here says *"…except on
 * Thursdays"*, which is exactly the relationship the two tables have.
 *
 * **"Same as usual" is the honest label, and "Off" would be a lie.** A weekday with no
 * override row does not mean *no quiet hours that day* — it means *the base window
 * applies that day*. The API has no way to say "quiet every night except Thursday", so a
 * row offering an On/Off toggle (as the mockup draws) would promise a state that does not
 * exist, and a user who switched Thursday "off" expecting 3am reminders would get their
 * usual silence instead. The two states this control can actually distinguish are **"Same
 * as usual"** and **a window of its own**, so those are the two it shows. Logged as a
 * deliberate departure from `component.control.day-picker`'s toggle wording.
 *
 * **One request, always — the whole week.** Changing Thursday sends all seven entries,
 * not a Thursday-shaped patch, because `replace_quiet_hours_overrides` is a **replace**:
 * a payload carrying only Thursday would delete the other six. It is also what makes the
 * acceptance criterion true — the server never observes a partially-updated week — and it
 * costs nothing, since the full list is the natural shape of a replace.
 *
 * **The accordion is not decoration.** Seven start/end pairs is fourteen time inputs and
 * fourteen tab stops, which does not fit a phone and does not read on a desktop either.
 * One day open at a time is what the mockup draws (Monday expanded, the rest collapsed)
 * and what makes 375px work without a second layout.
 *
 * **A full-day window never leaves this component.** `start == end` is refused by the
 * server with `InvalidQuietHoursWindowError`, and here it is simply not sent: the
 * acceptance criterion asks that the UI cannot produce the form, so the save is withheld
 * and the row says what is wrong. The server's refusal is still rendered if one ever
 * arrives — this is a guard in front of the rule, not a second copy of it.
 */
import { useCallback, useMemo, useState } from "react";

import { SaveFeedback } from "@/components/settings/save-feedback";
import { saveFailureMessage } from "@/components/settings/save-failure";
import { UpgradePrompt } from "@/components/upgrade/upgrade-prompt";
import { api } from "@/lib/backend-client";
import { readCapDetails } from "@/lib/cap-details";
import { WEEKDAYS, clockForInput, crossesMidnight, windowLabel } from "@/lib/notification-settings";

/** One weekday's window, as the server stores and returns it. */
export type WeekdayWindow = {
  weekday: number;
  start: string;
  end: string;
};

export type WeekdayQuietHoursProps = {
  /** The user's stored per-weekday windows. Any weekday may be absent. */
  initialOverrides: readonly WeekdayWindow[];
  /** The base window, shown as what a "Same as usual" day falls back to. */
  baseStart: string;
  /** The base window's end. */
  baseEnd: string;
  /**
   * Whether this user may change these windows.
   *
   * **`false` is the lapsed Pro user**, whose rows are kept on purpose and stay readable
   * forever. They see their week; they cannot edit it until they resubscribe.
   */
  canEdit?: boolean;
};

/** The offline failure line, matching the base window's. */
const FAILURE = "Couldn't save.";

/** What a row says when the day has no window of its own. */
const SAME_AS_USUAL = "Same as usual";

/** What a row says when its two clocks are the same. */
const EMPTY_WINDOW = "A quiet window needs a start and an end that differ.";

export function WeekdayQuietHours({
  initialOverrides,
  baseStart,
  baseEnd,
  canEdit = true,
}: WeekdayQuietHoursProps) {
  /** The week, by weekday. A weekday absent from the map is "same as usual". */
  const [windows, setWindows] = useState<Map<number, { start: string; end: string }>>(
    () =>
      new Map(
        initialOverrides.map((override) => [
          override.weekday,
          { start: clockForInput(override.start), end: clockForInput(override.end) },
        ]),
      ),
  );
  /** Which day's clocks are showing, or `null` when the week is collapsed. */
  const [openDay, setOpenDay] = useState<number | null>(null);
  /** Whether a save is in flight. */
  const [busy, setBusy] = useState(false);
  /** The failure line to show, or `null`. */
  const [failure, setFailure] = useState<string | null>(null);
  /** The server's upgrade sentence, when it refused on tier. */
  const [capHint, setCapHint] = useState<string | null>(null);
  /** Whether the last save succeeded. */
  const [saved, setSaved] = useState(false);

  const base = useMemo(
    () => ({ start: clockForInput(baseStart), end: clockForInput(baseEnd) }),
    [baseEnd, baseStart],
  );

  /**
   * Saving the week.
   *
   * **The argument is the whole week**, never one day — see the module docstring. The
   * entries are sorted by weekday so the payload reads the way the screen does; the
   * server does not care, and a reader comparing a request to the UI does.
   */
  const save = useCallback(async (week: Map<number, { start: string; end: string }>) => {
    setBusy(true);
    setFailure(null);
    setCapHint(null);
    setSaved(false);
    try {
      const response = await api.PUT("/api/settings/notifications", {
        body: {
          quiet_hours_overrides: [...week.entries()]
            .sort(([a], [b]) => a - b)
            .map(([weekday, window]) => ({
              weekday,
              start: window.start,
              end: window.end,
            })),
        },
      });
      if (response.error) {
        // **A tier refusal is not a failure line.** The server sent its own sentence and
        // the inline prompt renders it, exactly as the save cap and the calendar cap do.
        const cap = readCapDetails(response.error);
        if (cap) {
          setCapHint(cap.upgradeHint);
          return;
        }
        setFailure(saveFailureMessage(response.error, FAILURE));
        return;
      }
      if (!response.data) {
        setFailure(FAILURE);
        return;
      }
      // **The server's answer replaces the client's.** What came back is what was stored.
      setWindows(
        new Map(
          (response.data.quiet_hours_overrides ?? []).map((override) => [
            override.weekday,
            { start: clockForInput(override.start), end: clockForInput(override.end) },
          ]),
        ),
      );
      setSaved(true);
    } catch {
      setFailure(FAILURE);
    } finally {
      setBusy(false);
    }
  }, []);

  /**
   * Changing one clock on one day.
   *
   * **A half-filled or full-day window is held back, not sent.** The two clocks are one
   * window; the user keeps what they typed either way, and the row says what is missing.
   */
  const change = useCallback(
    (weekday: number, which: "start" | "end", value: string) => {
      setSaved(false);
      setFailure(null);
      setCapHint(null);

      const current = windows.get(weekday) ?? { start: base.start, end: base.end };
      const next = { ...current, [which]: value };
      const week = new Map(windows);
      week.set(weekday, next);
      setWindows(week);

      if (!next.start || !next.end) return;
      if (next.start === next.end) {
        setFailure(EMPTY_WINDOW);
        return;
      }
      void save(week);
    },
    [base.end, base.start, save, windows],
  );

  /** Giving a day its own window, seeded from the base one. */
  const addWindow = useCallback(
    (weekday: number) => {
      setSaved(false);
      setFailure(null);
      setCapHint(null);
      const week = new Map(windows);
      week.set(weekday, { start: base.start, end: base.end });
      setWindows(week);
      setOpenDay(weekday);
      if (base.start && base.end && base.start !== base.end) void save(week);
    },
    [base.end, base.start, save, windows],
  );

  /**
   * Returning a day to the base window — the absence of a row.
   *
   * **Not named `useUsual`.** A `use` prefix makes this look like a React hook to both a
   * reader and `react-hooks/rules-of-hooks`, which refuses it inside the row callback.
   */
  const resetToUsual = useCallback(
    (weekday: number) => {
      setSaved(false);
      setFailure(null);
      setCapHint(null);
      const week = new Map(windows);
      week.delete(weekday);
      setWindows(week);
      void save(week);
    },
    [save, windows],
  );

  return (
    <section aria-label="Per-day quiet hours" data-weekday-quiet-hours>
      <p className="text-ink-secondary [font:var(--type-scale-body-md)]">
        A different window on any day. Days you leave alone follow your usual one.
      </p>

      <ul className="mt-6 border-t border-border-subtle" data-weekday-rows>
        {WEEKDAYS.map((day) => {
          const window = windows.get(day.index);
          const open = openDay === day.index;
          const panelId = `weekday-panel-${day.index}`;
          return (
            <li key={day.index} className="border-b border-border-subtle">
              <button
                type="button"
                aria-expanded={open}
                // **Only while the panel exists.** `aria-controls` naming an id that is
                // not in the document is a dangling reference: the collapsed row renders
                // no panel at all, which is what keeps fourteen time inputs off a phone.
                aria-controls={open ? panelId : undefined}
                onClick={() => setOpenDay(open ? null : day.index)}
                className="flex min-h-[44px] w-full items-center justify-between gap-4 px-1 py-3 text-left"
                data-weekday-row={day.index}
              >
                <span className="text-ink-primary [font:var(--type-scale-body-md)]">
                  {day.long}
                </span>
                <span
                  className={
                    window
                      ? "rounded-subtle bg-surface-subtle px-2 py-1 text-ink-secondary [font:var(--type-scale-meta-sm)]"
                      : "text-ink-muted italic [font:var(--type-scale-meta-sm)]"
                  }
                  data-weekday-chip={day.index}
                >
                  {window ? windowLabel(window.start, window.end) : SAME_AS_USUAL}
                </span>
              </button>

              {open ? (
                <div id={panelId} className="px-1 pb-4" data-weekday-panel={day.index}>
                  {window ? (
                    <>
                      <div className="flex flex-wrap items-end gap-3">
                        <label className="flex flex-col gap-1">
                          <span className="text-ink-secondary [font:var(--type-scale-meta-sm)]">
                            {day.long} starts
                          </span>
                          <input
                            type="time"
                            value={window.start}
                            disabled={!canEdit}
                            onChange={(event) => change(day.index, "start", event.target.value)}
                            className="min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-3 py-2 text-ink-primary [font:var(--type-scale-body-md)]"
                          />
                        </label>

                        <span aria-hidden="true" className="text-ink-muted">
                          →
                        </span>

                        <label className="flex flex-col gap-1">
                          <span className="text-ink-secondary [font:var(--type-scale-meta-sm)]">
                            {day.long} ends
                          </span>
                          <input
                            type="time"
                            value={window.end}
                            disabled={!canEdit}
                            onChange={(event) => change(day.index, "end", event.target.value)}
                            className="min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-3 py-2 text-ink-primary [font:var(--type-scale-body-md)]"
                          />
                        </label>
                      </div>

                      {/*
                        **A window that crosses midnight says so.** Two clocks reading
                        22:00 and 08:00 do not tell a user that Friday's window owns
                        Saturday's small hours, and that is the one thing about this
                        control that is not self-evident.
                      */}
                      {crossesMidnight(window.start, window.end) ? (
                        <p
                          className="mt-2 text-ink-muted [font:var(--type-scale-meta-sm)]"
                          data-weekday-midnight={day.index}
                        >
                          Reaches into {nextDay(day.index)} morning.
                        </p>
                      ) : null}

                      {canEdit ? (
                        <button
                          type="button"
                          onClick={() => resetToUsual(day.index)}
                          className="mt-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
                        >
                          Use my usual window on {day.long}
                        </button>
                      ) : null}
                    </>
                  ) : (
                    <p className="text-ink-secondary [font:var(--type-scale-body-md)]">
                      {day.long} follows your usual window.{" "}
                      {canEdit ? (
                        <button
                          type="button"
                          onClick={() => addWindow(day.index)}
                          className="text-ink-primary underline underline-offset-4"
                        >
                          Give {day.long} its own
                        </button>
                      ) : null}
                    </p>
                  )}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      {capHint ? <UpgradePrompt hint={capHint} className="mt-4" /> : null}

      <div className="mt-4">
        <SaveFeedback busy={busy} saved={saved} failure={failure} />
      </div>
    </section>
  );
}

/**
 * The day after this one, for the midnight line.
 *
 * Wraps at Sunday, which is the case a plain `index + 1` gets wrong by running off the
 * end of the week and printing nothing at all.
 */
function nextDay(weekday: number): string {
  const day = WEEKDAYS[(weekday + 1) % WEEKDAYS.length];
  return day ? day.long : "";
}
