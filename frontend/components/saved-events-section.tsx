import type { components } from "@/lib/api/schema";
import { apiBaseUrl } from "@/lib/api-base-url";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";
import { utcInstantToLocal } from "@/lib/timezones";

type SavedEvent = components["schemas"]["SavedEventOut"];

/**
 * The events the user has saved from the public catalog — a **server** read, like the
 * personal-events section beside it.
 *
 * The placeholder home "links to personal and saved events" (the work item). Neither has
 * a route of its own in the route map — `/timeline` and `/conflicts` exist, a saved-events
 * page does not — so the two are shown here rather than linked to a 404.
 *
 * It is read-only. Saving and unsaving happen on the catalog and event-detail surfaces,
 * which this intent does not build.
 *
 * The read carries the visitor's cookies (`sessionHeaders`), because the Next.js server
 * is a separate HTTP client with no session of its own. Like the personal read, a failure
 * is an empty list rather than an error page: the home must render for a signed-in user
 * whatever the saved-events endpoint is doing.
 */
export async function SavedEventsSection() {
  const { events, omitted } = await readSavedEvents();

  return (
    <div>
      <h2 className="[font:var(--type-scale-headline-lg)]">Saved events</h2>
      {events.length === 0 ? (
        <p className="mt-4 [font:var(--type-scale-body-md)] text-ink-muted">
          You haven&apos;t saved any events yet.
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-2">
          {events.map((event) => (
            <li key={event.id}>
              <SavedEventRow event={event} />
            </li>
          ))}
        </ul>
      )}
      {/*
        Saves whose catalog event has since been superseded or unpublished. The API counts
        them rather than dropping them, and says why: "the count lets the client tell the
        user that something they saved is no longer available, rather than silently
        dropping it". They have no title left to show, so the count is all there is to say.
      */}
      {omitted > 0 ? (
        <p className="mt-4 [font:var(--type-scale-body-sm)] text-ink-muted">
          {omitted === 1
            ? "1 saved event is no longer available."
            : `${omitted} saved events are no longer available.`}
        </p>
      ) : null}
    </div>
  );
}

type SavedEvents = { events: SavedEvent[]; omitted: number };

async function readSavedEvents(): Promise<SavedEvents> {
  if (!apiBaseUrl()) return { events: [], omitted: 0 };

  try {
    const response = await api.GET("/api/personal/saved-events", {
      headers: await sessionHeaders(),
    });
    return {
      events: response.data?.items ?? [],
      omitted: response.data?.omitted ?? 0,
    };
  } catch {
    return { events: [], omitted: 0 };
  }
}

/**
 * One saved event.
 *
 * The cool-public stripe is paired with the visible label "Saved", because colour is
 * never the sole carrier of meaning (WCAG 1.4.1) — the same pairing the personal rows use
 * for their warm stripe.
 */
function SavedEventRow({ event }: { event: SavedEvent }) {
  const zone = event.start_time_tz || "UTC";
  const local = utcInstantToLocal(new Date(event.start_time_utc), zone);
  return (
    <div className="flex items-center gap-3 rounded-card border border-border-subtle bg-surface-elevated px-4 py-3">
      <span aria-hidden="true" className="h-8 w-[3px] shrink-0 rounded-full bg-accent-slate" />
      <span className="text-[11px] font-semibold tracking-[0.08em] text-accent-slate uppercase">
        Saved
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate [font:var(--type-scale-meta-md)]">{event.title}</span>
        <span className="block [font:var(--type-scale-body-sm)] text-ink-muted">
          {local.date} · {local.time}
          {event.venue_city ? ` · ${event.venue_city}` : ""}
        </span>
      </span>
    </div>
  );
}
