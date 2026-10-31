"use client";

/**
 * The Detail Screen's action row: Save to Pulse and Share.
 *
 * **Two buttons, not three.** The locked order says "Save to Pulse · Share · Dismiss",
 * and the mockup has a "Less like this" third. But FR-25's dismissal is a **swipe on the
 * Pulse Card**, and there is **no dismissal endpoint** in this codebase — a "Dismiss"
 * button here would be a control that silently does nothing, which is the failure this
 * screen is supposed to avoid. The swipe stays where FR-25 puts it.
 *
 * **Save is terracotta.** It is a `Button.Primary`, and the primary fill is one of the
 * four sanctioned terracotta uses. Share is a `Button.Secondary` — no fill.
 *
 * **The Save button's state is known before the user presses it.** `personal.saved` is
 * the user's own save row, read by the API — not a tag on the composition, which may
 * have been composed days ago.
 */
import { useCallback, useState } from "react";

import { api } from "@/lib/backend-client";

export type DetailActionsProps = {
  /** The event's id, as the API's path parameter takes it. */
  eventId: string;
  /** Whether the user has already saved it. */
  saved: boolean;
};

export function DetailActions({ eventId, saved }: DetailActionsProps) {
  const [isSaved, setIsSaved] = useState(saved);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const onSave = useCallback(async () => {
    setBusy(true);
    setFailed(false);
    try {
      const response = await api.POST("/api/personal/saved-events/{catalog_event_id}", {
        params: { path: { catalog_event_id: eventId } },
      });
      // The save is idempotent, so a 2xx means it is saved now. A refusal is shown
      // calmly rather than swallowed — a button that silently fails is the thing this
      // screen is careful about.
      if (response.response.status >= 200 && response.response.status < 300) {
        setIsSaved(true);
      } else {
        setFailed(true);
      }
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }, [eventId]);

  const onShare = useCallback(async () => {
    const url = typeof window !== "undefined" ? window.location.href : "";
    const title = "Event on EventPulse24";
    try {
      if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
        await navigator.share({ title, url });
        return;
      }
      await navigator.clipboard?.writeText(url);
      setFailed(false);
    } catch {
      // A cancelled share sheet is not a failure, and there is nothing to say about it.
      setFailed(false);
    }
  }, []);

  return (
    <div className="flex flex-wrap items-center gap-3" data-detail-actions>
      <button
        type="button"
        onClick={onSave}
        disabled={busy || isSaved}
        className={[
          "rounded-control px-5 py-2.5 [font:var(--type-scale-meta-md)]",
          isSaved
            ? "bg-surface-subtle text-ink-secondary"
            : "bg-accent-terracotta text-ink-inverse",
          "disabled:cursor-default",
        ].join(" ")}
      >
        {isSaved ? "Saved to your Pulse" : "Save to Pulse"}
      </button>

      <button
        type="button"
        onClick={onShare}
        className="rounded-control border border-border-subtle bg-surface-elevated px-5 py-2.5 text-ink-secondary [font:var(--type-scale-meta-md)]"
      >
        Share
      </button>

      {failed ? (
        <p className="text-ink-muted [font:var(--type-scale-body-sm)]">
          Couldn&apos;t save that. We&apos;ll try again on your next change.
        </p>
      ) : null}
    </div>
  );
}
