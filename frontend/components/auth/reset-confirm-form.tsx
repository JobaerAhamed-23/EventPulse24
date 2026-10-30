"use client";

/**
 * Setting a new password, from the link in the reset email.
 *
 * **The token is a bearer credential for the account**, with a 30-minute life and a
 * single use. It arrives in the URL because an email can only carry a link, so this
 * component gets it out of the URL as soon as it has it: `history.replaceState` drops the
 * query string, which keeps the token out of the back/forward history and out of anything
 * that reads `location.href` later. The page also sets `referrer: "no-referrer"`, so the
 * token cannot leave in a `Referer` header.
 *
 * **The expired-or-used state appears on submit, not on load.** There is no endpoint that
 * says whether a token is still good, and adding one would be an oracle: anybody holding
 * a guess could test it without spending it. So the token is spent, and a `422
 * invalid_reset_token` — "That reset link isn't valid anymore. Ask for a new one." — is
 * what expired, already-used and never-valid all look like. The API does not distinguish
 * them either, deliberately.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { readApiError } from "@/lib/api-errors";
import {
  MIN_PASSWORD_LENGTH,
  PASSWORDS_DONT_MATCH,
  PASSWORD_TOO_SHORT,
} from "@/lib/auth-validation";
import { api } from "@/lib/backend-client";

import { PasswordInput } from "./auth-field";
import { FormAlert, SubmitButton } from "./submit-button";

export function ResetConfirmForm({ token }: { token: string }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [expired, setExpired] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  // Take the token out of the address bar. The component already holds it, so the URL
  // does not need to — and a URL carrying a live credential ends up in history, in a
  // shared screenshot, and in whatever reads `location`.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.location.search === "") return;
    window.history.replaceState(null, "", window.location.pathname);
  }, []);

  const submit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setFormError(null);

    let invalid = false;
    if (password.length < MIN_PASSWORD_LENGTH) {
      setPasswordError(PASSWORD_TOO_SHORT);
      invalid = true;
    } else setPasswordError(null);
    if (confirm !== password) {
      setConfirmError(PASSWORDS_DONT_MATCH);
      invalid = true;
    } else setConfirmError(null);
    if (invalid) return;

    setBusy(true);
    let response;
    try {
      response = await api.POST("/api/auth/password-reset/confirm", {
        body: { token, new_password: password },
      });
    } catch (thrown) {
      // A request that never reached the API. The token is unspent, so trying again works.
      setFormError(readApiError(thrown).message);
      setBusy(false);
      return;
    }

    if (response.error) {
      const failure = readApiError(response.error);
      if (failure.code === "invalid_reset_token") {
        // The token is spent, expired or was never ours. The API's words, and a way to
        // ask for another link.
        setExpired(failure.message);
        setBusy(false);
        return;
      }
      // A weak password: Django's own validator messages, on the field.
      if (failure.fieldErrors.new_password || failure.fieldErrors.password) {
        setPasswordError(failure.fieldErrors.new_password ?? failure.fieldErrors.password);
      } else {
        setFormError(failure.message);
      }
      setBusy(false);
      return;
    }

    setDone(true);
  };

  if (expired !== null) {
    return (
      <div className="flex flex-col gap-4">
        <p role="alert" className="[font:var(--type-scale-body-md)] text-signal-warn">
          {expired}
        </p>
        <Link
          href="/reset-password"
          className="[font:var(--type-scale-body-sm)] text-accent-terracotta underline underline-offset-4"
        >
          Ask for a new link →
        </Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="flex flex-col gap-4">
        <p role="status" className="[font:var(--type-scale-body-md)] text-ink-secondary">
          Your password is changed. Sign in with your new password.
        </p>
        <Link
          href="/signin"
          className="[font:var(--type-scale-body-sm)] text-accent-terracotta underline underline-offset-4"
        >
          Sign in →
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5">
      {formError ? <FormAlert message={formError} /> : null}

      <PasswordInput
        id="reset-new-password"
        name="new_password"
        label="New password"
        value={password}
        autoComplete="new-password"
        placeholder="At least 8 characters"
        hint="8 characters minimum"
        error={passwordError ?? undefined}
        readOnly={busy}
        onChange={(value) => {
          setPassword(value);
          if (passwordError) setPasswordError(null);
        }}
      />

      <PasswordInput
        id="reset-confirm-password"
        name="new_password_confirm"
        label="Confirm new password"
        value={confirm}
        autoComplete="new-password"
        placeholder="Re-enter your new password"
        error={confirmError ?? undefined}
        readOnly={busy}
        onChange={(value) => {
          setConfirm(value);
          if (confirmError) setConfirmError(null);
        }}
        onBlur={() => {
          if (confirm !== "" && confirm !== password) setConfirmError(PASSWORDS_DONT_MATCH);
        }}
      />

      <div className="flex justify-end">
        <SubmitButton label="Set new password" busyLabel="Saving…" busy={busy} />
      </div>
    </form>
  );
}
