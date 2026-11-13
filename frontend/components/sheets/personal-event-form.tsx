"use client";

/**
 * `Sheet.PersonalEventCreate` and `Sheet.PersonalEventEdit` — one form, two modes.
 *
 * The create and edit sheets share the same field vocabulary, so they share one component.
 * The edit mode is the create mode with a different heading, pre-filled values, and a
 * different submit.
 *
 * **The timezone is a first-class required field.** The API takes `start_time_utc` as an
 * absolute instant and `start_time_tz` as the zone the event is displayed in, so the
 * browser converts the local date and time into that instant. A floating local time is a
 * time the backend would have to guess at, and AD-6 says it is refused rather than guessed.
 */
import { useId, useState } from "react";

import { ZONE_CHOICES, browserZone, localToUtcInstant, toApiInstant } from "@/lib/timezones";

import { Sheet } from "./sheet";

/** The form's own state — every field, as the user typed it. */
export type PersonalEventFormValues = {
  name: string;
  date: string;
  time: string;
  timezone: string;
  endDate: string;
  endTime: string;
  location: string;
  notes: string;
};

export type PersonalEventFormProps = {
  /** Whether the sheet is open. */
  open: boolean;
  /** Create or edit. */
  mode: "create" | "edit";
  /** The values to start from. In create mode these are the defaults. */
  initial?: Partial<PersonalEventFormValues>;
  /**
   * Whether the start time is the field to change.
   *
   * The conflict prompt's "Edit the new one" opens the event with the conflicting time
   * pre-highlighted (FR-58). The form does not guess: this is a prop, set only by the
   * conflict flow.
   */
  highlightStartTime?: boolean;
  /** Called when the sheet closes without saving. */
  onClose: () => void;
  /**
   * Called when the user confirms the deletion of the event being edited.
   *
   * **Given only in edit mode, and only by a caller that can delete.** A create has no
   * event to delete, and the danger zone is rendered only when this is given — so a
   * caller that cannot delete shows no control that would fail if pressed, rather than
   * one that is merely disabled.
   */
  onDelete?: () => void;
  /** Called with the API's body when the form is submitted. */
  onSubmit: (body: {
    name: string;
    start_time_utc: string;
    start_time_tz: string;
    end_time_utc: string | null;
    location: string | null;
    notes: string | null;
  }) => void;
};

/** The empty form's defaults: today, an hour from now, in the browser's own zone. */
function defaultValues(): PersonalEventFormValues {
  const zone = browserZone() ?? "UTC";
  const now = new Date(Date.now() + 60 * 60 * 1000);
  const shown = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  })
    .format(now)
    .split(", ");
  return {
    name: "",
    date: shown[0] ?? "",
    time: shown[1] ?? "",
    timezone: zone,
    endDate: "",
    endTime: "",
    location: "",
    notes: "",
  };
}

export function PersonalEventForm({
  open,
  mode,
  initial,
  highlightStartTime = false,
  onClose,
  onSubmit,
  onDelete,
}: PersonalEventFormProps) {
  // **The field ids are per instance.** The sheet is mounted by the sidenav, the
  // bottom-tab bar, the digest header's quick-add and the personal-events list, so one
  // page carries four of these forms. Fixed ids repeated four times made every label point
  // at the *first* form's input, inside a closed dialog: clicking "Name" did nothing, and a
  // screen reader paired the open form's fields with another form's labels.
  const uid = useId();
  const fieldId = (name: string): string => `${uid}-${name}`;

  // The form's state is seeded **once**, from the caller's `initial`. Re-seeding it when
  // the sheet opens is React's `key` prop's job — the parent gives a fresh key per
  // opening, and the form is remounted with the new seed. Doing it here with an effect
  // would mean a cascading render on every open.
  const [values, setValues] = useState<PersonalEventFormValues>(() => ({
    ...defaultValues(),
    ...initial,
  }));
  const [errors, setErrors] = useState<Record<string, string>>({});
  // **The deletion is a two-step, like the conflict prompt's (FR-58).** The first press
  // asks; the deletion does not complete until the second one. The step is local to this
  // mount, and the parent gives a fresh key per opening, so a sheet reopened after a
  // cancelled deletion asks again from the start rather than reopening mid-question.
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  // **The name in the question is the event's stored name, not the field's.** The user
  // may have typed a new name they have not saved; "Delete 'X'?" must name the event as
  // it exists, which is the name the sheet was seeded with. `initial` is fixed for this
  // mount, so the question cannot drift as the form is typed into.
  const storedName = initial?.name?.trim() ?? "";

  const set =
    (field: keyof PersonalEventFormValues) =>
    (
      event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
    ): void => {
      setValues((current) => ({ ...current, [field]: event.target.value }));
    };

  const submit = (event: React.FormEvent): void => {
    event.preventDefault();
    const found: Record<string, string> = {};

    if (!values.name.trim()) found.name = "Give the event a name.";
    if (!values.date) found.date = "Pick a date.";
    if (!values.time) found.time = "Pick a start time.";
    if (!values.timezone) found.timezone = "Pick a timezone.";

    let startUtc: string | null = null;
    if (!found.timezone && values.date && values.time) {
      const instant = localToUtcInstant({ date: values.date, time: values.time }, values.timezone);
      if (!instant) {
        found.time = "That time doesn't exist in this timezone. Pick another.";
      } else {
        startUtc = toApiInstant(instant);
      }
    }

    let endUtc: string | null = null;
    if (values.endDate && values.endTime) {
      const instant = localToUtcInstant(
        { date: values.endDate, time: values.endTime },
        values.timezone,
      );
      if (!instant) {
        found.endTime = "That time doesn't exist in this timezone. Pick another.";
      } else {
        endUtc = toApiInstant(instant);
      }
    } else if (values.endDate || values.endTime) {
      found.endTime = "Give both an end date and an end time.";
    }

    setErrors(found);
    if (Object.keys(found).length > 0 || !startUtc) return;

    onSubmit({
      name: values.name.trim(),
      start_time_utc: startUtc,
      start_time_tz: values.timezone,
      end_time_utc: endUtc,
      location: values.location.trim() || null,
      notes: values.notes.trim() || null,
    });
  };

  return (
    <Sheet
      open={open}
      dismissible
      onClose={onClose}
      label={mode === "create" ? "Add personal event" : "Edit personal event"}
      className="max-w-(--layout-container-form)"
    >
      <form onSubmit={submit}>
        <div className="flex items-start justify-between gap-4 border-b border-border-subtle px-6 py-6">
          <div>
            <h2 className="[font:var(--type-scale-headline-lg)]">
              {mode === "create" ? "Add personal event" : "Edit personal event"}
            </h2>
            <p className="mt-1 [font:var(--type-scale-body-sm)] text-ink-muted">
              {mode === "create"
                ? "Personal events appear alongside public ones on your timeline."
                : "Change what you need. The conflict check runs again when you save."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-control px-2 py-1 text-ink-muted"
          >
            ✕
          </button>
        </div>

        <div className="flex flex-col gap-4 px-6 py-6">
          <Field label="Name" id={fieldId("name")} error={errors.name} required>
            <input
              id={fieldId("name")}
              name="name"
              value={values.name}
              onChange={set("name")}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={errors.name ? fieldId("name-error") : undefined}
              className="w-full rounded-control border border-border-subtle bg-surface-subtle px-3 py-2"
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Date" id={fieldId("date")} error={errors.date} required>
              <input
                id={fieldId("date")}
                name="date"
                type="date"
                value={values.date}
                onChange={set("date")}
                aria-invalid={Boolean(errors.date)}
                aria-describedby={errors.date ? fieldId("date-error") : undefined}
                className="w-full rounded-control border border-border-subtle bg-surface-subtle px-3 py-2"
              />
            </Field>
            <Field
              label="Start time"
              id={fieldId("time")}
              error={errors.time}
              required
              highlighted={highlightStartTime}
              hint={
                highlightStartTime
                  ? "This is the time that overlaps. Shift it to fix it."
                  : undefined
              }
            >
              <input
                id={fieldId("time")}
                name="time"
                type="time"
                value={values.time}
                onChange={set("time")}
                aria-invalid={Boolean(errors.time)}
                aria-describedby={errors.time ? fieldId("time-error") : undefined}
                className="w-full rounded-control border border-border-subtle bg-surface-subtle px-3 py-2"
              />
            </Field>
          </div>

          <Field
            label="Timezone"
            id={fieldId("timezone")}
            error={errors.timezone}
            required
            hint="The event's own timezone. It is not guessed from your browser."
          >
            <select
              id={fieldId("timezone")}
              name="timezone"
              value={values.timezone}
              onChange={set("timezone")}
              aria-invalid={Boolean(errors.timezone)}
              aria-describedby={errors.timezone ? fieldId("timezone-error") : undefined}
              className="w-full rounded-control border border-border-subtle bg-surface-subtle px-3 py-2"
            >
              <option value="">Choose a timezone</option>
              {ZONE_CHOICES.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.value} — {choice.label}
                </option>
              ))}
            </select>
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="End date" id={fieldId("end-date")} error={errors.endDate}>
              <input
                id={fieldId("end-date")}
                name="end_date"
                type="date"
                value={values.endDate}
                onChange={set("endDate")}
                aria-invalid={Boolean(errors.endDate)}
                aria-describedby={errors.endDate ? fieldId("end-date-error") : undefined}
                className="w-full rounded-control border border-border-subtle bg-surface-subtle px-3 py-2"
              />
            </Field>
            <Field
              label="End time"
              id={fieldId("end-time")}
              error={errors.endTime}
              hint="Optional."
            >
              <input
                id={fieldId("end-time")}
                name="end_time"
                type="time"
                value={values.endTime}
                onChange={set("endTime")}
                aria-invalid={Boolean(errors.endTime)}
                aria-describedby={errors.endTime ? fieldId("end-time-error") : undefined}
                className="w-full rounded-control border border-border-subtle bg-surface-subtle px-3 py-2"
              />
            </Field>
          </div>

          <Field label="Location" id={fieldId("location")} hint="Optional.">
            <input
              id={fieldId("location")}
              name="location"
              value={values.location}
              onChange={set("location")}
              className="w-full rounded-control border border-border-subtle bg-surface-subtle px-3 py-2"
            />
          </Field>

          <Field label="Notes" id={fieldId("notes")} hint="Optional.">
            <textarea
              id={fieldId("notes")}
              name="notes"
              value={values.notes}
              onChange={set("notes")}
              className="w-full rounded-control border border-border-subtle bg-surface-subtle px-3 py-2"
            />
          </Field>
          {mode === "edit" && onDelete ? (
            <DangerZone
              eventName={storedName}
              confirming={confirmingDelete}
              onAsk={() => setConfirmingDelete(true)}
              onCancel={() => setConfirmingDelete(false)}
              onConfirm={onDelete}
            />
          ) : null}
        </div>

        <div className="flex justify-end gap-3 border-t border-border-subtle px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-control border border-border-subtle px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="rounded-control bg-accent-terracotta px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-inverse"
          >
            {mode === "create" ? "Save to my Pulse" : "Save event"}
          </button>
        </div>
      </form>
    </Sheet>
  );
}

/**
 * The edit sheet's danger zone — "Delete this event" (FR-18, `personal-event-edit-desktop.html`).
 *
 * **The deletion is confirmed before it completes**, the rule FR-58 states for the
 * conflict prompt's delete and which holds here for the same reason: the event and its
 * reminders are gone, and nothing restores them. The first press replaces the zone with
 * the question rather than opening a second dialog over the sheet — a dialog inside a
 * dialog has two Escape targets and the wrong one closes the whole sheet.
 *
 * **Every button here is `type="button"`.** The zone sits inside the sheet's `<form>`,
 * where a button with no type is a submit button — pressing "Delete event" would have
 * saved the event instead of asking about deleting it.
 */
function DangerZone({
  eventName,
  confirming,
  onAsk,
  onCancel,
  onConfirm,
}: {
  /** The event's stored name, used in the question. */
  eventName: string;
  confirming: boolean;
  onAsk: () => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  // The name is part of a sentence, so an unnamed event needs a phrase that still reads
  // as one. It is the seeded name that is missing here, not the user's input.
  const subject = eventName || "this event";
  return (
    <div className="rounded-card border border-accent-terracotta/20 bg-accent-terracotta/5 p-4">
      {confirming ? (
        <>
          <p className="[font:var(--type-scale-body-md)]">Delete “{subject}”?</p>
          <p className="mt-1 [font:var(--type-scale-body-sm)] text-ink-muted">
            This can&apos;t be undone.
          </p>
          <div className="mt-4 flex gap-3">
            <button
              type="button"
              onClick={onConfirm}
              aria-label={`Delete ${subject}. This cannot be undone.`}
              className="rounded-control bg-accent-terracotta px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-inverse"
            >
              Delete it
            </button>
            <button
              type="button"
              onClick={onCancel}
              aria-label={`Keep ${subject}. The event is not deleted.`}
              className="rounded-control border border-border-subtle px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
            >
              Keep it
            </button>
          </div>
        </>
      ) : (
        <>
          <h3 className="[font:var(--type-scale-meta-md)] text-accent-terracotta">
            Delete this event
          </h3>
          <p className="mt-1 [font:var(--type-scale-body-sm)] text-ink-muted">
            Permanently removes the event and any reminders. Pulse Ping history won&apos;t
            reference it again. This cannot be undone.
          </p>
          <button
            type="button"
            onClick={onAsk}
            className="mt-3 [font:var(--type-scale-meta-md)] text-accent-terracotta underline-offset-[3px] hover:underline"
          >
            Delete event →
          </button>
        </>
      )}
    </div>
  );
}

/**
 * One labelled field, with its required marker, its error and its hint.
 *
 * **The label is associated with the control by `htmlFor`.** The control's `id` is the
 * field's identity in the document — the error message points at it with
 * `aria-describedby`, and the label points at it with `htmlFor`. A `<label>` that merely
 * *wraps* the control announces the name but does not make the name a queryable
 * accessible name, and the click-the-label-to-focus affordance disappears.
 *
 * The hint is rendered **once**. When the field is the pre-highlighted one (the conflict
 * flow's "edit the new one"), the same hint is shown in the amber tone rather than in the
 * muted one — a second copy of it would be the same sentence said twice.
 */
function Field({
  label,
  id,
  error,
  hint,
  required = false,
  highlighted = false,
  children,
}: {
  label: string;
  /** The control's `id` — the label's `htmlFor` and the error's `aria-describedby` target. */
  id: string;
  error?: string;
  hint?: string;
  required?: boolean;
  highlighted?: boolean;
  children: React.ReactNode;
}) {
  const errorId = `${id}-error`;
  return (
    <div>
      <label htmlFor={id} className="mb-2 flex items-baseline justify-between gap-2">
        <span className="text-[12px] font-semibold tracking-[0.06em] text-ink-secondary uppercase">
          {label}
        </span>
        {required ? <span className="text-[11px] text-accent-terracotta">required</span> : null}
      </label>
      {children}
      {error ? (
        <p id={errorId} className="mt-1 [font:var(--type-scale-body-sm)] text-signal-error">
          {error}
        </p>
      ) : hint ? (
        <p
          className={[
            "mt-1 [font:var(--type-scale-body-sm)]",
            highlighted ? "text-warn-amber" : "text-ink-muted",
          ].join(" ")}
        >
          {hint}
        </p>
      ) : null}
    </div>
  );
}
