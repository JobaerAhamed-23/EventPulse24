"use client";

/**
 * Step 1 — connect a calendar (FR-3, FR-50, AD-18).
 *
 * Three things here are not obvious from the mockup.
 *
 * **The address is a credential.** The user pastes their provider's *secret* ICS/webcal
 * address; anyone holding it can read the calendar, which is why the backend encrypts it
 * and never returns it. So the field is masked, it is cleared the moment the connect
 * succeeds, and it is never written to `localStorage` or `sessionStorage`. There is no
 * reveal toggle: the sign-in password toggle exists so someone can check their own
 * typing, but this is a pasted string nobody needs to read back.
 *
 * **The import does not happen in the request.** `POST /api/personal/calendars` answers
 * immediately and marks the connection due; the worker's 60-second tick picks it up
 * (AD-11 forbids long work in a request). So connecting starts a **poll**, bounded at
 * `SYNC_WAIT_MS`, and when it runs out the step says the import is still running rather
 * than spinning forever. Continue and Skip work the whole time — the user is never held
 * hostage to a background job, which is also what a developer with no worker running
 * sees.
 *
 * **The events shown are this connection's.** `PersonalEventOut.calendar_connection_id`
 * says which connection imported a row, so the step can show exactly what this calendar
 * brought in rather than the user's whole list.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { components } from "@/lib/api/schema";
import { readApiError } from "@/lib/api-errors";
import { api } from "@/lib/backend-client";
import { CALENDAR_PROVIDERS, SECRET_ADDRESS_WARNING } from "@/lib/calendar-providers";
import { utcInstantToLocal } from "@/lib/timezones";

type Connection = components["schemas"]["CalendarConnectionOut"];
type PersonalEvent = components["schemas"]["PersonalEventOut"];

/** How often the connection is re-read while its first import runs. */
const POLL_EVERY_MS = 3000;

/**
 * How long the step waits for the first import before saying it will finish in the
 * background: the dispatcher's 60-second tick, plus time for the fetch itself.
 */
const SYNC_WAIT_MS = 75000;

type Phase =
  | { kind: "choosing" }
  | { kind: "connecting" }
  | { kind: "importing"; connection: Connection }
  | { kind: "imported"; connection: Connection; events: PersonalEvent[] }
  | { kind: "background"; connection: Connection }
  | { kind: "failed"; connection: Connection | null };

export type CalendarStepProps = {
  /** A connection the user already has, read with the step's first paint. */
  existing?: Connection | null;
};

function providerName(key: string): string {
  return CALENDAR_PROVIDERS.find((candidate) => candidate.key === key)?.name ?? key;
}

export function CalendarStep({ existing = null }: CalendarStepProps) {
  const [provider, setProvider] = useState<string | null>(null);
  const [address, setAddress] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [capMessage, setCapMessage] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>(
    // A user who comes back to step 1 sees what they already connected, not a blank form.
    existing ? { kind: "imported", connection: existing, events: [] } : { kind: "choosing" },
  );
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending) clearTimeout(timer);
    };
  }, []);

  const wait = useCallback(
    (ms: number) =>
      new Promise<void>((resolve) => {
        timers.current.push(setTimeout(resolve, ms));
      }),
    [],
  );

  /** The events this connection imported. An empty list is a fine answer. */
  const importedEvents = useCallback(async (connectionId: string): Promise<PersonalEvent[]> => {
    const response = await api.GET("/api/personal/events");
    const items = response.data?.items ?? [];
    return items.filter((event) => event.calendar_connection_id === connectionId);
  }, []);

  /**
   * A calendar connected earlier still has to say what it brought in.
   *
   * The page hands this component the connection, not its events, so without this the
   * step would greet a returning user with "Connected. Nothing upcoming in that calendar
   * yet." over a calendar that had imported a fortnight of them — a sentence that is
   * false rather than merely empty.
   */
  useEffect(() => {
    if (!existing) return;
    let current = true;
    void importedEvents(existing.id).then((events) => {
      if (current) setPhase({ kind: "imported", connection: existing, events });
    });
    return () => {
      current = false;
    };
  }, [existing, importedEvents]);

  /**
   * Watch the connection until its first import lands, or until the wait runs out.
   *
   * A connection that comes back needing a reconnection, or carrying an error kind, has
   * failed — the address was refused or the feed could not be read — and that is the
   * failure state, not a slow import.
   */
  const watchSync = useCallback(
    async (connection: Connection): Promise<void> => {
      const deadline = Date.now() + SYNC_WAIT_MS;

      while (Date.now() < deadline) {
        await wait(POLL_EVERY_MS);

        let current;
        try {
          const response = await api.GET("/api/personal/calendars/{connection_id}", {
            params: { path: { connection_id: connection.id } },
          });
          current = response.data;
        } catch {
          // One failed poll is not a failed import: the connection is already made and
          // the worker is working. Keep watching until the deadline.
          continue;
        }
        if (!current) continue;

        if (current.status === "needs_reconnect" || current.last_error_kind) {
          setPhase({ kind: "failed", connection: current });
          return;
        }
        if (!current.sync_in_progress && current.last_synced_at) {
          setPhase({
            kind: "imported",
            connection: current,
            events: await importedEvents(current.id),
          });
          return;
        }
      }

      setPhase({ kind: "background", connection });
    },
    [importedEvents, wait],
  );

  const connect = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    if (provider === null) return;
    setFieldError(null);
    setCapMessage(null);
    setPhase({ kind: "connecting" });

    let response;
    try {
      response = await api.POST("/api/personal/calendars", {
        // The label is the provider's own name: onboarding does not ask the user to name
        // a calendar, and the backend's default is an empty string. Settings → Sources is
        // where a user will rename one.
        body: { provider, address: address.trim(), display_label: providerName(provider) },
      });
    } catch {
      // The request never left the browser, so no calendar was connected and the address
      // the user pasted is still in the field for them to try again with.
      setPhase({ kind: "failed", connection: null });
      return;
    }

    if (response.error) {
      const failure = readApiError(response.error);
      if (failure.code === "calendar_cap_reached") {
        setCapMessage(failure.message);
        setPhase({ kind: "choosing" });
        return;
      }
      if (failure.code === "invalid_calendar_credential" || failure.fieldErrors.url) {
        setFieldError(failure.fieldErrors.url ?? failure.message);
        setPhase({ kind: "choosing" });
        return;
      }
      setPhase({ kind: "failed", connection: null });
      return;
    }

    // The address has done its job. It is a credential, so it does not linger in state
    // where a later render could put it back on screen.
    setAddress("");
    setPhase({ kind: "importing", connection: response.data });
    await watchSync(response.data);
  };

  const retry = (): void => {
    setPhase({ kind: "choosing" });
    setFieldError(null);
  };

  if (phase.kind === "failed") {
    // `EXPERIENCE.md`'s locked copy, with two equal-weight buttons: neither skipping nor
    // retrying is the "right" answer, so neither is the primary.
    return (
      <div className="rounded-card border border-border-subtle bg-surface-subtle px-6 py-4">
        <p role="alert" className="[font:var(--type-scale-body-md)] text-ink-primary">
          Connection failed. Skip for now?
        </p>
        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            onClick={retry}
            className="rounded-control border border-border-subtle px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
          >
            Try again
          </button>
        </div>
        <p className="mt-3 [font:var(--type-scale-body-sm)] text-ink-muted">
          Or use “Skip for now” below — you can connect a calendar later in Settings.
        </p>
      </div>
    );
  }

  if (phase.kind === "importing" || phase.kind === "connecting") {
    return (
      <SyncState
        line={
          phase.kind === "connecting"
            ? "Connecting…"
            : "Connected. Importing your events — this takes a moment."
        }
      />
    );
  }

  if (phase.kind === "background") {
    return (
      <SyncState line="Connected. We're still importing — your events will appear on your Pulse shortly." />
    );
  }

  if (phase.kind === "imported") {
    return <ImportedEvents connection={phase.connection} events={phase.events} />;
  }

  return (
    <div>
      <div role="group" aria-label="Choose a calendar provider" className="flex flex-col gap-3">
        {CALENDAR_PROVIDERS.map((candidate) => (
          <button
            key={candidate.key}
            type="button"
            aria-pressed={provider === candidate.key}
            onClick={() => {
              setProvider(candidate.key);
              setFieldError(null);
            }}
            className={[
              "flex items-center gap-4 rounded-card border px-4 py-3 text-left",
              provider === candidate.key ? "border-accent-terracotta" : "border-border-subtle",
            ].join(" ")}
          >
            <span
              aria-hidden="true"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-control bg-surface-inset [font:var(--type-scale-meta-md)]"
            >
              {candidate.monogram}
            </span>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="[font:var(--type-scale-meta-md)] text-ink-primary">
                {candidate.name}
              </span>
              <span className="[font:var(--type-scale-body-sm)] text-ink-muted">
                {candidate.subLabel}
              </span>
            </span>
            <span aria-hidden="true" className="text-ink-muted">
              →
            </span>
          </button>
        ))}
      </div>

      {capMessage ? (
        /* The Free cap. Inline, with a quiet link — the API's payload carries no modal
           semantics and this surface adds none. */
        <div
          role="alert"
          className="mt-4 rounded-card border border-border-subtle bg-surface-subtle px-4 py-3"
        >
          <p className="[font:var(--type-scale-body-sm)] text-ink-secondary">{capMessage}</p>
          <a
            href="/pricing"
            className="mt-1 inline-block [font:var(--type-scale-body-sm)] text-accent-terracotta underline underline-offset-4"
          >
            Upgrade
          </a>
        </div>
      ) : null}

      {provider !== null ? (
        <AddressForm
          provider={provider}
          address={address}
          error={fieldError}
          onAddressChange={setAddress}
          onSubmit={connect}
        />
      ) : null}

      <p className="mt-6 flex items-start gap-2 [font:var(--type-scale-body-sm)] text-ink-muted">
        <span aria-hidden="true">ⓘ</span>
        <span>
          We never write to your calendar. Read-only access lets us see what&apos;s coming up — we
          never add anything. The Free plan connects one calendar.
        </span>
      </p>
    </div>
  );
}

/** The chosen provider's guidance, and the masked field. */
function AddressForm({
  provider,
  address,
  error,
  onAddressChange,
  onSubmit,
}: {
  provider: string;
  address: string;
  error: string | null;
  onAddressChange: (value: string) => void;
  onSubmit: (event: React.FormEvent) => void;
}) {
  const chosen = CALENDAR_PROVIDERS.find((candidate) => candidate.key === provider);
  if (!chosen) return null;

  return (
    <form
      onSubmit={onSubmit}
      className="mt-6 rounded-card border border-border-subtle bg-surface-subtle px-6 py-4"
    >
      <p className="[font:var(--type-scale-body-sm)] text-ink-secondary">{chosen.guidance}</p>

      <label
        htmlFor="calendar-address"
        className="mt-4 mb-2 block text-[12px] font-semibold tracking-[0.06em] text-ink-secondary uppercase"
      >
        {chosen.name} address
      </label>
      <input
        id="calendar-address"
        name="calendar_address"
        /* Masked: it is a credential, not a setting. */
        type="password"
        value={address}
        autoComplete="off"
        spellCheck={false}
        placeholder="https://…/basic.ics"
        aria-invalid={Boolean(error)}
        aria-describedby={error ? "calendar-address-error" : "calendar-address-warning"}
        onChange={(event) => onAddressChange(event.target.value)}
        className={[
          "w-full rounded-control border bg-surface-elevated px-3 py-2 [font:var(--type-scale-body-md)]",
          error ? "border-signal-warn" : "border-border-subtle",
        ].join(" ")}
      />
      {error ? (
        <p
          id="calendar-address-error"
          role="alert"
          className="mt-2 flex items-start gap-2 [font:var(--type-scale-body-sm)] text-signal-warn"
        >
          <span aria-hidden="true">⚠</span>
          <span>{error}</span>
        </p>
      ) : (
        <p
          id="calendar-address-warning"
          className="mt-2 [font:var(--type-scale-body-sm)] text-ink-muted"
        >
          {SECRET_ADDRESS_WARNING}
        </p>
      )}

      <button
        type="submit"
        disabled={address.trim() === ""}
        className="mt-4 rounded-control bg-accent-terracotta px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-inverse disabled:bg-surface-inset disabled:text-ink-faint"
      >
        Connect
      </button>
    </form>
  );
}

/** The sync line: a static dot and a sentence. No spinner — the product has none. */
function SyncState({ line }: { line: string }) {
  return (
    <p
      role="status"
      className="flex items-center gap-3 rounded-card border border-border-subtle bg-surface-subtle px-6 py-4 [font:var(--type-scale-body-md)] text-ink-secondary"
    >
      <span aria-hidden="true" className="h-2 w-2 rounded-full bg-accent-terracotta" />
      {line}
    </p>
  );
}

/** What the connected calendar brought in. */
function ImportedEvents({
  connection,
  events,
}: {
  connection: Connection;
  events: PersonalEvent[];
}) {
  return (
    <div className="rounded-card border border-border-subtle bg-surface-subtle px-6 py-4">
      <p role="status" className="[font:var(--type-scale-body-md)] text-ink-primary">
        {events.length === 0
          ? "Connected. Nothing upcoming in that calendar yet."
          : events.length === 1
            ? "Connected. 1 event is on your Pulse."
            : `Connected. ${events.length} events are on your Pulse.`}
      </p>
      <p className="mt-1 [font:var(--type-scale-body-sm)] text-ink-muted">
        {connection.display_label || connection.provider} · read-only · disconnect any time in
        Settings
      </p>

      {events.length > 0 ? (
        <ul className="mt-4 flex flex-col gap-2">
          {events.slice(0, 5).map((event) => (
            <li
              key={event.id}
              className="flex items-center gap-3 rounded-control bg-surface-elevated px-3 py-2"
            >
              {/* The warm Personal tone is always paired with the word (WCAG 1.4.1). */}
              <span
                aria-hidden="true"
                className="h-6 w-[3px] shrink-0 rounded-full bg-warm-personal"
              />
              <span className="text-[11px] font-semibold tracking-[0.08em] text-warm-personal uppercase">
                Personal
              </span>
              <span className="min-w-0 flex-1 truncate [font:var(--type-scale-body-sm)]">
                {event.name}
              </span>
              <span className="[font:var(--type-scale-body-sm)] text-ink-muted">
                {startedAt(event)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function startedAt(event: PersonalEvent): string {
  const zone = event.start_time_tz || "UTC";
  const local = utcInstantToLocal(new Date(event.start_time_utc), zone);
  return `${local.date} · ${local.time}`;
}
