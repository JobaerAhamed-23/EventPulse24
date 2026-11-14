import { redirect } from "next/navigation";

import { SETTINGS_DEFAULT_HREF } from "@/lib/settings-sections";

/**
 * `/settings` — **the redirect to the first section.**
 *
 * ## It used to be an index, and the index was a step nobody wanted
 *
 * The settings screens shipped one per work item, each inheriting the convention *"there
 * is no `/settings` index page and no settings sub-navigation"*, so four of six working
 * screens could not be reached by clicking. The fix was one list — `SETTINGS_SECTIONS` —
 * rendered twice: as a stack of described rows here, and as `SettingsNav` on every
 * section screen.
 *
 * **That left the user clicking twice to reach any setting.** Settings, then a row, then
 * the screen — where the second click lands on a sub-nav that lists the same sections
 * again, in a row, with the chosen one marked. The index was a table of contents for a
 * navigation that was already going to be on the screen.
 *
 * So `/settings` now forwards straight to the first section, and the sub-nav *is* the
 * index. Every section remains one tap from every other, which was the whole point of
 * the list; the step that offered the list on its own is gone.
 *
 * ## The default is the first section, by construction
 *
 * `SETTINGS_DEFAULT_HREF` is `SETTINGS_SECTIONS[0].href`, not a second hard-coded route.
 * Reordering the list moves the default with it, and there is no way to name a default
 * that is not a section.
 *
 * ## It reads no session
 *
 * The other `/settings/*` routes each call `homeRoute(session)` to send an anonymous
 * visitor to `/preview` and a half-onboarded one to `/onboarding`. **This one does not
 * need to**: it redirects to a route that performs exactly that check, so a signed-out
 * visitor lands on `/preview` either way. Reading the session here to reach the same
 * destination would be a second place the rule is written, and a second place it can be
 * written wrongly.
 */
export const dynamic = "force-dynamic";

/**
 * **`Promise<never>`, declared rather than inferred.** `redirect` throws, so this
 * function has no return path — and without the annotation TypeScript infers
 * `Promise<void>`, which is not a `ReactNode` and which anything rendering this page
 * rejects. The annotation says what the body already does.
 */
export default async function SettingsIndexPage(): Promise<never> {
  // `redirect` throws, so it is called outside any try/catch.
  redirect(SETTINGS_DEFAULT_HREF);
}
