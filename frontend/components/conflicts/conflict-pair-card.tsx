"use client";

import {
  actionSide,
  asResolution,
  movableSide,
  RESOLUTION_GLYPHS,
  RESOLUTION_HINTS,
  reviewActionAria,
  reviewActionLabel,
  type ConflictSide,
  type Resolution,
} from "@/lib/conflict-wording";
import type { ConflictPair } from "@/lib/conflict-list-read";

import { ConflictSideView } from "./conflict-side";

/**
 * One active conflict pair: the two sides side by side, and the actions.
 *
 * **Both sides are shown, always.** The pair row is symmetric — the server stores the
 * sides sorted by id, so neither one is "the new one" — so the card shows the user the
 * whole clash and lets the action name the one it acts on.
 *
 * **The actions are the server's, not the client's.** `pair.actions` is the allowed set
 * for this pair, computed from the same maps the resolve endpoint enforces, so the card
 * cannot offer a resolution this pair does not allow. A name outside the closed set
 * renders nothing — a choice the surface cannot explain is not a choice it offers.
 *
 * **Every action says which side it is about.** The request has to name the side
 * (`ConflictResolutionIn.side`) because the row cannot, so the button knows its target
 * before it is pressed, and its label names the event ("Move Work standup", "Skip
 * Designers coffee chat").
 */
export function ConflictPairCard({
  pair,
  busy,
  onChoose,
}: {
  pair: ConflictPair;
  /** The pair currently posting — its actions are disabled while the write is in flight. */
  busy: boolean;
  /**
   * The user's choice.
   *
   * The resolution and the side it acts on. The side is computed by the caller from the
   * pair's own kinds, because the pair row cannot say which side the user means.
   */
  onChoose: (resolution: Resolution, side: { kind: ConflictSide["kind"]; id: string }) => void;
}) {
  const actions = pair.actions
    .map((action) => asResolution(action))
    .filter((resolution): resolution is Resolution => resolution !== null);

  return (
    <article
      aria-label={`Conflict between ${sideTitle(pair.left)} and ${sideTitle(pair.right)}`}
      className="rounded-timeline-cell border border-border-subtle bg-surface-elevated p-4"
    >
      {/* The two sides, side by side. The grid stacks them on a narrow screen. */}
      <div className="grid gap-3 sm:grid-cols-2">
        <ConflictSideView side={pair.left} />
        <ConflictSideView side={pair.right} />
      </div>

      {/*
        The actions. **A vertical column of quiet buttons**, not a row of primaries:
        there is no single recommended answer here, so no one button may look like the
        answer. Terracotta is rationed to four sanctioned uses and a list of three
        equal choices is not one of them.
      */}
      <div
        role="group"
        aria-label={`Choices for the conflict between ${sideTitle(pair.left)} and ${sideTitle(pair.right)}`}
        className="mt-4 flex flex-col gap-2"
      >
        {actions.map((resolution) => {
          const target = actionSide(resolution, pair.left, pair.right);
          // `keep_both` acts on neither side, so it is the one action with no target.
          const subject = target ? subjectName(resolution, pair.left, pair.right, target.id) : null;
          // The side the request names. **For every action but `keep_both`, this is the
          // one the server requires** — the backend's `_target_side_kind` maps
          // `skip_public` to the saved side and everything else to the personal side,
          // and refuses any other pairing with `IllegalResolutionError`.
          //
          // **`keep_both` is about neither side**, so the backend accepts *either* of
          // the pair's own sides for it — it checks `value != KEEP_BOTH` before it
          // compares kinds. The left side is named here, and it is one of the pair's
          // own, so the server accepts it.
          const label = reviewActionLabel(resolution, subject);
          const aria = reviewActionAria(resolution, subject);
          const glyph = RESOLUTION_GLYPHS[resolution] ?? "•";

          return (
            <button
              key={resolution}
              type="button"
              disabled={busy}
              onClick={() => {
                if (target) onChoose(resolution, target);
                else onChoose(resolution, { kind: pair.left.kind, id: pair.left.id });
              }}
              aria-label={aria}
              className="flex w-full items-start gap-3 rounded-control border border-border-subtle bg-surface-subtle px-4 py-3 text-left hover:bg-surface-inset disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span
                aria-hidden="true"
                className="mt-1 flex size-6 shrink-0 items-center justify-center rounded-full bg-surface-inset text-xs text-ink-secondary"
              >
                {glyph}
              </span>
              <span>
                <span className="block [font:var(--type-scale-meta-md)] text-ink-primary">
                  {label}
                </span>
                <span className="mt-1 block [font:var(--type-scale-body-sm)] text-ink-muted">
                  {RESOLUTION_HINTS[resolution]}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </article>
  );
}

/**
 * The event's own name, for the action's label.
 *
 * **The side the action acts on, not the first one.** A "Skip" that named the personal
 * event would be a lie about what the button does.
 */
function subjectName(
  resolution: Resolution,
  left: ConflictSide,
  right: ConflictSide,
  targetId: string,
): string | null {
  // A move opens the edit sheet, so it can only be about a personal event — and the
  // name it shows is that event's.
  const movable = movableSide(resolution, left, right);
  if (movable) return movable.name ?? null;

  const side = targetId === left.id ? left : right;
  return side.name ?? null;
}

/** A side's name, for a label that mentions both sides. */
function sideTitle(side: ConflictSide): string {
  if (!side.available) return "an event no longer available";
  return side.name ?? "an event no longer available";
}
