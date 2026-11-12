"use client";

/**
 * FR-52's *"Settings → Download my data"* — the request, and what honestly happens next.
 *
 * **It does not download anything, and the copy must not suggest it does.** The export is
 * built by a worker and the links arrive by email; a button labelled "Download" that
 * produced no file would read as broken. So the control says **"Email me my data"**, and
 * the confirmation says when it will arrive rather than claiming it has.
 *
 * **It is not Pro-gated, and it is not in a Pro section.** `data-export`'s checkpoint
 * settled that: GDPR Article 20 is a right, not a tier feature, and the acceptance
 * criterion for this screen explicitly forbids gating it *by placement* — putting the
 * control inside a Pro-only block would be the same gate wearing a layout.
 *
 * **Asking twice is not an error.** The backend joins a second request to the one already
 * in flight (a partial unique constraint makes that a database fact), so a second click
 * returns the same request. The UI says the same calm thing rather than reporting a
 * conflict the user did not cause.
 */
import { useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";

/** What the user is told once the request lands. The promise FR-52 makes, in words. */
const REQUESTED = "On its way. We'll email your data within 24 hours.";

/**
 * The failure line for the **offline** case, where the API said nothing to quote.
 *
 * `saveFailureMessage` shows the API's own refusal when there is one and this when there
 * is not — the same split every settings control uses. Nothing is lost by a failed
 * request here, because there was nothing to lose, so the line simply invites a retry.
 */
const FAILED = "Couldn't start that. Try again in a moment.";

export function DownloadMyData() {
  const [busy, setBusy] = useState(false);
  const [requested, setRequested] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const request = async (): Promise<void> => {
    setBusy(true);
    setFailure(null);
    try {
      const response = await api.POST("/api/exports");
      if (response.data) {
        setRequested(true);
      } else {
        // **`|| fallback` because a refusal with no sentence must not render as no
        // refusal at all.** `saveFailureMessage` returns the API's own message
        // whenever the body is the project's error shape — including when that
        // message is empty, which would leave the user staring at an unchanged
        // screen after a failed action.
        setFailure(saveFailureMessage(response.error, FAILED) || FAILED);
      }
    } catch {
      // The request never reached the API, so there is nothing to quote.
      setFailure(FAILED);
    }
    setBusy(false);
  };

  return (
    <section aria-label="Download my data" data-download-my-data>
      <p className="text-ink-secondary [font:var(--type-scale-body-md)]">
        Everything we hold about you, as JSON and as a calendar file.
      </p>

      <button
        type="button"
        onClick={request}
        disabled={busy}
        aria-busy={busy}
        data-request-export
        className="mt-6 min-h-[44px] rounded-control border border-border-strong px-4 py-3 text-ink-primary [font:var(--type-scale-meta-md)] disabled:cursor-default"
      >
        {busy ? "Starting…" : "Email me my data"}
      </button>

      {/*
        **Always present, so its arrival is announceable.** An empty live region is what
        lets a screen reader notice the text appearing at all — the same reasoning
        `SaveFeedback` records.
      */}
      <div role="status" aria-live="polite" className="mt-2">
        {requested ? (
          <p className="text-ink-secondary [font:var(--type-scale-body-sm)]" data-export-requested>
            {REQUESTED}
          </p>
        ) : null}
      </div>

      {failure ? (
        <p
          role="alert"
          className="mt-2 text-warn-amber [font:var(--type-scale-body-sm)]"
          data-export-failed
        >
          {failure}
        </p>
      ) : null}
    </section>
  );
}
