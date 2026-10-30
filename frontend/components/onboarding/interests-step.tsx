"use client";

/**
 * Step 2 — the interest chips (FR-1).
 *
 * **The chips come from the API.** `GET /api/personal/onboarding/interest-chips` projects
 * `shared/constants.py`'s `INTEREST_CHIPS`, which is the one copy of the ten. The step-2
 * mockup draws twelve, including "Music" and "Food & dining", which are not in that set —
 * the intent brief locks the ten, and a hard-coded list here would be a second copy that
 * drifts. The chip's **key** is what is sent and stored; the label is display only, so a
 * renamed label never orphans a stored pick.
 *
 * **Three picks is the cap.** The API refuses a fourth (`TooManyInterestsError`), and the
 * UI stops it earlier: at three, the unpicked chips are disabled and a line says why.
 * Both halves matter — the UI prevents a mistake, the API prevents a client.
 *
 * Zero picks is a perfectly good answer and is sent as an empty list, which is also what
 * skipping the step writes.
 */

import { useState } from "react";

import type { components } from "@/lib/api/schema";

type Chip = components["schemas"]["InterestChipOut"];

/** FR-1: "up to 3 picks". The server's `MAX_INTEREST_PICKS`. */
export const MAX_PICKS = 3;

/**
 * The picks after toggling `key`, with the cap applied.
 *
 * It is a pure function and it is exported because it is the **rule**, while the chips'
 * `disabled` attribute is only its appearance. A disabled button cannot be clicked, so
 * driving the cap through the UI can never exercise the rule itself — the two are tested
 * separately on purpose, and both have to hold: the attribute stops a mouse, the rule
 * stops everything else (a keyboard, an extension, a future chip that forgets to disable).
 */
export function nextSelection(selected: string[], key: string): string[] {
  if (selected.includes(key)) return selected.filter((candidate) => candidate !== key);
  if (selected.length >= MAX_PICKS) return selected;
  return [...selected, key];
}

export type InterestsStepProps = {
  chips: Chip[];
  /** The user's stored picks, so returning to the step shows them. */
  picked: string[];
  onChange: (keys: string[]) => void;
};

export function InterestsStep({ chips, picked, onChange }: InterestsStepProps) {
  const [selected, setSelected] = useState<string[]>(picked);
  const full = selected.length >= MAX_PICKS;

  const toggle = (key: string): void => {
    const next = nextSelection(selected, key);
    setSelected(next);
    onChange(next);
  };

  if (chips.length === 0) {
    // The chips could not be read. The step is optional, so this is not an error page —
    // the user can skip or continue, and nothing is lost.
    return (
      <p className="[font:var(--type-scale-body-md)] text-ink-muted">
        We couldn&apos;t load the interests just now. Skip this step — you can pick them later in
        Settings.
      </p>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {chips.map((chip) => {
          const isSelected = selected.includes(chip.key);
          const blocked = full && !isSelected;
          return (
            <button
              key={chip.key}
              type="button"
              aria-pressed={isSelected}
              disabled={blocked}
              aria-disabled={blocked}
              onClick={() => toggle(chip.key)}
              className={[
                "rounded-control border px-4 py-2 [font:var(--type-scale-meta-md)]",
                isSelected
                  ? "border-accent-terracotta text-ink-primary"
                  : "border-border-subtle text-ink-secondary",
                blocked ? "opacity-50" : "",
              ].join(" ")}
            >
              {isSelected ? <span aria-hidden="true">✓ </span> : null}
              {chip.label}
            </button>
          );
        })}
      </div>

      {full ? (
        <p role="status" className="mt-4 [font:var(--type-scale-body-sm)] text-ink-muted">
          That&apos;s three — unpick one to change it.
        </p>
      ) : null}
    </div>
  );
}

/** The count shown beside the step label, e.g. "2 of 3 picked". */
export function pickedNote(count: number): string {
  return `${count} of ${MAX_PICKS} picked`;
}
