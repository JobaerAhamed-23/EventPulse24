import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The signed-in user's plan state, read on the server.
 *
 * **It calls the wider read, not the entitlement bool.** `GET /api/billing/subscription`
 * answers `is_pro`, which is **true for a `past_due` account as well as an `active` one** —
 * so a screen built on it cannot see the one state it exists to show. `GET
 * /api/billing/account` carries `needs_payment` beside the bool, which is the difference.
 *
 * **The read carries the visitor's cookies.** A server-side read without them is anonymous,
 * and an anonymous read of a subscription is nobody's subscription.
 *
 * **This module is server-only.** It reaches `sessionHeaders()`, and so `next/headers` — a
 * `"use client"` component importing it breaks the production build, which is the failure
 * `lib/notification-settings.ts` exists to keep apart.
 */
export type BillingAccountOut = components["schemas"]["BillingAccountOut"];

export type BillingAccountRead =
  { kind: "found"; account: BillingAccountOut } | { kind: "unavailable" };

/**
 * The caller's plan.
 *
 * **One kind of nothing.** There is no "missing" here: an account that never subscribed is
 * a perfectly good answer with `status: null`, not an absence. The only failure left is a
 * failure to answer — and an account screen that silently rendered "free plan" because the
 * API blinked would tell a paying subscriber they are not one.
 */
export async function readBillingAccount(): Promise<BillingAccountRead> {
  try {
    const response = await api.GET("/api/billing/account", {
      headers: await sessionHeaders(),
    });
    if (!response.data) return { kind: "unavailable" };
    return { kind: "found", account: response.data };
  } catch {
    return { kind: "unavailable" };
  }
}
