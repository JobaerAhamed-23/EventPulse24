"use client";

/**
 * The Pulse Digest's delivery time — **editable here, because onboarding is not the
 * only place a person can be**.
 *
 * **The control is the onboarding one.** `DigestTimeControl` was extracted out of
 * `digest-step.tsx` so this route reuses it rather than growing a second copy of a
 * time control — two copies is how two screens come to disagree about what a time
 * means.
 *
 * **The zone travels with the time.** `DigestScheduleIn` says it plainly: *"Both or
 * neither. A wall clock without its zone is not a schedule."* So this sends the zone it
 * read, unchanged, alongside the new time. The zone is set during onboarding and this
 * route does not second-guess it — but it does send it, because the server refuses to
 * half-apply the pair.
 *
 * **The save is inline and it sends one field.** The digest schedule goes up as
 * `{ digest: { delivery_time, timezone } }`; the quiet window and the default slots
 * are omitted, and an omitted field is left alone.
 */
import { useCallback, useState } from "react";

import { DigestTimeControl } from "@/components/onboarding/digest-time-control";
import { SaveFeedback } from "@/components/settings/save-feedback";
import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";
import { clockForInput } from "@/lib/notification-settings";

export type DigestDeliveryTimeProps = {
  /** The stored delivery time — `HH:MM:SS`. */
  initialDeliveryTime: string;
  /** The stored zone. */
  initialTimezone: string;
};

/**
 * The failure line, **verbatim** — and it is the **offline** line.
 *
 * *The work item's own words:* "Couldn't save." — the same line the quiet-hours route
 * uses, because the same thing happened: the save did not take.
 *
 * **The API's own refusal is shown instead of this one, when the API made one.** A
 * schedule the server refuses comes back with a message written for the user, and that
 * message says what to change.
 */
const FAILURE = "Couldn't save.";

export function DigestDeliveryTime({
  initialDeliveryTime,
  initialTimezone,
}: DigestDeliveryTimeProps) {
  /** The delivery time, as the user has it. */
  const [deliveryTime, setDeliveryTime] = useState(() => clockForInput(initialDeliveryTime));
  /** Whether a save is in flight. */
  const [busy, setBusy] = useState(false);
  /**
   * The failure line to show, or `null`.
   *
   * **The message, not a flag** — so the API's own refusal can be shown verbatim.
   */
  const [failure, setFailure] = useState<string | null>(null);
  /** Whether the last save succeeded. */
  const [saved, setSaved] = useState(false);

  /**
   * Saving the delivery time.
   *
   * **The zone goes with it, unchanged.** The server refuses to change the time without
   * the zone, and the zone is not this control's to change.
   */
  const save = useCallback(
    async (time: string) => {
      setBusy(true);
      setFailure(null);
      setSaved(false);
      try {
        const response = await api.PUT("/api/settings/notifications", {
          body: { digest: { delivery_time: time, timezone: initialTimezone } },
        });
        if (response.error) {
          // **The API refused it, and it said why.**
          setFailure(saveFailureMessage(response.error, FAILURE));
          return;
        }
        if (!response.data) {
          setFailure(FAILURE);
          return;
        }
        // **The server's answer replaces the server's answer.**
        setDeliveryTime(clockForInput(response.data.digest.delivery_time));
        setSaved(true);
      } catch {
        // **The request never reached the API**, so there is nothing to quote.
        setFailure(FAILURE);
      } finally {
        setBusy(false);
      }
    },
    [initialTimezone],
  );

  /**
   * The time changing.
   *
   * **An emptied input is not saved.** A time with nothing in it is not a schedule,
   * and the server would refuse it — so the client does not send it. The user's own
   * field is left as they left it.
   */
  const change = useCallback(
    (value: string) => {
      setSaved(false);
      setFailure(null);
      setDeliveryTime(value);
      if (!value) return;
      void save(value);
    },
    [save],
  );

  return (
    <section aria-label="Digest delivery time" data-digest-delivery-time>
      <DigestTimeControl
        id="settings-delivery-time"
        label="Delivery time"
        value={deliveryTime}
        onChange={change}
      />

      <div className="mt-4">
        <SaveFeedback busy={busy} saved={saved} failure={failure} />
      </div>
    </section>
  );
}
