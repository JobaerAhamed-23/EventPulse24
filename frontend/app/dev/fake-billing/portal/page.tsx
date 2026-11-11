import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { FakePortalPanel } from "@/app/dev/fake-billing/fake-billing-panel";

export const metadata: Metadata = { title: "Fake customer portal · EventPulse24" };

/**
 * `/dev/fake-billing/portal` — the stand-in for the provider's customer portal.
 *
 * **The URL is minted by `FakeBillingAdapter`**, which puts `next` in the query string:
 * the URL the provider would return the user to after they manage their subscription.
 * That is the only parameter, and it is read here by exactly that name.
 *
 * **A developer page: it doesn't exist in production builds.**
 */
export default async function DevFakeBillingPortalPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  if (process.env.NODE_ENV === "production") notFound();

  const query = await searchParams;

  return <FakePortalPanel next={query.next} />;
}
