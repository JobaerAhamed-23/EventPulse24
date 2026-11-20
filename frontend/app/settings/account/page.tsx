import { redirect } from "next/navigation";

import { DownloadMyData } from "@/components/settings/download-my-data";
import { PlanSummary } from "@/components/settings/plan-summary";
import { SettingsNav } from "@/components/settings/settings-nav";
import { SettingsStates } from "@/components/settings/settings-states";
import { AppShell } from "@/components/shell/app-shell";
import { readBillingAccount } from "@/lib/billing-account-read";
import { displayName } from "@/lib/display-name";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/settings/account` — **the plan, the portal, and Download my data**.
 *
 * These are one screen because they are one concern: the account itself, rather than what
 * it is configured to do. Splitting the export control from the billing state would mean
 * building this surface twice.
 *
 * **The plan is read from `Subscription`, never inferred from a feature.** A screen that
 * guessed the tier by checking whether some Pro capability worked would be wrong in exactly
 * the case that matters — a `past_due` account, which still has the capability and still
 * has a problem.
 *
 * **`past_due` is the state this screen exists for.** It is the only place in the product
 * where a failed payment becomes visible, and rendering such a user as plain "Free" would
 * hide a problem only they can fix. `GET /api/billing/account` carries `needs_payment`
 * precisely because `is_pro` cannot see it.
 *
 * **Download my data is not in a Pro block, and that is load-bearing.** `data-export`
 * settled that Article 20 is a right rather than a tier feature; putting the control inside
 * a Pro-only section would be the same gate wearing a layout, which this item's acceptance
 * criterion forbids by name.
 *
 * **The city is not here, and no longer has a signpost here either.** It was on this
 * screen because Browse's "Change city" link pointed at this route; it then moved to
 * `/settings/profile`, and a row saying so was left behind so that the link and anyone's
 * memory still landed somewhere useful. **A signpost is a cost that only pays while
 * something still points at it** — and the links were repointed at `/settings/profile`
 * with the move. What is left is a heading over a sentence over nothing, between the
 * plan and the export, on a screen whose subject is neither. So it is gone, and this
 * paragraph is the record that it was deliberate rather than dropped.
 *
 * **Cancellation is Stripe's.** No local cancel flow — it would be a second write path into
 * subscription state for the webhook to reconcile against.
 *
 * **It is an authed surface**, guarded the way the other `/settings/*` routes are.
 */
export const dynamic = "force-dynamic";

export default async function SettingsAccountPage() {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  // **An account screen for somebody who is not signed in would be offering to change a
  // plan that is not theirs.**
  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="" avatarUrl="">
        <SettingsStates />
      </AppShell>
    );
  }

  // **One read: the plan.** The city used to be named on this screen and is not any
  // more, so there is nothing else to ask for.
  const read = await readBillingAccount();

  const name = displayName(session.user);

  if (read.kind === "unavailable") {
    return (
      <AppShell
        name={name}
        email={session.user.email}
        avatarUrl={session.user.avatar_url}
      >
        <SettingsNav />

        <SettingsStates />
      </AppShell>
    );
  }

  const account = read.account;

  return (
    <AppShell
        name={name}
        email={session.user.email}
        avatarUrl={session.user.avatar_url}
      >
      <SettingsNav />

      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Account</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          Your plan, and your data.
        </p>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        <h2 className="text-ink-primary [font:var(--type-scale-headline-sm)]">Plan</h2>
        <div className="mt-6">
          <PlanSummary
            status={account.status}
            isPro={account.is_pro}
            needsPayment={account.needs_payment}
            hadPro={account.had_pro}
            periodEnd={account.period_end}
          />
        </div>
      </div>

      {/*
        **Its own section, at the same level as the plan.** Not nested under it, not
        conditional on it — see the module docstring.
      */}
      <div className="mt-12 max-w-(--layout-container-reading)">
        <h2 className="text-ink-primary [font:var(--type-scale-headline-sm)]">Your data</h2>
        <div className="mt-6">
          <DownloadMyData />
        </div>
      </div>
    </AppShell>
  );
}

