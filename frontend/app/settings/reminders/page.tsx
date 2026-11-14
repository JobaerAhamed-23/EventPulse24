import { redirect } from "next/navigation";

import { SETTINGS_GENERAL_ANCHORS } from "@/lib/settings-sections";

/**
 * `/settings/reminders` — **a redirect to its section of `/settings/general`.**
 *
 * This route used to be the Default reminders screen. The preferences were three routes, one
 * per work item, and each cost a row in the sub-nav every settings screen carries — so
 * the navigation grew by one every time a switch was added. They are now three sections
 * of one page, and the nav rows that remain are *things* a user owns rather than switches
 * they set.
 *
 * **The route stays because the URL is out in the world.** It has been linked from
 * onboarding copy and is in people's history; deleting it would turn those into 404s to
 * save a file. It forwards to the anchor rather than to the top of the page, so the
 * visitor lands on the setting they asked for.
 *
 * It reads no session: `/settings/general` runs `homeRoute` itself, so an anonymous
 * visitor is still sent to `/preview`. Checking here as well would be a second copy of
 * the same rule, free to disagree with the first.
 */
export const dynamic = "force-dynamic";

export default async function SettingsRemindersRedirectPage(): Promise<never> {
  // `redirect` throws, so it is called outside any try/catch.
  redirect(SETTINGS_GENERAL_ANCHORS.reminders);
}
