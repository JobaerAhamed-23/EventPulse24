"use client";

/**
 * Sign out.
 *
 * It lives in the **home's footer**, not in the topbar: the topbar-quiet rule keeps
 * account affordances out of the topbar, and the sidenav footer that will carry "Account"
 * (`Component.Sidenav.Footer`) does not exist yet. The footer is where the spine puts
 * secondary affordances until it does.
 *
 * `POST /api/auth/signout` is a state-changing request, so it carries the CSRF token like
 * every other write — the client's middleware does that. Afterwards the user goes to
 * `/signin` rather than to `/`, because `/` would bounce an anonymous visitor on to
 * `/preview`: the person who just signed out asked to be signed out, not to be shown the
 * marketing page.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { readApiError } from "@/lib/api-errors";
import { api } from "@/lib/backend-client";

export function SignOutButton() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const signOut = async (): Promise<void> => {
    setError(null);
    setBusy(true);
    let response;
    try {
      response = await api.POST("/api/auth/signout");
    } catch (thrown) {
      // A request that never reached the API. The session is untouched, so the button
      // comes back rather than leaving the user in a half-signed-out limbo.
      setError(readApiError(thrown).message);
      setBusy(false);
      return;
    }
    if (response.error) {
      setError(readApiError(response.error).message);
      setBusy(false);
      return;
    }
    router.replace("/signin");
    // The server components re-run, so nothing from the old session is left on screen.
    router.refresh();
  };

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={signOut}
        disabled={busy}
        aria-busy={busy}
        className="rounded-control border border-border-subtle px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
      >
        {busy ? "Signing out…" : "Sign out"}
      </button>
      {error ? (
        <p role="alert" className="[font:var(--type-scale-body-sm)] text-signal-warn">
          {error}
        </p>
      ) : null}
    </div>
  );
}
