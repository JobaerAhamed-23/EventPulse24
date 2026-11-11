/**
 * The upgrade prompt at a tier cap — one component, every cap.
 *
 * **It is inline, and that is the whole design.** `EXPERIENCE.md` §3 pairs the approved
 * copy ("You saved one event today. Save more with Pro.") against the rejected one
 * ("LIMITED TIME: Upgrade now and get UNLIMITED saves!"), and the backend's payloads were
 * shaped to make the second hard to build: `calendar_connections.py` and `save_cap.py`
 * both state that the refusal carries `{cap, upgrade_hint}` and *"no `modal`, no `title`,
 * no `actions`, no `dismissable`"*. This component is the frontend half of that promise.
 *
 * So, deliberately:
 *
 * - **No `role="dialog"`, no `aria-modal`, no overlay, no portal.** It renders where the
 *   refusal happened, in the normal flow, and the surface behind it stays usable.
 * - **It does not take focus.** Nothing here is autofocused and nothing is a focus trap.
 *   The user was in the middle of something; a cap is not a reason to move their cursor.
 * - **No dismiss control.** The payload carries no `dismissable` field by design, so there
 *   is no dismissal to persist and no setting to invent. The prompt goes away when the
 *   state that produced it does.
 * - **`role="status"`, not `role="alert"`.** `alert` is assertive: it interrupts a screen
 *   reader mid-sentence. Hitting a tier ceiling is information, not an emergency. (This
 *   is a deliberate change from the `role="alert"` the onboarding cap block used.)
 *
 * **It takes no tier prop, and that is what makes "a Pro user never sees it" true.** The
 * component cannot be asked to render for a Pro user, because entitlement is not one of
 * its inputs: it renders a refusal the server sent, and the server does not refuse a Pro
 * user. There is no client-side tier flag to drift out of date — including immediately
 * after an upgrade, with no reload, since the next request simply is not refused.
 *
 * **The sentence is the server's.** It is rendered verbatim, never edited, interpolated or
 * chosen between; `cap` is deliberately not rendered, because the server's sentence
 * already says what it needs to say about the number.
 */

export type UpgradePromptProps = {
  /** The server's `upgrade_hint`, shown as it arrived. */
  hint: string;
  /** Extra layout classes from the call site. Spacing is the surface's business. */
  className?: string;
};

/** Where "Upgrade" goes. The pricing page is the one place that sells anything. */
export const UPGRADE_HREF = "/pricing";

export function UpgradePrompt({ hint, className = "" }: UpgradePromptProps) {
  return (
    <div
      role="status"
      className={`rounded-card border border-border-subtle bg-surface-subtle px-4 py-3 ${className}`.trim()}
    >
      <p className="[font:var(--type-scale-body-sm)] text-ink-secondary">{hint}</p>
      <a
        href={UPGRADE_HREF}
        className="mt-1 inline-block [font:var(--type-scale-body-sm)] text-accent-terracotta underline underline-offset-4"
      >
        Upgrade
      </a>
    </div>
  );
}
