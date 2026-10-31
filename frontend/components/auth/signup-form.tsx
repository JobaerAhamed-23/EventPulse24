"use client";

/**
 * `Component.Auth.SignUp` — account creation (`signup-desktop.html`).
 *
 * Three things about this form are not what the mockup draws, and each has a reason in a
 * binding document:
 *
 * **1. Sign-up is followed by a sign-in.** `POST /api/auth/signup` establishes **no**
 * session: the auth item's review found that a `Set-Cookie` on one response and not on
 * another is an account-existence oracle — a stronger one than a differing body, because
 * it confirms the *password*. So the endpoint answers identically for every address, and
 * the session is created in the one place that creates sessions. This form makes that
 * second call, which is what keeps the criterion "sign-up and sign-in establish a
 * session" true from the user's side: they fill in one form and end up signed in.
 *
 * **2. There is no "An account with that email already exists" state.** The mockup's
 * State C renders it from a 409 that the API cannot send — sign-up answers `201
 * {"status": "accepted"}` for a new address and a taken one alike (AD-18), and the holder
 * of an existing address is told by email. This work item's own criterion says the UI
 * never adds wording that reveals whether an account exists, so the state is gone rather
 * than faked from a different signal.
 *
 * **3. There are no provider buttons.** The OIDC stack is drawn here, but nothing is
 * wired to it in this intent and the criterion forbids dead, clickable buttons. The
 * position is held in code (below) so the later intent drops the stack in without moving
 * anything else.
 *
 * What a taken address looks like, honestly: the sign-up answers 201, and the follow-up
 * sign-in fails unless the password happens to be that account's. The form then shows the
 * API's own "That email and password don't match." — the same words `/signin` shows, and
 * no claim about whether an account exists.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { readApiError } from "@/lib/api-errors";
import {
  EMAIL_INVALID,
  MIN_PASSWORD_LENGTH,
  PASSWORDS_DONT_MATCH,
  PASSWORD_TOO_SHORT,
  isEmailLike,
} from "@/lib/auth-validation";
import { api } from "@/lib/backend-client";

import { AuthTextInput, PasswordInput } from "./auth-field";
import { FormAlert, SubmitButton } from "./submit-button";

/**
 * How long the "Account created." notice is held before the redirect.
 *
 * `EXPERIENCE.md` locks 1.5 s, and locks 0 ms under `prefers-reduced-motion` — the hold
 * is a timed transition, and a user who asked for no motion gets the destination
 * directly.
 */
const SUCCESS_HOLD_MS = 1500;

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

type Errors = { email?: string; password?: string; confirm?: string };

export function SignupForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // The hold is a pending navigation. If the component goes away first — the user hit
  // Back during the hold — the timer goes with it rather than routing a page that is no
  // longer on screen.
  useEffect(() => {
    return () => {
      if (timer.current !== null) clearTimeout(timer.current);
    };
  }, []);

  const validate = (): Errors => {
    const found: Errors = {};
    if (!isEmailLike(email)) found.email = EMAIL_INVALID;
    if (password.length < MIN_PASSWORD_LENGTH) found.password = PASSWORD_TOO_SHORT;
    // The mismatch is reported on Confirm, the field being filled — not on Password,
    // which the user already typed correctly. Clearing it would be unkind.
    if (confirm !== password) found.confirm = PASSWORDS_DONT_MATCH;
    return found;
  };

  const submit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setFormError(null);
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setBusy(true);
    const address = email.trim();
    let signup;
    try {
      signup = await api.POST("/api/auth/signup", { body: { email: address, password } });
    } catch (thrown) {
      // A request that never reached the API. No account was created, so the form comes
      // back as it was and the same submit will work once the connection does.
      setFormError(readApiError(thrown).message);
      setBusy(false);
      return;
    }

    if (signup.error) {
      // A weak password or a malformed address: the API's own `details.errors` name the
      // field, and its messages are shown verbatim (Django's validators wrote them).
      const failure = readApiError(signup.error);
      const fields: Errors = {};
      if (failure.fieldErrors.email) fields.email = failure.fieldErrors.email;
      if (failure.fieldErrors.password) fields.password = failure.fieldErrors.password;
      setErrors(fields);
      if (Object.keys(fields).length === 0) setFormError(failure.message);
      setBusy(false);
      return;
    }

    // The account exists (or the address was already taken — the answer is the same, and
    // that is the point). Now the one place a session is created.
    let signin;
    try {
      signin = await api.POST("/api/auth/signin", { body: { email: address, password } });
    } catch (thrown) {
      // The account may well exist now; only the sign-in failed to go out. Saying so and
      // re-enabling the form is better than a button stuck on "Creating account…".
      setFormError(readApiError(thrown).message);
      setBusy(false);
      return;
    }
    if (signin.error) {
      setFormError(readApiError(signin.error).message);
      setBusy(false);
      return;
    }

    setCreated(true);
    // The post-signup routing lock: email/password sign-up always goes to `/onboarding`
    // step 1, never straight to `/`.
    timer.current = setTimeout(
      () => {
        router.replace("/onboarding");
        router.refresh();
      },
      prefersReducedMotion() ? 0 : SUCCESS_HOLD_MS,
    );
  };

  if (created) {
    return (
      <p role="status" className="[font:var(--type-scale-body-md)] text-ink-secondary">
        Account created. Taking you to onboarding…
      </p>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-6">
      {/*
        The OIDC provider stack's position (`Component.Auth.SignUp`, zone 1): three
        equal-weight provider buttons and the "or" separator go here, above the
        email/password form, when a later intent wires them to a real handshake. Nothing
        renders now — a button that cannot sign anyone in, or one labelled "coming soon"
        under a promise to "auto-connect your calendar", would be a dead affordance this
        item's criteria forbid.
      */}

      {formError ? <FormAlert message={formError} /> : null}

      <AuthTextInput
        id="signup-email"
        name="email"
        label="Email"
        type="email"
        value={email}
        autoComplete="email"
        placeholder="you@example.com"
        error={errors.email}
        readOnly={busy}
        onChange={(value) => {
          setEmail(value);
          if (errors.email) setErrors((current) => ({ ...current, email: undefined }));
        }}
        onBlur={() => {
          if (email.trim() !== "" && !isEmailLike(email)) {
            setErrors((current) => ({ ...current, email: EMAIL_INVALID }));
          }
        }}
      />

      <PasswordInput
        id="signup-password"
        name="password"
        label="Password"
        value={password}
        autoComplete="new-password"
        placeholder="At least 8 characters"
        hint="8 characters minimum"
        error={errors.password}
        readOnly={busy}
        onChange={(value) => {
          setPassword(value);
          if (errors.password) setErrors((current) => ({ ...current, password: undefined }));
        }}
      />

      <PasswordInput
        id="signup-password-confirm"
        name="password_confirm"
        label="Confirm password"
        value={confirm}
        autoComplete="new-password"
        placeholder="Re-enter your password"
        error={errors.confirm}
        readOnly={busy}
        onChange={(value) => {
          setConfirm(value);
          if (errors.confirm) setErrors((current) => ({ ...current, confirm: undefined }));
        }}
        onBlur={() => {
          // The cross-field check fires on Confirm's blur as well as on submit.
          if (confirm !== "" && confirm !== password) {
            setErrors((current) => ({ ...current, confirm: PASSWORDS_DONT_MATCH }));
          }
        }}
      />

      <div className="flex justify-end">
        <SubmitButton label="Create account" busyLabel="Creating account…" busy={busy} />
      </div>

      <div className="border-t border-border-subtle pt-6 text-center">
        <p className="[font:var(--type-scale-body-sm)] text-ink-secondary">
          Already have an account?{" "}
          <Link href="/signin" className="text-accent-terracotta underline underline-offset-4">
            Sign in →
          </Link>
        </p>
        <p className="mt-2 [font:var(--type-scale-body-sm)] text-ink-muted">
          By creating an account, you agree to our{" "}
          <Link href="/terms" className="underline underline-offset-4">
            Terms
          </Link>{" "}
          and{" "}
          <Link href="/privacy" className="underline underline-offset-4">
            Privacy Policy
          </Link>
          .
        </p>
      </div>
    </form>
  );
}
