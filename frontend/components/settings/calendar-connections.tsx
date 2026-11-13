"use client";

/**
 * Calendar sync — disconnect, and reconnect a revoked connection (FR-50).
 *
 * **Two endpoints that had no caller.** `DELETE /api/personal/calendars/{id}` and
 * `POST /api/personal/calendars/{id}/reconnect` were built and tested with the
 * onboarding intent, whose API work item said the surface was *"onboarding step 1 (and,
 * later, Settings → Sources)"*. The later never came, so onboarding promised the user
 * twice — *"You can disconnect anytime"*, *"read-only · disconnect any time in Settings"* —
 * and pointed at a screen that did not exist.
 *
 * **The address is a credential and lives here for as long as one keystroke needs.** The
 * reconnect form holds it in state only until the request is sent, then clears it, exactly
 * as the onboarding connect form does. Nothing renders it back.
 *
 * **Disconnect confirms in place.** It purges that connection's imported events, so the
 * confirmation says so. It uses the same two-step idiom as the personal event's danger
 * zone rather than inventing a third confirmation style, and no overlay or focus trap: A-16
 * reserves that weight for deleting an account.
 */
import { useCallback, useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import type { CalendarConnection } from "@/lib/calendars-read";
import { api } from "@/lib/backend-client";

export type CalendarConnectionsProps = {
  /** The connections, as the server read them. */
  initial: CalendarConnection[];
};

/** The offline failure line. Nothing was lost, so it invites a retry. */
const FAILED = "Couldn't do that. Try again in a moment.";

/**
 * One error slug, as a sentence.
 *
 * **A slug is not a sentence, and `last_error_kind` is a slug** — `revoked`, `transient`
 * and whatever the adapter adds next. Printing it raw shows a person an identifier. An
 * unknown slug falls back to a neutral line rather than to the slug itself.
 */
function errorLine(kind: string | null | undefined): string | null {
  if (!kind) return null;
  if (kind === "revoked") return "The provider revoked this address. Paste a new one to reconnect.";
  if (kind === "transient") return "The last sync didn't go through. It will be retried.";
  return "The last sync didn't go through.";
}

/** When a connection last synced, as a person reads it. */
function syncedLine(connection: CalendarConnection): string {
  if (connection.sync_in_progress) return "Syncing now.";
  if (!connection.last_synced_at) return "Not synced yet.";
  const parsed = new Date(connection.last_synced_at);
  if (Number.isNaN(parsed.getTime())) return "Not synced yet.";
  return `Last synced ${parsed.toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  })}.`;
}

export function CalendarConnections({ initial }: CalendarConnectionsProps) {
  const [connections, setConnections] = useState<CalendarConnection[]>(initial);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  /** Which connection is awaiting a disconnect confirmation, if any. */
  const [confirming, setConfirming] = useState<string | null>(null);
  /** Which connection is being reconnected, and the address pasted so far. */
  const [reconnecting, setReconnecting] = useState<{ id: string; address: string } | null>(null);

  /** Re-read, so what is on screen is the server's list rather than a guess. */
  const refresh = useCallback(async (): Promise<void> => {
    const response = await api.GET("/api/personal/calendars");
    if (response.data) setConnections(response.data.items);
  }, []);

  const run = useCallback(
    async (write: () => Promise<{ error?: unknown; data?: unknown }>): Promise<boolean> => {
      setBusy(true);
      setFailure(null);
      try {
        const response = await write();
        if (response.error) {
          setFailure(saveFailureMessage(response.error, FAILED) || FAILED);
          return false;
        }
        await refresh();
        return true;
      } catch {
        setFailure(FAILED);
        return false;
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const disconnect = useCallback(
    async (id: string) => {
      const ok = await run(() =>
        api.DELETE("/api/personal/calendars/{connection_id}", {
          params: { path: { connection_id: id } },
        }),
      );
      // **A refused disconnect keeps the row and the confirmation.** Clearing them would
      // leave a connected calendar on screen with a line saying something went wrong and
      // no control to try again with.
      if (ok) setConfirming(null);
    },
    [run],
  );

  const reconnect = useCallback(async () => {
    if (!reconnecting) return;
    const address = reconnecting.address.trim();
    if (!address) return;
    await run(() =>
      api.POST("/api/personal/calendars/{connection_id}/reconnect", {
        params: { path: { connection_id: reconnecting.id } },
        body: { address, display_label: "" },
      }),
    );
    // **The address has done its job, and that is true whether or not the request
    // succeeded.** It is a credential, so it does not linger in state — the same rule the
    // onboarding connect form follows. The result is deliberately not branched on: a
    // failed reconnect costs the user a re-paste, and holding a secret in memory to save
    // them that is the wrong trade. The connection is still `needs_reconnect`, so the
    // Reconnect control is still there, and `run` has already shown what went wrong.
    setReconnecting(null);
  }, [reconnecting, run]);

  return (
    <section aria-label="Calendar sync" data-calendar-connections>
      {failure ? (
        <p role="alert" className="mb-4 text-signal-error [font:var(--type-scale-body-sm)]">
          {failure}
        </p>
      ) : null}

      {connections.length === 0 ? (
        // **An honest empty state, not an error.** A user who never connected a calendar
        // has nothing wrong with their account.
        <p className="text-ink-muted [font:var(--type-scale-body-md)]" data-no-calendars>
          No calendar connected. You can connect one when you set up your Pulse.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {connections.map((connection) => {
            const problem = errorLine(connection.last_error_kind);
            const needsReconnect = connection.status === "needs_reconnect";
            return (
              <li
                key={connection.id}
                className="rounded-card border border-border-subtle bg-surface-elevated px-4 py-3"
                data-calendar={connection.id}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block truncate text-ink-primary [font:var(--type-scale-meta-md)]">
                      {connection.display_label || connection.provider}
                    </span>
                    <span className="block text-ink-muted [font:var(--type-scale-body-sm)]">
                      read-only · {syncedLine(connection)}
                    </span>
                  </span>

                  {confirming === connection.id ? null : (
                    <button
                      type="button"
                      onClick={() => setConfirming(connection.id)}
                      disabled={busy}
                      data-disconnect={connection.id}
                      className="min-h-[44px] rounded-control border border-border-subtle px-3 text-ink-secondary [font:var(--type-scale-meta-sm)]"
                    >
                      Disconnect
                    </button>
                  )}
                </div>

                {problem ? (
                  <p className="mt-2 text-warn-amber [font:var(--type-scale-body-sm)]">{problem}</p>
                ) : null}

                {confirming === connection.id ? (
                  <div className="mt-3 flex flex-wrap items-center gap-3" data-disconnect-confirm>
                    <p className="text-ink-secondary [font:var(--type-scale-body-sm)]">
                      Disconnect this calendar? Its imported events are removed from your
                      Pulse. Events you added yourself stay.
                    </p>
                    <button
                      type="button"
                      onClick={() => disconnect(connection.id)}
                      disabled={busy}
                      data-disconnect-yes
                      className="min-h-[44px] rounded-control border border-border-strong px-4 text-ink-primary [font:var(--type-scale-meta-sm)]"
                    >
                      Disconnect it
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirming(null)}
                      data-disconnect-no
                      className="min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
                    >
                      Keep it
                    </button>
                  </div>
                ) : null}

                {/*
                  **Reconnect is offered only for a revoked connection.** The provider
                  revoked the old secret, so this is a *new* address — which is why it is
                  a form and not a button.
                */}
                {needsReconnect ? (
                  reconnecting?.id === connection.id ? (
                    <div className="mt-3 flex flex-col gap-2" data-reconnect-form>
                      <label
                        htmlFor={`reconnect-${connection.id}`}
                        className="text-ink-secondary [font:var(--type-scale-meta-sm)]"
                      >
                        New address
                      </label>
                      <input
                        id={`reconnect-${connection.id}`}
                        type="url"
                        inputMode="url"
                        autoComplete="off"
                        spellCheck={false}
                        value={reconnecting.address}
                        placeholder="https://…/basic.ics"
                        onChange={(event) =>
                          setReconnecting({ id: connection.id, address: event.target.value })
                        }
                        className="w-full rounded-control border border-border-subtle bg-surface-subtle px-3 py-2 text-ink-primary"
                      />
                      <div className="flex flex-wrap gap-3">
                        <button
                          type="button"
                          onClick={reconnect}
                          disabled={busy || !reconnecting.address.trim()}
                          data-reconnect-submit
                          className="min-h-[44px] rounded-control border border-border-strong px-4 text-ink-primary [font:var(--type-scale-meta-sm)]"
                        >
                          Reconnect
                        </button>
                        <button
                          type="button"
                          onClick={() => setReconnecting(null)}
                          data-reconnect-cancel
                          className="min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setReconnecting({ id: connection.id, address: "" })}
                      disabled={busy}
                      data-reconnect={connection.id}
                      className="mt-3 min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
                    >
                      Reconnect
                    </button>
                  )
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
