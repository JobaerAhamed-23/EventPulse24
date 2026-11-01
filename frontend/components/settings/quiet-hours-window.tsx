"use client";

/**
 * The Quiet Hours window editor — **two local wall clocks**, saved inline.
 *
 * **The window is two wall clocks, not two instants.** `22:00` means ten at night
 * *where the user is* — so the window crosses midnight and crosses the user's timezone
 * with them. The server owns the arithmetic; this control owns the two values.
 *
 * **The default is 22:00–08:00, and the label says so.** The server's
 * `DEFAULT_QUIET_HOURS_START`/`END` are `time(22, 0)` and `time(8, 0)`. The mockup
 * drew `07:00` — a stale value — and the work item locks the label *"10pm–8am.
 * Nothing during this window."* The server and the label win over the mockup.
 *
 * **The save is inline and it sends one field.** `NotificationSettingsIn` is a patch,
 * and `quiet_hours` is the field where **`null` is a value** — it turns the window off.
 * So the save sends `{ quiet_hours: { start, end } }` and nothing else; the default
 * reminder slots and the digest schedule are omitted, and an omitted field is left
 * alone. A payload that re-sent the slots on every window change would be a payload
 * that could rewrite the user's default plan by accident.
 *
 * **A full-day window is refused, and the refusal is the server's.** The same clock
 * twice is a window that never ends, and the server refuses it. The client does not
 * pre-empt that rule with a second copy of it — it sends the window, and shows the
 * server's answer.
 */
import { useCallback, useState } from "react";

import { SaveFeedback } from "@/components/settings/save-feedback";
import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";
import { clockForInput } from "@/lib/notification-settings";

export type QuietHoursWindowProps = {
  /** The user's current window, as the server stores it — `HH:MM:SS`. */
  initialStart: string;
  /** The user's current window's end, as the server stores it — `HH:MM:SS`. */
  initialEnd: string;
};

/**
 * The failure line, **verbatim** — and it is the **offline** line.
 *
 * *The work item's own words:* "Couldn't save." — **shorter than the reminders
 * route's**, and deliberately so: there is no "next change" to retry on, because the
 * next change is another window the user has to choose.
 *
 * **The API's own refusal is shown instead of this one, when the API made one.** A
 * full-day window is refused by the server with *"A quiet window needs a start and an
 * end that differ."* — and that line says what to fix, which this one does not.
 */
const FAILURE = "Couldn't save.";

export function QuietHoursWindow({ initialStart, initialEnd }: QuietHoursWindowProps) {
  /** The window's start, as the user has it. */
  const [start, setStart] = useState(() => clockForInput(initialStart));
  /** The window's end, as the user has it. */
  const [end, setEnd] = useState(() => clockForInput(initialEnd));
  /** Whether a save is in flight. */
  const [busy, setBusy] = useState(false);
  /**
   * The failure line to show, or `null`.
   *
   * **The message, not a flag.** A boolean can only carry "something went wrong", and
   * the one failure the user can actually fix — the full-day window — needs the API's
   * own words to say so.
   */
  const [failure, setFailure] = useState<string | null>(null);
  /** Whether the last save succeeded. */
  const [saved, setSaved] = useState(false);

  /**
   * Saving the window.
   *
   * **The chosen state is kept on failure.** The user's two clocks stay where they
   * put them, and the failure line says so.
   */
  const save = useCallback(async (nextStart: string, nextEnd: string) => {
    setBusy(true);
    setFailure(null);
    setSaved(false);
    try {
      const response = await api.PUT("/api/settings/notifications", {
        body: { quiet_hours: { start: nextStart, end: nextEnd } },
      });
      if (response.error) {
        // **The API refused it, and it said why.** A full-day window — the same clock
        // twice — is the server's own refusal, with a message written for the user.
        setFailure(saveFailureMessage(response.error, FAILURE));
        return;
      }
      if (!response.data) {
        setFailure(FAILURE);
        return;
      }
      // **The server's answer replaces the server's answer.** The response carries the
      // whole settings surface, and its window is what was actually saved.
      const window = response.data.quiet_hours;
      if (window) {
        setStart(clockForInput(window.start));
        setEnd(clockForInput(window.end));
      }
      setSaved(true);
    } catch {
      // **The request never reached the API**, so there is nothing to quote and the
      // route's own line is shown.
      setFailure(FAILURE);
    } finally {
      setBusy(false);
    }
  }, []);

  /**
   * Changing one clock.
   *
   * **A half-changed window is not saved.** The two clocks are one window, and a window
   * with one end missing is not a window — so the save waits until both are filled in.
   */
  const change = useCallback(
    (which: "start" | "end", value: string) => {
      setSaved(false);
      setFailure(null);
      const nextStart = which === "start" ? value : start;
      const nextEnd = which === "end" ? value : end;
      setStart(nextStart);
      setEnd(nextEnd);
      if (!nextStart || !nextEnd) return;
      void save(nextStart, nextEnd);
    },
    [end, save, start],
  );

  return (
    <section aria-label="Quiet hours" data-quiet-hours>
      {/*
        **The label is locked.** "10pm–8am. Nothing during this window." — the work
        item's own words, and the window's actual shape.
      */}
      <p className="text-ink-secondary [font:var(--type-scale-body-md)]" data-quiet-hours-label>
        10pm–8am. Nothing during this window.
      </p>

      <div className="mt-6 flex flex-wrap items-end gap-3" data-quiet-hours-inputs>
        <label className="flex flex-col gap-1">
          <span className="text-ink-secondary [font:var(--type-scale-meta-sm)]">Starts</span>
          <input
            id="quiet-hours-start"
            name="quiet_hours_start"
            type="time"
            value={start}
            onChange={(event) => change("start", event.target.value)}
            aria-describedby="quiet-hours-hint"
            className="min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-3 py-2 text-ink-primary [font:var(--type-scale-body-md)]"
          />
        </label>

        <span aria-hidden="true" className="text-ink-muted">
          →
        </span>

        <label className="flex flex-col gap-1">
          <span className="text-ink-secondary [font:var(--type-scale-meta-sm)]">Ends</span>
          <input
            id="quiet-hours-end"
            name="quiet_hours_end"
            type="time"
            value={end}
            onChange={(event) => change("end", event.target.value)}
            aria-describedby="quiet-hours-hint"
            className="min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-3 py-2 text-ink-primary [font:var(--type-scale-body-md)]"
          />
        </label>

        <p id="quiet-hours-hint" className="text-ink-muted [font:var(--type-scale-meta-sm)]">
          In your own time zone.
        </p>
      </div>

      <div className="mt-4">
        <SaveFeedback busy={busy} saved={saved} failure={failure} />
      </div>
    </section>
  );
}
