"use client";

/**
 * FR-10's **Pulse Ping switch** — the control onboarding has been promising all along.
 *
 * **What it controls.** The Pulse Ping is the one daily mail that links to your brief.
 * This turns it off, and back on.
 *
 * ---
 *
 * ## Why this exists
 *
 * Onboarding tells every new user *"One calm Pulse Ping per day. It links to your brief.
 * **You can change this anytime** — and quiet hours come later in Settings."*
 * (`onboarding-flow.tsx`). Until this control, they could not: the only way to stop the
 * Ping was the one-click unsubscribe inside a Ping they had to receive first, and the
 * backend had no command to turn it back on at all. The 2026-11-17 traceability pass
 * recorded that as open item **O-1** — a promise the product did not keep.
 *
 * ---
 *
 * ## Off is not the same as quiet
 *
 * **Quiet Hours defer; this stops.** A deferred send still arrives, later. This control
 * cancels the digest sends already pending and mints no more — so the description says
 * "stops" rather than anything softer. A settings screen that blurred the two would
 * leave a user wondering why mail they thought they had silenced arrived in the morning.
 *
 * ---
 *
 * ## The scope is the digest, and only the digest
 *
 * **Reminders are untouched, in both directions.** FR-11 splits the two unsubscribe
 * scopes deliberately: the Ping's is per *user* and has no event to hang off, while a
 * reminder's is per `(user, event)`. The server enforces that split — this control just
 * must not imply otherwise, which is why the description names the daily brief and not
 * "notifications".
 *
 * ---
 *
 * ## The body is one key, and that is a real difference
 *
 * `PUT /api/settings/notifications` is a **true patch**: an omitted field is left alone,
 * so this control sends `{"pulse_ping": false}` and nothing else. It deliberately does
 * **not** follow `digest-personal-events.tsx`, which has to resend the whole schedule —
 * that is a constraint of `DigestPreferenceIn` (where `delivery_time` and `timezone` are
 * required), not a house pattern to copy.
 *
 * ---
 *
 * ## The state after a save is the server's answer
 *
 * **The switch moves at once**, so it feels like a control rather than a form. **The
 * server's answer then replaces the guess**, and **a failed save puts it back** — the
 * Ping was not turned off, and a switch claiming otherwise would be claiming something
 * that did not happen.
 */
import { useCallback, useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import { SaveFeedback } from "@/components/settings/save-feedback";
import { SettingRow } from "@/components/settings/setting-row";
import { SwitchControl } from "@/components/settings/switch-control";
import { api } from "@/lib/backend-client";

export type PulsePingSwitchProps = {
  /**
   * Whether the Ping is on. **The server's answer.**
   *
   * The backend reports `true` for a user who has never turned it off — which is the
   * default and the common case — so the control shows what the server believes rather
   * than what this client assumes.
   */
  initialPulsePing: boolean;
};

/**
 * The failure line, **verbatim** — the same one every other row on this screen uses,
 * because the same thing happened: the save did not take.
 *
 * The API's own refusal is shown instead when the API made one; a generic line would
 * throw away a message written for the user.
 */
const FAILURE = "Couldn't save.";

/**
 * The switch's stable accessible name.
 *
 * **It names the thing, not the action.** A name that changed with the state would say
 * both "press me" and "nothing to press" at once — the rule
 * `digest-personal-events.tsx` and `detail-mute-control.tsx` both follow, for the same
 * reason.
 */
const ACCESSIBLE_NAME = "Daily Pulse Ping";

/**
 * The two visible descriptions.
 *
 * **Both are statements about the world**, not instructions — the switch's own name says
 * what pressing it does. The "off" line names the consequence a user actually cares
 * about: no mail, rather than a setting's value.
 */
const VISIBLE = {
  on: "One Pulse Ping a day, linking to your brief",
  off: "No Pulse Ping — your brief is still here when you want it",
} as const;

export function PulsePingSwitch({ initialPulsePing }: PulsePingSwitchProps) {
  /** The setting, as the user has it. The server's answer is the starting state. */
  const [on, setOn] = useState(initialPulsePing);
  /** Whether a save is in flight, so the switch cannot be pressed twice. */
  const [busy, setBusy] = useState(false);
  /** The failure line to show, or `null` — the message, not a flag. */
  const [failure, setFailure] = useState<string | null>(null);
  /** Whether the last save succeeded. */
  const [saved, setSaved] = useState(false);

  const onToggle = useCallback(async () => {
    const next = !on;

    setBusy(true);
    setFailure(null);
    setSaved(false);
    // **The optimistic move.** It flips at once, so the control feels like a control.
    setOn(next);

    try {
      // **One key.** The endpoint is a patch, so every other setting on this screen is
      // left exactly as it was — including the ones this user has never opened.
      const response = await api.PUT("/api/settings/notifications", {
        body: { pulse_ping: next },
      });
      if (response.error) {
        // **The API refused it, and it said why.**
        setFailure(saveFailureMessage(response.error, FAILURE));
        setOn(!next);
        return;
      }
      if (!response.data) {
        setFailure(FAILURE);
        setOn(!next);
        return;
      }
      // **The server's answer replaces the guess.**
      setOn(response.data.pulse_ping);
      setSaved(true);
    } catch {
      // **The request never reached the API**, so there is nothing to quote.
      setFailure(FAILURE);
      setOn(!next);
    } finally {
      setBusy(false);
    }
  }, [on]);

  return (
    <section aria-label="Daily Pulse Ping" data-pulse-ping>
      <SettingRow
        label="Daily Pulse Ping"
        description={on ? VISIBLE.on : VISIBLE.off}
        control={
          <SwitchControl
            checked={on}
            onToggle={() => {
              void onToggle();
            }}
            disabled={busy}
            label={ACCESSIBLE_NAME}
            testAttribute="data-pulse-ping-switch"
          />
        }
        footer={<SaveFeedback busy={busy} saved={saved} failure={failure} />}
      />
    </section>
  );
}
