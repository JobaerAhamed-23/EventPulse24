"use client";

/**
 * The forgot-password request: one field, one locked sentence.
 *
 * `EXPERIENCE.md` defers the visual and locks the copy: "We've sent a reset link to
 * {email}." — shown in the `.form-footer` success pattern, with no new component
 * invented. So this is the sign-in vocabulary with one field.
 *
 * **The success state is unconditional.** `POST /api/auth/password-reset` answers `202`
 * for a known address and an unknown one alike (AD-18) — a known address gets mail, an
 * unknown one gets nothing, and the response cannot say which. The sentence names the
 * address the user typed, which is information they already have, and never says whether
 * there is an account behind it.
 */

import Link from "next/link";
import { useState } from "react";

import { readApiError } from "@/lib/api-errors";
import { EMAIL_INVALID, isEmailLike } from "@/lib/auth-validation";
import { api } from "@/lib/backend-client";

import { AuthTextInput } from "./auth-field";
import { FormAlert, SubmitButton } from "./submit-button";

export function ResetRequestForm() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);

  const submit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setFormError(null);
    const address = email.trim();
    if (!isEmailLike(address)) {
      setEmailError(EMAIL_INVALID);
      return;
    }
    setEmailError(null);

    setBusy(true);
    let response;
    try {
      response = await api.POST("/api/auth/password-reset", { body: { email: address } });
    } catch (thrown) {
      // A request that never reached the API: the user is told so, not left waiting.
      setFormError(readApiError(thrown).message);
      setBusy(false);
      return;
    }
    if (response.error) {
      // A 429 or an unreachable API. Not an answer about the address.
      setFormError(readApiError(response.error).message);
      setBusy(false);
      return;
    }
    setSentTo(address);
  };

  if (sentTo !== null) {
    return (
      <div className="flex flex-col gap-4">
        <p role="status" className="[font:var(--type-scale-body-md)] text-ink-secondary">
          We&apos;ve sent a reset link to <strong className="text-ink-primary">{sentTo}</strong>.
        </p>
        <p className="[font:var(--type-scale-body-sm)] text-ink-muted">
          The link works once, and for 30 minutes.
        </p>
        <Link
          href="/signin"
          className="[font:var(--type-scale-body-sm)] text-accent-terracotta underline underline-offset-4"
        >
          Back to sign in →
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5">
      {formError ? <FormAlert message={formError} /> : null}

      <AuthTextInput
        id="reset-email"
        name="email"
        label="Email"
        type="email"
        value={email}
        autoComplete="email"
        placeholder="you@example.com"
        error={emailError ?? undefined}
        readOnly={busy}
        onChange={(value) => {
          setEmail(value);
          if (emailError) setEmailError(null);
        }}
      />

      <div className="flex items-center justify-between gap-4">
        <Link
          href="/signin"
          className="[font:var(--type-scale-body-sm)] text-ink-muted underline underline-offset-4"
        >
          Back to sign in
        </Link>
        <SubmitButton label="Send reset link" busyLabel="Sending…" busy={busy} />
      </div>
    </form>
  );
}
