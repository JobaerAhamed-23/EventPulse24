"use client";

/**
 * The auth forms' field vocabulary: a labelled input, its hint, and its error row.
 *
 * It is the same shape as `components/sheets/personal-event-form.tsx`'s `Field` — the
 * label is tied to the control by `htmlFor`, the error is tied by `aria-describedby`, and
 * the control carries `aria-invalid`. The difference is the **colour**: an auth
 * validation error renders in `color.signal.warn` with a `⚠` glyph, not in
 * `color.signal.error`. `EXPERIENCE.md` reserves the error red for destructive actions,
 * and a mistyped password is not one.
 *
 * The error row is `role="alert"`, so it is announced when it appears.
 */

import { useState } from "react";

export type AuthFieldProps = {
  label: string;
  /** The control's `id`: the label's `htmlFor` and the error's `aria-describedby` target. */
  id: string;
  /** The API's or the form's message for this field. Shown verbatim. */
  error?: string;
  /** A standing hint, shown when there is no error to show instead. */
  hint?: string;
  children: React.ReactNode;
};

export function AuthField({ label, id, error, hint, children }: AuthFieldProps) {
  return (
    <div>
      <label
        htmlFor={id}
        className="mb-2 block text-[12px] font-semibold tracking-[0.06em] text-ink-secondary uppercase"
      >
        {label}
      </label>
      {children}
      {error ? (
        <p
          id={`${id}-error`}
          role="alert"
          className="mt-2 flex items-start gap-2 [font:var(--type-scale-body-sm)] text-signal-warn"
        >
          <span aria-hidden="true">⚠</span>
          <span>{error}</span>
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-2 [font:var(--type-scale-body-sm)] text-ink-faint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** The classes every auth input shares, so one border rule covers them all. */
function inputClassName(invalid: boolean): string {
  return [
    "w-full rounded-control border bg-surface-subtle px-3 py-2 [font:var(--type-scale-body-md)]",
    invalid ? "border-signal-warn" : "border-border-subtle",
  ].join(" ");
}

export type AuthTextInputProps = {
  id: string;
  name: string;
  type?: "email" | "text";
  value: string;
  autoComplete?: string;
  placeholder?: string;
  error?: string;
  hint?: string;
  readOnly?: boolean;
  onChange: (value: string) => void;
  onBlur?: () => void;
};

/** A plain labelled text input, wired to its error. */
export function AuthTextInput({
  id,
  name,
  type = "text",
  value,
  autoComplete,
  placeholder,
  error,
  hint,
  readOnly = false,
  onChange,
  onBlur,
  label,
}: AuthTextInputProps & { label: string }) {
  return (
    <AuthField label={label} id={id} error={error} hint={hint}>
      <input
        id={id}
        name={name}
        type={type}
        value={value}
        autoComplete={autoComplete}
        placeholder={placeholder}
        readOnly={readOnly}
        spellCheck={false}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        className={inputClassName(Boolean(error))}
      />
    </AuthField>
  );
}

export type PasswordInputProps = {
  id: string;
  name: string;
  label: string;
  value: string;
  autoComplete: string;
  placeholder?: string;
  error?: string;
  hint?: string;
  readOnly?: boolean;
  onChange: (value: string) => void;
  onBlur?: () => void;
};

/**
 * `component.auth.input.password` — a password field with the reveal toggle.
 *
 * The toggle's `aria-pressed` reflects the current state, and its **label names what
 * tapping will do** ("Show password" / "Hide password") rather than what is true now.
 * `EXPERIENCE.md` is specific about this: a screen-reader user does not need to hear the
 * current state every time the toggle takes focus — they need to know what the control
 * does.
 */
export function PasswordInput({
  id,
  name,
  label,
  value,
  autoComplete,
  placeholder,
  error,
  hint,
  readOnly = false,
  onChange,
  onBlur,
}: PasswordInputProps) {
  const [revealed, setRevealed] = useState(false);

  return (
    <AuthField label={label} id={id} error={error} hint={hint}>
      <div className="flex items-stretch gap-2">
        <input
          id={id}
          name={name}
          type={revealed ? "text" : "password"}
          value={value}
          autoComplete={autoComplete}
          placeholder={placeholder}
          readOnly={readOnly}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
          onChange={(event) => onChange(event.target.value)}
          onBlur={onBlur}
          className={inputClassName(Boolean(error))}
        />
        <button
          type="button"
          aria-pressed={revealed}
          aria-label={revealed ? "Hide password" : "Show password"}
          onClick={() => setRevealed((current) => !current)}
          className="rounded-control border border-border-subtle px-3 [font:var(--type-scale-meta-sm)] text-ink-secondary"
        >
          {revealed ? "Hide" : "Show"}
        </button>
      </div>
    </AuthField>
  );
}
