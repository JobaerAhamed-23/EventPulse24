"use client";

/**
 * The client island that owns the personal-event flow: create → conflict → resolve → edit.
 *
 * **The conflict sheet is not opened by the user — it is opened by the server's 409.** The
 * backend writes the event and *then* detects the conflict, leaving the pair `active` as
 * the pending prompt. So a 409 is not a failed write: the event exists, and the prompt
 * resolves it.
 *
 * This component is therefore the only place that knows the round trip:
 *
 *   1. post the create → a 201 means no conflict; close the form
 *   2. a 409 means the event was written and a prompt is pending → open the conflict sheet
 *   3. the user's choice goes to the resolve endpoint with the id the 409 carried
 *   4. "edit the new one" opens the new event in the edit sheet; "update the existing one"
 *      opens the *existing* event; "delete the new one" deletes it; "keep both" does neither
 *
 * The API is reached only through `api` from `@/lib/backend-client` (AD-19).
 */
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { cardTime } from "@/lib/detail-time";
import { utcInstantToLocal } from "@/lib/timezones";

import { ConflictResolution, type Conflict } from "./sheets/conflict-resolution";
import { PersonalEventForm, type PersonalEventFormValues } from "./sheets/personal-event-form";

type PersonalEvent = components["schemas"]["PersonalEventOut"];
type ConflictDetails = components["schemas"]["SchedulingConflictDetails"];
/** The resolutions the API accepts. */
type Resolution = components["schemas"]["ConflictResolutionIn"]["resolution"];

export type PersonalEventsPanelProps = {
  /** The user's personal events, read by the server component that renders this. */
  events?: PersonalEvent[];
  /**
   * The create sheet's open state, when the caller drives it.
   *
   * The **Add** nav affordance opens the create sheet from outside the panel, so the
   * panel has to accept the state from its caller. Left `undefined`, the panel owns it
   * and its own "Add event" button drives it.
   */
  createOpen?: boolean;
  /** Called when the caller drives the create sheet's open state. */
  onCreateOpenChange?: (open: boolean) => void;
  /**
   * Mount the flow's two sheets and nothing else — no heading, no list, no button.
   *
   * The nav's **Add** affordance needs the create → conflict → resolve round trip, not the
   * panel around it. Rendered whole inside the sidenav, the panel pushed a headline-sized
   * "Your personal events" between the routes and the footer; rendered whole beside the
   * bottom-tab bar, it became a third column of the shell's flex row and squeezed the
   * mobile page to a sliver. The sheets are native `<dialog>`s, so closed they take no
   * space. The outcome line is announced, not shown: there is no panel to hold a line.
   * The visible confirmation is the page's own list, which every successful write
   * refreshes (`router.refresh()`).
   */
  sheetsOnly?: boolean;
  /**
   * Whether the panel draws its own "Add event" button. The home page's header already
   * carries "+ Add personal event", and a second Add a few hundred pixels below it would
   * be two controls for one action.
   */
  addButton?: boolean;
};

export function PersonalEventsPanel({
  events = [],
  createOpen,
  onCreateOpenChange,
  sheetsOnly = false,
  addButton = true,
}: PersonalEventsPanelProps) {
  // **Every successful write refreshes the server's read.** The list is a server
  // component's read (`PersonalEventsSection`), so a write in this island is invisible
  // until the route re-renders; `router.refresh()` re-runs the server components and keeps
  // this island's state. Without it, a saved event looked like nothing happened.
  // The panel's own create state, used when the caller does not drive it.
  const router = useRouter();
  const [ownFormOpen, setOwnFormOpen] = useState(false);
  const [editing, setEditing] = useState<PersonalEvent | null>(null);
  const [highlightStartTime, setHighlightStartTime] = useState(false);
  // A fresh key per opening, so the form is remounted with the new seed rather than
  // carrying the last one's values.
  const [formKey, setFormKey] = useState(0);

  // The pending conflict: the server's 409 payload, kept until it is answered.
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [pending, setPending] = useState<{
    id: string;
    name: string;
    start_time_utc: string;
  } | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const formOpen = createOpen ?? ownFormOpen;

  const setFormOpen = (open: boolean): void => {
    if (createOpen === undefined) setOwnFormOpen(open);
    onCreateOpenChange?.(open);
  };

  const closeForm = (): void => {
    setFormOpen(false);
    setEditing(null);
    setHighlightStartTime(false);
  };

  const openCreate = (): void => {
    setEditing(null);
    setHighlightStartTime(false);
    setFormKey((key) => key + 1);
    setFormOpen(true);
  };

  const openEdit = (event: PersonalEvent, highlight = false): void => {
    setEditing(event);
    setHighlightStartTime(highlight);
    setFormKey((key) => key + 1);
    setFormOpen(true);
  };

  /** The create and the edit share the submit: the mode says which endpoint to call. */
  const submit = async (body: {
    name: string;
    start_time_utc: string;
    start_time_tz: string;
    end_time_utc: string | null;
    location: string | null;
    notes: string | null;
  }): Promise<void> => {
    const response = editing
      ? await api.PATCH("/api/personal/events/{event_id}", {
          params: { path: { event_id: editing.id } },
          body,
        })
      : await api.POST("/api/personal/events", { body });

    if (response.error && "details" in response.error && response.error.details) {
      const details = response.error.details as ConflictDetails;
      const first = details.conflicts?.[0];
      if (first) {
        // A 409: the event was written and a prompt is pending. The conflict sheet opens.
        setConflict(first);
        setPending({
          id: details.event_id,
          name: body.name,
          start_time_utc: body.start_time_utc,
        });
        setFormOpen(false);
        setEditing(null);
        setHighlightStartTime(false);
        router.refresh();
        return;
      }
    }

    if (response.error) {
      setMessage("We couldn't save that. Try again.");
      return;
    }
    setMessage(editing ? `"${body.name}" was updated.` : `"${body.name}" was added.`);
    closeForm();
    router.refresh();
  };

  /** The user's choice on the conflict prompt. */
  const resolve = async (resolution: Resolution): Promise<void> => {
    if (!conflict || !pending) return;
    const response = await api.POST("/api/personal/events/conflicts/{pair_id}/resolve", {
      params: { path: { pair_id: conflict.pair_id } },
      body: { resolution, new_side_id: pending.id },
    });
    if (response.error) {
      setMessage("We couldn't record that choice. Try again.");
      return;
    }

    const other = conflict.other;
    const resolved = conflict;
    setConflict(null);
    setPending(null);
    router.refresh();

    if (resolution === "edit_new") {
      // The new event, opened in edit mode with the conflicting time pre-highlighted.
      openEdit(
        {
          id: pending.id,
          name: pending.name,
          start_time_utc: pending.start_time_utc,
          start_time_tz: "",
          version: 1,
        },
        true,
      );
      return;
    }
    if (resolution === "update_existing") {
      // The **existing** event — for a duplicate, the second action opens this one.
      openEdit(
        {
          id: other.id,
          name: other.name,
          start_time_utc: other.start_time_utc,
          start_time_tz: "",
          version: 1,
        },
        true,
      );
      return;
    }
    if (resolution === "delete_new") {
      setMessage(`"${pending.name}" was deleted.`);
      return;
    }
    setMessage(`Both events are on your timeline.${resolved.kind === "duplicate" ? "" : ""}`);
  };

  const sheets = (
    <>
      <PersonalEventForm
        key={formKey}
        open={formOpen}
        mode={editing ? "edit" : "create"}
        initial={editing ? seedFrom(editing) : undefined}
        highlightStartTime={highlightStartTime}
        onClose={closeForm}
        onSubmit={submit}
      />

      <ConflictResolution
        open={conflict !== null}
        conflict={conflict}
        newEvent={pending}
        onResolve={resolve}
      />
    </>
  );

  if (sheetsOnly) {
    return (
      <>
        {/* A live region without `role="status"`: the nav mounts this on every authed
            page, and a page's own status region (the digest's "ready" line) stays the
            only one there is. */}
        <p aria-live="polite" className="sr-only">
          {message}
        </p>
        {sheets}
      </>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-4">
        <h2 className="[font:var(--type-scale-headline-lg)]">Your personal events</h2>
        {addButton ? (
          <button
            type="button"
            onClick={openCreate}
            className="rounded-control bg-accent-terracotta px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-inverse"
          >
            Add event
          </button>
        ) : null}
      </div>

      {message ? (
        <p className="mt-3 [font:var(--type-scale-body-sm)] text-ink-secondary">{message}</p>
      ) : null}

      {events.length === 0 ? (
        <p className="mt-4 [font:var(--type-scale-body-md)] text-ink-muted">
          You haven&apos;t added any personal events yet.
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-2">
          {events.map((event) => (
            <li key={event.id}>
              <PersonalEventRow event={event} onEdit={() => openEdit(event)} />
            </li>
          ))}
        </ul>
      )}

      {sheets}
    </div>
  );
}

/**
 * One personal event.
 *
 * The warm-personal stripe is **always paired with the visible text label "Personal"** —
 * colour is never the sole carrier of meaning (WCAG 1.4.1). This is the same pairing the
 * design system specifies for the timeline event-block and the digest card; there is no
 * Pulse Card in this item, so the rule is proven here and in the conflict sheet's cards.
 */
function PersonalEventRow({ event, onEdit }: { event: PersonalEvent; onEdit: () => void }) {
  return (
    <div className="flex items-center gap-3 rounded-card border border-border-subtle bg-surface-elevated px-4 py-3">
      <span aria-hidden="true" className="h-8 w-[3px] shrink-0 rounded-full bg-warm-personal" />
      <span className="text-[11px] font-semibold tracking-[0.08em] text-warm-personal uppercase">
        Personal
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate [font:var(--type-scale-meta-md)]">{event.name}</span>
        <span className="block [font:var(--type-scale-body-sm)] text-ink-muted">
          {cardTime(event.start_time_utc, event.start_time_tz)}
        </span>
      </span>
      <button
        type="button"
        onClick={onEdit}
        aria-label={`Edit ${event.name}`}
        className="rounded-control border border-border-subtle px-3 py-1 [font:var(--type-scale-meta-sm)] text-ink-secondary"
      >
        Edit
      </button>
    </div>
  );
}

/** The edit form's seed values, taken from the event being edited. */
function seedFrom(event: PersonalEvent): Partial<PersonalEventFormValues> {
  const zone = event.start_time_tz || "UTC";
  const start = utcInstantToLocal(new Date(event.start_time_utc), zone);
  const end = event.end_time_utc ? utcInstantToLocal(new Date(event.end_time_utc), zone) : null;
  return {
    name: event.name,
    date: start.date,
    time: start.time,
    timezone: zone,
    endDate: end?.date ?? "",
    endTime: end?.time ?? "",
    location: event.location ?? "",
    notes: event.notes ?? "",
  };
}
