"use client";

/**
 * The **three-state source control** — Mute / Show less / Default.
 *
 * **Three buttons in a labelled group, and the selected one is `aria-pressed`.** This is
 * the mockup's own markup, and it is the right shape: a radio group would hide the two
 * inactive options from a screen-reader user, and a `<select>` would hide the three
 * choices from everyone. Three buttons show every option and name the group, so a reader
 * hears "Mute controls for Barbican Centre, Mute, pressed" and knows what else is on
 * offer.
 *
 * **The three options say different things, and the labels are the difference.**
 *
 * - **Mute** — "do not show me this source's events"
 * - **Show less** — "show me fewer of them"
 * - **Default** — "as I found it"
 *
 * A "show less" that hid the events would be indistinguishable from a mute on the wire,
 * and would be a lie to the user who asked for fewer rather than none. The server keeps
 * the two apart, and the labels keep them apart on screen.
 *
 * **The state is the server's.** The control shows what the last read said, and it moves
 * only when the server confirms. A failed write leaves the state where it was, because
 * the server did not record the change and a control claiming otherwise would be claiming
 * something that did not happen.
 */
import { useCallback, useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";

export type SourceMuteState = "mute" | "show_less" | "default";

export type SourceMuteControlProps = {
  /** The source's id — the mute's own path parameter. */
  sourceId: string;
  /** The source's name, for the group's accessible name. */
  sourceName: string;
  /** The source's current state. The server's fact. */
  state: SourceMuteState;
  /** Called when the state changes, so the row can redraw. */
  onStateChange?: (state: SourceMuteState) => void;
};

/** The failure line. Nothing was lost, so it invites a retry. */
const FAILED = "Couldn't save that. Try again in a moment.";

/**
 * The three options, in the mockup's order.
 *
 * **The order is the spectrum.** Mute is the strongest statement, Default is the absence
 * of one, and "Show less" sits between them — so the row reads left to right as "hide
 * it, show less of it, or leave it alone".
 */
const OPTIONS: readonly { value: SourceMuteState; label: string }[] = [
  { value: "mute", label: "Mute" },
  { value: "show_less", label: "Show less" },
  { value: "default", label: "Default" },
];

export function SourceMuteControl({
  sourceId,
  sourceName,
  state,
  onStateChange,
}: SourceMuteControlProps) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  // **The prop is the state.** The parent owns it — it is the row's `mute_state`, and it
  // is the server's last answer. So the control renders `state` and holds no copy of it.
  //
  // That is what makes "Restore all defaults" work: the reset rewrites the rows in the
  // parent, the new `state` prop arrives, and the control moves because it was always
  // reading the prop. A control that mirrored the prop into local state would need a
  // synchronising effect to notice the change, and a mirroring effect is a second source
  // of truth that can disagree with the first.
  //
  // The one thing the control holds on to is **the write in flight**: `pending` is the
  // state the server has confirmed but the parent has not yet adopted, so the button the
  // user pressed stays pressed for the moment between the response and the parent's
  // re-render — and never moves to a position the server did not confirm.
  //
  // **`pending` lives for exactly one gap, and then it is gone.** It exists to cover the
  // moment between the server's answer and the parent's re-render.
  //
  // **`pending` is dropped the first time the prop changes.** It exists to cover one gap,
  // and it is spent as soon as the prop moves — whether to the confirmed state (the
  // parent adopted it) or to "default" (a bulk reset cleared it). Keeping it would let it
  // sit *ahead* of the prop forever: a bulk reset moves every row's prop to "default",
  // and a stale `pending` of "mute" would keep that row showing Mute while the server had
  // just cleared it.
  //
  // `propAtWrite` is the prop the write was made against, and `propSeen` is the prop as
  // of the last render. The override is live only while they are equal — that is, only
  // while the prop has not moved since the write.
  const [pending, setPending] = useState<SourceMuteState | null>(null);
  const [propAtWrite, setPropAtWrite] = useState<SourceMuteState | null>(null);
  const [propSeen, setPropSeen] = useState<SourceMuteState>(state);

  // **The prop moved, so the gap is closed.** This is React's documented way to adjust
  // state during a render rather than in an effect: set the state, and React re-runs the
  // component immediately with the new value, before it touches the DOM. It is not a
  // synchronising effect, so there is no second render pass and no "setState in an
  // effect" — and the condition is checked on every render, so the override is dropped
  // the moment it stops being true.
  if (propSeen !== state) {
    setPropSeen(state);
    if (pending !== null && propAtWrite !== state) {
      setPending(null);
      setPropAtWrite(null);
    }
  }

  const current = pending ?? state;

  const choose = useCallback(
    async (next: SourceMuteState) => {
      if (next === current || busy) return;
      setBusy(true);
      setFailure(null);
      // **The write is made against the prop on screen.** `propAtWrite` records it, so
      // the override that follows is only good while the prop has not moved since.
      const from = state;
      try {
        const response = await api.PUT("/api/settings/sources/{source_id}", {
          params: { path: { source_id: sourceId } },
          body: { state: next },
        });
        if (response.error) {
          setFailure(saveFailureMessage(response.error, FAILED) || FAILED);
          return;
        }
        // **The server's answer moves the control.** The response carries the state it
        // now holds, and it is the server's — not the value we asked for.
        const confirmed = (response.data?.state ?? next) as SourceMuteState;
        setPending(confirmed);
        setPropAtWrite(from);
        onStateChange?.(confirmed);
      } catch {
        setFailure(FAILED);
      } finally {
        setBusy(false);
      }
    },
    [busy, current, onStateChange, sourceId],
  );

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <span
        role="group"
        aria-label={`Mute controls for ${sourceName}`}
        className="inline-flex gap-1"
        data-source-mute={sourceId}
      >
        {OPTIONS.map((option) => {
          const selected = option.value === current;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => choose(option.value)}
              disabled={busy}
              aria-pressed={selected}
              data-source-mute-option={option.value}
              className={
                selected
                  ? "min-h-[36px] rounded-control border border-border-strong bg-surface-inset px-3 text-ink-primary [font:var(--type-scale-meta-sm)]"
                  : "min-h-[36px] rounded-control border border-border-subtle px-3 text-ink-secondary [font:var(--type-scale-meta-sm)]"
              }
            >
              {option.label}
            </button>
          );
        })}
      </span>
      {failure ? (
        <span role="alert" className="text-signal-error [font:var(--type-scale-body-sm)]">
          {failure}
        </span>
      ) : null}
    </span>
  );
}
