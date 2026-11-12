import type { Metadata } from "next";

import { BrandTopbar } from "@/components/brand-topbar";
import { PreAuthFooter } from "@/components/pre-auth/pre-auth-footer";
import { PricingPage, type PricingTier } from "@/components/pricing/pricing-page";
import { api } from "@/lib/backend-client";
import { getSession, sessionHeaders, type Session } from "@/lib/session";

/**
 * `/pricing` — the pricing screen (FR-48).
 *
 * **The page is public.** A signed-out visitor can read it, and choosing a plan routes
 * them to sign-in rather than raising an authentication error. So it uses the **pre-auth
 * frame** — the brand topbar and the pre-auth footer — not `AppShell`, which is the
 * signed-in frame with the sidenav.
 *
 * **The tier is read on the server, from the one entitlement read.** `getSession()`
 * answers *who* is asking; `GET /api/billing/subscription` answers *whether they are
 * Pro*. Both are needed, and neither can be derived from the other: a signed-out visitor
 * has no session, and a signed-in Free user has a session and no entitlement.
 *
 * **The entitlement read is skipped for an anonymous visitor**, because there is nobody
 * to read it for — the endpoint would answer 401 — and because asking would be a
 * pointless request. The tier is then `signed-out`, which is the first of the three
 * states rather than an error.
 *
 * **An unavailable session is not folded into "signed out".** The API could not answer
 * who is asking; the page still has to render, and a page that fails to render because
 * the API blinked would be a worse answer than a page that shows its tiers. But the page
 * does not *claim* the visitor is signed out — `lib/session.ts` is explicit that
 * "sending a signed-in user to the anonymous preview because the API blinked would be a
 * lie about who they are", and "Sign in to buy" would be that lie in a button. So the
 * page shows the tiers and the checkout button, and the checkout says what is true.
 *
 * **It is rendered per request**, because it depends on the session: a prerendered page
 * would bake one visitor's tier into a page whose whole job is to tell them apart.
 */
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Two ways to keep calm. Free and Pro, $4.99/month or $49/year.",
};

export default async function PricingRoute() {
  const session = await getSession();
  const tier = await readTier(session);

  return (
    <div className="flex min-h-screen flex-col">
      <BrandTopbar />
      {/*
        `<main>`, as `/preview` has it. The page's content is the main landmark, and a
        screen-reader user navigating by landmark should find it.
      */}
      <main className="flex flex-1 flex-col">
        <PricingPage tier={tier} />
      </main>
      <PreAuthFooter current="/pricing" />
    </div>
  );
}

/**
 * Which of the three states this visitor is in.
 *
 * **Signed out is a state, not a failure.** The page is public, so somebody who has
 * never signed in reads it exactly as a signed-in Free user does — they just cannot buy
 * a plan without an account.
 *
 * **An unavailable session is not the same as an anonymous one, and the difference
 * shows.** `lib/session.ts` is explicit about this: *"sending a signed-in user to the
 * anonymous preview because the API blinked would be a lie about who they are."* So the
 * page still renders — a page that fails because the API blinked is worse — but it does
 * not claim the visitor is signed out. It shows the tiers and offers the checkout
 * button, and the checkout itself will say what is true: a 401 sends them to sign-in, a
 * 409 tells them they are already Pro.
 */
async function readTier(session: Session): Promise<PricingTier> {
  if (session.kind === "anonymous") return "signed-out";
  if (session.kind === "unavailable") return "free";

  try {
    const response = await api.GET("/api/billing/subscription", {
      headers: await sessionHeaders(),
    });
    if (response.data) return response.data.is_pro ? "pro" : "free";
  } catch {
    // The API could not answer. The page still renders — see the module docstring.
  }

  // The entitlement is unknown, so the page shows the **Free** state: the buy button is
  // there, and if the visitor is in fact Pro, the checkout will refuse with 409 and the
  // page will swap itself to the Pro state. That is the honest direction to be wrong in.
  return "free";
}
