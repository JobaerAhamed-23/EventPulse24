"use client";

/**
 * The **report flag** — FR-59's "Report this event", on the Detail Screen.
 *
 * **A report is a private signal, not a state.** The event does not change when one is
 * made: no badge, no greyed card, no second read. FR-59 says it twice — *"A single report
 * does not auto-reject an event"* and *"Out of Scope: Auto-rejection on a single report
 * (rejected — editorial confirmation required)"* — and the reason is the calm principle:
 * if one person's report changed what everyone else saw, one report would be a lever on
 * a listing. So this control's entire visible footprint is the flag, the modal, and the
 * toast. **The control holds no state about the event**, and no prop carries one — the
 * server does not send one, and `EventReportOut` has no such field.
 *
 * ---
 *
 * ## The flag
 *
 * **A glyph *and* the words.** FR-59 asks for "Icon: small flag glyph". The house rule
 * forbids an icon-only button — `share-control.tsx` puts it in its own docstring:
 * *"A visible label, never an icon-only button (WCAG 1.1.1, as this repo reads it — see
 * the Source Badge's own docstring). There is no icon library in the product (`DESIGN.md`:
 * 'UI system: None'), and a share icon with no label would fail the rule that every other
 * control here passes."* So the ⚑ is `aria-hidden` and the words carry the name.
 *
 * **The accessible name contains the visible text** (WCAG 2.5.3, "label in name"), so the
 * name is "Report this event" — the same phrase the user reads.
 *
 * **It is the quietest thing on the row.** Save is the filled terracotta primary; Share
 * is a bordered secondary; the flag is muted ink with an underline — the treatment
 * `DetailMuteControl` already uses for this surface's quietest control. No fill, no
 * border, no terracotta: FR-59's "Not a primary button", stated as the *absence* of the
 * tokens the other two have.
 *
 * ---
 *
 * ## The modal
 *
 * **A `Sheet`, and a dismissible one.** The shared `<dialog>` gives the top layer and the
 * focus trap with no JavaScript and no library — a focus-trap package would also break
 * `tests/architecture.test.ts`'s ban on UI kits. It is **dismissible**, unlike the
 * conflict prompt (`ConflictResolution` uses `dismissible={false}`), because a conflict
 * is a forced choice (FR-58) and **a report is optional**: a user who opens the modal and
 * changes their mind has to be able to leave without reporting.
 *
 * **The options are a radio group, because a category is a *state*.** Exactly one of the
 * four is true, which is the definition of a radio group, and `role="radiogroup"` +
 * `role="radio"` + `aria-checked` is its ARIA spelling. This is **not** the conflict
 * prompt's `role="group"` of buttons — those three are *actions*, and this one is a
 * choice among four states.
 *
 * **The radio's accessible name is the label alone.** The mockup's description under each
 * option is helpful to a sighted reader and `aria-hidden` to everyone else, so that
 * `getByRole("radio", { name: "Wrong date or time" })` resolves to exactly the label the
 * editorial queue triages on.
 *
 * **There is no free-text field, and the Submit is disabled until something is chosen.**
 * FR-59: *"No free-text field in MVP."* The API's `EventReportIn` has two fields, so
 * there is nowhere for free text to go — a text field would be a control that cannot be
 * submitted. And **choosing an option does not submit**: a report that fires on a
 * mis-tapped radio is a report the user did not mean to make. The choice is one action;
 * the submission is the further one.
 *
 * ---
 *
 * ## What each answer does
 *
 * | The answer | What happens |
 * | --- | --- |
 * | 201 | The modal closes, the toast says thanks, focus returns to the flag. |
 * | 429 | The modal **stays open**, with the API's message inline. |
 * | 404 / 422 | The modal stays open, with the API's message inline. |
 * | A network failure | The modal stays open, the selection is preserved, `OFFLINE_MESSAGE`. |
 *
 * **Every failure leaves the modal open.** A modal that closes on a failed submit tells
 * the user the report went somewhere. It did not.
 *
 * **The rate limit is the API's to enforce, and the client's to render calmly.** The
 * client cannot know the user is on their sixth report — there is no endpoint that carries
 * the user's daily tally, and FR-59 rejects a visible counter outright — so the limit is
 * *discovered by attempting* and shown as the server's own sentence. FR-59's mockup wanted
 * the Submit disabled in advance; that would mean disabling it for the first five reports
 * too, which is a control that is wrong most of the time.
 *
 * **The messages are the API's own.** `lib/api-errors.ts` exists so the frontend quotes
 * the API verbatim: *"The frontend's job is to put those words on the screen, not to write
 * its own."* The one string the frontend owns is `OFFLINE_MESSAGE`, because in that case
 * the API never spoke.
 *
 * ---
 *
 * ## The toast, and the focus
 *
 * **A bare `aria-live="polite"`, never a second `role="status"`.** The Detail Screen's
 * action row already owns one — the conflict-failure line in `detail-actions.tsx` — and
 * `app/events/[id]/page.test.tsx` asserts the page carries no status region in its
 * resting state. Two status regions on one surface would make "which one is the page
 * talking?" a question the DOM cannot answer.
 *
 * **It is always in the DOM.** A live region added to the page together with its text is
 * not announced reliably; a region that is already there and then changes is. So the `<p>`
 * is unconditional and the *change* to it is what gets announced.
 *
 * **Focus returns to the flag when the modal closes.** The browser's default is to move
 * focus to `<body>` when a modal dialog closes, which dumps a keyboard user at the top of
 * the document with no focus at all (WCAG 2.4.3). So the flag holds a ref and the focus
 * moves back — **on the transition**, guarded by `wasOpen`, because an effect that runs
 * "when the modal is closed" also runs on the first render and would steal focus before
 * the user had done anything.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { Sheet } from "@/components/sheets/sheet";
import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { OFFLINE_MESSAGE } from "@/lib/api-errors";

/**
 * The report's body, as the **generated contract** states it.
 *
 * **Derived, never declared.** The category union is the contract's own, so a category
 * the API does not have is a type error here rather than a request the server refuses
 * (AD-19: the frontend reaches the backend only through the generated client, and a
 * hand-written copy of its shapes is one that can say something the API does not).
 */
type ReportBody = components["schemas"]["EventReportIn"];

/**
 * The one category value.
 *
 * **`EventReportIn["category"]` is the union**, so it cannot drift from the schema.
 */
type ReportCategory = ReportBody["category"];

/**
 * The four categories, worded exactly as FR-59 words them.
 *
 * **The labels are the contract.** FR-59 lists them, and the work item's acceptance
 * criteria say "worded exactly as in FR-59" — so they are neither paraphrased nor
 * shortened, and the mockup's descriptions are *not* part of the label.
 *
 * **The descriptions are the mockup's**, and they are for the sighted reader; they are
 * `aria-hidden` on the control, so the radio's accessible name is its label alone.
 */
const CATEGORIES: ReadonlyArray<{
  value: ReportCategory;
  label: string;
  description: string;
  glyph: string;
}> = [
  {
    value: "wrong_date_time",
    label: "Wrong date or time",
    description: "The event is on a different day, at a different time, or the date is missing.",
    glyph: "📅",
  },
  {
    value: "wrong_venue",
    label: "Wrong venue or address",
    description: "The location is off, the venue moved, or the address doesn't exist.",
    glyph: "📍",
  },
  {
    value: "does_not_exist",
    label: "Doesn't exist or is cancelled",
    description: "The event was cancelled, the link is dead, or it never happened.",
    glyph: "🚫",
  },
  {
    value: "duplicate",
    label: "Duplicate of another event",
    description: "You've seen the same event listed twice — this is a copy.",
    glyph: "⎘",
  },
];

/**
 * What the control last said.
 *
 * **One outcome, and it is the only one the toast carries.** "Reported" means the
 * server accepted the report. **Every refusal is the server's answer, and it is shown
 * inside the modal** — the rate limit, a 404, a 422 and a network failure all set
 * `refusal` and none of them sets a toast. So this union has exactly one member: there
 * is no failure toast to render, because a failure is not a toast.
 */
type Message = "reported";

/** The success toast's words. FR-59's own, verbatim. */
const REPORTED_MESSAGE = "Thanks — we'll review this.";

export type EventReportControlProps = {
  /** The event's id — the report's own field, and the path it acts on. */
  eventId: string;
  /**
   * The event's own title.
   *
   * **The modal names the event the user is looking at.** The screen knows what it is
   * showing — it is the screen for it — so the client does not look it up and does not
   * guess one.
   */
  eventName: string;
};

export function EventReportControl({ eventId, eventName }: EventReportControlProps) {
  /** Whether the modal is open. */
  const [open, setOpen] = useState(false);
  /**
   * The chosen category.
   *
   * **It survives a failed submit.** The selection is the user's work, and losing it
   * because the server said "not today" would make the user do the thing twice — the
   * opposite of FR-59's "one tap submits".
   */
  const [selected, setSelected] = useState<ReportCategory | null>(null);
  /** Whether a write is in flight, so the Submit cannot be pressed twice. */
  const [busy, setBusy] = useState(false);
  /** What the control last said, for the toast. */
  const [message, setMessage] = useState<Message | null>(null);
  /**
   * **The server's answer, shown inside the modal.**
   *
   * **It is not a toast.** A toast is transient, and the rate limit lasts until
   * tomorrow — a message that disappears on a timer is a message the user will miss. And
   * a modal that closed on a 429 would take the selection away from the user.
   */
  const [refusal, setRefusal] = useState<string | null>(null);

  /** The flag, so the focus can come back to it. */
  const flagRef = useRef<HTMLButtonElement>(null);
  /** The heading, so the focus can go into the modal when it opens. */
  const headerRef = useRef<HTMLHeadingElement>(null);
  /** Whether the modal *was* open, so the focus move is a transition and not a first render. */
  const wasOpen = useRef(false);

  /**
   * **Focus moves to the heading when the modal opens**, so a screen reader lands on the
   * question rather than on the first option. The `conflict-resolution.tsx` pattern.
   */
  useEffect(() => {
    if (open) headerRef.current?.focus();
  }, [open]);

  /**
   * **Focus returns to the flag when the modal closes.**
   *
   * **The `wasOpen` guard is load-bearing.** An effect that ran "when the modal is
   * closed" would also run on the first render — and would steal focus to the flag
   * before the user had done anything. This moves the focus only on the transition from
   * open to closed.
   */
  useEffect(() => {
    if (wasOpen.current && !open) {
      flagRef.current?.focus();
    }
    wasOpen.current = open;
  }, [open]);

  /**
   * **Opening the modal clears the last answer.** The line is about the last attempt, and
   * a refusal still on screen next to a freshly opened modal is a claim about an attempt
   * the user has not made yet.
   */
  const openModal = useCallback(() => {
    setRefusal(null);
    setMessage(null);
    setOpen(true);
  }, []);

  const closeModal = useCallback(() => {
    setOpen(false);
  }, []);

  const submit = useCallback(async () => {
    if (!selected) return;

    setBusy(true);
    setRefusal(null);

    /**
     * **The body is typed by the generated contract**, so a category outside the union is
     * a compile error rather than a request the server refuses.
     */
    const body: ReportBody = { event_id: eventId, category: selected };

    try {
      const response = await api.POST("/api/personal/event-reports", { body });

      /**
       * **A 429 is the server's answer, not a failure.** It says the report was not
       * accepted, and it says why — in a sentence written for the user. So the modal
       * stays open and the sentence goes inside it, where the user is already looking.
       */
      if (response.response.status === 429) {
        setRefusal(response.error?.message ?? OFFLINE_MESSAGE);
        return;
      }

      if (response.response.status < 200 || response.response.status >= 300) {
        setRefusal(response.error?.message ?? OFFLINE_MESSAGE);
        return;
      }

      /**
       * **The report is made. The modal closes, the toast says thanks.**
       *
       * **Nothing else happens.** The event is not re-read — the report does not change
       * it, so a second read could only answer the same thing — and nothing on the page
       * changes, because a report is a private signal and not a state of the event.
       */
      setOpen(false);
      setSelected(null);
      setMessage("reported");
    } catch {
      /**
       * **The request never reached the API.** The modal stays open, the selection is
       * still chosen, and the Submit is live again — so the user can simply press it
       * once more.
       */
      setRefusal(OFFLINE_MESSAGE);
    } finally {
      setBusy(false);
    }
  }, [eventId, selected]);

  return (
    <>
      <div className="inline-flex flex-col items-start gap-1">
        <button
          ref={flagRef}
          type="button"
          onClick={openModal}
          /**
           * **The name is the visible text, so "label in name" holds** (WCAG 2.5.3). The
           * glyph is `aria-hidden` and carries no name of its own.
           */
          aria-label="Report this event"
          className="min-h-[44px] text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-md)]"
        >
          <span aria-hidden="true">⚑ </span>
          Report this event
        </button>

        {/*
          The toast. **A bare live region, not a `role="status"`** — the action row
          already owns this surface's one status region (the conflict-failure line), and
          two status regions on a surface would make "which one is the page talking?" a
          question the DOM cannot answer.

          **It is always in the DOM**, even when it says nothing: a live region added to
          the page together with its text is not announced reliably, and a region that is
          already there and then changes is.
        */}
        <p aria-live="polite" className="text-ink-muted [font:var(--type-scale-meta-sm)]">
          {message === "reported" ? REPORTED_MESSAGE : null}
        </p>
      </div>

      {/*
        The modal. **It is dismissible** — Escape closes it, and so does the Cancel
        button — because a report is optional. (The conflict sheet is not: a conflict is
        a forced choice.)

        **The dialog's accessible name is the same phrase the user reads**, so the name
        is not doubled up with the heading.
      */}
      <Sheet open={open} onClose={closeModal} label="Report this event">
        <div className="px-6 pt-6 pb-4">
          {/*
            The amber flag. **The glyph is decorative** — the heading beside it carries
            the meaning, and the header glyph is amber and never red (the conflict
            prompt's own rule).
          */}
          <div
            aria-hidden="true"
            className="flex size-12 items-center justify-center rounded-full bg-warn-amber/15 text-xl text-warn-amber"
          >
            ⚑
          </div>
          <h2
            ref={headerRef}
            tabIndex={-1}
            className="mt-3 [font:var(--type-scale-headline-lg)] outline-none"
          >
            Report this event
          </h2>
          <p className="mt-2 [font:var(--type-scale-body-sm)] text-ink-secondary">
            Help us keep EventPulse24 trustworthy. Pick what&apos;s off about{" "}
            <span className="text-ink-primary">{eventName}</span>. Editorial reviews reports within
            24 hours.
          </p>
        </div>

        <div className="px-6 pb-4">
          {/*
            The four categories. **A radio group**, because exactly one of them is true.
            The group's accessible name is the mockup's.
          */}
          <p className="text-ink-muted text-[11px] font-semibold tracking-[0.08em] uppercase">
            What&apos;s wrong?
          </p>
          <div role="radiogroup" aria-label="Report category" className="mt-2 flex flex-col gap-2">
            {CATEGORIES.map((category) => {
              const isSelected = selected === category.value;
              return (
                <button
                  key={category.value}
                  type="button"
                  role="radio"
                  aria-checked={isSelected}
                  /**
                   * **The name is the label alone.** The description is `aria-hidden`, so
                   * the radio resolves to exactly the phrase FR-59 words it with — and
                   * the description is still there for the sighted reader.
                   */
                  aria-label={category.label}
                  onClick={() => setSelected(category.value)}
                  className={[
                    "flex w-full items-start gap-3 rounded-timeline-cell border p-4 text-left",
                    isSelected
                      ? "border-accent-terracotta bg-accent-terracotta/6"
                      : "border-border-subtle bg-surface-paper",
                  ].join(" ")}
                >
                  <span
                    aria-hidden="true"
                    className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-inset text-sm text-ink-secondary"
                  >
                    {category.glyph}
                  </span>
                  <span className="flex-1">
                    <span className="block [font:var(--type-scale-meta-md)]">{category.label}</span>
                    <span
                      aria-hidden="true"
                      className="mt-1 block [font:var(--type-scale-body-sm)] text-ink-muted"
                    >
                      {category.description}
                    </span>
                  </span>
                  <span
                    aria-hidden="true"
                    className={[
                      "mt-1 size-4 shrink-0 rounded-full border",
                      isSelected
                        ? "border-accent-terracotta bg-accent-terracotta"
                        : "border-ink-faint",
                    ].join(" ")}
                  />
                </button>
              );
            })}
          </div>
        </div>

        {/*
          **The server's refusal, inside the modal.** It is not a toast: the rate limit
          lasts until tomorrow, and a message that disappears on a timer is a message the
          user will miss. And the modal stays open, so the selection survives.
        */}
        {refusal ? (
          <p className="px-6 pb-4 [font:var(--type-scale-body-sm)] text-ink-secondary">{refusal}</p>
        ) : null}

        <div className="flex items-center justify-end gap-3 border-t border-border-subtle px-6 py-4">
          <button
            type="button"
            onClick={closeModal}
            className="rounded-control border border-border-subtle px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              void submit();
            }}
            /**
             * **Disabled until a category is chosen.** There is no "submit nothing" state
             * to handle, and the button's own disabledness is the only place that says so.
             */
            disabled={!selected || busy}
            className="rounded-control bg-accent-terracotta px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-inverse disabled:cursor-default disabled:bg-surface-inset disabled:text-ink-muted"
          >
            Submit report
          </button>
        </div>
      </Sheet>
    </>
  );
}
