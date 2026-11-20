"use client";

/**
 * `Component.Settings.DangerZone` — **the section for what cannot be undone.**
 *
 * ## It is a section and not a screen, and that is the point
 *
 * A destructive, irreversible control sitting beside an avatar upload invites the
 * accidental click — next to the button people use every day. **So the danger zone lives
 * at `/settings/privacy` and nowhere else.** A-16 chose the route, and the separation is
 * the design: irreversible things are put away from the reversible ones.
 *
 * ## It is a container, and this file is the container
 *
 * The modal that opens from the delete row and the "Keep my account" action that
 * replaces it are two mutually-referencing pieces of this section, and folding the
 * section into either of them makes each wait on the other. **This file is the thing
 * they both hang on.**
 *
 * **So it is a client component, and that is what "container" costs.** The section has
 * to decide between two states, and the decision changes *after* a cancellation — the
 * moment the pending state is gone and the request row is back. A server component
 * renders once per request and cannot know that a button was pressed. **The state that
 * decides which row shows therefore has to live here**, and the pending row's own
 * details live in the island it delegates to.
 *
 * ## The row's subtitle does not say "Permanent. Cannot be undone."
 *
 * **That is A-16's mockup's wording, and it is false.** The mockup predates the
 * deletion engine, and the engine holds a thirty-day grace period: the account is not
 * destroyed at request time, and a person can call the whole thing off inside that
 * window. A subtitle that claims otherwise is a promise the product does not keep —
 * **the same failure this section exists to prevent**, so the copy says what is true.
 *
 * ## The terracotta is on the destructive control, and only there
 *
 * The project's rule is that terracotta is reserved for destructive actions. The
 * personal-event delete row already uses exactly this treatment
 * (`components/sheets/personal-event-form.tsx`), so this row reuses it rather than
 * inventing a second spelling of the same control. **The section's heading is not
 * terracotta** — a heading in the destructive colour would spend the accent on
 * decoration and leave the actual destructive control unmarked.
 *
 * **The pending state is not terracotta either.** It is the way back *from* a
 * destructive action, so spending the destructive colour on it would spend the accent
 * on the opposite of what it means.
 *
 * ## It renders unconditionally
 *
 * **A danger zone that vanishes is the opposite of what a danger zone is for.** This
 * section is not conditional on a read succeeding: when the pending-deletion read lands
 * and fails, the section shows the state it can *prove* — which is the request row,
 * because *"no pending deletion I can see"* and *"no pending deletion"* are different
 * things, and only the first is provable.
 *
 * ## It renders one state at a time
 *
 * A section showing both a "Delete account →" row *and* a "Keep my account" button is
 * a section offering two contradictory instructions. **This component is where that
 * rule is enforced** — one ternary, one state, and the other state is not rendered at
 * all rather than rendered and hidden.
 *
 * ## It owns the modal, and the modal owns the rest of itself
 *
 * **The section decides whether the confirmation modal is open**, because the section
 * is the thing that knows whether a deletion is pending — and a modal in front of a
 * pending deletion would be offering a second request for something already asked
 * for. **The modal owns everything inside the dialog**: the typed word, the gate, the
 * focus trap and the request.
 *
 * **The two paragraphs are the server's.** They are fetched from
 * `GET /api/auth/profile/deletion`, which publishes the same two strings the
 * confirmation mail renders. **This file keeps no second spelling of them** — a
 * frontend that paraphrased the destruction would be telling the person one thing on
 * the screen and another thing in their inbox.
 */
import { useCallback, useEffect, useState } from "react";

import { AccountDeleteModal } from "@/components/settings/account-delete-modal";
import { DangerZonePending } from "@/components/settings/danger-zone-pending";
import { SettingRow } from "@/components/settings/setting-row";
import { api } from "@/lib/backend-client";

export type DangerZoneProps = {
  /**
   * When the account will be destroyed, ISO-8601, or `""` when no deletion is pending.
   *
   * **The server's moment.** It was computed once, when the request was made, and
   * asking again does not move it — so the surface shows the date the product promised.
   */
  deletionScheduledFor?: string;
  /**
   * When the deletion was requested, ISO-8601, or `""` when no deletion is pending.
   *
   * **What lets the pending state say "you asked on the 3rd."**
   */
  deletionRequestedAt?: string;
};

export function DangerZone({
  deletionScheduledFor = "",
  deletionRequestedAt = "",
}: DangerZoneProps) {
  /**
   * Whether a deletion is pending.
   *
   * **It starts from the server's answer** and moves when the person cancels — and the
   * cancellation is the only thing that can move it, because the pending state is the
   * only thing that can cancel one.
   */
  const [pending, setPending] = useState(deletionScheduledFor !== "");

  /**
   * When the account will be destroyed, once the server has said so.
   *
   * **It starts from the prop and moves to the server's answer.** The prop is what the
   * page's server read found; the answer is what the request just computed. Both are
   * the server's moment — **never a duration typed into this file.**
   */
  const [scheduledFor, setScheduledFor] = useState(deletionScheduledFor);
  /**
   * Whether the cancellation has landed.
   *
   * **The reassurance outlives the row it replaced.** A person who pressed "Keep my
   * account" is afraid they have just destroyed something, and the row that told them
   * their account was scheduled for deletion is the row that goes away. **So the
   * confirmation is the section's, not the pending row's** — it stays on screen next to
   * the request row that came back, and it says what survived.
   */
  const [kept, setKept] = useState(false);

  /**
   * Whether the confirmation modal is open.
   *
   * **The container owns it, because the container is the thing that knows whether a
   * deletion is pending.** The modal owns its own input, its gate and its focus trap;
   * this owns the one question the modal cannot answer for itself — *should this dialog
   * be on screen at all?*
   */
  const [modalOpen, setModalOpen] = useState(false);

  /**
   * The two sentences the modal shows, and where they come from.
   *
   * **They are the server's, and the server is the only place they are written.** The
   * confirmation mail renders the same two strings; a modal that paraphrased them
   * would be a second version of the same story about the same destruction. So the
   * copy is fetched from the API, and the frontend keeps no second spelling of it.
   *
   * **The empty string is not a sentence, so the modal waits for the copy.** A dialog
   * that opened with a blank paragraph would be worse than no dialog: the whole point
   * of the modal is that it says what is about to happen.
   */
  const [copy, setCopy] = useState<{ whatIsDeleted: string; whatSurvives: string } | null>(null);

  /**
   * The copy, fetched once, when the section mounts.
   *
   * **It is fetched rather than bundled because it is the server's.** A hard-coded
   * paragraph here would be a third spelling of the same sentence — the one the mail
   * renders and the one the endpoint publishes — and the third is the one that drifts.
   *
   * **The read happens whether or not the modal is opened**, because the copy is the
   * modal's to show and a dialog that had to load before it could say anything would
   * put a spinner in front of the one screen a person reads before destroying an
   * account.
   */
  useEffect(() => {
    let live = true;
    const load = async (): Promise<void> => {
      try {
        const response = await api.GET("/api/auth/profile/deletion");
        if (!live || response.error) return;
        setCopy({
          whatIsDeleted: response.data.what_is_deleted,
          whatSurvives: response.data.what_survives,
        });
      } catch {
        // **The copy could not be fetched, and the modal stays closed.** A dialog
        // with two blank paragraphs in it would say nothing about what is about to
        // happen — which is the one thing this dialog exists to say.
      }
    };
    void load();
    return () => {
      live = false;
    };
  }, []);

  /**
   * The request landed.
   *
   * **The server's date, and the section moves to the pending state itself.** A
   * `router.refresh()` would be a second round trip for a value the client is already
   * holding, and it would re-render the whole page to change one row.
   */
  const onRequested = useCallback((scheduledFor: string) => {
    setModalOpen(false);
    setPending(true);
    // **The date is kept, because the pending row shows it.** The server's moment,
    // never a duration computed here.
    setScheduledFor(scheduledFor);
  }, []);

  /** The request row. It is what the section shows when nothing is pending. */
  const requestRow = (
    <SettingRow
      label="Delete account"
      description="Your account is destroyed after a 30-day grace period. You can change your mind until then."
      testAttribute="data-danger-delete-row"
      control={
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          data-open-delete-modal
          className="[font:var(--type-scale-meta-md)] text-accent-terracotta underline-offset-[3px] hover:underline"
        >
          Delete account →
        </button>
      }
    />
  );

  return (
    <section aria-labelledby="danger-zone-heading" data-danger-zone>
      <h2
        id="danger-zone-heading"
        className="text-ink-primary [font:var(--type-scale-headline-sm)]"
      >
        Danger zone
      </h2>

      {/*
        **One row, one control.** The "Export your data" row is deliberately *not* here
        — it lives on `/settings/account`, where `DownloadMyData` already is, and moving
        it would move a working control for no reason.
      */}
      <div className="mt-6">
        {pending ? (
          /*
            **The pending state, and it replaces the row entirely.**

            Not beside it — *instead of* it. A section offering both a "Delete account →"
            row and a "Keep my account" button is offering two contradictory
            instructions, and the person reading it would not know which one they meant.
          */
          <SettingRow
            label="Deletion scheduled"
            description="Your account is scheduled for deletion. You can cancel it before the date below."
            testAttribute="data-danger-pending-row"
            control={
              <DangerZonePending
                scheduledFor={scheduledFor}
                requestedAt={deletionRequestedAt}
                onCancelled={() => {
                  setPending(false);
                  setKept(true);
                }}
              />
            }
          />
        ) : (
          requestRow
        )}
      </div>

      {/*
        **The reassurance, and it is always present so its arrival is announceable.**
        An empty live region is what lets a screen reader notice the text appearing at
        all — the same reasoning `SaveFeedback` records.
      */}
      <div role="status" aria-live="polite" className="mt-3">
        {kept ? (
          <p className="text-ink-secondary [font:var(--type-scale-body-sm)]" data-kept>
            Your account is safe. Nothing was deleted, and your plan and history are all still here.
          </p>
        ) : null}
      </div>

      {/*
        **The confirmation modal.**

        **It opens only when the copy is here.** The two paragraphs are the server's, and
        a dialog that opened before it had them would show two blank lines where the
        explanation of the destruction belongs.

        **It is a sibling of the section's content, not a child of the row.** The row
        unmounts when the request lands, and a dialog that lived inside the row would
        unmount with it — taking the pending state it had just asked for.
      */}
      {copy ? (
        <AccountDeleteModal
          open={modalOpen}
          whatIsDeleted={copy.whatIsDeleted}
          whatSurvives={copy.whatSurvives}
          onRequested={onRequested}
          onClose={() => setModalOpen(false)}
        />
      ) : null}
    </section>
  );
}
