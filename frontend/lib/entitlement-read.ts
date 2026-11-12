import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * Whether the signed-in visitor is Pro, read on the server.
 *
 * **`GET /api/billing/subscription` is the one published answer to this question.** Its
 * own description says so: *"one bool and nothing else … may this person buy a plan?"*
 * The alternative — inferring the tier from the settings response, by checking whether
 * `quiet_hours_overrides` is non-empty — gets two cases wrong in opposite directions. A
 * Pro user who has not set a weekday yet would read as Free and be shown an upgrade
 * prompt for something they already pay for; a **lapsed** Pro user, whose rows are kept
 * on purpose, would read as Pro and be offered an editor the API will refuse.
 *
 * **Unknown is reported as not-Pro, and that is the honest direction to be wrong in** —
 * the same choice `/pricing` made in as many words. A visitor wrongly shown the Free
 * screen sees one extra upgrade line; a visitor wrongly shown the Pro editor fills in
 * seven windows and is refused on save. The first is a smaller lie, and it corrects
 * itself on the next read.
 *
 * **This module is server-only.** It reaches `sessionHeaders()`, and so `next/headers` —
 * a `"use client"` component that imports it breaks the production build, which is the
 * failure `lib/notification-settings.ts` exists to prevent.
 */
export async function readIsPro(): Promise<boolean> {
  try {
    const response = await api.GET("/api/billing/subscription", {
      headers: await sessionHeaders(),
    });
    return response.data?.is_pro === true;
  } catch {
    // The API could not answer. See the module docstring: unknown is not-Pro.
    return false;
  }
}
