"use client";

/**
 * The client island that owns the personal-event flow: create → conflict → resolve →
 * edit → delete.
 *
 * **There are two deletions, and they are not the same one.** The conflict prompt's
 * "Delete the new one" is an *answer to a pending prompt*: it goes to the resolve
 * endpoint, which deletes the new event and closes the pair in one act. The edit
 * sheet's danger zone is the ordinary one (FR-18) — any personal event, at any time,
 * through `DELETE /api/personal/events/{event_id}`. Routing the second through the
 * first would require a conflict that does not exist.
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
import { utcInstantToLocal, formatLocalDate } from "@/lib/timezones";

import { ConflictResolution, type Conflict } from "./sheets/conflict-resolution";
import { PersonalEventForm, type PersonalEventFormValues } from "./sheets/personal-event-form";

type PersonalEvent = components["schemas"]["PersonalEventOut"];
type ConflictDetails = components["schemas"]["SchedulingConflictDetails"];
/** The resolutions the API accepts. */
type Resolution = components["schemas"]["ConflictResolutionIn"]["resolution"];

/**
 * **The narrow shape the edit sheet needs.**
 *
 * The sheet seeds itself from an event's id, name, times, zone, location and notes —
 * and from nothing else. `PersonalEventOut` also carries `version`, the
 * optimistic-locking counter, and `calendar_connection_id`. **A caller that does not
 * have those must not invent them**: a fabricated `version: 1` is a fact about the
 * event that is not true, and the day it stops being true is the day a reader believes
 * a lie. So the prop takes the shape the sheet reads, and a caller that *does* hold a
 * full `PersonalEventOut` passes one — it satisfies this type by having more.
 */
export type PersonalEventSeed = {
  id: string;
  name: string;
  start_time_utc: string;
  start_time_tz: string;
  end_time_utc?: string | null;
  location?: string | null;
  notes?: string | null;
};

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
  /**
   * The personal events the **Timeline** offers to edit, and the events it opens the
   * edit sheet for.
   *
   * **The Timeline is read-only at MVP** (ASSUM-7) — no drag-to-reschedule, no inline
   * rename — but a personal block opens the existing **Edit personal event** sheet.
   * The sheet lives inside this island, so the panel needs to know *which* event the
   * Timeline clicked, and it learns it here: the list is the set of events the sheet
   * may open, and the sheet opens on the one the caller names.
   *
   * **The panel finds the event by id**, so a caller that passes an event the panel does
   * not know opens nothing rather than opening the wrong one.
   *
   * **The shape is the narrow one the sheet reads** (`PersonalEventSeed`), because the
   * Timeline's block payload carries no `version` and a fabricated one would be a lie
   * about the event. A caller holding a full `PersonalEventOut` passes one unchanged.
   */
  editingEvents?: PersonalEventSeed[];
  /**
   * The id of the event the sheet is open on, when the caller drives it.
   *
   * **The Timeline drives it.** A personal block on the Timeline is a button that opens
   * the edit sheet, and the sheet's state lives in this island — so the Timeline tells
   * the panel *which* event to open, and the panel opens it. Left `undefined`, the panel
   * owns the choice and its own "Edit" buttons drive it.
   */
  editingEventId?: string | null;
  /**
   * Called when the caller drives which event the sheet is open on.
   *
   * **`null` closes the sheet.** The panel opens the sheet when the id names an event
   * it knows, and closes it when the id goes back to `null` — so the caller can close
   * the sheet by clearing the id, and the sheet's own "Cancel" does the same thing
   * through this callback.
   */
  onEditingEventChange?: (id: string | null) => void;
  /**
   * Whether the sheet highlights the start time, when the caller drives it.
   *
   * **A "move" action opens the sheet with the conflicting time pre-highlighted**, so
   * the user lands on the field they have to change rather than on a form that looks
   * like any other edit. The conflict prompt's "Edit the new one" says so; the review
   * screen's "Move" says so; and this is the prop that makes both true.
   *
   * **Left `undefined`, the panel owns it** — the panel's own conflict flow sets it
   * when the user chooses a move. Given, it is derived during render, like the editing
   * id: two sources of truth would show the wrong form in the render between them.
   */
  highlightStartTime?: boolean;
  /**
   * Called when an event was **created**, with the local day it landed on.
   *
   * **The panel owns the write, so the panel is what knows it succeeded.** The caller
   * cannot see the panel's state, and a caller that guessed would be guessing. So the
   * panel reports the fact: the event's name and the local date it starts on.
   *
   * **The local day, not the instant.** The week a personal event belongs to is the
   * week of the day it starts *in the user's own zone* — the same rule the server uses
   * to cut a week. An instant in UTC would put an 11pm Tokyo event on the previous
   * day, and the link would take the user to the wrong week.
   */
  onCreated?: (event: { name: string; localDate: string }) => void;
  /**
   * Called when a write **failed**, with the calm message the panel would have shown.
   *
   * **A failure is as visible as a success.** A caller that takes over the success
   * message has to take over the failure message too — otherwise a refused save
   * would say nothing at all, and a sheet that closes with no word is the same as
   * nothing happening.
   */
  onFailed?: (message: string) => void;
  /**
   * Whether the **caller** is the one showing the panel's message.
   *
   * **A message is announced once.** The panel's `sheetsOnly` mode has no visible
   * message of its own — it announces through a hidden live region instead. But a
   * caller that renders the confirmation itself (the digest header's quick-add does:
   * a visible line with a link to the week) would then have **two** announcements of
   * the same fact, and a screen reader would say it twice.
   *
   * So the caller says it owns the message, and the panel's hidden region goes quiet.
   * The panel still *sets* the message — the caller reads it through its own
   * `onCreated` and `onFailed` — it just does not also announce it.
   */
  messageShownByCaller?: boolean;
};

export function PersonalEventsPanel({
  events = [],
  createOpen,
  onCreateOpenChange,
  sheetsOnly = false,
  addButton = true,
  editingEvents = [],
  editingEventId,
  onEditingEventChange,
  highlightStartTime: drivenHighlight,
  onCreated,
  onFailed,
  messageShownByCaller = false,
}: PersonalEventsPanelProps) {
  // **Every successful write refreshes the server's read.** The list is a server
  // component's read (`PersonalEventsSection`), so a write in this island is invisible
  // until the route re-renders; `router.refresh()` re-runs the server components and keeps
  // this island's state. Without it, a saved event looked like nothing happened.
  // The panel's own create state, used when the caller does not drive it.
  const router = useRouter();
  const [ownFormOpen, setOwnFormOpen] = useState(false);
  const [ownEditing, setOwnEditing] = useState<PersonalEventSeed | null>(null);
  const [ownHighlightStartTime, setOwnHighlightStartTime] = useState(false);
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

  /**
   * **The caller drives the sheet when it says which event to open.**
   *
   * The Timeline's personal block is a button, and the sheet lives in this island — so
   * the Timeline names the event and the sheet opens on it.
   *
   * **The state is derived, not synchronised.** When `editingEventId` is given, the
   * event being edited is *computed* from it during render — there is no effect that
   * copies the id into a `useState`, because that would be two sources of truth and a
   * render between them would show the wrong event. A caller that clears the id is
   * closing the sheet, and the sheet's own "Cancel" clears the id through the same
   * callback, so the two paths agree.
   *
   * **An id the panel does not know opens nothing.** The panel finds the event in
   * `editingEvents` by id, so a caller naming an event it did not pass opens no sheet
   * rather than opening the wrong one.
   */
  const driven = editingEventId !== undefined;
  const drivenEvent = driven
    ? (editingEvents.find((candidate) => candidate.id === editingEventId) ?? null)
    : null;

  const editing = driven ? drivenEvent : ownEditing;
  const formOpen = driven ? drivenEvent !== null : (createOpen ?? ownFormOpen);

  // **The highlight is derived too, when the caller drives it.** A caller that says
  // "open this event with its time highlighted" must not also have to say "and turn the
  // highlight off when it closes" — the sheet's own close already clears the caller's id,
  // and a derived highlight falls away with it. The panel's own conflict flow keeps
  // owning the flag when nobody drives it.
  const highlight = drivenHighlight ?? ownHighlightStartTime;

  const setFormOpen = (open: boolean): void => {
    if (!driven && createOpen === undefined) setOwnFormOpen(open);
    if (!driven) onCreateOpenChange?.(open);
  };

  const closeForm = (): void => {
    setFormOpen(false);
    setOwnEditing(null);
    setOwnHighlightStartTime(false);
    // **The caller drives the sheet's open event too**, so clearing its id is what
    // actually closes it. Without this the caller would still believe the sheet was
    // open, and the next id it set would not reopen the form.
    onEditingEventChange?.(null);
  };

  const openCreate = (): void => {
    setOwnEditing(null);
    setOwnHighlightStartTime(false);
    setFormKey((key) => key + 1);
    setFormOpen(true);
  };

  const openEdit = (event: PersonalEventSeed, highlightTime = false): void => {
    setOwnEditing(event);
    setOwnHighlightStartTime(highlightTime);
    setFormKey((key) => key + 1);
    setFormOpen(true);
    onEditingEventChange?.(event.id);
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
        setOwnEditing(null);
        setOwnHighlightStartTime(false);
        router.refresh();
        return;
      }
    }

    if (response.error) {
      setMessage("We couldn't save that. Try again.");
      // **A refused save is reported too.** A caller that shows the success message
      // has to show this one — otherwise the sheet closes with no word at all, which
      // reads as nothing happening.
      onFailed?.("We couldn't save that. Try again.");
      return;
    }
    setMessage(editing ? `"${body.name}" was updated.` : `"${body.name}" was added.`);
    // **A create is reported, an edit is not.** The caller's line says the event was
    // added and points at the week it landed on — a week an edit does not change.
    if (!editing) {
      onCreated?.({
        name: body.name,
        localDate: localDateIn(body.start_time_utc, body.start_time_tz),
      });
    }
    closeForm();
    router.refresh();
  };

  /**
   * The edit sheet's danger zone, after the user has confirmed it.
   *
   * **It is only ever the event the sheet is open on.** The id comes from `editing`,
   * which is the event the form was seeded from — there is no other way to name a
   * target, so a delete cannot be aimed at an event the user is not looking at.
   */
  const remove = async (): Promise<void> => {
    if (!editing) return;
    const name = editing.name;
    const response = await api.DELETE("/api/personal/events/{event_id}", {
      params: { path: { event_id: editing.id } },
    });

    if (response.error) {
      // **The sheet stays open on a refusal.** Closing it would leave the user with an
      // event still on the timeline and a line saying something went wrong, with no way
      // back to the control they just used.
      setMessage("We couldn't delete that. Try again.");
      onFailed?.("We couldn't delete that. Try again.");
      return;
    }

    setMessage(`"${name}" was deleted.`);
    closeForm();
    router.refresh();
  };

  /** The user's choice on the conflict prompt. */
  const resolve = async (resolution: Resolution, pair: Conflict): Promise<void> => {
    if (!conflict || !pending) return;
    const response = await api.POST("/api/personal/events/conflicts/{pair_id}/resolve", {
      // **The pair the user answered is the pair the request is about.** The sheet
      // passes the pair it rendered, so the choice cannot be applied to a different
      // pair than the one on screen.
      params: { path: { pair_id: pair.pair_id } },
      // **The request names the side the action is about**, with its kind. The pair row is
      // symmetric, so the server cannot infer which side the user is acting on — and the
      // action decides what it may act on: `delete_new` deletes a personal event,
      // `skip_public` releases a save.
      body: { resolution, side: { kind: "personal_event", id: pending.id } },
    });
    if (response.error) {
      setMessage("We couldn't record that choice. Try again.");
      return;
    }

    const other = pair.other_side;
    const resolved = pair;
    setConflict(null);
    setPending(null);
    router.refresh();

    if (resolution === "edit_new") {
      // The new event, opened in edit mode with the conflicting time pre-highlighted.
      // **The zone is empty** — the 409 payload does not carry it, and the sheet falls
      // back to UTC rather than showing a zone it was never told.
      openEdit(
        {
          id: pending.id,
          name: pending.name,
          start_time_utc: pending.start_time_utc,
          start_time_tz: "",
        },
        true,
      );
      return;
    }
    if (resolution === "update_existing") {
      // The **existing** event — for a duplicate, the second action opens this one.
      // **The zone is empty** for the same reason as above: the conflict payload
      // carries a side's times but not its zone, and the sheet falls back to UTC.
      openEdit(
        {
          id: other.id,
          name: other.name,
          start_time_utc: other.start_time_utc,
          start_time_tz: "",
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
        // **A fresh key per opening, so the form is remounted with the new seed**
        // rather than carrying the last one's values. When the caller drives the
        // sheet, the key follows the event it named — so naming a second event
        // remounts the form with that event's values, and the panel's own `formKey`
        // is left alone for the case it owns.
        key={driven ? `driven-${editing?.id ?? "none"}` : formKey}
        open={formOpen}
        mode={editing ? "edit" : "create"}
        initial={editing ? seedFrom(editing) : undefined}
        highlightStartTime={highlight}
        onClose={closeForm}
        onSubmit={submit}
        // **Only an edit can delete**, and the form renders no danger zone without this.
        onDelete={editing ? remove : undefined}
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
            only one there is.

            **And it is only here when the caller is not showing the message.** A
            caller that renders the confirmation itself would otherwise hear the same
            fact twice — once from the visible line, once from here. */}
        {messageShownByCaller ? null : (
          <p aria-live="polite" className="sr-only">
            {message}
          </p>
        )}
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
function seedFrom(event: PersonalEventSeed): Partial<PersonalEventFormValues> {
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

/**
 * The calendar day an instant falls on, in the zone it was written in.
 *
 * **The zone is the event's own, not the browser's.** An event the user entered as
 * "Nov 7, 11pm, Asia/Tokyo" starts on Nov 7 *in Tokyo* — which is Nov 6 in UTC. The
 * week the event belongs to is the week of the day the user will see it on their own
 * calendar, so the date has to be read in the zone the event was written in.
 *
 * **An unparseable instant falls back to UTC**, which is the same fallback the form
 * makes for a missing zone. A wrong zone would put the event in the wrong week; a
 * fallback at least puts it in a real one.
 */
function localDateIn(startTimeUtc: string, zone: string): string {
  const instant = new Date(startTimeUtc);
  if (Number.isNaN(instant.getTime())) return startTimeUtc.slice(0, 10);
  return formatLocalDate(instant, zone || "UTC");
}
