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
      <AppShell name="" email="">
        <SettingsStates />
      </AppShell>
    );
  }

  const read = await readBillingAccount();

  const name = displayName(session.user);

  if (read.kind === "unavailable") {
    return (
      <AppShell name={name} email={session.user.email}>
        <SettingsNav />

        <SettingsStates />
      </AppShell>
    );
  }

  const account = read.account;

  return (
    <AppShell name={name} email={session.user.email}>
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

