"use client";

/**
 * The muted categories list (FR-25) — the screen behind `Settings → Taste`.
 *
 * **This is the reversal surface the mockup points at.** The prompt says "You can undo
 * anytime in Settings → Taste", and this is that screen: every category the user has
 * muted, with the server's own label for each, and a one-tap way back.
 *
 * **The label is the server's.** It arrives on the row, not from a list the frontend
 * owns — the vocabulary is ten broad buckets the server defines, and a frontend copy of
 * it would be a second opinion about what a category is.
 *
 * **Unmuting is one tap, and it deletes the row.** There is no "unmuted" state to
 * record: the absence of a row *is* the absence of a mute. So the control is a single
 * button that removes the row from the list when the server confirms.
 *
 * **"Restore all defaults" confirms before it does.** §10.4's bulk-action safeguard is
 * that the destructive action is confirmed *before it completes*, and the confirmation is
 * the client's job: the endpoint is a single idempotent delete, and a confirmation the
 * server owned would have to survive a page refresh. The control is a **text link** —
 * it reads as the reversible-sounding thing it is, and the destructive confirmation
 * replaces it in place — the same two-step idiom the sources screen's bulk reset uses,
 * rather than a third confirmation style.
 *
 * **Unmuting does not resurrect the muted events.** The events excluded from a digest
 * are excluded from the digests they were excluded from; the next digest is composed
 * from the current candidate pool. A user who unmutes is asking for the category back
 * *from now on*, and the mockup's own framing is "in your next digest".
 */
import { useCallback, useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";
import type { CategoryMute } from "@/lib/taste-mutes-read";

export type TasteMuteListProps = {
  /** The muted categories, as the server read them. */
  mutes: CategoryMute[];
};

/** The failure line. Nothing was lost, so it invites a retry. */
const FAILED = "Couldn't do that. Try again in a moment.";

/**
 * How long a mute has left, in words.
 *
 * **The words come from the expiry, not from a duration the client kept.** The server
 * computes the expiry from the instant the mute was set, and the client does not know
 * that instant — so it would have to guess, and a guess that says "30 days" for a mute
 * with six left is a lie on the screen. So the client reads the expiry and says what it
 * can say truthfully: whether it ends, and when.
 */
function expiryWords(mute: CategoryMute): string {
  if (mute.is_indefinite || !mute.expires_at) return "Until you change it";
  const ends = new Date(mute.expires_at);
  const now = new Date();
  const days = Math.ceil((ends.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  if (days <= 0) return "Ended";
  if (days === 1) return "Ends tomorrow";
  return `Ends in ${days} days`;
}

export function TasteMuteList({ mutes }: TasteMuteListProps) {
  // **The screen holds the state the server gave it.** A row leaves the list when the
  // server confirms the unmute, and the local copy is what makes that happen without a
  // full re-read.
  const [rows, setRows] = useState<CategoryMute[]>(mutes);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const unmute = useCallback(async (categoryKey: string) => {
    setBusy(true);
    setFailure(null);
    try {
      const response = await api.DELETE("/api/settings/taste/mutes/{category_key}", {
        params: { path: { category_key: categoryKey } },
      });
      if (response.error) {
        setFailure(saveFailureMessage(response.error, FAILED) || FAILED);
        return;
      }
      // **The row is gone.** The server deleted it, and the screen says so rather than
      // re-reading to find out what happened.
      setRows((current) => current.filter((row) => row.category_key !== categoryKey));
    } catch {
      setFailure(FAILED);
    } finally {
      setBusy(false);
    }
  }, []);

  const restoreDefaults = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    try {
      const response = await api.POST("/api/settings/taste/mutes/restore-defaults");
      if (response.error) {
        setFailure(saveFailureMessage(response.error, FAILED) || FAILED);
        return;
      }
      // **Every row goes.** The server cleared them all, and the screen says so rather
      // than re-reading to find out what happened.
      setRows([]);
      setConfirming(false);
    } catch {
      setFailure(FAILED);
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <section aria-label="Muted categories" data-taste-list>
      {failure ? (
        <p role="alert" className="mb-4 text-signal-error [font:var(--type-scale-body-sm)]">
          {failure}
        </p>
      ) : null}

      {rows.length === 0 ? (
        // **An honest empty state, not an error.** No muted categories is an answer, and
        // it is a good one — it means nothing is being held back.
        <p className="text-ink-muted [font:var(--type-scale-body-md)]" data-no-mutes>
          Nothing is muted. If you swipe past a few similar events, we&apos;ll ask whether you want
          to see less of that.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {rows.map((mute) => (
            <li
              key={mute.category_key}
              className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border-subtle bg-surface-elevated px-4 py-3"
              data-mute={mute.category_key}
            >
              <span className="min-w-0">
                <span className="block truncate text-ink-primary [font:var(--type-scale-meta-md)]">
                  {mute.label}
                </span>
                <span className="block text-ink-muted [font:var(--type-scale-body-sm)]">
                  {expiryWords(mute)}
                </span>
              </span>

              {/*
                **One tap, and the row is gone.** The button says what it does in the
                words the screen uses — "Show them again" — rather than "Unmute", which
                is a word the product never puts on screen.
              */}
              <button
                type="button"
                onClick={() => unmute(mute.category_key)}
                disabled={busy}
                aria-label={`Show ${mute.label} again`}
                className="min-h-[44px] rounded-control border border-border-strong px-4 text-ink-primary [font:var(--type-scale-meta-sm)]"
              >
                Show them again
              </button>
            </li>
          ))}
        </ul>
      )}

      {/*
        **The bulk reset, and its confirmation.**

        The confirmation replaces the link in place rather than opening an overlay: A-16
        reserves that weight for deleting an account, and the sources screen's bulk reset
        already set the precedent for a settings screen's in-place two-step.
      */}
      {rows.length === 0 ? null : confirming ? (
        <div className="mt-8 flex flex-wrap items-center gap-3" data-restore-confirm>
          <p className="text-ink-secondary [font:var(--type-scale-body-sm)]">
            Unmute every category? You&apos;ll start seeing all of them again in your next digest.
          </p>
          <button
            type="button"
            onClick={restoreDefaults}
            disabled={busy}
            data-restore-yes
            className="min-h-[44px] rounded-control border border-border-strong px-4 text-ink-primary [font:var(--type-scale-meta-sm)]"
          >
            Unmute them
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            disabled={busy}
            data-restore-no
            className="min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
          >
            Keep them muted
          </button>
        </div>
      ) : (
        <div className="mt-8 flex flex-col gap-2">
          <p className="text-ink-muted [font:var(--type-scale-body-sm)]">
            Tap &quot;Restore all defaults&quot; to unmute every category. We ask once before
            applying — you&apos;ll start seeing all of them again in your next digest.
          </p>
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={busy}
            data-restore
            aria-label="Unmute every category"
            className="self-start min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
          >
            Restore all defaults
          </button>
        </div>
      )}
    </section>
  );
}
