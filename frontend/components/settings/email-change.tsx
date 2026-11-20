"use client";

/**
 * The account's email address — **and the one control on this screen that waits.**
 *
 * ## Why this one does not save on change
 *
 * Every other settings island saves on keystroke, and the name right above this one does
 * too: *"the control the user pressed is the thing that saves."* **This one cannot.** An
 * address typed a character at a time would mail `m@`, then `ma@`, then `may@` — to
 * strangers, from an endpoint that sends real mail. So it has an explicit action, and the
 * copy says what that action does *before* it is pressed rather than after.
 *
 * **That makes it the odd control on the screen, deliberately.** A reader who notices the
 * difference is noticing something real: this is the only setting here that changes a
 * credential, and the only one that cannot take effect immediately.
 *
 * ## Nothing changes until the link is opened
 *
 * The request sends a link to the new address and a warning to the current one. The login
 * does not move until somebody opens that link. The screen says so in those words,
 * because a person who sees "Saved." and keeps using their old address has been told
 * something false.
 *
 * ## A taken address looks exactly like a free one
 *
 * The API answers a free address and one another account already holds with the **same**
 * 202 — anything else would make it an oracle for *"does an account exist here?"*. **So
 * this island must not become that oracle either.** There is one success line, and it is
 * the same sentence both times. This is why the success copy says a link *was sent to*
 * the address rather than anything about the address being available.
 *
 * ## Resend is the request, again
 *
 * There is no resend endpoint and none is needed: the raw token is never stored, so a
 * resend has to mint a new link anyway, and the request endpoint already revokes the
 * outstanding one. **Pressing Resend posts the same address again**, which is honest
 * about what it does — the previous link stops working.
 *
 * ## Cancel is the remedy, not a convenience
 *
 * The warning mail tells someone who did not ask for this to reset their password. **This
 * is the gentler route for the commoner case**: the account holder mistyped the address,
 * or changed their mind, and would rather stop than wait a day for a link they cannot
 * use. It is idempotent on the server, so pressing it twice is not an error.
 *
 * ## What this island does **not** say
 *
 * It does not warn about being signed out elsewhere. The design decided an email change
 * ends no sessions — an email change invalidates no session auth hash — and a screen that
 * implied otherwise would be describing a product that does not exist.
 */
import { useCallback, useState } from "react";

import { SaveFeedback } from "@/components/settings/save-feedback";
import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";

export type EmailChangeProps = {
  /** The address the account signs in with today. */
  email: string;
  /** The address an outstanding change is *to*, or `""` when none is pending. */
  initialPendingEmail: string;
  /**
   * When the pending link stops working, ISO-8601, or `""` when none is pending.
   *
   * **The moment comes from the server, and the screen formats it.** Writing "24 hours"
   * here would be the same mistake the mail templates carried — copy that keeps claiming
   * a number the constant has since changed.
   */
  initialPendingExpiresAt: string;
};

/** The offline line — the same short sentence the other islands use. */
const FAILURE = "Couldn't save.";

/**
 * The success line, **word for word in both cases**.
 *
 * It names the address a link went to and says nothing about whether that address was
 * free. A sentence that differed between the two would hand back the account-existence
 * oracle the endpoint refuses to be.
 */
function sentTo(address: string): string {
  return `We've sent a link to ${address}. Your address changes when you open it.`;
}

/**
 * The expiry as a sentence, or `null` when there is nothing useful to say.
 *
 * **A link that has already expired is not described as expiring.** Somebody looking at a
 * dead link needs to be told to send a new one, not given a time that has passed.
 */
function expiryLine(iso: string, now: number): string | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return null;
  if (at <= now) return "That link has expired — send a new one.";
  const hours = Math.round((at - now) / 3_600_000);
  if (hours >= 2) return `The link works for about ${hours} more hours.`;
  const minutes = Math.max(1, Math.round((at - now) / 60_000));
  return `The link works for about ${minutes} more ${minutes === 1 ? "minute" : "minutes"}.`;
}

export function EmailChange({
  email,
  initialPendingEmail,
  initialPendingExpiresAt,
}: EmailChangeProps) {
  const [pending, setPending] = useState(initialPendingEmail);
  const [expiresAt, setExpiresAt] = useState(initialPendingExpiresAt);
  const [value, setValue] = useState("");
  /*
    **The clock, read once, on mount.**

    This used to be two bare `Date.now()` calls in the markup below — one in the guard
    that decided whether to render the expiry line, one in the line itself. A single
    sentence was therefore decided by two clocks, and they could land on opposite sides
    of the expiry: the guard would see a live link and the paragraph would print "that
    link has expired" beneath it.

    **It was also impure.** `Date.now()` in render has no stable value, which is what
    React's compiler objected to, and nothing re-renders when the clock passes the
    expiry — so the sentence was never going to update anyway.

    **A lazy initializer, so it is read once and not on every render.** This is
    deliberately not a ticking countdown: a sentence that is true when the page loads is
    what `expiryLine` was written for, and an interval that re-renders a settings screen
    every minute is a different product decision.
  */
  const [now] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  /** The message, not a flag — so the API's own refusal can be shown verbatim. */
  const [failure, setFailure] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  /**
   * The expiry sentence, or `null` when there is nothing useful to say.
   *
   * **Computed once, from one clock**, so the decision to render it and the words
   * rendered cannot disagree. That is the whole of the fix.
   */
  const expiry = expiryLine(expiresAt, now);

  /** Ask for a change to `address`. This is also what Resend does. */
  const request = useCallback(async (address: string) => {
    setBusy(true);
    setFailure(null);
    setSent(null);
    try {
      const response = await api.POST("/api/auth/profile/email", {
        body: { new_email: address },
      });
      if (response.error) {
        setFailure(saveFailureMessage(response.error, FAILURE));
        return;
      }
      // **The same outcome for a free address and a taken one.** The server told us
      // nothing about which it was, and this is where that silence has to be kept.
      setPending(address);
      // **The new link's expiry is not known here.** The server minted it, and this
      // response does not carry it — so the line is cleared rather than left showing the
      // *previous* link's deadline, which would now be wrong. It returns on the next
      // render of the page, which reads `me`.
      setExpiresAt("");
      setValue("");
      setSent(address);
    } catch {
      // The request never reached the API, so there is nothing to quote.
      setFailure(FAILURE);
    } finally {
      setBusy(false);
    }
  }, []);

  const cancel = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    setSent(null);
    try {
      const response = await api.DELETE("/api/auth/profile/email");
      if (response.error) {
        setFailure(saveFailureMessage(response.error, FAILURE));
        return;
      }
      setPending("");
      setExpiresAt("");
    } catch {
      setFailure(FAILURE);
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <section aria-label="Email address" data-email-change>
      <p className="text-ink-secondary [font:var(--type-scale-meta-sm)]">Your email address</p>
      <p className="mt-1 text-ink-primary [font:var(--type-scale-body-md)]" data-current-email>
        {email}
      </p>

      {pending ? (
        /*
          **The pending state, and it names the address.** Somebody who mistyped it needs
          to see what they typed — otherwise they wait a day for a mail that will never
          arrive, with no way to tell why.
        */
        <div className="mt-4 rounded-control border border-border-subtle p-3" data-pending-change>
          <p className="text-ink-primary [font:var(--type-scale-body-sm)]">
            Waiting for you to confirm <strong>{pending}</strong>. Your address changes when
            you open the link we sent there.
          </p>
          {expiry !== null ? (
            <p
              className="mt-1 text-ink-secondary [font:var(--type-scale-meta-sm)]"
              data-pending-expiry
            >
              {expiry}
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void request(pending)}
              disabled={busy}
              data-resend
              className="min-h-[44px] rounded-control border border-border-subtle px-3 py-2 text-ink-primary [font:var(--type-scale-body-sm)]"
            >
              Send the link again
            </button>
            <button
              type="button"
              onClick={() => void cancel()}
              disabled={busy}
              data-cancel
              className="min-h-[44px] rounded-control border border-border-subtle px-3 py-2 text-ink-primary [font:var(--type-scale-body-sm)]"
            >
              Cancel this change
            </button>
          </div>
        </div>
      ) : (
        <form
          className="mt-4 flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (value.trim()) void request(value.trim());
          }}
        >
          <label className="flex flex-col gap-1">
            <span className="text-ink-secondary [font:var(--type-scale-meta-sm)]">
              New email address
            </span>
            <input
              type="email"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder="you@example.com"
              data-new-email-input
              aria-busy={busy}
              aria-invalid={failure !== null || undefined}
              className="min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-3 py-2 text-ink-primary [font:var(--type-scale-body-md)]"
            />
          </label>
          {/*
            **The copy says what the button does before it is pressed.** This control does
            not take effect on its own, and a person who expects it to would be left
            thinking the change had happened.
          */}
          <p className="text-ink-secondary [font:var(--type-scale-meta-sm)]">
            We&rsquo;ll send a link to the new address, and tell your current one. Nothing
            changes until you open the link.
          </p>
          <button
            type="submit"
            disabled={busy || !value.trim()}
            data-request-change
            className="min-h-[44px] self-start rounded-control border border-border-subtle px-3 py-2 text-ink-primary [font:var(--type-scale-body-sm)]"
          >
            Send the link
          </button>
        </form>
      )}

      {sent ? (
        <p role="status" className="mt-3 text-ink-secondary [font:var(--type-scale-body-sm)]" data-sent>
          {sentTo(sent)}
        </p>
      ) : null}

      <div className="mt-2">
        <SaveFeedback busy={busy} saved={false} failure={failure} />
      </div>
    </section>
  );
}
