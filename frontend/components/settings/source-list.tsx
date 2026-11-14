"use client";

/**
 * The source registry, grouped, with each source's trust and visibility control.
 *
 * **The screen's job is transparency.** Every source in the registry is listed, including
 * the ones the user has muted — a muted source that disappeared would be a preference the
 * user could not see or undo, on the screen whose whole purpose is to show them what is
 * informing their timeline.
 *
 * **The four groups are the Source Badge types**, in the order the mockup shows them:
 * Official, Community, Aggregator, Crawled. That order is the order of decreasing
 * confidence in a source's own facts, so reading the screen top to bottom is reading the
 * spectrum of how sure we are.
 *
 * **An empty registry is an empty registry, and nothing is invented to fill it.** The
 * registry holds a handful of sources today. A screen that fabricated sources to look
 * populated would be asserting a registry that does not exist — so the empty state is
 * first-class and the groups simply have no rows under them.
 *
 * **"Restore all defaults" confirms before it does.** §10.4's bulk-action safeguard is
 * that the destructive action is confirmed *before it completes*, and the confirmation is
 * the client's job: the endpoint is a single idempotent delete, and a confirmation the
 * server owned would have to survive a page refresh, which is a state machine to buy a
 * dialog. The control is a **text link** — it reads as the reversible-sounding thing it
 * is, and the destructive confirmation replaces it in place — the same two-step idiom the
 * calendar screen's disconnect uses, rather than a third confirmation style.
 */
import { useCallback, useState } from "react";

import { SourceMuteControl } from "@/components/settings/source-mute-control";
import type { SourceMuteState } from "@/components/settings/source-mute-control";
import { SourceTrustDots } from "@/components/settings/source-trust-dots";
import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";
import type { RegistryGroup, RegistrySource } from "@/lib/source-mutes-read";

export type SourceListProps = {
  /** The registry, grouped. */
  groups: RegistryGroup[];
};

/** The failure line. Nothing was lost, so it invites a retry. */
const FAILED = "Couldn't do that. Try again in a moment.";

/** How a source describes itself, under its name. */
function sourceSub(source: RegistrySource): string {
  const parts: string[] = [];
  if (source.city) parts.push(source.city);
  if (source.is_paused) parts.push("paused");
  return parts.join(" · ");
}

export function SourceList({ groups }: SourceListProps) {
  // **The screen holds the state the server gave it.** A row's state changes when the
  // server confirms, and the local copy is what makes the control move without a full
  // re-read.
  const [sources, setSources] = useState<RegistryGroup[]>(groups);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const setState = useCallback((sourceId: string, next: SourceMuteState) => {
    setSources((current) =>
      current.map((group) => ({
        ...group,
        sources: group.sources.map((source) =>
          source.id === sourceId ? { ...source, mute_state: next } : source,
        ),
      })),
    );
  }, []);

  const restoreDefaults = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    try {
      const response = await api.POST("/api/settings/sources/restore-defaults");
      if (response.error) {
        setFailure(saveFailureMessage(response.error, FAILED) || FAILED);
        return;
      }
      // **Every row goes back to the default.** The server cleared them all, and the
      // screen says so rather than re-reading to find out what happened.
      setSources((current) =>
        current.map((group) => ({
          ...group,
          sources: group.sources.map((source) => ({ ...source, mute_state: "default" })),
        })),
      );
      setConfirming(false);
    } catch {
      setFailure(FAILED);
    } finally {
      setBusy(false);
    }
  }, []);

  // **The rendered list is the local copy, not the prop.** The screen holds the state
  // the server gave it so a row can move without a full re-read — so it renders `sources`
  // and not the `groups` it was handed. (Rendering the prop would make the local copy
  // dead code, and the reset would move nothing on screen.)
  const total = sources.reduce((count, group) => count + group.sources.length, 0);

  return (
    <section aria-label="Sources" data-source-list>
      {failure ? (
        <p role="alert" className="mb-4 text-signal-error [font:var(--type-scale-body-sm)]">
          {failure}
        </p>
      ) : null}

      {total === 0 ? (
        // **An honest empty state, not an error.** A registry with no sources is an
        // answer, and it is not a failure of the user's account.
        <p className="text-ink-muted [font:var(--type-scale-body-md)]" data-no-sources>
          No sources yet. We&apos;re still adding them — your events will appear here as soon as
          they do.
        </p>
      ) : (
        <div className="flex flex-col gap-8">
          {sources.map((group) => (
            <section key={group.badge} aria-labelledby={`group-${group.badge}`}>
              <h2
                id={`group-${group.badge}`}
                className="text-ink-primary [font:var(--type-scale-title-sm)]"
              >
                {group.label}{" "}
                <span className="text-ink-muted [font:var(--type-scale-meta-sm)]">
                  {group.sources.length} {group.sources.length === 1 ? "source" : "sources"}
                </span>
              </h2>

              {group.sources.length === 0 ? (
                // **An empty group keeps its heading.** The screen's shape should not
                // depend on which groups happen to have sources in them.
                <p className="mt-2 text-ink-muted [font:var(--type-scale-body-sm)]">None yet.</p>
              ) : (
                <ul className="mt-3 flex flex-col gap-3">
                  {group.sources.map((source) => (
                    <li
                      key={source.id}
                      className="rounded-card border border-border-subtle bg-surface-elevated px-4 py-3"
                      data-source={source.id}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <span className="min-w-0">
                          <span className="block truncate text-ink-primary [font:var(--type-scale-meta-md)]">
                            {source.name}
                          </span>
                          {sourceSub(source) ? (
                            <span className="block text-ink-muted [font:var(--type-scale-body-sm)]">
                              {sourceSub(source)}
                            </span>
                          ) : null}
                        </span>

                        <span className="flex flex-wrap items-center gap-4">
                          <SourceTrustDots band={source.trust.band} />
                          <SourceMuteControl
                            sourceId={source.id}
                            sourceName={source.name}
                            state={source.mute_state}
                            onStateChange={(next) => setState(source.id, next)}
                          />
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      )}

      {/*
        **The bulk reset, and its confirmation.**

        The confirmation replaces the button in place rather than opening an overlay:
        A-16 reserves that weight for deleting an account, and the calendar screen's
        disconnect already set the precedent for a settings screen's in-place
        two-step.
      */}
      {total === 0 ? null : confirming ? (
        <div className="mt-8 flex flex-wrap items-center gap-3" data-restore-confirm>
          <p className="text-ink-secondary [font:var(--type-scale-body-sm)]">
            Reset every source to its default visibility? This clears your mutes and &quot;show
            less&quot; settings across the board.
          </p>
          <button
            type="button"
            onClick={restoreDefaults}
            disabled={busy}
            data-restore-yes
            className="min-h-[44px] rounded-control border border-border-strong px-4 text-ink-primary [font:var(--type-scale-meta-sm)]"
          >
            Reset them
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            disabled={busy}
            data-restore-no
            className="min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
          >
            Keep them
          </button>
        </div>
      ) : (
        <div className="mt-8 flex flex-col gap-2">
          <p className="text-ink-muted [font:var(--type-scale-body-sm)]">
            Tap &quot;Restore all defaults&quot; to reset every source to its default visibility. We
            ask once before applying — this clears custom mutes across the board.
          </p>
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={busy}
            data-restore
            aria-label="Restore default visibility for all sources"
            className="self-start min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
          >
            Restore all defaults
          </button>
        </div>
      )}
    </section>
  );
}
