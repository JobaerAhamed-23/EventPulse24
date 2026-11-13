"use client";

/**
 * The Detail Screen's action row: Save to Pulse and Share — and the conflict prompt.
 *
 * **Two buttons, not three.** The locked order says "Save to Pulse · Share · Dismiss",
 * and the mockup has a "Less like this" third. But FR-25's dismissal is a **swipe on the
 * Pulse Card**, and there is **no dismissal endpoint** in this codebase — a "Dismiss"
 * button here would be a control that silently does nothing, which is the failure this
 * screen is supposed to avoid. The swipe stays where FR-25 puts it.
 *
 * **Save is terracotta.** It is a `Button.Primary`, and the primary fill is one of the
 * four sanctioned terracotta uses. Share is a `Button.Secondary` — no fill.
 *
 * **Share hands over the *public* page (FR-28).** It used to share
 * `window.location.href`, which on this screen is `/events/{uuid}` — *this* screen's
 * address, and a sign-in wall for anyone who was not already signed in. The shared link
 * is now `/events/{slug}`: the FR-26 public page, with its Open Graph metadata and its
 * "Save to Pulse →" CTA. The share itself lives in `components/share/share-control.tsx`,
 * which the Pulse Card uses too — so the two surfaces cannot drift apart.
 *
 * **A sold-out event keeps its Share control.** It is still published and still public;
 * what it has lost is its tickets, not its page. So the row narrows — Save and the
 * reminder link go, Share stays — rather than disappearing.
 *
 * **The Save button's state is known before the user presses it.** `personal.saved` is
 * the user's own save row, read by the API — not a tag on the composition, which may
 * have been composed days ago.
 *
 * **A 409 opens the prompt, and the save stands.** The server writes the save row and
 * *then* finds the clash, so the event is saved and the pair is waiting for a choice.
 * Saying "Couldn't save that" would be false, and pressing Save again would only return
 * the same 409. So the button reads "Saved to your Pulse" and the prompt opens over it.
 *
 * **The three actions do three different things**, and none of them is a second save:
 *
 *   - **Move {personal}** — opens the personal event in the **edit sheet**, with the
 *     conflicting time highlighted. The sheet edits personal events, so the full record
 *     is read first — the clash carries only the time, not the event's zone.
 *   - **Skip {this event}** — **un-saves** the event, and the button returns to "Save to
 *     Pulse".
 *   - **Keep both** — the event stays saved, the indicator stays, and the prompt closes.
 *
 * **The request names the side**, because the server checks it: `skip_public` acts on the
 * **saved** side and everything else on the **personal** one. That rule lives in
 * `actionSide()` (`lib/conflict-wording.ts`), read from the same source the server
 * enforces — so a client cannot release a save by naming a personal event, or delete
 * one by naming a save.
 *
 * **There are two ways in, and both end at the same prompt.**
 *
 *   - The **save** clashing: the POST answers 409 with the pair, and the prompt opens
 *     over the button. The 409's `new_side` is the **save row**, so its id is the one a
 *     `skip_public` has to name.
 *   - The **indicator**: the payload already carries an active pair for this event, so
 *     the screen shows the mark and the prompt opens from it. The payload's
 *     `saved_side_id` is that save row's id, and it is not derivable from the catalog
 *     event id this screen is keyed by — so the server sends it and the client reads it.
 */
import { useCallback, useEffect, useState } from "react";

import { PersonalEventsPanel, type PersonalEventSeed } from "@/components/personal-events-panel";
import { readCapDetails, type CapDetails } from "@/lib/cap-details";
import { UpgradePrompt } from "@/components/upgrade/upgrade-prompt";
import { ConflictResolution, type Conflict } from "@/components/sheets/conflict-resolution";
import { ShareControl } from "@/components/share/share-control";
import { EventReportControl } from "@/components/detail/event-report-control";
import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { onConflictOpen } from "@/lib/conflict-open";
import { actionSide, type Resolution } from "@/lib/conflict-wording";

export type DetailActionsProps = {
  /** The event's id, as the API's path parameter takes it. */
  eventId: string;
  /**
   * The event's **minted public slug** — the FR-26 public page's URL segment.
   *
   * **Never the id.** The id is this screen's own address (`/events/{uuid}`), and a
   * friend who opened it would meet a sign-in wall instead of the event. The detail
   * read only ever answers for a public event, so the slug is always present here.
   */
  slug: string;
  /**
   * The site's public origin, resolved on the server.
   *
   * **`PUBLIC_SITE_URL` has no `NEXT_PUBLIC_` prefix**, so a client component cannot
   * read it. The page resolves it (`lib/site-url.ts`) and passes it down.
   */
  shareOrigin?: string | null;
  /** Whether the user has already saved it. */
  saved: boolean;
  /**
   * The caller's **active** conflict pair for this event, or `null`.
   *
   * **The server's fact, not the client's.** The payload says there is a pair waiting for
   * a choice; the screen shows the indicator and opens the prompt. A client that decided
   * for itself would be recomputing a persisted fact at render — the failure AD-10
   * exists to prevent.
   */
  conflict: DetailConflict | null;
  /**
   * The event's own title, for the prompt's saved-side card.
   *
   * **The payload names only the *other* side.** The screen knows which event it is
   * showing — it is the screen for it — so the saved side's name is the title the page
   * already has. The client does not look it up, and it does not guess one.
   */
  eventName: string;
  /** The event's start time, for the prompt's saved-side card. */
  startTimeUtc: string;
  /** The event's end time, for the prompt's saved-side card. */
  endTimeUtc?: string | null;
  /**
   * Whether the event is sold out (A-15, FR-53).
   *
   * **A sold-out event is still published and still public.** So it keeps its share
   * control — the public page still exists and a friend can still open it — and it
   * loses the Save button and the reminder link, which are about *this* user's
   * relationship with a ticket that no longer exists.
   */
  soldOut?: boolean;
};

/**
 * The caller's active pair for this event, as the payload hands it over.
 *
 * **Derived from the generated contract**, so it cannot drift from what the server
 * actually sends. The schema is the contract (AD-19), and a hand-written copy of it is
 * one that can say something the API does not.
 */
export type DetailConflict = components["schemas"]["DetailConflictOut"];

export function DetailActions({
  eventId,
  slug,
  shareOrigin = null,
  saved,
  conflict: serverConflict,
  eventName,
  startTimeUtc,
  endTimeUtc = null,
  soldOut = false,
}: DetailActionsProps) {
  const [isSaved, setIsSaved] = useState(saved);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  /**
   * The tier cap, when a save was refused for one (FR-49).
   *
   * Held apart from `failed`: a cap is not a failure. The save did not happen, but
   * nothing went wrong and there is nothing to retry — which is why the refusal is
   * **not** retried and the prompt is shown instead of "Couldn't save that."
   */
  const [cap, setCap] = useState<CapDetails | null>(null);

  // **The prompt's conflict**, once the server has named one. It is either the pair the
  // payload already carried, or the one a 409 named — and in both cases it is the
  // server's, never the client's guess.
  const [conflict, setConflict] = useState<Conflict | null>(null);
  /**
   * **Whether the prompt is open.**
   *
   * The mark in the header opens it, and the Save button's 409 opens it. So the open
   * state is its own flag rather than a consequence of the conflict's presence: a
   * payload that already carries a pair must **not** slam the prompt open over a screen
   * the user came to read — the mark says "there is a choice", and the user takes it
   * when they take it.
   */
  const [promptOpen, setPromptOpen] = useState(false);
  // **A failed write leaves the prompt open.** A prompt that closed on a failed write
  // would tell the user the conflict is handled when it is not.
  const [resolveFailed, setResolveFailed] = useState(false);
  // **The personal event being moved**, once the full record has been read. The edit
  // sheet edits personal events, and it needs the zone.
  const [moving, setMoving] = useState<PersonalEventSeed | null>(null);
  // **Whether the edit sheet highlights the start time** — a move always does.
  const [highlight, setHighlight] = useState(false);

  /**
   * **The header's mark announces the open; this island listens.**
   *
   * The header is server-rendered content and the prompt lives here, so the mark
   * dispatches a DOM event and this effect picks it up. The event carries the event's
   * id, and an island for a different event ignores it.
   *
   * **The listener is removed when the island unmounts**, so a mark that outlives the
   * screen cannot open a prompt for an event that is no longer there.
   */
  useEffect(() => onConflictOpen(eventId, () => setPromptOpen(true)), [eventId]);

  const onSave = useCallback(async () => {
    setBusy(true);
    setFailed(false);
    setCap(null);
    try {
      const response = await api.POST("/api/personal/saved-events/{catalog_event_id}", {
        params: { path: { catalog_event_id: eventId } },
      });
      // **The 409 is one of two refusals, and the `code` says which.**
      //
      // `scheduling_conflict` carries the pair and the three actions; `save_cap_reached`
      // carries the cap and an upgrade sentence (FR-49). They share a status code and
      // nothing else, so the client narrows on `code` — the field the server set — rather
      // than reaching for a field that only one of them has.
      const error = response.error;
      const clash =
        response.response.status === 409 && error?.code === "scheduling_conflict"
          ? error.details?.conflicts?.[0]
          : undefined;
      // The other 409: `save_cap_reached`, carrying `{cap, upgrade_hint}`.
      const capDetails = readCapDetails(error);
      // The save is idempotent, so a 2xx means it is saved now. A refusal is shown
      // calmly rather than swallowed — a button that silently fails is the thing this
      // screen is careful about.
      if (response.response.status >= 200 && response.response.status < 300) {
        setIsSaved(true);
      } else if (clash) {
        // **A 409 is not a failed save.** The server wrote the save row and *then* found
        // the clash, so the event is saved and the pair is waiting for a choice. The
        // prompt opens over it.
        setIsSaved(true);
        setConflict(clash);
        setPromptOpen(true);
      } else if (capDetails !== null) {
        // **A cap is a refusal, not a failure, and it is final until the user upgrades.**
        // The save is not retried — re-sending it would spend nothing and be refused
        // again, and a button that keeps trying is the thing this screen avoids.
        setCap(capDetails);
      } else {
        setFailed(true);
      }
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }, [eventId]);

  /**
   * The user's choice.
   *
   * **The side comes from the pair's kinds**, through `actionSide()` — the same rule the
   * server enforces, and the same rule the conflict review screen uses. The prompt's
   * row is symmetric, so it cannot say which side the user means.
   */
  const onResolve = useCallback(async (resolution: Resolution, pair: Conflict) => {
    setResolveFailed(false);

    const newSide = {
      kind: pair.new_side.kind,
      id: pair.new_side.id,
      name: pair.new_side.name,
      start_time_utc: pair.new_side.start_time_utc,
    };
    const otherSide = {
      kind: pair.other_side.kind,
      id: pair.other_side.id,
      name: pair.other_side.name,
      start_time_utc: pair.other_side.start_time_utc,
    };

    const target = actionSide(resolution, newSide, otherSide);
    // `keep_both` acts on neither side, and the server accepts either of the pair's own
    // sides for it — so the new side is named.
    const side = target ?? { kind: newSide.kind, id: newSide.id };

    const response = await api.POST("/api/personal/events/conflicts/{pair_id}/resolve", {
      params: { path: { pair_id: pair.pair_id } },
      body: { resolution, side },
    });

    if (response.error) {
      // **The prompt stays open.** The pair is still active, and the user still has to
      // choose.
      setResolveFailed(true);
      return;
    }

    if (resolution === "skip_public") {
      // **The save is released.** The button goes back to "Save to Pulse", because the
      // event is no longer saved.
      setIsSaved(false);
      setConflict(null);
      setPromptOpen(false);
      return;
    }

    if (resolution === "edit_new" || resolution === "update_existing") {
      // **The personal event opens in the edit sheet**, with the conflicting time
      // highlighted. The full record is read first: the sheet edits personal events,
      // and the clash carries no zone.
      const personalId = side.kind === "personal_event" ? side.id : pair.other_side.id;
      const response2 = await api.GET("/api/personal/events/{event_id}", {
        params: { path: { event_id: personalId } },
      });
      const personal = response2.data;
      if (personal) {
        setMoving({
          id: personal.id,
          name: personal.name,
          start_time_utc: personal.start_time_utc,
          end_time_utc: personal.end_time_utc,
          start_time_tz: personal.start_time_tz,
          location: personal.location,
          notes: personal.notes,
        });
      }
      setConflict(null);
      setPromptOpen(false);
      setHighlight(true);
      return;
    }

    // **Keep both.** The event stays saved, the indicator stays, and the prompt closes.
    setConflict(null);
    setPromptOpen(false);
  }, []);

  /**
   * The pair the payload carried, as a `ConflictOut` the sheet can read.
   *
   * **The payload names the *other* side** — the screen knows which event it is
   * showing, so the pair's saved side is the event on screen. The sheet's "new" side is
   * that event, and the "other" side is the personal event it clashes with.
   *
   * **The saved side's id is the payload's `saved_side_id`** — the save row's, which is
   * what the pair stores and what a `skip_public` has to name. It is not the catalog
   * event id the screen is keyed by, and it is not derivable from it.
   *
   * **The saved side's name is the event's own title**, because the screen knows the
   * event it is showing. The payload does not repeat it, and the client does not look
   * it up again.
   */
  const payloadConflict: Conflict | null = serverConflict
    ? {
        pair_id: serverConflict.pair_id,
        kind: serverConflict.kind,
        actions: serverConflict.actions,
        new_side: {
          kind: "saved_event",
          id: serverConflict.saved_side_id,
          name: eventName,
          start_time_utc: startTimeUtc,
          end_time_utc: endTimeUtc,
        },
        other_side: {
          kind: serverConflict.other_side.kind,
          id: serverConflict.other_side.id,
          name: serverConflict.other_side.name ?? "",
          start_time_utc: serverConflict.other_side.start_time_utc,
          end_time_utc: serverConflict.other_side.end_time_utc ?? null,
        },
      }
    : null;

  /**
   * **The pair the prompt is about.**
   *
   * The 409's pair wins when there is one — it is the freshest statement about what
   * just happened — and the payload's pair is the fallback. When there is neither, there
   * is nothing to answer and the sheet stays closed.
   */
  const openConflict = conflict ?? payloadConflict;

  /**
   * The prompt's subject for each resolution — **the name of the event the action is
   * about**, not the name of the pair.
   *
   * "Skip" is about the **saved** side — the event on screen — and "Move" is about the
   * **personal** one. So the map is built from the pair's kinds, the same way the side
   * is.
   *
   * **It is built from whichever pair the prompt is about** — the 409's or the
   * payload's. A prompt opened from the header's mark has no 409 behind it, and a
   * prompt with no subjects would fall back to "Move the personal event" — which names
   * no event the user is looking at.
   */
  const subjects = openConflict ? buildSubjects(openConflict) : undefined;

  /**
   * **Whether the sheet is open.**
   *
   * **The flag, not the conflict's presence.** A payload that carries a pair says "there
   * is a choice"; it does not say "show the choice now". The user came to read an
   * event, and a prompt that slams itself open over the page is the thing FR-58's
   * forced sheet is *for* — but only once something has put it there: a 409, or the
   * mark they pressed.
   */
  const sheetOpen = promptOpen && openConflict !== null;

  return (
    <>
      {/*
        The edit sheet. The panel renders only sheets — the Detail Screen has its own heading, and
        the panel whole would push a headline between the page's header and its content.

        **The sheet is driven**, the same way the Timeline and the conflict review drive
        it: the island names the event, and the sheet opens on it. The highlight is
        derived from the island's own state rather than synchronised into the sheet, so a
        render between the two cannot show the wrong form.

        **The island names the event by id**, and the sheet's own close clears the id —
        so the two paths agree on what "closed" means, and the highlight falls away with
        it rather than lingering on the next opening.
      */}
      <PersonalEventsPanel
        editingEvents={moving ? [moving] : []}
        editingEventId={moving?.id ?? null}
        onEditingEventChange={(id) => {
          // **`null` closes the sheet**, and the seed goes with it: a seed left behind
          // would be the event the sheet opens on next time, and the next move may be a
          // different event entirely.
          //
          // **A non-null id is the panel echoing back the event it opened** — the panel
          // finds the event in `editingEvents` by id, and the island's `moving` is the
          // only thing in there. So there is nothing to change: the island already named
          // the event, and the id coming back is the same one.
          if (id === null) {
            setMoving(null);
            setHighlight(false);
          }
        }}
        highlightStartTime={highlight}
      />

      <div className="flex flex-wrap items-center gap-3" data-detail-actions>
        {/*
          **The Save button — and not on a sold-out event.**
          A sold-out event is still public and still shareable, but it is no longer
          savable: there is nothing to save. So the row *narrows* rather than
          disappearing, and Share stays.
        */}
        {soldOut ? null : (
          <button
            type="button"
            onClick={onSave}
            disabled={busy || isSaved}
            className={[
              "rounded-control px-6 py-3 [font:var(--type-scale-meta-md)]",
              isSaved
                ? "bg-surface-subtle text-ink-secondary"
                : "bg-accent-terracotta text-ink-inverse",
              "disabled:cursor-default",
            ].join(" ")}
          >
            {isSaved ? "Saved to your Pulse" : "Save to Pulse"}
          </button>
        )}

        {/*
          **The Share control — FR-28's sender side.**
          It shares the **public** page, `/events/{slug}`, not this screen's own address:
          the old button shared `window.location.href`, which on the Detail Screen *is*
          `/events/{uuid}` — so a friend met a sign-in wall instead of the event.

          **The confirmation is a bare live region, not a second `role="status"`.** The
          row's conflict-failure line below is this surface's status region, and it
          stays the only one.
        */}
        <ShareControl slug={slug} title={eventName} origin={shareOrigin} />

        {/*
          **The report flag — FR-59's "Report this event".**

          **It is the quietest thing on the row**, after the two buttons that matter: Save
          is the filled terracotta primary and Share is the bordered secondary, so the
          flag is muted ink with an underline — FR-59's "Not a primary button", stated as
          the absence of the tokens the other two have.

          **It is here, and not in the page, because the row is already gated.** The whole
          row lives inside `{personal ? … : null}` on the page, so the flag is **hidden
          for a signed-out reader** — inherited from the same `if` that hides Save, so the
          two cannot drift apart. A flag that led to a sign-in wall would be a control
          that does nothing, plus three taps.
        */}
        <EventReportControl eventId={eventId} eventName={eventName} />

        {cap !== null ? <UpgradePrompt hint={cap.upgradeHint} className="w-full" /> : null}

        {failed ? (
          <p className="text-ink-muted [font:var(--type-scale-body-sm)]">
            Couldn&apos;t save that. We&apos;ll try again on your next change.
          </p>
        ) : null}

        {resolveFailed ? (
          <p role="status" className="text-ink-muted [font:var(--type-scale-body-sm)]">
            Couldn&apos;t record that choice. Try again.
          </p>
        ) : null}
      </div>

      {/*
        The prompt. **It is the same sheet the personal-events panel uses** — one
        component, two callers, one vocabulary — with the `named` wording, because the
        Detail Screen knows the event the user is looking at.
      */}
      <ConflictResolution
        open={sheetOpen}
        conflict={openConflict}
        newEvent={
          openConflict
            ? {
                id: openConflict.new_side.id,
                name: openConflict.new_side.name,
                start_time_utc: openConflict.new_side.start_time_utc,
              }
            : null
        }
        wording="named"
        subjects={subjects}
        onResolve={onResolve}
      />
    </>
  );
}

/**
 * The name of the side each action acts on.
 *
 * **"Skip" is about the saved side and "Move" is about the personal one** — the same
 * rule `actionSide()` follows, read here from the pair's kinds so the label and the
 * request cannot disagree about which side they mean.
 */
function buildSubjects(conflict: Conflict): Partial<Record<Resolution, string | null>> {
  const newSide = {
    kind: conflict.new_side.kind,
    id: conflict.new_side.id,
    name: conflict.new_side.name,
    start_time_utc: conflict.new_side.start_time_utc,
  };
  const otherSide = {
    kind: conflict.other_side.kind,
    id: conflict.other_side.id,
    name: conflict.other_side.name,
    start_time_utc: conflict.other_side.start_time_utc,
  };

  const subjects: Partial<Record<Resolution, string | null>> = {};
  for (const action of conflict.actions) {
    const resolution = action as Resolution;
    const target = actionSide(resolution, newSide, otherSide);
    if (!target) continue;
    const side = target.id === newSide.id ? newSide : otherSide;
    subjects[resolution] = side.name;
  }
  return subjects;
}
