"use client";

/**
 * The **state-change banner** — FR-54's in-app half, on the Detail Screen of an affected
 * event.
 *
 * **Persistent, and quiet.** The strip on the digest home is dismissible; this is not.
 * The user came to this page *on purpose*, and the page's whole job here is to tell them
 * what happened to the event they were planning around. A banner they could dismiss
 * would be a banner they might dismiss before reading, and then the change would be
 * gone from the only surface that explains it.
 *
 * ---
 *
 * ## What it says, and who says it
 *
 * **Two sentences, and both come from the shared table.** `lib/notice-copy.ts` restates
 * the backend's `domain/notices.py` — `NOTICE_SUBJECTS` for what changed, and
 * `REMINDER_CONSEQUENCE` for what it means for the user's reminders. The second sentence
 * is the point: *"Your reminders have been rescheduled to the new time."* is what tells
 * the reader whether the 1-day-before reminder still fires and at what time.
 *
 * **The reminder line is verbatim, and that is deliberate.** It is a promise about sends
 * the server has already decided, derived from `LIFECYCLE_SEND_BEHAVIOUR`. A frontend
 * that reworded it would be making a weaker claim, and a user reading it would be less
 * sure than they should be.
 *
 * ---
 *
 * ## A dismissed notice still shows
 *
 * **The banner reports the newest notice for this event, whether or not it has been
 * dismissed** — that is the backend's deliberate rule (`delivery.services.notice_state`):
 * the banner is about *this* event, which the user navigated to on purpose, so
 * dismissing the strip on the digest home must not hide "this event was cancelled" from
 * the event's own page.
 *
 * **So the banner says so.** A dismissed notice renders with the line *"You've already
 * dismissed this."* — because the notice is still the truth about this event, and the
 * reader may still want to read it. Pretending the correction never happened would be
 * the other lie, and the worse one.
 *
 * ---
 *
 * ## A muted event gets no banner — unless the change was terminal
 *
 * **FR-55's mute silences the correction, and the banner *is* the correction.** So a muted
 * event renders no banner, for a moved time or a moved venue or a sold-out. That is the
 * whole point of the mute, and a banner that kept showing a muted event's time change
 * would make the mute a lie.
 *
 * **But a *terminal* change still shows, and the backend is the reason.** The backend
 * raises a `cancelled` or `superseded` notice *despite* the mute —
 * `backend/apps/delivery/services/state_notices.py` skips the mute check for exactly
 * those two kinds, and `services/mutes.py` says why: *"FR-55 has already removed the
 * event from their digest, so silence about it is the one failure with no second channel
 * to catch it."*
 *
 * **So the rule is not "muted means silent".** It is: **the mute silences the
 * corrections the backend would have suppressed anyway, and leaves the one correction the
 * backend deliberately raised.** A frontend that hid a muted event's cancellation would be
 * undoing the server's decision — and the reader would never learn the event was off.
 *
 * **And the mute control stays**, because the mute is per-event and reversible. A control
 * that could be set but never unset would be a trap.
 *
 * ---
 *
 * ## A kind the table has no word for renders no banner at all
 *
 * **The backend does the same, and for the same reason.** `domain/notices.py`'s
 * `subject_template` raises `KeyError` for a kind it has no subject for, and the renderer
 * turns that into a cancelled send: *"a kind `domain.lifecycle` gained without this module
 * learning it must not produce a generic subject — FR-54 fixes the copy, and a wrong
 * subject is worse than no email."*
 *
 * **So the banner says nothing rather than something generic.** "This event has changed."
 * would be a claim about the world made by a client that was told *what* changed and
 * could not understand it. ASSUMPTION-9 says a kind this system has never heard of shows
 * nothing.
 */
import { useCallback, useState } from "react";

import { DetailMuteControl } from "@/components/state/detail-mute-control";
import { muteSilencesNotice, noticeLinesFor } from "@/lib/notice-copy";

/**
 * One notice, as the banner reads it.
 *
 * **The same fields `DetailNoticeOut` carries**, restated so this component does not
 * import the generated schema into a client island's props.
 */
export type BannerNotice = {
  id: string;
  change_kind: string;
  /** When the user dismissed it, if they did. */
  dismissed_at?: string | null;
};

export type DetailNoticeBannerProps = {
  /**
   * The newest notice for this event, or `null`.
   *
   * **`null` means there is nothing to say** — no notice has been raised for this event.
   * The server's answer, not the client's (AD-10).
   */
  notice: BannerNotice | null;
  /**
   * Whether the user has muted this event's notices (FR-55).
   *
   * **The server's fact.** The mute is a persisted row the API read, and the client does
   * not decide it.
   */
  muted: boolean;
  /** The event's id — the mute's own path parameter. */
  eventId: string;
};

/**
 * The banner, the mute control, or nothing.
 *
 * **A muted event renders no banner** — the *banner* is what the mute silences — **but
 * the mute control always stays**, because the user needs a way back.
 *
 * **And the mute control is offered on an event with no notice at all.** A user who
 * does not want to hear about changes to an event should be able to say so *before* one
 * arrives; a control that only appears once there is something to mute would be a
 * control that arrives too late to be useful.
 */
export function DetailNoticeBanner({ notice, muted, eventId }: DetailNoticeBannerProps) {
  /**
   * **Whether the user has muted this event — the server's confirmed answer.**
   *
   * **The server's answer is the starting state**, and this state changes **only when
   * the server has confirmed the mute**. `DetailMuteControl` calls `onMuteChange`
   * after the write succeeds, not before, so the banner's disappearance is always a
   * fact the server has stated (AD-10) — never a claim the client made and then had to
   * take back.
   */
  const [isMuted, setIsMuted] = useState(muted);

  const onMuteChange = useCallback((next: boolean) => {
    setIsMuted(next);
  }, []);

  const lines = notice === null ? null : noticeLinesFor(notice.change_kind);

  /**
   * **Whether the mute silences *this* notice.**
   *
   * **The mute's reach is the backend's, and the backend's is narrower than "everything".**
   * A `cancelled` or `superseded` notice was raised *despite* the mute — deliberately, and
   * because there is no second channel that would tell the reader the event is off. So the
   * banner is silenced by a mute only for a correction the backend would have suppressed
   * anyway.
   */
  const silenced = isMuted && notice !== null && muteSilencesNotice(notice.change_kind);

  /**
   * **The banner, if there is one to show.**
   *
   * **The two conditions are the two reasons there is no banner**, and they are checked
   * together so the narrowing below is one guard: no notice at all, or a notice this
   * table has no words for, or a notice the mute silences.
   */
  const showBanner = notice !== null && lines !== null && !silenced;

  return (
    <>
      {showBanner ? (
        <section
          aria-label="This event has changed"
          // **The same register as the strip**, and the same anatomy: a dashed
          // `{color.border.strong}` stroke, a quiet fill, plain ink. `component.emptystate.quiet`
          // is "bordered by a 1px dashed `{color.border.strong}` to feel intentional, not
          // failed", and that is exactly what this region is saying — something needs
          // saying, and it is not a failure of the product.
          className="mt-6 rounded-card border border-dashed border-border-strong bg-surface-elevated p-6"
          data-detail-notice
        >
          {/*
            **The change.** The shared table's sentence for this kind — and it says
            "This event" because the banner is on the event's own page, where the title
            is the `<h1>` directly above it.
          */}
          <p className="text-ink-primary [font:var(--type-scale-body-lg)]">{lines.change}</p>

          {/*
            **What it means for the user's reminders.** The second sentence is the one
            the reader actually needs: it tells them whether their reminders still fire,
            and when.

            **It is a second line, not a second paragraph.** The banner is one fact and
            its consequence, and they belong together.
          */}
          <p className="mt-1 text-ink-secondary [font:var(--type-scale-body-md)]">
            {lines.reminder}
          </p>

          {/*
            **A dismissed notice says so.** The reader may have closed this on the
            digest home; telling them keeps the banner honest about what they have
            already seen, and the notice is still the truth about the event.
          */}
          {notice.dismissed_at ? (
            <p className="mt-2 text-ink-muted [font:var(--type-scale-meta-md)]">
              You&apos;ve already dismissed this.
            </p>
          ) : null}
        </section>
      ) : null}

      {/*
        The mute control. **It is outside the banner**, because it must survive the
        banner's absence — a muted event renders no banner, and the control is how the
        user unmutes it.

        **It is below the banner in the reading order**, so a reader who has just been
        told their event moved sees the control that silences such messages *after* the
        message, not before it.
      */}
      <div className="mt-4">
        <DetailMuteControl eventId={eventId} muted={isMuted} onMuteChange={onMuteChange} />
      </div>
    </>
  );
}
