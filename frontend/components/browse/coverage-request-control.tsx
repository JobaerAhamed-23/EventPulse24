"use client";

/**
 * **Ask us to cover this city** — the one way out of the no-sources state.
 *
 * **A city with no sources is a fact about *our* coverage, and this is the reader's
 * answer to it.** The state says "we couldn't find any event sources for {city}", and
 * this control is the sentence that follows: *tell us and we'll go and look.* Without
 * it the state is a dead end, and a dead end is a lie about the product — we do have a
 * way, and the reader should be able to take it.
 *
 * ---
 *
 * ## Where it appears, and where it does not
 *
 * **The control appears in the no-sources family and nowhere else.** Four statuses
 * share that treatment — `no_providers`, `failed`, `yielded_nothing` and `paused` — and
 * they share it because from the reader's side they are one sentence: we have nothing
 * to collect this city from.
 *
 * **It does not appear in the collecting state**, because asking us to collect a city
 * we are collecting is asking for what we are already doing. **Nor in the quiet state**
 * — a covered city with nothing on tonight is a working collection on a Tuesday, and
 * nothing about it is broken. **Nor for a reader with no city** — they have no
 * collection to report on, and the way out for them is the picker.
 *
 * **The rule is enforced by the branch, not by a condition inside the control.** The
 * page renders the control *inside* the no-sources branch and nowhere else, so "only
 * there" is a fact about the page's structure rather than a runtime `if` that a later
 * edit could widen.
 *
 * ---
 *
 * ## The four states
 *
 * | The state | What the reader sees |
 * | --- | --- |
 * | **idle** | the button |
 * | **busy** | the button, disabled, `aria-busy` — and a quiet dot, never a spinner |
 * | **recorded** | *the confirmation sentence*, and **no button** |
 * | **failed** | the button again, and the server's own sentence under it |
 *
 * **After a success the button is *replaced*, not disabled.** A disabled button that
 * says "Ask us to cover this city" is a control that reads as broken — it looks like
 * something the reader could still do and cannot. **The confirmation replaces it**, so
 * the surface says what is now true: we have been asked. This is the same rule the
 * Detail Screen's mute control follows in the other direction — *the server's answer is
 * the authority on the state* (AD-10), and the reader's state here is "have we asked?",
 * which the server has just answered.
 *
 * **A failure puts the button back and says the server's own words.** The rate limit
 * is the API's to enforce and the client's to render calmly (`lib/api-errors.ts`): the
 * frontend quotes the API rather than writing its own sentence, so the reader is told
 * *"You've asked us to cover enough cities for today. Please try again tomorrow."*
 * rather than a paraphrase that might drift from it. **The one message the frontend
 * owns is the offline one**, because in that case the API never spoke.
 *
 * **A failure never leaves a false confirmation behind.** The confirmation is set only
 * on a 2xx — the server's own answer — so a failed request cannot leave "We've asked"
 * on the screen, which would be a claim about the world that nothing supports.
 *
 * ---
 *
 * ## The request
 *
 * **The body is typed by the generated contract**, so a body that does not match the
 * API is a compile error rather than a request the server refuses (AD-19). **It carries
 * the city and nothing else** — no user id, because the reader comes from the session.
 *
 * **The count is on the wire and not on the screen.** The response carries
 * `request_count` — how many readers have asked — and the control does not show it. A
 * reader told "you are the 47th person to ask" is being told something about a crowd,
 * and the product's voice is calm.
 */
import { useCallback, useState } from "react";

import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { OFFLINE_MESSAGE } from "@/lib/api-errors";

/**
 * The request's body, as the **generated contract** states it.
 *
 * **Derived, never declared** — a hand-written copy of the API's shape is one that can
 * say something the API does not (AD-19).
 */
type CoverageRequestBody = components["schemas"]["CoverageRequestIn"];

export type CoverageRequestControlProps = {
  /** The city to ask about — the catalog's own name for it. */
  city: string;
};

/**
 * The button's words.
 *
 * **A verb, because the button performs the ask.** The sentence below the button
 * explains it; the button names the action.
 */
const ASK_LABEL = "Ask us to cover this city";

/**
 * The confirmation, after the server says yes.
 *
 * **It is a sentence about what we will do, not about what the reader did.** "Thanks —
 * we'll go and look" is the promise the ask actually is; "Request sent" would be a
 * ticket number's worth of nothing to a reader.
 */
const RECORDED_MESSAGE = "Thanks — we'll go and look for sources in this city.";

export function CoverageRequestControl({ city }: CoverageRequestControlProps) {
  /** Whether a request is in flight, so the button cannot be pressed twice. */
  const [busy, setBusy] = useState(false);
  /** Whether the server has answered yes. */
  const [recorded, setRecorded] = useState(false);
  /** The server's own refusal, shown under the button. */
  const [failure, setFailure] = useState<string | null>(null);

  const ask = useCallback(async () => {
    setBusy(true);
    setFailure(null);

    /** **The body is the contract's own**, so a mismatch is a compile error. */
    const body: CoverageRequestBody = { city };

    try {
      const response = await api.POST("/api/catalog/coverage-requests", { body });

      /**
       * **Only a 2xx is the server's answer.** A 429 is the server's own sentence about
       * the rate limit, and a 422 is its sentence about the city — both are refusals,
       * and both are shown as they arrive.
       */
      if (response.response.status < 200 || response.response.status >= 300) {
        setFailure(response.error?.message ?? OFFLINE_MESSAGE);
        return;
      }

      /**
       * **The server has said yes, so the confirmation is now true.**
       *
       * **The button is replaced rather than disabled** — a disabled "Ask us to cover
       * this city" reads as a broken control. The sentence takes its place.
       */
      setRecorded(true);
    } catch {
      /** **The request never reached the API**, so the API never spoke. */
      setFailure(OFFLINE_MESSAGE);
    } finally {
      setBusy(false);
    }
  }, [city]);

  return (
    <div className="flex flex-col items-center gap-2">
      {recorded ? (
        /*
         * **The confirmation replaces the button.**
         *
         * **It is `role="status"`, so it announces itself** — the reader pressed a
         * button and the surface changed under them, and a screen reader user is the
         * one who most needs to hear that it did.
         *
         * **And it is in the DOM only when it is true.** This is not a live region that
         * fills in later: the whole element arrives with the sentence, and the state
         * change it announces is the button's *disappearance* — which a live region
         * would not catch anyway. The sentence is the announcement.
         */
        <p
          role="status"
          aria-live="polite"
          className="text-ink-secondary [font:var(--type-scale-body-sm)]"
          data-coverage-recorded
        >
          {RECORDED_MESSAGE}
        </p>
      ) : (
        <>
          <button
            type="button"
            onClick={() => {
              void ask();
            }}
            /**
             * **Disabled while the request is in flight**, so a second press cannot race
             * the first — and `aria-busy` says so to assistive technology, because a
             * disabled button is removed from the tab order and the reader would
             * otherwise hear nothing at all.
             */
            disabled={busy}
            aria-busy={busy}
            className="rounded-control border border-border-subtle px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary disabled:cursor-default"
            data-coverage-ask
          >
            {ASK_LABEL}
          </button>

          {/*
            **The in-flight dot.** It sits beside the control, so the thing being asked
            is the thing that shows the wait. **It is `aria-hidden`** because the
            button's own `aria-busy` already carries that state.

            **It is a dot and not a spinner** — `EXPERIENCE.md` §"No spinners, anywhere":
            a spinner is a visual urgency badge, and asking for coverage is not urgent.
          */}
          {busy ? (
            <span
              aria-hidden="true"
              className="inline-block h-2 w-2 rounded-full bg-current"
              data-coverage-busy
            />
          ) : null}

          {/*
            **The refusal, and it is the server's own sentence.**

            **It is `role="alert"`** — the failure is not the outcome the reader was
            waiting for, and an alert is announced without the focus moving. **And it is
            conditional**, so it appears with its text rather than filling a live region
            in later: an `alert` that is added to the page together with its text is
            announced by most agents and is not announced by all of them, whereas the
            conditional element here is the shape assistive technology expects.
          */}
          {failure ? (
            <p
              role="alert"
              className="text-warn-amber [font:var(--type-scale-body-sm)]"
              data-coverage-failed
            >
              {failure}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
