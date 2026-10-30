"use client";

/**
 * `Component.Auth.SignIn` — the returning user's way back in (`signin-desktop.html`).
 *
 * **The account-enumeration rule is the shape of this component** (`EXPERIENCE.md`,
 * locked): a failed sign-in renders its error on the **Password** field, never on Email,
 * whichever half was actually wrong. The API makes that easy to honour — a wrong password
 * and an unknown address are one byte-identical 401 — and the form keeps it true by
 * never marking Email invalid from a server answer.
 *
 * The message shown is the API's own ("That email and password don't match."), not the
 * copy bank's "That password doesn't match. Try again or reset it.". The two disagree,
 * and the copy bank's line quietly implies the *address* was right, which is the leak the
 * rule exists to prevent. The way to a reset is the "Forgot password?" link, which sits
 * under the field.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { readApiError } from "@/lib/api-errors";
import { EMAIL_INVALID, isEmailLike } from "@/lib/auth-validation";
import { api } from "@/lib/backend-client";

import { AuthTextInput, PasswordInput } from "./auth-field";
import { FormAlert, SubmitButton } from "./submit-button";

export function SigninForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const checkEmail = (): boolean => {
    // The format check runs on blur and on submit, never on every keystroke: telling
    // someone their address is malformed while they are still typing it is hostile.
    const valid = isEmailLike(email);
    setEmailError(valid ? null : EMAIL_INVALID);
    return valid;
  };

  const submit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setFormError(null);
    setPasswordError(null);
    if (!checkEmail()) return;

    setBusy(true);
    const response = await api.POST("/api/auth/signin", {
      body: { email: email.trim(), password },
    });

    if (response.error) {
      const failure = readApiError(response.error);
      // The API's words, on the Password field. Email is left untouched — marking it
      // invalid would say "this address is the problem", which is the enumeration leak.
      if (failure.code === "invalid_credentials") setPasswordError(failure.message);
      else setFormError(failure.message);
      setBusy(false);
      return;
    }

    // The session cookie is set. `replace` rather than `push`, so Back does not return to
    // a sign-in form the user is already past; `refresh` re-runs the server components so
    // `/` sees the new session rather than a cached anonymous render.
    router.replace("/");
    router.refresh();
  };

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5">
      {formError ? <FormAlert message={formError} /> : null}

      <AuthTextInput
        id="signin-email"
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
        onBlur={() => {
          if (email.trim() !== "") checkEmail();
        }}
      />

      <PasswordInput
        id="signin-password"
        name="password"
        label="Password"
        value={password}
        autoComplete="current-password"
        error={passwordError ?? undefined}
        readOnly={busy}
        onChange={(value) => {
          setPassword(value);
          if (passwordError) setPasswordError(null);
        }}
      />

      <div className="flex items-center justify-between gap-4">
        <Link
          href="/reset-password"
          className="[font:var(--type-scale-body-sm)] text-ink-muted underline underline-offset-4"
        >
          Forgot password?
        </Link>
        <SubmitButton label="Sign in" busyLabel="Signing in…" busy={busy} />
      </div>
    </form>
  );
}
