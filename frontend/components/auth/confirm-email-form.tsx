"use client";

/**
 * The form that spends a confirmation token.
 *
 * **It is a form, and that is the security decision.** The token could be spent by the
 * page simply loading — but a `GET` that moves a login is performed by every mail
 * scanner, link prefetcher and security appliance that touches the message, and the
 * account would change address because software followed a link. So a person presses a
 * button, and the endpoint behind it is a `POST`.
 *
 * **The token leaves the address bar as soon as this component holds it**, exactly as
 * `ResetConfirmForm` does: a URL carrying a live credential ends up in history, in a
 * shared screenshot, and in whatever reads `location`.
 *
 * **Every refusal is one message.** Expired, already used, revoked by a cancel or a
 * password reset, and "somebody else took that address in the meantime" are
 * indistinguishable at the endpoint on purpose — a message that told them apart would be
 * an oracle for guessed tokens. So the copy does not guess either: it says the link did
 * not work and what to do next, which is the same action in all five cases.
 */
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/backend-client";
import { readApiError } from "@/lib/api-errors";

/** Shown when the request never reached the API — there is nothing to quote. */
const OFFLINE = "We couldn't reach us just now. Try again in a moment.";

/**
 * Shown when the API refused the token.
 *
 * **The API's own message is preferred**, following the frontend's rule that the backend
 * writes its refusals for the reader. This is the fallback for a body that is not the
 * project's error shape.
 */
const REFUSED = "That link isn't valid anymore. Ask for a new one from your profile.";

export function ConfirmEmailForm({ token }: { token: string | null }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<string | null>(null);

  // Take the token out of the address bar. The component already holds it.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.location.search === "") return;
    window.history.replaceState(null, "", window.location.pathname);
  }, []);

  const submit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (token === null) return;

      setBusy(true);
      setFailure(null);
      try {
        const response = await api.POST("/api/auth/profile/email/confirm", {
          body: { token },
        });
        if (response.error) {
          const refusal = readApiError(response.error);
          setFailure(refusal.message || REFUSED);
          return;
        }
        setConfirmed(response.data?.email ?? "");
      } catch {
        setFailure(OFFLINE);
      } finally {
        setBusy(false);
      }
    },
    [token],
  );

  if (confirmed !== null) {
    return (
      <div role="status" data-confirmed>
        <p className="text-ink-primary [font:var(--type-scale-body-md)]">
          Done. Your account now signs in with <strong>{confirmed}</strong>.
        </p>
      </div>
    );
  }

  if (token === null) {
    /*
      **No token in the URL.** Not an error about the account — the person has opened the
      page without the link, or a mail client mangled it. Saying "invalid link" here would
      accuse them of something that did not happen.
    */
    return (
      <p className="text-ink-secondary [font:var(--type-scale-body-md)]" data-no-token>
        Open the link from the email we sent to your new address. If the link looks broken,
        copy it into your browser.
      </p>
    );
  }

  return (
    <form onSubmit={submit} data-confirm-email-form>
      <p className="text-ink-secondary [font:var(--type-scale-body-md)]">
        Confirming moves your account to this address. Your old one stops signing you in.
      </p>
      <button
        type="submit"
        disabled={busy}
        aria-busy={busy}
        data-confirm
        className="mt-4 min-h-[44px] rounded-control border border-border-subtle px-3 py-2 text-ink-primary [font:var(--type-scale-body-sm)]"
      >
        Confirm this address
      </button>
      {failure !== null ? (
        <p role="alert" className="mt-3 text-ink-secondary [font:var(--type-scale-body-sm)]" data-failure>
          {failure}
        </p>
      ) : null}
    </form>
  );
}
