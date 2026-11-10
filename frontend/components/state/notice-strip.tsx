"use client";

/**
 * The **state-change strip** — FR-54's in-app half, on the digest home.
 *
 * **A strip, not a bell, and not an inbox.** FR-10's design removed the topbar
 * Notifications button and said why: *"per PRD FR-10 there is no in-app notifications
 * inbox."* So there is no bell, no badge count, no history, no "view all" — the strip
 * shows the few notices the user has not dismissed, and a dismissal empties it. FR-54's
 * "one calm correction", told where the user already is.
 *
 * ---
 *
 * ## The register is `component.emptystate.quiet`'s, not an alert banner's
 *
 * Everything the user is being told here is bad news about plans they made, delivered by
 * a product whose positioning is calm. `EXPERIENCE.md` §5 is canonical and stricter than
 * both `DESIGN.md` and the mockups — the empty-state precedent, where a terracotta
 * primary button in the mockup was ruled a mockup bug, is the standard.
 *
 * **So there is no terracotta, no red, no `role="alert"`, no exclamation mark, and no
 * "Urgent".** The strip is the empty state's weight: a bordered card, a quiet fill, one
 * line of plain ink, and an underlined text control with no fill. `component.emptystate.quiet`
 * is *"bordered by a 1px dashed `{color.border.strong}` to feel intentional, not failed"*
 * — and that dashed stroke is what separates "nothing is wrong" from "something needs
 * saying". The strip borrows it.
 *
 * **The copy is the product's voice, not a notification service's.** `EXPERIENCE.md` §3's
 * microcopy contract has a row for the state-change email: *"EventPulse24: {event name}
 * was moved to {new date}"* — **not** *"⚠️ Important update about your event!"*. The strip
 * says the same thing in the same register, without the mail's product-name prefix.
 *
 * ---
 *
 * ## Nothing at all when there is nothing to say
 *
 * **The strip's visible chrome renders no element when the list is empty** — not an
 * empty container, not a collapsed one, not a hidden one. The AC says the home screen
 * must render "exactly as it does today, with no layout shift", and an empty `<section>`
 * is a layout shift waiting for a stylesheet. **No element is not.**
 *
 * **The live region is the one exception, and it is `sr-only`.** It has to be in the DOM
 * before the text arrives — otherwise the announcement that matters most (the last
 * notice being dismissed) happens in a region that is leaving the page at the same
 * moment, which is the case screen readers announce unreliably. It is visually hidden,
 * so it costs no layout and the home screen still renders exactly as it does today.
 *
 * ---
 *
 * ## Dismissing calls the API
 *
 * **The dismissal is a write, and the server keeps the record.** FR-54's "never repeats"
 * and the daily cap both depend on the notice row surviving, so `POST
 * /api/notices/{id}/dismiss` sets `dismissed_at` rather than deleting. A client-only
 * dismissal would make the strip empty until the next page load — which is exactly the
 * "not client-only state" the AC rules out, and it would let the same notice come back
 * on the next render.
 *
 * **A failed dismissal puts the notice back.** The entry was not closed, and a strip that
 * showed it as closed would be claiming something that did not happen.
 *
 * ---
 *
 * ## The announcement, and why there is only one status region on this page
 *
 * The digest home already carries exactly one `role="status"` — "Pulse Digest ready, N
 * events for today." (`app/page.tsx`). **Two status regions on a page would make "which
 * one is the page talking?" a question the DOM cannot answer**, so the strip announces
 * through a **bare `aria-live="polite"`**, the same rule `components/share/share-control.tsx`
 * and `components/add-event-button.tsx` already follow.
 *
 * **And it does not steal focus.** The strip is not `role="alert"` (which interrupts), it
 * moves no focus, and the only focusable thing in it is the dismiss control — which the
 * user reaches by tabbing, on purpose. The strip appearing above the digest must not
 * yank the reader away from the cards they were reading.
 *
 * **The live region is always in the DOM.** A live region added to the page together
 * with its text is not announced reliably; a region that is already there and then changes
 * is.
 */
import { useCallback, useState } from "react";
import Link from "next/link";

import { api } from "@/lib/backend-client";
import { noticeLinesFor } from "@/lib/notice-copy";

/** One notice, as the strip holds it. */
export type StripNotice = {
  id: string;
  event_id: string;
  change_kind: string;
};

export type NoticeStripProps = {
  /**
   * The user's open notices, newest first.
   *
   * **The server's list, unchanged.** The strip does not count them, does not sort them,
   * does not filter them by kind, and does not work out whether it has seen them
   * (AD-10). It renders what it was given.
   *
   * **An empty list renders nothing at all** — see the file's own docstring.
   */
  notices: StripNotice[];
};

/**
 * The strip, or nothing.
 *
 * **The visible strip renders nothing for an empty list.** Not an empty `<section>`,
 * not a `<section hidden>` — no element in the DOM at all, so the home screen renders
 * byte-for-byte as it does today.
 *
 * **But the live region is always there.** See the announcement's own note below: a live
 * region that arrives together with its text is not announced reliably, and the *one*
 * moment that matters most is the dismissal of the last notice — which is exactly when
 * a strip that returns `null` would take its own live region with it. So the region
 * lives outside the strip's visible chrome, and only the chrome comes and goes.
 */
export function NoticeStrip({ notices }: NoticeStripProps) {
  /**
   * **The open notices, and which of them the user has closed.**
   *
   * **`closed` is a set of ids, and it starts empty.** The list the server sent is the
   * list of *open* notices, so nothing in it is closed; the set only grows as the user
   * dismisses, and a dismissal that failed does not enter it.
   */
  const [closed, setClosed] = useState<ReadonlySet<string>>(() => new Set());

  /**
   * **The dismissals still in flight.**
   *
   * **A notice is not removed until the server says so.** The entry goes when the write
   * succeeds; a failed write leaves the entry exactly where it was, because it *was* not
   * closed. The in-flight set disables the control while the write runs, so a second
   * click cannot fire a second dismissal.
   */
  const [dismissing, setDismissing] = useState<ReadonlySet<string>>(() => new Set());

  const open = notices.filter((notice) => !closed.has(notice.id));

  /**
   * **The entries that actually render, and each one's position among them.**
   *
   * **The position is counted over the *rendered* entries, not over `open`.** An entry
   * whose change kind this table has no word for renders nothing (ASSUMPTION-9), so it
   * is not a thing the reader can dismiss — counting it would make the positions skip a
   * number and land the last entry on "3 of 4" when there are three on screen.
   */
  const renderable = open.filter((notice) => noticeLinesFor(notice.change_kind) !== null);
  const total = renderable.length;

  /**
   * **The announcement.**
   *
   * **One line, and it names the count.** "One change to an event you saved." /
   * "Two changes to events you saved." The count is not a badge — it is not rendered
   * visually, and there is no `aria-label` on a bell anywhere — it is a sentence, which
   * is what a screen reader can say out loud without a number appearing on the page.
   *
   * **It counts the entries that render, not the entries the server sent.** A notice
   * whose change kind this table has no word for is not a change the reader was told
   * about — it renders nothing at all (ASSUMPTION-9) — so counting it would announce
   * "Two changes" over a screen showing one.
   *
   * **It is derived from the open list, not held in state.** A live region that is
   * *already in the DOM* and then changes is what gets announced reliably; a region
   * whose text arrives together with it is not. And a derived value cannot disagree
   * with what is on screen: dismiss one and it says "two changes"; dismiss the last one
   * and the strip leaves the DOM — but the live region stays, so the change to it is
   * still announced.
   */
  const announcement =
    total === 0
      ? ""
      : total === 1
        ? "One change to an event you saved."
        : `${total} changes to events you saved.`;

  const onDismiss = useCallback(async (noticeId: string) => {
    setDismissing((current) => new Set(current).add(noticeId));

    try {
      const response = await api.POST("/api/notices/{notice_id}/dismiss", {
        params: { path: { notice_id: noticeId } },
      });

      // **A 2xx is a dismissal**, and the entry goes. The endpoint is idempotent, so a
      // notice that was already dismissed answers 200 with `changed: false` — and it is
      // still closed, so the entry still goes.
      if (response.response.status >= 200 && response.response.status < 300) {
        setClosed((current) => new Set(current).add(noticeId));
      }
    } catch {
      // **A failed dismissal leaves the entry alone.** It was not closed, and a strip
      // that showed it as closed would be claiming something that did not happen.
    } finally {
      setDismissing((current) => {
        const next = new Set(current);
        next.delete(noticeId);
        return next;
      });
    }
  }, []);

  return (
    <>
      {/*
        The live region. **A bare `aria-live="polite"`, not a second `role="status"`** —
        the digest page owns the page's `role="status"` ("Pulse Digest ready, N events
        for today."), and two status regions on a page would make "which one is the page
        talking?" a question the DOM cannot answer.

        **It is always in the DOM.** A live region added to the page together with its
        text is not announced reliably; a region that is already there and then changes
        is. **And that matters most at the moment the strip empties** — dismissing the
        last notice changes the region's text from "One change to an event you saved."
        to nothing, and a region that left the DOM at the same instant would take its
        own announcement with it.

        **It is `sr-only`, so it costs no layout.** The AC's "no layout shift" holds: the
        region is visually hidden and takes no space, so the home screen renders exactly
        as it does today.

        **It never steals focus.** `aria-live="polite"` waits for a pause, and nothing
        here moves focus.
      */}
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {renderable.length === 0 ? null : (
        <section
          aria-label="Changes to your saved events"
          // **The dashed stroke is `component.emptystate.quiet`'s.** "Bordered by a 1px
          // dashed `{color.border.strong}` to feel intentional, not failed" — and the
          // difference between "nothing is wrong" and "something needs saying" is
          // exactly what the strip has to communicate.
          className="mt-6 rounded-card border border-dashed border-border-strong bg-surface-elevated p-6"
        >
          {renderable.map((notice, index) => {
            const lines = noticeLinesFor(notice.change_kind);
            /** This entry's position among the rendered entries, one-based. */
            const position = index + 1;

            /**
             * **A kind the table has no word for renders nothing at all.**
             *
             * **The backend does the same, and for the same reason.** `domain/notices.py`'s
             * `subject_template` raises `KeyError` for a kind it has no subject for, and the
             * renderer turns that into a cancelled send: *"a kind `domain.lifecycle` gained
             * without this module learning it must not produce a generic subject — FR-54 fixes
             * the copy, and a wrong subject is worse than no email."*
             *
             * **So the strip says nothing rather than something generic.** "An event you saved
             * has changed." would be a claim about the world — that it changed — made by a
             * client that was told *what* changed and could not understand it. ASSUMPTION-9
             * says a kind this system has never heard of shows nothing.
             */
            if (!lines) return null;

            return (
              <div
                key={notice.id}
                className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2"
                data-notice-strip-item
              >
                {/*
                  **The link is the event's own Detail screen**, so the reader can go and
                  read why. The link's text is the change's sentence, and the sentence says
                  "This event" because the link *is* the event — the strip's payload carries
                  no title (AD-13), and a line naming an event the payload does not carry
                  would be a claim the client cannot make.
                */}
                <p className="text-ink-secondary [font:var(--type-scale-body-md)]">
                  {/*
                    **The link's text is the change, and it is the whole accessible name.**

                    A reader who hears "This event was cancelled." and nothing else would
                    not know *which* event — but the strip **cannot name it**, because the
                    notice payload carries no title (AD-13). So the sentence stands alone,
                    and the event's own card is in the digest right below, where the reader
                    can find it and see what it is.

                    **One tap from the strip, the reader is on the event's own page** — and
                    there the title *is* on the page, above the change's sentence.
                  */}
                  <Link
                    href={`/events/${notice.event_id}`}
                    // **The 44px floor, like every other tap target on the site.** The
                    // dismiss button beside it has it; the share control has it; the
                    // reminder link has it. This link is the strip's primary tap target and
                    // it is the way to the event, so it gets the same floor.
                    className="inline-flex min-h-[44px] items-center underline underline-offset-4 [font:var(--type-scale-body-md)]"
                  >
                    {lines.change}
                  </Link>
                  {/*
                    **The consequence line is a second line, not a second sentence in the
                    same one.** "Your reminders have been rescheduled to the new time." is
                    the answer to the question the reader actually has, and it is the
                    backend's own promise — restated verbatim from
                    `domain/notices.py`'s `REMINDER_CONSEQUENCE`, so the screen cannot
                    promise something the send machinery did not do.
                  */}
                  <span className="mt-1 block text-ink-muted [font:var(--type-scale-meta-md)]">
                    {lines.reminder}
                  </span>
                </p>

                {/*
                  **The dismiss control.** A plain text button in muted ink with an
                  underline — the geo-banner's own dismissible precedent, and the same
                  treatment `DigestEmpty` gives its one low-weight link. **No fill, no
                  terracotta, no icon-only button.**

                  **Its accessible name is the change's sentence.** "Dismiss: this event was
                  cancelled." says what dismissing will close. Three "Dismiss" buttons with
                  no object would tell a screen-reader user nothing about which one they
                  are about to press — and the strip cannot name the event, because the
                  payload carries no title (AD-13).

                  **And the sentence may repeat.** Two events cancelled in one day give
                  two buttons with the same name, and a screen reader offering two
                  identical "Dismiss: This event was cancelled." buttons does not tell the
                  reader which is which. So the name carries the notice's position as
                  well — "Dismiss: This event was cancelled. (2 of 2)" — which is the
                  only disambiguator the strip has, since the payload carries no title
                  (AD-13). The *visible* text stays "Dismiss": the position is a
                  screen-reader affordance, not something to print on the page.
                */}
                <button
                  type="button"
                  onClick={() => {
                    void onDismiss(notice.id);
                  }}
                  disabled={dismissing.has(notice.id)}
                  aria-label={`Dismiss: ${lines.change} (${position} of ${total})`}
                  className="min-h-[44px] text-ink-muted underline underline-offset-4 [font:var(--type-scale-meta-md)] disabled:cursor-default"
                >
                  Dismiss
                </button>
              </div>
            );
          })}
        </section>
      )}
    </>
  );
}
