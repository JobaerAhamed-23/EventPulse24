"use client";

/**
 * The pricing page's buy button — the one client island on an otherwise server-rendered
 * screen.
 *
 * **It buys a plan, so it is an action and it is a POST.** The endpoint mints a checkout
 * session and hands back a URL; the browser then *follows* that URL to the provider's
 * hosted page. It is a redirect rather than a fetch, because the URL is somebody else's
 * page, not an API answer.
 *
 * **Four outcomes, and every one of them is handled.**
 *
 *   - **200** — the browser follows the URL. The provider takes over.
 *   - **401** — the session went away between the page's read and this click, or the
 *     visitor was never signed in. The page **routes to sign-in** with a return path, so
 *     they come back here afterwards. It does not show an authentication error, because
 *     the answer to "you are not signed in" is "sign in", not a failure.
 *   - **409 `already_subscribed`** — the user is Pro after all: their plan landed
 *     between the page's read and this click. The page **swaps to the Pro state** and
 *     says so calmly. Showing a buy button to somebody who already pays is the failure
 *     this whole page is careful about, and the server has just told us the truth.
 *   - **anything else** — a calm inline line. **No modal**: the cap prompts follow the
 *     same rule (EXPERIENCE.md §3), and a pricing page that interrupts with a dialog
 *     would be arguing with itself.
 *
 * **The plan is the only thing sent.** The endpoint takes the plan and derives the
 * redirect URLs itself; nothing here names a URL, because a client that could name the
 * redirect target could send a paying user somewhere else.
 */
import { useRouter } from "next/navigation";
import { useState } from "react";

import { readApiError } from "@/lib/api-errors";
import { api } from "@/lib/backend-client";
import { signInUrl } from "@/lib/return-path";

export type BillingCycle = "monthly" | "yearly";

export type ChoosePlanButtonProps = {
  /** Which plan to buy. The endpoint's own enum, and nothing else. */
  cycle: BillingCycle;
  /**
   * Whether the visitor is signed in.
   *
   * **A signed-out visitor is routed to sign-in rather than refused.** The page is
   * public, so somebody who has never signed in can read it — and choosing a plan is
   * exactly the moment they want an account. So the button does not fail; it sends them
   * to sign in and back again.
   */
  signedIn: boolean;
  /**
   * Called when the server says the user already holds a live subscription.
   *
   * **The parent owns the tier state**, so it can swap the page into its Pro shape
   * rather than the button growing a second copy of the tier card.
   */
  onAlreadyPro?: () => void;
  /** The button's own label. The two states differ: "Continue to checkout" vs "Sign in to buy". */
  label?: string;
  /** The plan's price, for the signed-out button's label — "Sign in to buy Pro". */
  className?: string;
};

/**
 * The sign-in route, with a return path.
 *
 * **The `next` parameter is a path on this site**, and it is the only thing that goes
 * into the query string — so a signed-out visitor who signs in lands back on the pricing
 * page rather than at the digest home, and a paying intent is not lost.
 *
 * The path is built by `signInUrl()`, which encodes it, and the sign-in route guards it
 * again before using it — the open-redirect rules live in `lib/return-path.ts`.
 */
function signInPath(): string {
  return signInUrl("/pricing");
}

export function ChoosePlanButton({
  cycle,
  signedIn,
  onAlreadyPro,
  label,
  className,
}: ChoosePlanButtonProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  /**
   * A signed-out visitor goes to sign-in, and comes back here.
   *
   * **This is a redirect, not a failed purchase.** The page is public and the plan is
   * still theirs to buy; all that is missing is an account. So the button's failure mode
   * is the sign-in route, and the return path carries the intent.
   */
  if (!signedIn) {
    return (
      <a
        href={signInPath()}
        data-choose-plan="signed-out"
        className={className}
        onClick={(event) => {
          // A modified click (a new tab, a download) must not be swallowed by a
          // client-side navigation, so the plain anchor is left to do its job.
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
          event.preventDefault();
          router.push(signInPath());
        }}
      >
        {label ?? "Sign in to buy"}
      </a>
    );
  }

  const buy = async (): Promise<void> => {
    setBusy(true);
    setFailed(null);

    let response;
    try {
      response = await api.POST("/api/billing/checkout", { body: { plan: cycle } });
    } catch (thrown) {
      // The request never reached the API. The API said nothing, so the frontend's own
      // offline line is what there is to show.
      setFailed(readApiError(thrown).message);
      setBusy(false);
      return;
    }

    if (response.data) {
      // **The provider's page takes over.** The browser follows the URL; this component
      // is finished.
      window.location.assign(response.data.url);
      return;
    }

    const error = response.error;
    const status = response.response.status;

    if (status === 401) {
      // The session went away. Sign in, and come back here.
      router.push(signInPath());
      return;
    }

    if (status === 409 && error?.code === "already_subscribed") {
      // **They are Pro after all.** The plan landed between the page's read and this
      // click. The page swaps to its Pro shape.
      onAlreadyPro?.();
      setBusy(false);
      return;
    }

    // **Everything else is an inline line.** The API's own words where it gave any.
    setFailed(readApiError(error).message);
    setBusy(false);
  };

  return (
    <span className="flex flex-col gap-2">
      <button
        type="button"
        onClick={buy}
        disabled={busy}
        data-choose-plan="signed-in"
        className={className}
      >
        {busy ? "Opening checkout…" : (label ?? "Continue to checkout →")}
      </button>
      {failed ? (
        <p role="status" className="text-ink-muted [font:var(--type-scale-body-sm)]">
          {failed}
        </p>
      ) : null}
    </span>
  );
}
