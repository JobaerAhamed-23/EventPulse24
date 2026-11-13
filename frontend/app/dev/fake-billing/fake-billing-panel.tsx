"use client";

/**
 * The shared harness for the fake billing pages (FR-48).
 *
 * **This is a development stand-in, and it says so on the screen.** It stands in for the
 * payment provider's hosted checkout and customer portal so the local paid path can be
 * walked end to end: `FakeBillingAdapter` mints a URL under `/dev/fake-billing`, and this
 * is what that URL opens.
 *
 * **It is not the pricing page.** `pricing-page-desktop.html` is a design surface and it
 * lives at `/pricing`; this lives under `/dev/`, is `notFound()` in a production build,
 * and is styled as a harness. It must never be mistaken for the thing a user pays
 * through.
 *
 * **Completing a checkout here grants nothing.** That is not an oversight — it is the
 * point. Entitlement moves only when the provider's webhook lands, so a fake page that
 * granted Pro on a click would be teaching the wrong lesson about how the product works.
 * The panel says so, and the end-to-end proof posts the fake webhook instead.
 */
import Link from "next/link";

/** What a fake checkout session carries in its query string. */
export type FakeCheckoutParams = {
  /** The provider's session id. Echoed back so the page can name it. */
  session?: string;
  /** Which plan is being bought. */
  plan?: string;
  /** Where the provider would send the user on success. */
  next?: string;
};

/** The plan's display name, as the pricing page spells it. */
const PLAN_LABELS: Record<string, string> = {
  monthly: "Pro monthly",
  yearly: "Pro yearly",
};

/** The price, as the pricing page spells it. */
const PLAN_PRICES: Record<string, string> = {
  monthly: "$4.99/month",
  yearly: "$49/year",
};

/**
 * The plan's label, falling back to the raw value.
 *
 * A plan this page does not recognise is shown as it arrived rather than hidden: a
 * developer staring at a wrong value learns something, and a developer staring at an
 * empty page does not.
 */
function planLabel(plan: string | undefined): string {
  if (!plan) return "Unknown plan";
  return PLAN_LABELS[plan] ?? plan;
}

function planPrice(plan: string | undefined): string {
  if (!plan) return "";
  return PLAN_PRICES[plan] ?? "";
}

/**
 * The return target, if it is a path on this site.
 *
 * **The same rule the backend enforces, applied to a query string.**
 *
 * The backend derives its success URL from configuration and hands it to the adapter;
 * the adapter puts it in this page's query string. But a query string is
 * attacker-controllable by anyone who can hand a developer a link, and this page turns
 * `next` into the target of a link the user clicks. Left unguarded, `?next=https://
 * attacker.example` sends the user off-site — the classic open-redirect, in the one place
 * this project has been careful to refuse it.
 *
 * So the value is honoured only when it names a path on this origin. The backend's own
 * success URL is an absolute one (`http://localhost:3000/settings/account?…`), so it is
 * reduced to its path and query here rather than rejected — the point is *where it
 * points*, not *how it is spelled*.
 *
 * A target that is neither a path nor a same-origin URL is refused outright, and the page
 * says so rather than rendering a link that goes somewhere unexpected.
 */
function localTarget(next: string | undefined): string | undefined {
  if (!next) return undefined;
  if (next.startsWith("/")) return next;
  try {
    const url = new URL(next);
    // Same origin only: a different host is a different site, whatever it is called.
    const here = window.location.origin;
    return url.origin === here ? `${url.pathname}${url.search}${url.hash}` : undefined;
  } catch {
    return undefined;
  }
}

/**
 * The banner every fake page carries.
 *
 * **It is visible, not a footnote.** A stand-in that looks like a real payment screen is
 * a stand-in somebody will screenshot into a bug report.
 */
function DevBanner() {
  return (
    <p className="mb-6 rounded-card border border-accent-amber/45 bg-accent-amber/10 px-4 py-3 text-ink-secondary [font:var(--type-scale-meta-md)]">
      <strong className="font-semibold text-ink-primary">Development stand-in.</strong> This page
      stands in for the payment provider. No money moves here, and completing a checkout does not
      grant Pro — the provider&apos;s webhook is what does that.
    </p>
  );
}

/**
 * The fake checkout page.
 *
 * **Two outcomes, both walkable.** "Complete" and "Cancel" are the two paths a real
 * provider offers, and both are reachable from here, so the local paid path and the local
 * abandoned-checkout path can both be exercised.
 *
 * **The "Complete" button does not grant Pro.** It says where the user would land, and it
 * explains that the webhook is what flips entitlement. Granting here would make the local
 * flow disagree with the real one, and the disagreement would only show up in production.
 */
export function FakeCheckoutPanel({ session, plan, next }: FakeCheckoutParams) {
  const success = localTarget(next) ?? "";

  return (
    <main className="fade-in mx-auto max-w-(--layout-container-reading) px-6 py-20">
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        Checkout · {planLabel(plan)}
      </h1>

      <DevBanner />

      <dl className="mt-8 rounded-card border border-border-subtle bg-surface-elevated p-4">
        <div className="flex flex-wrap gap-2 border-b border-border-subtle pb-3">
          <dt className="w-20 text-ink-muted [font:var(--type-scale-meta-md)]">Plan</dt>
          <dd className="text-ink-primary [font:var(--type-scale-body-md)]">
            {planLabel(plan)}
            {planPrice(plan) ? ` · ${planPrice(plan)}` : ""}
          </dd>
        </div>
        <div className="flex flex-wrap gap-2 border-b border-border-subtle py-3">
          <dt className="w-20 text-ink-muted [font:var(--type-scale-meta-md)]">Session</dt>
          <dd className="font-mono break-all text-ink-secondary [font:var(--type-scale-meta-md)]">
            {session ?? "none"}
          </dd>
        </div>
        <div className="flex flex-wrap gap-2 pt-3">
          <dt className="w-20 text-ink-muted [font:var(--type-scale-meta-md)]">Returns to</dt>
          <dd className="font-mono break-all text-ink-secondary [font:var(--type-scale-meta-md)]">
            {success || "none"}
          </dd>
        </div>
      </dl>

      <div className="mt-8 flex flex-wrap gap-3">
        {/*
          The "Complete" action.
          *
          **It navigates to the success URL rather than granting anything.** `next` is the
          URL the backend configured, so following it is exactly what the browser does
          after a real checkout — and the user comes back a Free user, because no webhook
          has landed. That is the honest local simulation.
          */}
        {success ? (
          <a
            href={success}
            className="inline-flex min-h-[44px] items-center rounded-control bg-accent-terracotta px-4 py-2 font-semibold text-ink-inverse [font:var(--type-scale-meta-md)]"
          >
            Complete checkout
          </a>
        ) : (
          <span className="text-ink-muted [font:var(--type-scale-meta-md)]">
            No return URL on this session.
          </span>
        )}

        {/*
          The "Cancel" action. It goes nowhere in particular: the local abandoned-checkout
          path only needs to be walkable, and the backend's cancel URL is the same
          settings route with a different flag.
          */}
        <Link
          href="/settings/account?checkout=cancelled"
          className="inline-flex min-h-[44px] items-center rounded-control border border-border-strong px-4 py-2 font-semibold text-ink-secondary [font:var(--type-scale-meta-md)]"
        >
          Cancel
        </Link>
      </div>

      <p className="mt-6 text-ink-muted [font:var(--type-scale-meta-md)]">
        To make this user Pro, post the fake webhook:{" "}
        <code className="font-mono text-ink-secondary">POST /api/webhooks/billing</code> with the
        body <code className="font-mono text-ink-secondary">fake-signature</code> and a{" "}
        <code className="font-mono text-ink-secondary">subscription_started</code> event.
      </p>
    </main>
  );
}

/**
 * The fake customer portal.
 *
 * **The provider's own portal is where a paying user cancels.** This stand-in has to offer
 * the same choice, or the local path cannot exercise the cancellation that item 2's
 * webhook then acts on.
 */
export function FakePortalPanel({ next }: FakeCheckoutParams) {
  const returnTo = localTarget(next) ?? "";

  return (
    <main className="fade-in mx-auto max-w-(--layout-container-reading) px-6 py-20">
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Customer portal</h1>

      <DevBanner />

      <p className="mt-6 text-ink-secondary [font:var(--type-scale-body-md)]">
        The provider&apos;s portal is where a paying user changes their plan, updates their card, or
        cancels. This stand-in offers the same choice.
      </p>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          href="/settings/account?portal=closed"
          className="inline-flex min-h-[44px] items-center rounded-control border border-border-strong px-4 py-2 font-semibold text-ink-secondary [font:var(--type-scale-meta-md)]"
        >
          Close the portal
        </Link>
        <Link
          href="/settings/account?portal=cancelled"
          className="inline-flex min-h-[44px] items-center rounded-control bg-accent-terracotta px-4 py-2 font-semibold text-ink-inverse [font:var(--type-scale-meta-md)]"
        >
          Cancel the subscription
        </Link>
      </div>

      <p className="mt-6 text-ink-muted [font:var(--type-scale-meta-md)]">
        {returnTo ? (
          <>
            The provider would return you to{" "}
            <code className="font-mono text-ink-secondary">{returnTo}</code>.
          </>
        ) : (
          "This portal session carries no return URL."
        )}
      </p>
    </main>
  );
}
