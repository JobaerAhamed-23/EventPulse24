import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { FakeCheckoutPanel } from "@/app/dev/fake-billing/fake-billing-panel";

export const metadata: Metadata = { title: "Fake checkout · EventPulse24" };

/**
 * `/dev/fake-billing/checkout` — the stand-in for the provider's hosted checkout.
 *
 * **The URL is minted by `FakeBillingAdapter`**, which puts `session`, `plan` and `next`
 * in the query string. Those three parameters are the whole contract between the adapter
 * and this page, so they are read here by exactly those names.
 *
 * **`next` is the backend's own configured success URL** — it came from
 * `settings.BILLING_SUCCESS_PATH`, not from the client. The page follows it on
 * "Complete", so the local flow returns the user to the same place the real provider
 * would.
 *
 * **A developer page: it doesn't exist in production builds.**
 */
export default async function DevFakeBillingCheckoutPage({
  searchParams,
}: {
  searchParams: Promise<{ session?: string; plan?: string; next?: string }>;
}) {
  if (process.env.NODE_ENV === "production") notFound();

  const query = await searchParams;

  return <FakeCheckoutPanel session={query.session} plan={query.plan} next={query.next} />;
}
