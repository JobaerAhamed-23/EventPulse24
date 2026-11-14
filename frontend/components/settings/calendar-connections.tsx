"use client";

/**
 * Calendar sync — connect, sync now, disconnect, and reconnect a revoked connection (FR-50).
 *
 * **Two endpoints that had no caller.** `DELETE /api/personal/calendars/{id}` and
 * `POST /api/personal/calendars/{id}/reconnect` were built and tested with the
 * onboarding intent, whose API work item said the surface was *"onboarding step 1 (and,
 * later, Settings → Sources)"*. The later never came, so onboarding promised the user
 * twice — *"You can disconnect anytime"*, *"read-only · disconnect any time in Settings"* —
 * and pointed at a screen that did not exist.
 *
 * ## Connecting lives here too, and not only in onboarding
 *
 * `POST /api/personal/calendars` had exactly one caller: onboarding step 1. A user who
 * skipped that step, or who connected one calendar and later wanted a second, had no way
 * to add one without starting onboarding again — **the only route to the feature ran
 * through a flow you cannot re-enter.** The form below is the second caller, and it is the
 * one a user reaches on purpose.
 *
 * **The cap belongs to the server, and so does its sentence.** A Free account holds one
 * calendar and a Pro account three; the refusal is a 409 carrying `upgrade_hint`, rendered
 * verbatim through `readCapDetails`. Nothing here counts connections to decide whether to
 * offer the form — a client-side count would be a second copy of the cap, free to disagree
 * with the one the server enforces, and it would hide the form from a user whose tier had
 * just changed.
 *
 * ## "Sync now" asks; it does not fetch
 *
 * The button posts to `/calendars/{id}/sync`, which marks the connection due and lets the
 * 60-second dispatcher pick it up. So the honest feedback is *"Syncing…"*, not a result:
 * the row polls until its `last_synced_at` moves, then stops. The poll gives up after
 * `POLL_LIMIT` attempts and says so rather than spinning forever — if the worker is down,
 * a spinner that never resolves is a lie the user can watch.
 *
 * **The address is a credential and lives here for as long as one keystroke needs.** Both
 * forms hold it in state only until the request is sent, then clear it, exactly as the
 * onboarding connect form does. Nothing renders it back.
 *
 * **Disconnect confirms in place.** It purges that connection's imported events, so the
 * confirmation says so. It uses the same two-step idiom as the personal event's danger
 * zone rather than inventing a third confirmation style, and no overlay or focus trap: A-16
 * reserves that weight for deleting an account.
 */
import { useCallback, useEffect, useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";
import { CALENDAR_PROVIDERS, SECRET_ADDRESS_WARNING } from "@/lib/calendar-providers";
import type { CalendarProvider } from "@/lib/calendar-providers";
import type { CalendarConnection } from "@/lib/calendars-read";
import { readCapDetails } from "@/lib/cap-details";

export type CalendarConnectionsProps = {
  /** The connections, as the server read them. */
  initial: CalendarConnection[];
};

/** The offline failure line. Nothing was lost, so it invites a retry. */
const FAILED = "Couldn't do that. Try again in a moment.";

/**
 * How often a queued sync re-reads the list, and how many times.
 *
 * **Five seconds, twelve times — one minute of watching.** The dispatcher's tick is 60
 * seconds, so a sync queued just after a tick lands just before the last attempt. Polling
 * faster would ask the server questions the tick cannot have answered yet.
 */
const POLL_MS = 5_000;
const POLL_LIMIT = 12;

/** The line shown when the poll gave up before the sync landed. */
const SYNC_SLOW = "Still syncing. Reload the page to check.";

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
  /**
   * The connections whose sync we are waiting on, each remembering the `last_synced_at`
   * it had when the sync was asked for.
   *
   * **The remembered value is how "done" is decided.** A queued sync is finished when the
   * server reports a *different* `last_synced_at` than the one the user pressed the button
   * on — not when `sync_in_progress` goes false, which is also false in the gap between
   * the request and the dispatcher's next tick.
   */
  const [awaiting, setAwaiting] = useState<Record<string, string | null>>({});
  /** How many times the current wait has re-read. Reset whenever a new sync is asked for. */
  const [polls, setPolls] = useState(0);
  /** Which provider the connect form is pointed at, and the address typed so far. */
  const [connecting, setConnecting] = useState<{ provider: string; address: string } | null>(null);
  /** The server's own upgrade sentence, when the cap refused a connect. */
  const [capHint, setCapHint] = useState<string | null>(null);

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

  /**
   * The connections still waiting on a queued sync — **derived, never stored.**
   *
   * A wait is over when the server reports a *different* `last_synced_at` than the one the
   * user pressed the button on. That is a question about the list in hand, so it is
   * answered while rendering rather than by an effect writing state: an effect would have
   * to re-run, decide, and set state to say something the list already said, and a
   * `setState` inside an effect costs a second render pass for the privilege.
   *
   * It is **not** `sync_in_progress`, which is also false in the gap between the request
   * and the dispatcher's next tick — the row would flicker back to "Sync now" before the
   * worker had started.
   */
  const pending = connections
    .filter(
      (connection) =>
        connection.id in awaiting &&
        (connection.last_synced_at ?? null) === awaiting[connection.id],
    )
    .map((connection) => connection.id);

  /**
   * The wait ran out before the sync landed.
   *
   * **Giving up is a state, not a silence.** The row says the sync is still going and
   * offers the one thing that will show the truth; the alternative is a "Syncing…" that
   * never resolves because the worker is not running.
   */
  const gaveUp = polls >= POLL_LIMIT;

  /** A stable key for the poll's dependencies — the ids, not the array's identity. */
  const pendingKey = pending.join(",");

  /** While something is queued, re-read. The timeout's callback is what sets state. */
  useEffect(() => {
    if (pendingKey === "" || polls >= POLL_LIMIT) return;
    const timer = setTimeout(() => {
      setPolls((count) => count + 1);
      void refresh();
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [pendingKey, polls, refresh]);

  const syncNow = useCallback(
    async (connection: CalendarConnection) => {
      const before = connection.last_synced_at ?? null;
      const ok = await run(() =>
        api.POST("/api/personal/calendars/{connection_id}/sync", {
          params: { path: { connection_id: connection.id } },
        }),
      );
      // **Only a accepted request starts a wait.** A refusal — the cooldown, a revoked
      // connection — has already been shown by `run`, and marking the row "Syncing…" on
      // top of it would contradict the sentence next to it.
      if (!ok) return;
      setAwaiting((current) => ({ ...current, [connection.id]: before }));
      setPolls(0);
    },
    [run],
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

  const connect = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!connecting) return;
      const address = connecting.address.trim();
      if (!address) return;
      const provider = CALENDAR_PROVIDERS.find((one) => one.key === connecting.provider);
      if (!provider) return;

      setCapHint(null);
      setBusy(true);
      setFailure(null);
      let response;
      try {
        response = await api.POST("/api/personal/calendars", {
          // The label is the provider's own name, the same default onboarding sends.
          body: { provider: provider.key, address, display_label: provider.name },
        });
      } catch {
        setFailure(FAILED);
        setBusy(false);
        return;
      } finally {
        // The address has done its job. It is a credential, so it does not linger in
        // state where a later render could put it back on screen — and that holds whether
        // the connect succeeded, was refused, or never left the browser.
        setConnecting((current) => (current ? { ...current, address: "" } : null));
      }

      if (response.error) {
        // **The cap's own sentence, not the refusal's `message`.** `message` is the fact;
        // `upgrade_hint` is the server-owned upgrade copy the prompt exists to render,
        // and rendering it is what keeps a backend wording change from needing a frontend
        // change.
        const cap = readCapDetails(response.error);
        if (cap !== null) setCapHint(cap.upgradeHint);
        else setFailure(saveFailureMessage(response.error, FAILED) || FAILED);
        setBusy(false);
        return;
      }

      await refresh();
      setBusy(false);
      setConnecting(null);
    },
    [connecting, refresh],
  );

  const chosen: CalendarProvider | undefined = connecting
    ? CALENDAR_PROVIDERS.find((one) => one.key === connecting.provider)
    : undefined;

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
          No calendar connected. Connect one below to see your personal events alongside public
          ones.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {connections.map((connection) => {
            const problem = errorLine(connection.last_error_kind);
            const needsReconnect = connection.status === "needs_reconnect";
            const queued = pending.includes(connection.id);
            // **Waiting and given-up are different.** Once the wait has run out the row
            // says so and the button comes back, so the user can ask again rather than
            // watch a label that will never change.
            const waiting = queued && !gaveUp;
            const syncing = waiting || connection.sync_in_progress;
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
                      read-only · {waiting ? "Syncing…" : syncedLine(connection)}
                    </span>
                  </span>

                  <span className="flex flex-wrap items-center gap-2">
                    {/*
                      **Offered only for an active connection**, because only an active one
                      can be synced: the endpoint answers 409 for the rest, and a button
                      whose only outcome is a refusal is not a button.
                    */}
                    {connection.status === "active" ? (
                      <button
                        type="button"
                        onClick={() => syncNow(connection)}
                        disabled={busy || syncing}
                        data-sync-now={connection.id}
                        className="min-h-[44px] rounded-control border border-border-subtle px-3 text-ink-secondary [font:var(--type-scale-meta-sm)] disabled:opacity-60"
                      >
                        {syncing ? "Syncing…" : "Sync now"}
                      </button>
                    ) : null}

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
                  </span>
                </div>

                {queued && gaveUp ? (
                  <p
                    className="mt-2 text-ink-muted [font:var(--type-scale-body-sm)]"
                    data-sync-slow={connection.id}
                  >
                    {SYNC_SLOW}
                  </p>
                ) : null}

                {problem ? (
                  <p className="mt-2 text-warn-amber [font:var(--type-scale-body-sm)]">{problem}</p>
                ) : null}

                {confirming === connection.id ? (
                  <div className="mt-3 flex flex-wrap items-center gap-3" data-disconnect-confirm>
                    <p className="text-ink-secondary [font:var(--type-scale-body-sm)]">
                      Disconnect this calendar? Its imported events are removed from your Pulse.
                      Events you added yourself stay.
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

      {/*
        **The connect form is always offered**, whatever the user already holds. The cap is
        the server's, and a form hidden by a client-side count would be hidden wrongly for
        anyone whose tier changed in another tab — and would teach the user that the
        feature is missing rather than that their plan is full.
      */}
      <div className="mt-8 border-t border-border-subtle pt-6" data-calendar-connect>
        <h2 className="text-ink-primary [font:var(--type-scale-headline-sm)]">
          Connect a calendar
        </h2>

        {capHint ? (
          // The server's own sentence, with the quiet upgrade link beside it. An inline
          // prompt, never a modal — EXPERIENCE.md §3's Free-tier cap rule.
          <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-sm)]" data-calendar-cap>
            {capHint}{" "}
            <a href="/pricing" className="text-ink-primary underline underline-offset-4">
              Upgrade
            </a>
          </p>
        ) : null}

        {connecting === null ? (
          <ul className="mt-3 flex flex-wrap gap-2">
            {CALENDAR_PROVIDERS.map((provider) => (
              <li key={provider.key}>
                <button
                  type="button"
                  onClick={() => setConnecting({ provider: provider.key, address: "" })}
                  disabled={busy}
                  data-connect-provider={provider.key}
                  className="min-h-[44px] rounded-control border border-border-subtle px-4 text-ink-secondary [font:var(--type-scale-meta-sm)]"
                >
                  {provider.name}
                </button>
              </li>
            ))}
          </ul>
        ) : chosen ? (
          <form className="mt-3 flex flex-col gap-2" onSubmit={connect} data-connect-form>
            <p className="text-ink-secondary [font:var(--type-scale-body-sm)]">{chosen.guidance}</p>
            <label
              htmlFor="calendar-address"
              className="text-ink-secondary [font:var(--type-scale-meta-sm)]"
            >
              {chosen.name} address
            </label>
            <input
              id="calendar-address"
              type="url"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              value={connecting.address}
              placeholder="https://…/basic.ics"
              onChange={(event) =>
                setConnecting({ provider: chosen.key, address: event.target.value })
              }
              className="w-full rounded-control border border-border-subtle bg-surface-subtle px-3 py-2 text-ink-primary"
            />
            {/*
              The standing warning, and the reason the field is treated as a secret:
              anyone holding this address can read the calendar.
            */}
            <p className="text-ink-muted [font:var(--type-scale-body-sm)]">
              {SECRET_ADDRESS_WARNING}
            </p>
            <div className="flex flex-wrap gap-3">
              <button
                type="submit"
                disabled={busy || !connecting.address.trim()}
                data-connect-submit
                className="min-h-[44px] rounded-control border border-border-strong px-4 text-ink-primary [font:var(--type-scale-meta-sm)]"
              >
                Connect
              </button>
              <button
                type="button"
                onClick={() => setConnecting(null)}
                data-connect-cancel
                className="min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : null}
      </div>
    </section>
  );
}
