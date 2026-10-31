"use client";

/**
 * `Sheet.ConflictResolution` — the forced three-action conflict prompt (FR-58).
 *
 * **There is no dismiss.** No X, no Escape, no backdrop click. The user must choose one of
 * the three, because a conflict that can be closed without being answered is exactly the
 * missed double-booking the prompt exists to prevent.
 *
 * **The three actions are rendered from the server's own closed set.** The 409 carries
 * `actions: string[]` — the resolutions this conflict's kind allows — and the sheet maps
 * them to their labels. It cannot offer a resolution the pair's kind does not allow,
 * because it never decides what the choices are.
 *
 * **Two surfaces, one prompt, one vocabulary.** This sheet is used by two callers:
 *
 *   - the **personal-events panel**, where the user has just created a personal event and
 *     the pair's other side is something they had already saved. Its labels are
 *     **relative**: "Edit the new one", "Update the existing one", "Skip the public
 *     event";
 *   - the **Detail Screen**, where the user has just saved a public event and the pair's
 *     other side is one of their own. Its labels **name the event the action is about**:
 *     "Move Work standup", "Skip Designers coffee chat".
 *
 * **The prompt cannot be relative on the Detail Screen**, because the thing the user
 * "just did" there is *saving* — and "Edit the new one" would name an event the user
 * never created and cannot edit. So the sheet takes a `wording` prop, and the two
 * vocabularies are built from the same module (`lib/conflict-wording.ts`) — the action
 * set is shared, and only the visible label is contextual.
 *
 * The copy is the UX spine's, verbatim, and the voice is calm: no exclamation marks, no
 * alarm words. The header glyph is the amber circle — **never red**.
 */
import { useEffect, useRef, useState } from "react";

import type { components } from "@/lib/api/schema";
import {
  asResolution,
  RESOLUTION_ARIA,
  RESOLUTION_GLYPHS,
  RESOLUTION_HINTS,
  RESOLUTION_LABELS,
  reviewActionAria,
  reviewActionLabel,
  type Resolution,
} from "@/lib/conflict-wording";

import { Sheet } from "./sheet";

type Conflict = components["schemas"]["ConflictOut"];
type ConflictSide = components["schemas"]["ConflictSideOut"];

/**
 * Which vocabulary the prompt speaks.
 *
 * - `relative` — the personal-events panel. The labels say "the new one" and "the
 *   existing one", because the prompt knows which is which.
 * - `named` — the Detail Screen. The labels say the **event's name**, because the
 *   surface knows the event the user is looking at and the pair's other side may be
 *   either kind.
 */
export type ConflictWording = "relative" | "named";

export type ConflictResolutionProps = {
  /** Whether the sheet is open. */
  open: boolean;
  /**
   * The conflict to answer.
   *
   * `null` means there is nothing to answer and the sheet stays closed — the state after
   * the choice has been recorded.
   */
  conflict: Conflict | null;
  /** The event the user just created — the prompt's "new" side. */
  newEvent: { id: string; name: string; start_time_utc: string } | null;
  /**
   * The user's choice.
   *
   * **The choice is the resolution, and the pair it is about.** The side the action
   * acts on is the caller's to work out — from the pair's kinds — and the pair travels
   * with the choice so the caller does not have to hold a second copy of it and risk
   * answering a different pair from the one on screen. The personal-events panel names
   * the personal side; the Detail Screen names the saved side for "skip" and the
   * personal side for the rest.
   */
  onResolve: (resolution: Resolution, conflict: Conflict) => void;
  /** Called when the sheet closes without a choice — impossible for a forced sheet. */
  onClose?: () => void;
  /**
   * Which vocabulary the prompt speaks. Defaults to `relative`, the panel's.
   */
  wording?: ConflictWording;
  /**
   * The name of the side each action acts on, for the `named` vocabulary.
   *
   * **A map from resolution to the event's name.** "Skip" is about the saved side and
   * "Move" is about the personal one, so the caller works that out — it is the caller
   * that knows which side is which — and the sheet just renders it.
   */
  subjects?: Partial<Record<Resolution, string | null>>;
};

/**
 * The two headers the spine names.
 *
 * **The prompt's headers are relative to a prompt** — "This overlaps with another
 * event." for a clash in time, "These overlap." for a duplicate. The review screen's
 * heading is its own ("These days overlap."), and it is not derived from these: it is
 * about the page, not about one pair.
 */
const HEADER_BY_KIND: Record<string, string> = {
  time: "This overlaps with another event.",
  duplicate: "These overlap.",
};

export function ConflictResolution({
  open,
  conflict,
  newEvent,
  onResolve,
  onClose,
  wording = "relative",
  subjects,
}: ConflictResolutionProps) {
  const headerRef = useRef<HTMLHeadingElement>(null);

  // Focus moves to the header when the prompt opens, so a screen reader lands on the
  // question rather than on the first button.
  useEffect(() => {
    if (open) headerRef.current?.focus();
  }, [open]);

  if (!conflict || !newEvent) return null;

  // The two sides, read from the conflict itself. `other_side` is the event that was
  // already saved; the "new" side is the event the client just created, which the
  // conflict does not carry (the pair row is symmetric — the client knows which side is
  // new).
  const other = conflict.other_side;
  const actions = conflict.actions;
  const header = HEADER_BY_KIND[conflict.kind] ?? HEADER_BY_KIND.time;

  return (
    <Sheet open={open} dismissible={false} onClose={() => onClose?.()} label="Schedule conflict">
      <div className="px-6 pt-6 pb-4 text-center">
        <div
          aria-hidden="true"
          className="mx-auto flex size-12 items-center justify-center rounded-full bg-warn-amber/15 text-xl text-warn-amber"
        >
          !
        </div>
        <h2
          ref={headerRef}
          tabIndex={-1}
          className="mt-3 [font:var(--type-scale-headline-lg)] outline-none"
        >
          {header}
        </h2>
        <p className="mx-auto mt-2 max-w-(--layout-container-reading) [font:var(--type-scale-body-sm)] text-ink-secondary">
          {wording === "relative"
            ? `You've already saved ${other.name}. Choose how to handle it.`
            : `It overlaps "${other.name}" on your calendar. Choose how to handle it.`}
        </p>
        {/* The announcement: assertive, because the prompt is a forced choice the user must
            not miss. The text is the same calm copy the header uses. */}
        <p aria-live="assertive" className="sr-only">
          Schedule conflict. Three choices.
        </p>
      </div>

      <div className="px-6 pb-4">
        <div className="grid gap-3 sm:grid-cols-2">
          {/*
            **The two cards say what each side is**, in the vocabulary of the surface.

            The personal-events panel's first side is one the user just **created**, so
            it is marked "NEW". The Detail Screen's first side is one the user just
            **saved** — they created nothing — so it is marked "Saved", and the other
            side, which is their own personal event, is marked "On your calendar". The
            badge is a fact about what the user did, so it cannot be the same badge on
            both surfaces.
          */}
          <ConflictCard
            when={
              wording === "relative"
                ? `New · ${formatWhen(newEvent.start_time_utc)}`
                : `Saved · ${formatWhen(newEvent.start_time_utc)}`
            }
            title={newEvent.name}
            isNew={wording === "relative"}
            isSaved={wording === "named"}
          />
          <ConflictCard
            when={
              wording === "relative"
                ? `Already saved · ${formatWhen(other.start_time_utc)}`
                : `On your calendar · ${formatWhen(other.start_time_utc)}`
            }
            title={other.name}
          />
        </div>
      </div>

      {/* The choices live in a child keyed by the pair, so a *different* conflict starts
          from the three choices rather than from a stale confirmation step — without an
          effect to reset anything. */}
      <ConflictChoices
        key={conflict.pair_id}
        actions={actions}
        newEventName={newEvent.name}
        wording={wording}
        subjects={subjects}
        conflict={conflict}
        onResolve={onResolve}
      />
    </Sheet>
  );
}

/**
 * The three choices, or — once "Delete the new one" is chosen — the confirmation step.
 *
 * The confirmation is a step **inside** this sheet, not a second overlay: one sheet, one
 * overlay level, and the prompt stays open while the user decides (FR-58).
 */
function ConflictChoices({
  actions,
  newEventName,
  wording,
  subjects,
  conflict,
  onResolve,
}: {
  actions: string[];
  newEventName: string;
  wording: ConflictWording;
  subjects: Partial<Record<Resolution, string | null>> | undefined;
  conflict: Conflict;
  onResolve: (resolution: Resolution, conflict: Conflict) => void;
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const choose = (resolution: Resolution): void => {
    if (resolution === "delete_new") {
      // FR-58: the deletion does not complete until the user confirms it.
      setConfirmingDelete(true);
      return;
    }
    onResolve(resolution, conflict);
  };

  if (confirmingDelete) {
    return (
      <div className="px-6 pb-6">
        <p className="[font:var(--type-scale-body-md)]">Delete “{newEventName}”?</p>
        <p className="mt-1 [font:var(--type-scale-body-sm)] text-ink-secondary">
          This can&apos;t be undone.
        </p>
        <div className="mt-4 flex gap-3">
          <button
            type="button"
            onClick={() => onResolve("delete_new", conflict)}
            aria-label={`Delete ${newEventName}. This cannot be undone.`}
            className="rounded-control bg-accent-terracotta px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-inverse"
          >
            Delete it
          </button>
          <button
            type="button"
            onClick={() => setConfirmingDelete(false)}
            aria-label="Keep the new event. The three choices are shown again."
            className="rounded-control border border-border-subtle px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
          >
            Keep it
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-6 pb-6">
      <div role="group" aria-label="Conflict resolution" className="flex flex-col gap-2">
        {actions.map((action) => {
          const resolution = asResolution(action);
          if (!resolution) return null;
          // **The two vocabularies.** The relative one says "the new one"; the named one
          // says the event's name. Both come from `lib/conflict-wording.ts`, so the two
          // surfaces cannot describe the same action differently.
          const named = wording === "named";
          const subject = subjects?.[resolution] ?? null;
          const label = named
            ? reviewActionLabel(resolution, subject)
            : RESOLUTION_LABELS[resolution];
          const aria = named ? reviewActionAria(resolution, subject) : RESOLUTION_ARIA[resolution];
          return (
            <button
              key={resolution}
              type="button"
              onClick={() => choose(resolution)}
              aria-label={aria}
              className="flex w-full items-start gap-3 rounded-timeline-cell border border-border-subtle bg-surface-paper p-4 text-left"
            >
              <span
                aria-hidden="true"
                className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-inset text-sm text-ink-secondary"
              >
                {RESOLUTION_GLYPHS[resolution] ?? "•"}
              </span>
              <span>
                <span className="block [font:var(--type-scale-meta-md)]">{label}</span>
                <span className="mt-1 block [font:var(--type-scale-body-sm)] text-ink-muted">
                  {RESOLUTION_HINTS[resolution]}
                </span>
              </span>
            </button>
          );
        })}
      </div>
      <p className="mt-4 text-center [font:var(--type-scale-body-sm)] text-ink-muted">
        No dismiss button — conflict must be resolved before continuing.
      </p>
    </div>
  );
}

/**
 * One of the two affected events, as a small card with the amber conflict dot.
 *
 * The dot is a **filled circle** in `--color-warn-amber`, top-right, carrying its own
 * `aria-label`. It is never red, and it is never `--color-signal-warn` — that is a
 * different token with a different job. Distinctness from the source badge and the
 * confidence pulse is by **shape and position**, not colour.
 */
function ConflictCard({
  when,
  title,
  isNew = false,
  isSaved = false,
}: {
  when: string;
  title: string;
  isNew?: boolean;
  isSaved?: boolean;
}) {
  return (
    <div
      className={[
        "relative rounded-timeline-cell border p-4",
        isNew || isSaved
          ? "border-accent-terracotta bg-accent-terracotta/6"
          : "border-border-subtle bg-surface-subtle",
      ].join(" ")}
    >
      {isNew ? (
        <span className="absolute -top-2 left-3 rounded-subtle border border-accent-terracotta/30 bg-surface-elevated px-2 text-[9px] font-bold tracking-[0.1em] text-accent-terracotta">
          NEW
        </span>
      ) : null}
      {isSaved ? (
        <span className="absolute -top-2 left-3 rounded-subtle border border-accent-terracotta/30 bg-surface-elevated px-2 text-[9px] font-bold tracking-[0.1em] text-accent-terracotta">
          SAVED
        </span>
      ) : null}
      <span
        role="img"
        aria-label="Schedule conflict"
        className="absolute top-3 right-3 size-[6px] rounded-full bg-warn-amber"
      />
      <p className="pr-6 text-[11px] font-semibold tracking-[0.04em] text-ink-muted uppercase">
        {when}
      </p>
      <p className="mt-2 [font:var(--type-scale-headline-sm)]">{title}</p>
    </div>
  );
}

/** The time of an instant, in the reader's own zone, as `Fri 7:00 PM`. */
function formatWhen(instant: string): string {
  const date = new Date(instant);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

/** Re-exported so the panel can type the conflict without importing the schema itself. */
export type { Conflict, ConflictSide };
