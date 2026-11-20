"use client";

/**
 * `Component.Settings.Timezone` — the zone every local time on the account is read in.
 *
 * ## It was unreachable, and that was visible in the data
 *
 * The zone is set once, in onboarding's digest step, and `digest_preferences.py` defaults
 * it to `UTC` for an account that never completed that step. After that **nothing in the
 * product could show it or change it**: `DigestDeliveryTime` reads `initialTimezone` and
 * sends it straight back (*"the zone is not this control's to change"*), so an account
 * stuck on `UTC` stayed there.
 *
 * The consequence is not cosmetic. The zone decides which day "today" is for the digest's
 * composition, when quiet hours start and end, and which seven days the timeline draws. A
 * user six hours from UTC with a `UTC` preference gets a brief composed for the wrong day
 * and a quiet window six hours out of place — with nothing on screen to explain it.
 *
 * `settings-desktop.html` has the row this restores: *"Timezone — auto-detected from your
 * device."*
 *
 * ## Changing the zone keeps the clock, not the instant
 *
 * 09:00 stays 09:00. The backend already treats `delivery_time` as a **local wall clock**
 * — `DigestScheduleIn` says so outright — so "my brief arrives at nine wherever I am" is
 * the reading the stored shape already has. Sending the same `delivery_time` with a new
 * `timezone` is therefore not a conversion; it is the same field meaning what it always
 * meant, somewhere else.
 *
 * **The moment does move, and the control says so**, because a change that silently
 * shifts when a daily email arrives is a change the user should see coming.
 *
 * ## The time goes with the zone, because the server requires both
 *
 * `DigestScheduleIn` takes `delivery_time` *and* `timezone`: *"Both or neither. A wall
 * clock without its zone is not a schedule."* So this control sends the delivery time it
 * was handed, unchanged — the mirror image of what `DigestDeliveryTime` does with the
 * zone.
 */
import { useCallback, useState } from "react";

import { SaveFeedback } from "@/components/settings/save-feedback";
import { saveFailureMessage } from "@/components/settings/save-failure";
import { SettingRow } from "@/components/settings/setting-row";
import { api } from "@/lib/backend-client";
import { ZONE_CHOICES, browserZone } from "@/lib/timezones";

export type DigestTimezoneProps = {
  /** The stored zone — an IANA name. */
  initialTimezone: string;
  /**
   * The stored delivery time, sent back unchanged with every zone change.
   *
   * The server refuses a zone without a time, and this control does not change the time.
   */
  deliveryTime: string;
  /**
   * Called with the zone this control now holds, whenever that changes.
   *
   * **It exists because this control no longer sits alone.** On `/settings/profile` the
   * city control sits beside it, and `HomeCity` posts `timezone` back *unchanged* with
   * every city change — so a city picked after a zone change would send the zone the
   * page was rendered with and quietly undo it. The two controls therefore share one
   * value, and this is how it travels.
   *
   * **It fires on the revert too**, not only on the save: a zone change the server
   * refused leaves this control showing the old zone, and a neighbour still holding the
   * refused one would send it back.
   */
  onTimezoneChange?: (timezone: string) => void;
};

/** The offline failure line. The same one the delivery-time control uses. */
const FAILURE = "Couldn't save.";

/** A zone's city label, or the IANA name when it is not one we offer. */
function zoneLabel(zone: string): string {
  return ZONE_CHOICES.find((choice) => choice.value === zone)?.label ?? zone;
}

/**
 * The zone's current offset from UTC, as "UTC+6".
 *
 * **Computed, never stored.** An offset is a fact about a zone *right now* — it moves
 * with daylight saving — so writing one down would be writing down something that goes
 * stale twice a year.
 */
function offsetLabel(zone: string): string | null {
  try {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: zone,
      timeZoneName: "shortOffset",
    }).formatToParts(new Date());
    return parts.find((part) => part.type === "timeZoneName")?.value ?? null;
  } catch {
    // An unknown zone. The select still shows the stored name; it just gets no offset.
    return null;
  }
}

export function DigestTimezone({
  initialTimezone,
  deliveryTime,
  onTimezoneChange,
}: DigestTimezoneProps) {
  const [zone, setZoneState] = useState(initialTimezone);
  const [busy, setBusy] = useState(false);
  /** The message, not a flag — so the API's own refusal can be shown verbatim. */
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  /**
   * Set the zone, and tell whoever is listening.
   *
   * **Every path goes through here — the optimistic guess, the server's answer and both
   * reverts.** A revert that did not notify would leave a neighbouring control holding a
   * zone the server had just refused.
   */
  const setZone = useCallback(
    (next: string) => {
      setZoneState(next);
      onTimezoneChange?.(next);
    },
    [onTimezoneChange],
  );

  const save = useCallback(
    async (next: string) => {
      const previous = zone;
      // **Optimistic, and reverted on failure.** A select that springs back on every
      // keystroke-equivalent is worse than one that shows the choice and undoes it if
      // the server says no.
      setZone(next);
      setBusy(true);
      setFailure(null);
      setSaved(false);
      try {
        const response = await api.PUT("/api/settings/notifications", {
          // The delivery time rides along unchanged: the server takes both or neither,
          // and the wall clock is what "keep the clock time" means.
          body: { digest: { delivery_time: deliveryTime, timezone: next } },
        });
        if (response.error) {
          setFailure(saveFailureMessage(response.error, FAILURE));
          setZone(previous);
          return;
        }
        if (!response.data) {
          setFailure(FAILURE);
          setZone(previous);
          return;
        }
        // **The server's answer replaces the client's guess** (AD-10).
        setZone(response.data.digest.timezone);
        setSaved(true);
      } catch {
        // The request never reached the API, so there is nothing to quote.
        setFailure(FAILURE);
        setZone(previous);
      } finally {
        setBusy(false);
      }
    },
    [deliveryTime, setZone, zone],
  );

  const offset = offsetLabel(zone);
  const detected = browserZone();
  // **Offered only when it would change something**, and only when the browser's zone is
  // one we accept. A button that does nothing is a button that teaches the user to
  // distrust the others.
  const canUseDetected = detected !== null && detected !== zone;

  return (
    <section aria-label="Timezone" data-digest-timezone>
      <SettingRow
        label="Timezone"
        /**
         * **Short, because the row puts it beside the control.** A description long
         * enough to fill the reading width pushes the select onto a line of its own, and
         * the right-hand column the mockup's rows line up in stops before it starts.
         *
         * **It names what reads the zone rather than saying "everything below".** The
         * control used to open `/settings/general`, with quiet hours and the digest
         * underneath it, and "below" was true there. It now sits on `/settings/profile`
         * under the city, with nothing under it that the zone governs — so the sentence
         * says which settings are read in this zone instead of pointing at the page.
         */
        description={
          <>
            Your Pulse Digest, quiet hours and timeline are read in this zone.
            {offset ? ` Currently ${offset}.` : null}
          </>
        }
        control={
          <span className="flex items-center gap-3">
            {/*
              **`aria-label`, not a second `<label>`.** The row already shows the word
              "Timezone" beside the control; an sr-only `<label>` saying it again would
              put two elements with that name in the document, and a screen reader would
              hear it twice.
            */}
            <select
              aria-label="Timezone"
              value={zone}
              disabled={busy}
              onChange={(event) => {
                void save(event.target.value);
              }}
              data-timezone-select
              className="min-h-[44px] rounded-control border border-border-subtle bg-surface-subtle px-3 text-ink-primary [font:var(--type-scale-meta-md)] disabled:opacity-60"
            >
              {/*
                **The stored zone is always an option, even off the curated list.** The
                backend accepts more zones than `ZONE_CHOICES` offers, and a select that
                silently dropped the user's own zone would show them somebody else's.
              */}
              {ZONE_CHOICES.some((choice) => choice.value === zone) ? null : (
                <option value={zone}>{zone}</option>
              )}
              {ZONE_CHOICES.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </span>
        }
        footer={
          <>
            {canUseDetected ? (
              <p className="text-ink-muted [font:var(--type-scale-meta-sm)]">
                Your device says {zoneLabel(detected)}.{" "}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    void save(detected);
                  }}
                  data-use-detected-zone
                  className="text-ink-secondary underline underline-offset-4 disabled:cursor-default"
                >
                  Use it
                </button>
              </p>
            ) : null}

            <div className="mt-4">
              <SaveFeedback busy={busy} saved={saved} failure={failure} />
            </div>
          </>
        }
      />
    </section>
  );
}
