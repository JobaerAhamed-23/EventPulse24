"use client";

/**
 * The **share control** — FR-28's sender side, on one component (FR-28, EXPERIENCE.md
 * §964).
 *
 * **One control, two surfaces, one behaviour.** The Pulse Card and the Detail Screen
 * both use it, and they must produce the *same* URL — a friend who opens the link from
 * one is on the same page as a friend who opens it from the other. The URL itself is
 * built in `lib/share-link.ts`, which is the only place it is built at all.
 *
 * **What it shares is the public page.** `/events/{slug}` — FR-26's page, which carries
 * its Open Graph metadata (so the unfurl is rich) and its "Save to Pulse →" CTA (so a
 * recipient with no account has somewhere to go). **Never `/events/{uuid}`** — that is
 * the signed-in Detail Screen, and a friend who opened it would meet a sign-in wall
 * instead of the event. That mistake existed here before this component did: the
 * Detail Screen's button shared `window.location.href`, which on that screen *is* the
 * uuid.
 *
 * **The Web Share API where it exists, the clipboard everywhere else.** `EXPERIENCE.md`
 * names the Web Share API as the platform capability for FR-28. A browser that has it
 * gets the native sheet — the user picks the app, and the app does the rest. A browser
 * that does not gets a copy to the clipboard, and the control **says so**, because
 * "I copied it" and "I shared it" are different claims and the user needs to know which
 * one happened.
 *
 * **A cancelled share sheet is not a failure.** The user dismissed it; that is their
 * choice, not an error, and reporting it as one would be a lie about their own action.
 * So a cancellation says **nothing at all** — and any other failure falls through to
 * the clipboard, because the sheet not opening is no reason the link cannot still be
 * copied.
 *
 * **The confirmation is shown *and* announced.** It is a **bare `aria-live="polite"`
 * region, never a second `role="status"`**: the digest page owns the page's
 * `role="status"` and the Detail Screen's action row owns one for the conflict
 * failure, and two status regions on a surface would make "which one is the page
 * talking?" a question the DOM cannot answer. This is the rule
 * `components/add-event-button.tsx` already follows, for the same reason.
 *
 * **A visible label, never an icon-only button** (WCAG 1.1.1, as this repo reads it —
 * see the Source Badge's own docstring). There is no icon library in the product
 * (`DESIGN.md`: "UI system: None"), and a share icon with no label would fail the rule
 * that every other control here passes.
 */
import { useCallback, useState } from "react";

import { publicEventUrl, shareOrigin } from "@/lib/share-link";

/**
 * How the control looks.
 *
 * **The weight is the surface's, not the behaviour's.** `EXPERIENCE.md` §4 puts the
 * Detail Screen's three buttons in *`Button.Secondary` weight*, and the mockup's card
 * actions are the small bordered ghost button. Same affordance, each at its own
 * surface's specified weight — and the same tokens either way.
 */
export type ShareWeight = "secondary" | "card";

export type ShareControlProps = {
  /** The event's minted public slug. Never its id. */
  slug: string;
  /** The event's own title — the Web Share payload's title. */
  title: string;
  /**
   * The site's public origin, resolved on the server.
   *
   * **`PUBLIC_SITE_URL` has no `NEXT_PUBLIC_` prefix**, so a client component cannot
   * read it — the server resolves it (`lib/site-url.ts`) and passes it down. When it is
   * absent, the browser's own origin is the fallback.
   */
  origin?: string | null;
  /** The surface's weight. */
  weight?: ShareWeight;
};

/** What the control last said. */
type Message = "shared" | "copied" | "failed";

/**
 * The message each outcome shows.
 *
 * **Three claims, and they are different claims.** "Shared" means the native sheet
 * took it; "Copied" means the link is on the clipboard; "Couldn't copy" means neither
 * happened. The confirmation must never claim a copy that did not happen.
 */
const MESSAGES: Record<Message, string> = {
  shared: "Shared.",
  copied: "Link copied.",
  failed: "Couldn't copy the link. Try again.",
};

/**
 * Whether an error is the user closing the share sheet.
 *
 * **The browser's own name, not the error's type.** `navigator.share` rejects with an
 * `AbortError` when the sheet is dismissed, and the rejection's *type* is not
 * dependable across browsers — the *name* is.
 */
function isAbort(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name?: unknown }).name === "AbortError"
  );
}

/** The control's class names, per weight. */
function weightClasses(weight: ShareWeight): string {
  if (weight === "card") {
    // **The card's own density** — the mockup's `.ghostbtn` (a bordered, ink-secondary
    // action) and the Preview card's Save button, which is the same treatment.
    //
    // **`min-h-[44px]` is the tap target**, the same floor the card's Source Badge
    // button uses. The card is a touch surface first, and a 36px control on a phone is
    // a miss.
    return "inline-flex min-h-[44px] items-center rounded-control border border-border-subtle px-4 py-2 text-ink-secondary [font:var(--type-scale-meta-md)]";
  }
  // **The Detail Screen's existing Share button, unchanged.** `DESIGN.md`
  // `component.button.secondary`: a subtle fill, a 1px subtle stroke, ink.secondary
  // label, spacing.3 × spacing.6. (px-6 py-3 on the meta scale is already 44px tall.)
  return "rounded-control border border-border-subtle bg-surface-elevated px-6 py-3 text-ink-secondary [font:var(--type-scale-meta-md)]";
}

export function ShareControl({
  slug,
  title,
  origin = null,
  weight = "secondary",
}: ShareControlProps) {
  const [message, setMessage] = useState<Message | null>(null);

  const onShare = useCallback(async () => {
    // **A new attempt clears the last one's message.** The line is about the last
    // attempt, and a line saying "Link copied." next to a button the user has just
    // pressed again would be a claim about an attempt they have not made yet.
    setMessage(null);

    // **The URL is built once, here and in one module.** `shareOrigin` prefers the
    // configured origin and falls back to the browser's own — so in a browser this is
    // always an absolute URL, which is what a pasted link has to be.
    const url = publicEventUrl(slug, shareOrigin(origin));

    if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
      try {
        await navigator.share({ title, url });
        setMessage("shared");
        return;
      } catch (error) {
        // **A cancelled sheet says nothing**, and any other failure falls through to
        // the clipboard: the sheet not opening is no reason the link cannot be copied.
        if (isAbort(error)) return;
      }
    }

    // **The clipboard path.** The API's *absence* is a failure, not a copy — claiming a
    // copy that did not happen is the one thing this confirmation must never do.
    const clipboard = typeof navigator !== "undefined" ? navigator.clipboard : undefined;
    if (!clipboard?.writeText) {
      setMessage("failed");
      return;
    }

    try {
      await clipboard.writeText(url);
      setMessage("copied");
    } catch {
      setMessage("failed");
    }
  }, [slug, title, origin]);

  return (
    // **A `<div>`, not a `<span>`.** The confirmation below is a `<p>`, and a `<p>` is
    // flow content while a `<span>` may hold only phrasing content — a `<p>` inside a
    // `<span>` is invalid HTML. The codebase's own precedent for the same shape is
    // `components/add-event-button.tsx`, which wraps its live region in a `<div>` too.
    <div className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={onShare}
        // **The accessible name names the event**, and it *contains* the visible label
        // ("Share") — WCAG 2.5.3's "label in name" rule. On a digest of three cards,
        // three buttons all named "Share" would tell a screen-reader user nothing about
        // which event they are about to share.
        aria-label={`Share ${title}`}
        className={weightClasses(weight)}
      >
        Share
      </button>

      {/*
        The confirmation. **A bare live region, not a `role="status"`** — the digest's
        own "ready" line and the Detail Screen's conflict-failure line are the surfaces'
        status regions, and they stay the only ones there are.

        **It is always in the DOM**, even when it says nothing. A live region that is
        added to the page together with its text is not announced reliably; a region
        that is already there and then changes is.
      */}
      <p aria-live="polite" className="text-ink-muted [font:var(--type-scale-meta-sm)]">
        {message ? MESSAGES[message] : null}
      </p>
    </div>
  );
}
