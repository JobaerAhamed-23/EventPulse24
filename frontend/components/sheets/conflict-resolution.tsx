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
 * The copy is the UX spine's, verbatim, and the voice is calm: no exclamation marks, no
 * alarm words. The header glyph is the amber circle — **never red**.
 */
import { useEffect, useRef, useState } from "react";

import type { components } from "@/lib/api/schema";

import { Sheet } from "./sheet";

type Conflict = components["schemas"]["ConflictOut"];
type ConflictSide = components["schemas"]["ConflictSideOut"];
/** The resolutions the API accepts. The prompt never offers one outside this set. */
type Resolution = components["schemas"]["ConflictResolutionIn"]["resolution"];

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
  /** The user's choice, or `null` while the prompt is open. */
  onResolve: (resolution: Resolution) => void;
  /** Called when the sheet closes without a choice — impossible for a forced sheet. */
  onClose?: () => void;
};

/** The three resolutions, and the label each kind gives the second one. */
const RESOLUTION_LABELS: Record<string, { label: string; hint: string; aria: string }> = {
  keep_both: {
    label: "Keep both — I'll manage",
    hint: "Both events stay on your timeline. A small amber dot on each reminds you they're close. We won't ask again.",
    aria: "Keep both events. The conflict indicator remains on both.",
  },
  edit_new: {
    label: "Edit the new one",
    hint: "Open the event in edit mode with the time pre-highlighted so you can shift it. Conflict re-checks automatically.",
    aria: "Edit the new event. Its start time is highlighted so you can move it.",
  },
  update_existing: {
    label: "Update the existing one",
    hint: "Open the event you already saved in edit mode so you can change it. Conflict re-checks automatically.",
    aria: "Update the existing event. Its details open in edit mode so you can change them.",
  },
  delete_new: {
    label: "Delete the new one",
    hint: "Removes the new event. You'll be asked to confirm before it's gone for good.",
    aria: "Delete the new event. You will be asked to confirm before it is removed.",
  },
  skip_public: {
    label: "Skip the public event",
    hint: "Releases your saved copy of the public event. Your own event stays exactly as it is.",
    aria: "Skip the public event. Your saved copy of it is released and your own event stays.",
  },
};

/** The glyph each action carries. Decorative — the label carries the meaning. */
const RESOLUTION_GLYPHS: Record<string, string> = {
  keep_both: "✓",
  edit_new: "✎",
  update_existing: "✎",
  delete_new: "✕",
  skip_public: "↷",
};

/**
 * Narrow a server-supplied action name to a resolution the API accepts.
 *
 * The contract types `actions` as the closed union the server owns. A name outside it is
 * one this sheet has no label for, so it is not offered — the sheet renders the server's
 * choices, and a choice it cannot explain is not a choice it offers.
 */
function asResolution(value: string): Resolution | null {
  return value === "keep_both" ||
    value === "edit_new" ||
    value === "update_existing" ||
    value === "delete_new" ||
    value === "skip_public"
    ? value
    : null;
}

/** The two headers the spine names. */
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
          You&apos;ve already saved {other.name}. Choose how to handle it.
        </p>
        {/* The announcement: assertive, because the prompt is a forced choice the user must
            not miss. The text is the same calm copy the header uses. */}
        <p aria-live="assertive" className="sr-only">
          Schedule conflict. Three choices.
        </p>
      </div>

      <div className="px-6 pb-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <ConflictCard
            when={`New · ${formatWhen(newEvent.start_time_utc)}`}
            title={newEvent.name}
            isNew
          />
          <ConflictCard
            when={`Already saved · ${formatWhen(other.start_time_utc)}`}
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
  onResolve,
}: {
  actions: string[];
  newEventName: string;
  onResolve: (resolution: Resolution) => void;
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const choose = (resolution: Resolution): void => {
    if (resolution === "delete_new") {
      // FR-58: the deletion does not complete until the user confirms it.
      setConfirmingDelete(true);
      return;
    }
    onResolve(resolution);
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
            onClick={() => onResolve("delete_new")}
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
          const copy = RESOLUTION_LABELS[resolution];
          return (
            <button
              key={resolution}
              type="button"
              onClick={() => choose(resolution)}
              aria-label={copy.aria}
              className="flex w-full items-start gap-3 rounded-timeline-cell border border-border-subtle bg-surface-paper p-4 text-left"
            >
              <span
                aria-hidden="true"
                className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-inset text-sm text-ink-secondary"
              >
                {RESOLUTION_GLYPHS[resolution] ?? "•"}
              </span>
              <span>
                <span className="block [font:var(--type-scale-meta-md)]">{copy.label}</span>
                <span className="mt-1 block [font:var(--type-scale-body-sm)] text-ink-muted">
                  {copy.hint}
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
}: {
  when: string;
  title: string;
  isNew?: boolean;
}) {
  return (
    <div
      className={[
        "relative rounded-timeline-cell border p-4",
        isNew
          ? "border-accent-terracotta bg-accent-terracotta/6"
          : "border-border-subtle bg-surface-subtle",
      ].join(" ")}
    >
      {isNew ? (
        <span className="absolute -top-2 left-3 rounded-subtle border border-accent-terracotta/30 bg-surface-elevated px-2 text-[9px] font-bold tracking-[0.1em] text-accent-terracotta">
          NEW
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
