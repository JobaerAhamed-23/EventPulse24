"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PersonalEventsPanel, type PersonalEventSeed } from "@/components/personal-events-panel";
import { api } from "@/lib/backend-client";
import {
  actionSide,
  movableSide,
  type ConflictSide,
  type Resolution,
} from "@/lib/conflict-wording";
import type { ConflictPair } from "@/lib/conflict-list-read";

import { ConflictPairCard } from "./conflict-pair-card";
import { ResolvedPairRow } from "./resolved-pair-row";

/**
 * The Conflict Review screen's client island.
 *
 * **The page is a server component; the decisions are not.** The pairs are read on the
 * server and arrive here as plain data — the island draws them and decides nothing
 * (AD-10). What the island *does* own is the write: posting a resolution, re-reading
 * after a success, and opening the edit sheet when the choice was "move".
 *
 * **The action's target side is computed from the pair's kinds, never from
 * `left`/`right`.** The pair row stores its two sides sorted, so the row cannot say
 * which side the user means — the request has to (`ConflictResolutionIn.side`). The
 * rule lives in `lib/conflict-wording.ts`, so the prompt and the review screen cannot
 * disagree about it.
 *
 * **A failed choice leaves the pair where it was.** The pair stays Active, its buttons
 * come back, and a calm line says what happened. A pair that vanished on a failed write
 * would be a lie about the user's schedule.
 *
 * **There is no auto-refresh.** No timer, no polling, no refetch on focus. The page
 * re-reads exactly once, after a successful write — a passive-pressure surface that
 * re-rendered under the user would move the button they were reaching for.
 */
export function ConflictsPanel({
  active,
  resolved,
}: {
  /** The pairs that still need a decision. */
  active: ConflictPair[];
  /** The pairs that were decided. */
  resolved: ConflictPair[];
}) {
  const router = useRouter();

  /** The pair currently posting — its actions are disabled while the write is in flight. */
  const [busyPairId, setBusyPairId] = useState<string | null>(null);
  /** The calm line under a pair, after a failed choice. */
  const [failedPairId, setFailedPairId] = useState<string | null>(null);
  /** The event the edit sheet is open on, driven from a "move" choice. */
  const [editingId, setEditingId] = useState<string | null>(null);
  /** Whether the edit sheet highlights the start time — a move always does. */
  const [highlight, setHighlight] = useState(false);

  /**
   * The personal events the edit sheet may open.
   *
   * **Only the personal sides of the active pairs.** A "move" can only move a personal
   * event — the sheet edits personal events, and a saved public event is edited on its
   * own detail screen.
   */
  const editableEvents: PersonalEventSeed[] = active.flatMap((pair) =>
    [pair.left, pair.right]
      .filter((side) => side.kind === "personal_event")
      .map((side) => ({
        id: side.id,
        name: side.name ?? "Personal event",
        start_time_utc: side.start_time_utc,
        end_time_utc: side.end_time_utc ?? null,
        start_time_tz: side.start_time_tz ?? "",
      })),
  );

  /**
   * The user's choice on a pair.
   *
   * **The resolution and the side it acts on** — the server needs both, and the side is
   * the one the button named.
   */
  const choose = async (
    pair: ConflictPair,
    resolution: Resolution,
    side: { kind: ConflictSide["kind"]; id: string },
  ): Promise<void> => {
    setBusyPairId(pair.pair_id);
    setFailedPairId(null);

    const response = await api.POST("/api/personal/events/conflicts/{pair_id}/resolve", {
      params: { path: { pair_id: pair.pair_id } },
      body: { resolution, side },
    });

    if (response.error) {
      // **The pair stays Active.** Nothing is removed, nothing is re-read — the user
      // still has a decision to make, and the buttons come back so they can try again.
      setBusyPairId(null);
      setFailedPairId(pair.pair_id);
      return;
    }

    // **A move opens the side in the edit sheet with its time highlighted.** The user
    // asked to move the event, so the sheet opens on the event and on the field they
    // have to change — not on a form that looks like any other edit.
    const movable = movableSide(resolution, pair.left, pair.right);
    if (movable) {
      setEditingId(movable.id);
      setHighlight(true);
    }

    // **The page re-reads.** The server component's read is what the page renders, so a
    // write is invisible until the route re-renders; `router.refresh()` re-runs the
    // read and the pair moves from Active to Resolved.
    router.refresh();
    setBusyPairId(null);
  };

  return (
    <>
      {/*
        The edit sheet. The panel renders only sheets — the page has its own heading, and the
        panel whole would push a headline between the page's header and its sections.

        **The sheet is driven**, the same way the Timeline drives it: the island names
        the event, and the sheet opens on it. The highlight is derived from the island's
        own state rather than synchronised into the sheet, so a render between the two
        cannot show the wrong form.
      */}
      <PersonalEventsPanel
        editingEvents={editableEvents}
        editingEventId={editingId}
        onEditingEventChange={(id) => {
          setEditingId(id);
          if (id === null) setHighlight(false);
        }}
        highlightStartTime={highlight}
      />

      {/*
        The Active section. **`aria-live="polite"` and `aria-atomic="false"`**, so the
        count is announced when the list changes and a reader is not made to listen to
        the whole section again.
      */}
      {active.length > 0 ? (
        <section aria-labelledby="conflicts-active" aria-live="polite" aria-atomic="false">
          <h2
            id="conflicts-active"
            className="flex items-center gap-3 text-ink-primary [font:var(--type-scale-headline-lg)]"
          >
            Active
            <span className="rounded-full border border-border-subtle px-2 py-1 text-ink-muted [font:var(--type-scale-meta-sm)]">
              {active.length}
            </span>
          </h2>

          <div className="mt-3 flex flex-col gap-3">
            {active.map((pair) => (
              <div key={pair.pair_id}>
                <ConflictPairCard
                  pair={pair}
                  busy={busyPairId === pair.pair_id}
                  onChoose={(resolution, side) => {
                    void choose(pair, resolution, side);
                  }}
                />
                {failedPairId === pair.pair_id ? (
                  <p
                    role="status"
                    className="mt-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
                  >
                    Couldn&apos;t record that choice. Try again.
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {/*
        The Resolved section. **History, and nothing else** — the rows carry no
        affordance, because a decided pair is never decided again.
      */}
      {resolved.length > 0 ? (
        <section aria-labelledby="conflicts-resolved" className="mt-8">
          <h2
            id="conflicts-resolved"
            className="flex items-center gap-3 text-ink-primary [font:var(--type-scale-headline-lg)]"
          >
            Resolved
            <span className="rounded-full border border-border-subtle px-2 py-1 text-ink-muted [font:var(--type-scale-meta-sm)]">
              {resolved.length}
            </span>
          </h2>

          <div className="mt-3 overflow-hidden rounded-timeline-cell border border-border-subtle bg-surface-elevated">
            {resolved.map((pair) => (
              <ResolvedPairRow key={pair.pair_id} pair={pair} />
            ))}
          </div>
        </section>
      ) : null}

      {/*
        The entry announcement. **A visually-hidden live region** that says the counts
        when the page loads — the section headings are visual, and a screen-reader user
        arriving on the page should hear how much is waiting without hunting for it.
      */}
      <p aria-live="polite" className="sr-only">
        Conflicts page loaded. {active.length} active{" "}
        {active.length === 1 ? "pair needs" : "pairs need"} a decision. {resolved.length} resolved{" "}
        {resolved.length === 1 ? "pair" : "pairs"} in history.
      </p>
    </>
  );
}

/**
 * The side a resolution acts on — re-exported from the wording module so the panel
 * does not have to reach past it for one rule.
 */
export { actionSide };
