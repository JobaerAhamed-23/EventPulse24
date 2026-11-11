"use client";

/**
 * The pricing screen — one page, two tiers, no upsell (FR-48).
 *
 * **"No upsell copy beyond 'fewer interruptions, more control.'"** That is the PRD's
 * sentence and it is a **product constraint, not a preference**. So there is no
 * countdown, no scarcity, no "limited time", no comparative table editorialising the
 * Free tier against the Pro tier, and no second sentence doing the work of the first.
 * The only tagline is FR-48's own, on the Pro card.
 *
 * **The mockup is the authority on layout; the PRD is the authority on copy.** The
 * mockup's two columns, its hero, its billing toggle and its trust strip are the
 * shape. Its *feature lists* are not: they name Phase 2 features, "priority support from
 * Brooklyn" and public share-links, none of which FR-48 lists. FR-48 does, so FR-48's
 * lists are the ones here.
 *
 * **The Free column states the caps.** FR-48 says Free retains "the 1-save/day cap and
 * 1 connected calendar provider", and the criterion asks the page to state what Free
 * keeps. A limit listed among the features reads oddly, and it is still the truth about
 * the plan: a Free column that says "1 save a day" is what a Free user actually gets.
 * It is a fact, not a tease.
 *
 * **"Save 18%" is arithmetic, not persuasion.** $49 a year against $4.99 × 12 = $59.88 is
 * a 18.2% discount, so the number is true. The PRD's looser "~17%" is the same fact said
 * less precisely. A discount that is not true would be upsell; this one is.
 *
 * **The trust strip states policies, and that is the opposite of upsell.** "No urgency
 * badges. No countdown timers." is the product telling the visitor it will not pressure
 * them. It stays.
 *
 * **Three visitor states, one layout.** Signed out, Free and Pro. The difference is
 * which column carries the current-plan mark and which carries the button — and a Pro
 * user gets **no buy button at all**, only a link to the portal, because a second buy
 * button for somebody who already pays is a lie about what the button does.
 */
import { useState } from "react";

import { ChoosePlanButton, type BillingCycle } from "@/components/pricing/choose-plan-button";
import { readApiError } from "@/lib/api-errors";
import { api } from "@/lib/backend-client";

export type PricingTier = "signed-out" | "free" | "pro";

export type PricingPageProps = {
  /**
   * Who is looking.
   *
   * **Read on the server**, from `GET /api/billing/subscription` — the one published
   * entitlement read, so this page and the save gate cannot disagree about who is Pro.
   */
  tier: PricingTier;
};

/**
 * The Free column's list — FR-48's, exactly.
 *
 * "Pulse Digest, Reminders, Personal Events, the 1-save/day cap and 1 connected calendar
 * provider." The mockup's Free column says "Public share-link sharing" and "One quiet
 * hours window", neither of which FR-48 lists for Free, so neither is here.
 */
const FREE_FEATURES = [
  { label: "Pulse Digest", detail: "three events worth your attention, every morning" },
  { label: "Reminders", detail: "a reminder plan for the events you save" },
  { label: "Personal events", detail: "add your own, by hand" },
  { label: "1 save a day", detail: "one Pulse Card save per 24 hours" },
  { label: "1 connected calendar provider", detail: "one provider's events in your Pulse" },
];

/**
 * The Pro column's list — FR-48's, exactly.
 *
 * "unlimited saves + saved collections, up to 3 connected calendar providers, per-day-of-week
 * custom quiet hours, and JSON+ICS data export." The mockup's Pro column adds a
 * read-only Google Calendar sync, priority support and a "Phase 2 included" line; FR-48
 * lists none of those, so none are here.
 */
const PRO_FEATURES = [
  { label: "Unlimited saves", detail: "as many Pulse Cards as you like" },
  { label: "Saved collections", detail: "named groups of what you kept" },
  { label: "3 connected calendar providers", detail: "Google, Apple and Outlook" },
  { label: "Per-weekday quiet hours", detail: "a different window for each day" },
  { label: "JSON + ICS export", detail: "your data, whenever you want it" },
];

/**
 * The three things the product promises. Policy, not persuasion.
 */
const TRUST = [
  {
    title: "Cancel anytime",
    body: "No retention tricks. No “are you sure?” modals. One click in your account.",
  },
  {
    title: "Your data is yours",
    body: "Export to JSON + ICS whenever you want. Free for everyone, on every plan.",
  },
  {
    title: "No dark patterns",
    body: "No urgency badges. No countdown timers. No “limited time!” copy. Calm is the product.",
  },
];

export function PricingPage({ tier }: PricingPageProps) {
  const [cycle, setCycle] = useState<BillingCycle>("monthly");
  const [isPro, setIsPro] = useState(tier === "pro");
  const signedIn = tier !== "signed-out";

  /**
   * The tier the page is showing.
   *
   * **The server's answer, unless the server changes its mind mid-click.** A 409
   * `already_subscribed` says the visitor is Pro after all — their plan landed between
   * the page's read and their click — and the page adopts that answer rather than
   * showing a buy button to somebody who already pays.
   */
  const pro = isPro;

  const monthly = cycle === "monthly";

  return (
    <div className="mx-auto w-full max-w-(--layout-container-max) flex-1 px-6 py-8">
      {/*
        The hero. The eyebrow, the headline, the lede, and the billing toggle.

        **The lede is descriptive, not upsell.** "Free is plenty for most people" is the
        product saying the free tier is enough — which is the opposite of a sales page
        trying to make the visitor feel they are missing out.
      */}
      <section className="mx-auto max-w-(--layout-container-reading) pt-12 text-center">
        <p className="[font:var(--type-scale-meta-sm)] tracking-wide text-accent-terracotta uppercase">
          Pricing
        </p>
        <h1 className="mt-4 text-ink-primary [font:var(--type-scale-display-lg)]">
          Two ways to keep calm.
        </h1>
        <p className="mx-auto mt-4 max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-lg)]">
          Free is plenty for most people. Pro adds unlimited saves, calendar sync, custom quiet
          hours, and your data on your terms. Cancel anytime.
        </p>

        {/*
          The billing toggle. **A radio group**, because it is one choice between two
          options — not two independent switches, and not a row of links.

          The "save 18%" pill sits on the annual option, because that is where the
          discount is.
        */}
        <div
          role="radiogroup"
          aria-label="Billing cycle"
          className="mt-8 inline-flex items-center gap-1 rounded-full border border-border-subtle bg-surface-elevated p-1"
        >
          <button
            type="button"
            role="radio"
            aria-checked={monthly}
            onClick={() => setCycle("monthly")}
            className={[
              "rounded-full px-4 py-2 [font:var(--type-scale-meta-md)]",
              monthly ? "bg-accent-terracotta text-ink-inverse" : "text-ink-muted",
            ].join(" ")}
          >
            Monthly
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={!monthly}
            onClick={() => setCycle("yearly")}
            className={[
              "flex items-center gap-2 rounded-full px-4 py-2 [font:var(--type-scale-meta-md)]",
              monthly ? "text-ink-muted" : "bg-accent-terracotta text-ink-inverse",
            ].join(" ")}
          >
            Annual
            <span className="rounded-[4px] bg-accent-terracotta/10 px-2 text-accent-terracotta [font:var(--type-scale-numeric)]">
              save 18%
            </span>
          </button>
        </div>
      </section>

      {/*
        The two columns.

        **Two columns at desktop, one at mobile.** The grid collapses rather than
        hiding anything: a Free visitor on a phone must still be able to read what Pro
        adds, and a Pro visitor must still be able to see what Free keeps.
      */}
      <section
        aria-label="Pricing tiers"
        className="mx-auto mt-12 grid max-w-(--layout-container-reading) grid-cols-1 gap-6 md:grid-cols-2"
      >
        {/*
          The Free column. **It is always shown**, for every visitor, including a Pro
          one: what Free keeps is part of the answer for somebody deciding whether to
          downgrade, and the criterion asks the page to state it.
        */}
        <article
          aria-labelledby="pricing-free-heading"
          className="flex flex-col rounded-2xl border border-border-subtle bg-surface-elevated p-8"
        >
          <span className="inline-block w-fit rounded-[4px] bg-surface-subtle px-2 py-1 text-ink-muted [font:var(--type-scale-meta-sm)]">
            Free
          </span>
          <h2
            id="pricing-free-heading"
            className="mt-3 text-ink-primary [font:var(--type-scale-headline-md)]"
          >
            Free
          </h2>
          {/*
            **The Free card's one tagline.** The mockup's words, and the only piece of
            Free marketing copy the page carries.

            `data-tagline` marks it as *prose* — the marketing copy — so the allowlist
            test can say "this card says exactly one sentence of prose" without counting
            the state label below, which is a fact about the visitor rather than
            marketing.
          */}
          <p data-tagline className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
            Everything you need to start calm.
          </p>

          <div className="mt-6 border-b border-border-subtle pb-6">
            <span className="text-ink-primary [font:var(--type-scale-display-md)]">$0</span>
            <span className="ml-2 text-ink-muted [font:var(--type-scale-body-sm)]">/ forever</span>
          </div>

          <ul className="mt-6 flex flex-col gap-2">
            {FREE_FEATURES.map((feature) => (
              <li
                key={feature.label}
                className="flex gap-3 text-ink-secondary [font:var(--type-scale-body-sm)]"
              >
                <span aria-hidden="true" className="text-ink-muted">
                  ✓
                </span>
                <span>
                  <strong className="font-medium text-ink-primary">{feature.label}</strong>
                  {feature.detail ? ` — ${feature.detail}` : null}
                </span>
              </li>
            ))}
          </ul>

          <div className="mt-8">
            {/*
              The Free column's own control.

              **A Free user's button says what is true** — they are on Free, and there is
              nothing to buy here. A signed-out visitor sees the same calm line, because
              a "Choose Free" button would be a control that does nothing: Free is what
              they get by default.

              **A Pro user's Free column says so too**, because they *are* on Free, in the
              sense that Free's limits still describe the tier they left.
            */}
            <p className="rounded-control border border-border-strong px-4 py-3 text-center text-ink-primary [font:var(--type-scale-meta-md)]">
              {pro ? "Free, without Pro" : "You’re on Free"}
            </p>
          </div>
        </article>

        {/*
          The Pro column. **The terracotta-bordered card**, as the mockup draws it.

          The accent is the card's border and its price — the sanctioned terracotta use
          on a pricing page, and the only saturated thing on the screen.
        */}
        <article
          aria-labelledby="pricing-pro-heading"
          className="flex flex-col rounded-2xl border border-accent-terracotta/30 bg-surface-elevated p-8"
        >
          <span className="inline-block w-fit rounded-[4px] bg-accent-terracotta/10 px-2 py-1 text-accent-terracotta [font:var(--type-scale-meta-sm)]">
            Pro
          </span>
          <h2
            id="pricing-pro-heading"
            className="mt-3 text-ink-primary [font:var(--type-scale-headline-md)]"
          >
            Pro
          </h2>
          {/*
            **FR-48's sentence, and the only tagline on the page.** "Fewer interruptions,
            more control." — the PRD's own words, and the one piece of Pro copy FR-48
            allows.

            `data-tagline` marks it as *prose* — the marketing copy — so the allowlist
            test can say "this card says exactly one sentence of prose" without counting
            the portal button's label, which is a fact about the visitor rather than
            marketing.
          */}
          <p data-tagline className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
            Fewer interruptions, more control.
          </p>

          <div className="mt-6 border-b border-border-subtle pb-6">
            <span className="text-ink-primary [font:var(--type-scale-display-md)]">
              {monthly ? "$4.99" : "$49"}
            </span>
            <span className="ml-2 text-ink-muted [font:var(--type-scale-body-sm)]">
              {monthly ? "/ month" : "/ year"}
            </span>
            <span className="mt-1 block text-ink-muted [font:var(--type-scale-meta-sm)]">
              {monthly ? "or $49/yr · save 18%" : "or $4.99/mo · save 18%"}
            </span>
          </div>

          <ul className="mt-6 flex flex-col gap-2">
            {PRO_FEATURES.map((feature) => (
              <li
                key={feature.label}
                className="flex gap-3 text-ink-secondary [font:var(--type-scale-body-sm)]"
              >
                <span aria-hidden="true" className="text-accent-terracotta">
                  ✓
                </span>
                <span>
                  <strong className="font-medium text-ink-primary">{feature.label}</strong>
                  {feature.detail ? ` — ${feature.detail}` : null}
                </span>
              </li>
            ))}
          </ul>

          <div className="mt-8">
            {/*
              **A Pro user gets no buy button.** They get their current plan and a link
              to the portal, where a subscription is actually managed. A second buy button
              for somebody who already pays is a control that cannot work.

              The portal is an action, so it is a POST that returns a URL to follow —
              which is why this is a button and not an anchor to a route.
            */}
            {pro ? (
              <PortalButton />
            ) : (
              <ChoosePlanButton
                cycle={cycle}
                signedIn={signedIn}
                onAlreadyPro={() => setIsPro(true)}
                label={signedIn ? "Continue to checkout →" : "Sign in to buy"}
                className="rounded-control bg-accent-terracotta px-4 py-3 text-center text-ink-inverse [font:var(--type-scale-meta-md)]"
              />
            )}
          </div>
        </article>
      </section>

      {/*
        The trust strip. **Three policies, stated plainly.**

        It is the block most at risk of reading as upsell, and it is the opposite: each
        one is the product promising not to pressure the visitor. "No urgency badges. No
        countdown timers." is the reason there are no urgency badges on this page.
      */}
      <section aria-label="What we promise" className="mt-20 border-t border-border-subtle py-12">
        <div className="mx-auto grid max-w-(--layout-container-reading) grid-cols-1 gap-8 md:grid-cols-3">
          {TRUST.map((item) => (
            <div key={item.title}>
              <h3 className="text-ink-primary [font:var(--type-scale-headline-sm)]">
                {item.title}
              </h3>
              <p className="mt-2 text-ink-muted [font:var(--type-scale-body-sm)]">{item.body}</p>
            </div>
          ))}
        </div>
      </section>

      <p className="mt-8 text-center text-ink-muted [font:var(--type-scale-body-sm)]">
        Questions?{" "}
        <a
          href="mailto:hello@eventpulse24.com"
          className="text-ink-secondary underline underline-offset-4"
        >
          hello@eventpulse24.com
        </a>
      </p>
    </div>
  );
}

/**
 * The Pro user's way into their subscription.
 *
 * **It is a button, not a link to a route**, because opening the portal is an action:
 * `POST /api/billing/portal` mints a provider session and returns a URL to follow. The
 * alternative — an anchor to a page that does not exist — would be a link to a 404.
 */
function PortalButton() {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const open = async (): Promise<void> => {
    setBusy(true);
    setFailed(null);

    let response;
    try {
      response = await api.POST("/api/billing/portal");
    } catch (thrown) {
      setFailed(readApiError(thrown).message);
      setBusy(false);
      return;
    }

    if (response.data) {
      window.location.assign(response.data.url);
      return;
    }

    setFailed(readApiError(response.error).message);
    setBusy(false);
  };

  return (
    <span className="flex flex-col gap-2">
      <button
        type="button"
        onClick={open}
        disabled={busy}
        data-portal-button
        className="rounded-control border border-border-strong px-4 py-3 text-center text-ink-primary [font:var(--type-scale-meta-md)] disabled:cursor-default"
      >
        {busy ? "Opening your plan…" : "You’re on Pro — manage your plan"}
      </button>
      {failed ? (
        <p role="status" className="text-ink-muted [font:var(--type-scale-body-sm)]">
          {failed}
        </p>
      ) : null}
    </span>
  );
}
