import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The user's notification settings, read on the server.
 *
 * **One call, one response.** The settings the two `/settings/*` screens need are split
 * across two tables in two apps — the quiet window and the default plan on one side,
 * the digest schedule on the other. The API assembles them; this read hands the whole
 * surface over rather than asking three times.
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous, and the settings of a signed-in user read anonymously are not their
 * settings.
 *
 * **This module is server-only, and the pure helpers live elsewhere.** It calls
 * `sessionHeaders()`, which reaches `next/headers` — so a `"use client"` component that
 * imports anything from here breaks the production build. The helpers that both sides
 * need — `clockForInput` and `DEFAULT_QUIET_HOURS` — are in
 * `@/lib/notification-settings`, which depends on nothing.
 */
export type NotificationSettingsRead =
  { kind: "found"; settings: NotificationSettingsOut } | { kind: "unavailable" };

export type NotificationSettingsOut = components["schemas"]["NotificationSettingsOut"];

/**
 * The signed-in user's notification settings.
 *
 * **One kind of nothing.** Unlike the reminder plan's read, there is no "missing" here:
 * the endpoint is a **singleton** — it is the user's own settings, and it *creates* them
 * on first read. There is no target that might not exist and no target that might
 * belong to somebody else, so the only failure left is a failure to answer.
 */
export async function readNotificationSettings(): Promise<NotificationSettingsRead> {
  try {
    const response = await api.GET("/api/settings/notifications", {
      headers: await sessionHeaders(),
    });
    if (!response.data) return { kind: "unavailable" };
    return { kind: "found", settings: response.data };
  } catch {
    return { kind: "unavailable" };
  }
}
