/**
 * FR-54's notice vocabulary, restated for the screen.
 *
 * **The vocabulary is the backend's.** `domain/notices.py` owns it — `NOTICE_SUBJECTS`
 * says what a change of each kind is called, and `REMINDER_CONSEQUENCE` says what it
 * means for the user's reminders. The frontend cannot import Python, so the words are
 * restated here — and `tests/notice-copy.test.ts` is what stops the restatement from
 * going stale. It reads the backend's tables out of the source and fails on drift.
 *
 * **This is the same arrangement as `lib/event-state.ts`**, and it is the same reason: a
 * fact said in two places is a fact that will be said in two different ways, and one of
 * them will be wrong. The Pulse Card's badge reads the shared table; the public page
 * reads the shared table; the Detail screen reads the shared table. This file is the
 * shared table for the *other* vocabulary — the one FR-54's notice carries.
 *
 * ---
 *
 * ## Two sentences, and the second one is the point
 *
 * FR-54's body requirement is *"what changed and what it means for the user's
 * reminders."* So a notice carries two lines:
 *
 * - **What changed** — `NOTICE_CHANGE_LINES`. The backend's subject, with the
 *   `EventPulse24: ` prefix and the `{title}` placeholder taken out. The prefix is the
 *   *mail*'s subject prefix: a screen that already has a heading does not need a
 *   product-name prefix on the line under it, and the email subject is a mail header,
 *   not a sentence.
 * - **What it means** — `NOTICE_REMINDER_LINES`. The backend's own
 *   `REMINDER_CONSEQUENCE`, verbatim, and it is verbatim because it is a *promise*: the
 *   backend derives it from `LIFECYCLE_SEND_BEHAVIOUR`, the table the send machinery
 *   follows, so it cannot promise something the sends did not do. A frontend that
 *   reworded it would be making a promise the server never made.
 *
 * **A user whose event moved needs the second sentence above all.** "Your reminders have
 * been rescheduled to the new time" is what tells them whether the 1-day-before reminder
 * still fires and at what time. Without it the notice says something happened and leaves
 * the reader to work out what it means for them.
 *
 * ---
 *
 * ## The `{title}` placeholder is gone, and that is deliberate
 *
 * The backend's subject names the event: *"{title} was cancelled."* The strip and the
 * banner **do not**, for two reasons that pull the same way.
 *
 * 1. **The notice carries no title.** `NoticeOut` is the notice's own facts and no more;
 *    the change's before/after values are source payload and stay off the wire (AD-13).
 *    A title is exactly the kind of thing that would leak.
 * 2. **Both surfaces already have the title, or can get it.** The Detail screen *is* the
 *    event's page — the title is the `<h1>` two elements above the banner. The strip's
 *    entry links to the event, and the card it sits above is the event's own card.
 *
 * **So the line says what changed, and the surface says which event.** "This event was
 * cancelled." reads correctly on the Detail screen and correctly in the strip, because in
 * both places the reader can see the event. A line reading "Brooklyn Symphony was
 * cancelled" in the strip would name an event the strip's payload does not carry.
 */

/**
 * The change kinds this table speaks for.
 *
 * **Seven, and they are `domain.lifecycle.ChangeKind`'s seven.** The backend's
 * `ChangeKind` is a `StrEnum` with exactly these members, and the notice's
 * `change_kind` is one of them carried through unchanged.
 *
 * **A kind this table has no line for is a kind the frontend says nothing about**
 * (ASSUMPTION-9): a status this system has never heard of is a fact it cannot put into
 * words, and rendering one as "unknown" would be inventing a claim about the world. So
 * `noticeChangeLineFor` returns `null` rather than a fallback sentence.
 */
export type NoticeChangeKind =
  | "cancelled"
  | "superseded"
  | "reinstated"
  | "postponed"
  | "time_moved"
  | "sold_out"
  | "detail_changed";

/**
 * What changed, per kind.
 *
 * **The backend's `NOTICE_SUBJECTS`, with the placeholders resolved by the caller and the
 * email's subject prefix taken off.**
 *
 * **`{title}` becomes "This event"** — the surface knows which event it is showing, and
 * the payload carries no title to put in the sentence (AD-13). The sentence is about the
 * event in front of the reader, and "This event was cancelled." says that on the Detail
 * screen and in the strip's own entry.
 *
 * **`{when}` and `{where}` are the backend's own degradation.** The backend's
 * `notice_subject` replaces a missing `{when}` with *"a new time"* and a missing `{where}`
 * with *"a new location"*, because a subject that cannot be built is worse than one that
 * says less. The frontend has the same problem — the notice payload carries no new date
 * and no new venue — so it uses the same words. Two vocabularies for one degradation is
 * exactly what this file exists to prevent.
 *
 * **One sentence needed a second substitution, and this is why.** The backend's supersede
 * subject is *"{title} was replaced by a new event."* — written for a *named* subject,
 * where "Brooklyn Symphony was replaced by a new event." reads naturally. With "This
 * event" substituted for the title it reads *"This event was replaced by a new event."*,
 * which trips over itself: the reader has just been told the thing is an event, twice,
 * with the second one sounding like a different thing.
 *
 * **So the object becomes "another event"** — *"This event was replaced by another
 * event."* — the same fact, said without the repetition, and it keeps the sentence's
 * subject and object distinct. **This is the one place the frontend's wording is not a
 * pure substitution**, and `tests/notice-copy.test.ts` holds it to exactly that one
 * exception rather than letting it drift.
 *
 * **A change of kind that moved the venue is `detail_changed`, and it says where.** The
 * backend notifies a `detail_changed` *only* when it moved the venue — a title or
 * description edit is not notified at all (FR-53: not every change deserves a
 * notification) — so the only `detail_changed` that can reach the screen is a venue
 * move.
 */
export const NOTICE_CHANGE_LINES: Record<NoticeChangeKind, string> = {
  cancelled: "This event was cancelled.",
  superseded: "This event was replaced by another event.",
  reinstated: "This event is back on.",
  postponed: "This event was moved to a new time.",
  time_moved: "This event was moved to a new time.",
  sold_out: "This event is sold out.",
  detail_changed: "This event moved to a new location.",
};

/**
 * What the change means for the user's reminders, per kind.
 *
 * **The backend's `REMINDER_CONSEQUENCE`, verbatim.**
 *
 * **Verbatim is the point.** These are promises about sends the server has already
 * decided: "Your reminders for this event have been cancelled." is true because the
 * backend cancelled them. A frontend that reworded it — "Your reminders will be
 * cancelled", say — would be making a different and weaker claim, and a user reading it
 * would be less sure than they should be. So the sentences are copied exactly, and
 * `tests/notice-copy.test.ts` fails if the backend's table and this one disagree.
 *
 * **The backend's table is not identical to its derivation.** `REMINDER_CONSEQUENCE`
 * overrides `reinstated` (whose behaviour is `REMINT`, but "rescheduled to the new time"
 * would promise a new time a reinstatement does not have) and states `sold_out` and
 * `detail_changed` as `KEEP`. This table carries the *resolved* sentences, which is what
 * the screen needs.
 */
export const NOTICE_REMINDER_LINES: Record<NoticeChangeKind, string> = {
  cancelled: "Your reminders for this event have been cancelled.",
  superseded: "Your reminders for this event have been cancelled.",
  postponed: "Your reminders have been rescheduled to the new time.",
  time_moved: "Your reminders have been rescheduled to the new time.",
  reinstated: "Your reminders are back on.",
  sold_out: "Your reminders are unchanged.",
  detail_changed: "Your reminders are unchanged.",
};

/**
 * The kinds a mute does **not** silence.
 *
 * **The backend raises these *despite* a mute, and the frontend must not hide them.**
 * `backend/apps/delivery/services/state_notices.py` raises a `cancelled` or `superseded`
 * notice even when the event is muted, and `services/mutes.py` says why: *"FR-55 has
 * already removed the event from their digest, so silence about it is the one failure with
 * no second channel to catch it."*
 *
 * **So the mute silences the *non*-terminal corrections** — a moved time, a moved venue, a
 * sold-out — and leaves the terminal ones alone. **And because the backend raises only
 * terminal notices for a muted event, a muted event's notice is *always* one of these two.**
 * That is the backend's fact, not the client's, and the banner's rule rests on it.
 */
export const TERMINAL_NOTICE_KINDS: ReadonlySet<NoticeChangeKind> = new Set([
  "cancelled",
  "superseded",
]);

/**
 * Whether a mute silences this kind of notice.
 *
 * **`false` for a terminal kind** — the backend raised it *because* the event was muted,
 * and a frontend that hid it would be undoing the server's deliberate decision (AD-10: the
 * client does not re-decide a fact the server has already stated).
 */
export function muteSilencesNotice(changeKind: string): boolean {
  return !TERMINAL_NOTICE_KINDS.has(changeKind as NoticeChangeKind);
}

/**
 * The change's line, or `null` for a kind this table has no word for.
 *
 * **`null`, not a fallback.** ASSUMPTION-9: a change kind this system has never heard of
 * is a fact it cannot put into words, and *"Something changed."* would be inventing a
 * claim — worse than saying nothing, because the reader cannot tell an invention from a
 * fact.
 */
export function noticeChangeLineFor(changeKind: string): string | null {
  const line = NOTICE_CHANGE_LINES[changeKind as NoticeChangeKind];
  return line ?? null;
}

/**
 * The consequence line, or `null` for a kind this table has no word for.
 *
 * **`null` for the same reason, and for one more.** The consequence is a *promise about
 * the user's reminders*, and a promise about a change kind this table has never heard of
 * would be a promise nobody made. So an unknown kind gets nothing.
 */
export function noticeReminderLineFor(changeKind: string): string | null {
  const line = NOTICE_REMINDER_LINES[changeKind as NoticeChangeKind];
  return line ?? null;
}

/**
 * The whole notice, as the two sentences the banner and the strip show.
 *
 * **`null` when either sentence is missing** — and this is deliberately *all or
 * nothing*. A notice that says what changed but not what it means for the user's
 * reminders is FR-54's requirement half-met, and a user reading "This event was
 * cancelled." with no consequence line would not know whether to cancel their own plans.
 * So the pair is returned together or not at all.
 */
export function noticeLinesFor(changeKind: string): { change: string; reminder: string } | null {
  const change = noticeChangeLineFor(changeKind);
  const reminder = noticeReminderLineFor(changeKind);
  if (change === null || reminder === null) return null;
  return { change, reminder };
}
