import { redirect } from "next/navigation";

import { DigestPersonalEvents } from "@/components/settings/digest-personal-events";
import { SettingsNav } from "@/components/settings/settings-nav";
import { SettingsStates } from "@/components/settings/settings-states";
import { AppShell } from "@/components/shell/app-shell";
import { readDigestPreference } from "@/lib/digest-preference-read";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/settings/digest` — **the Pulse Digest's own screen.**
 *
 * **What lives here.** The one control that decides whether the user's *own* saved
 * events travel in their digest alongside the public ones (FR-19). The digest's
 * delivery time lives on the quiet-hours page; the opt-out needs its own page, because
 * it is a different question — not *when* the digest arrives, but *what is in it*.
 *
 * ---
 *
 * ## It is a settings route, and it follows the house pattern exactly
 *
 * All four existing `/settings/*` routes do the same five things in the same order, and
 * this one does too:
 *
 * 1. `force-dynamic` — a settings screen is per-user and is never cached.
 * 2. `homeRoute(session)` redirects an anonymous visitor to `/preview` and a
 *    half-onboarded one to `/onboarding`. `redirect` throws, so it is called outside
 *    any try/catch.
 * 3. Not signed in → `SettingsStates` inside an empty `AppShell`.
 * 4. The read came back `unavailable` → `SettingsStates` inside a named `AppShell`.
 * 5. Otherwise the page itself, with a header and a reading-width content block.
 *
 * ---
 *
 * ## The schedule is built here, and it is all-or-nothing
 *
 * **The read hands back two independent nullable fields**, because that is what the
 * server's shape is. **The prop takes one value**, because a half-schedule — a time
 * with no zone — is not a state the server produces and not one the endpoint accepts.
 *
 * **So the route is where the two become one.** A schedule is present only when *both*
 * halves are, and otherwise the toggle is told there is no schedule — which is what
 * disables it, honestly, rather than letting it send a body the API must refuse.
 *
 * ---
 *
 * ## The discoverability link is not here
 *
 * **There is no `/settings` index page and no settings sub-navigation** — the convention
 * is stated outright in `sidenav.tsx` and again in the collections page. So this route
 * would be reachable but invisible without a link from somewhere else, and that link
 * lives on the quiet-hours page's existing "Pulse Digest" section.
 *
 * **One link, not two.** A link in two places is two places to keep in sync.
 */
export const dynamic = "force-dynamic";

export default async function SettingsDigestPage() {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  // **Settings are a signed-in surface.** A screen that rendered for somebody who is
  // not signed in would offer to change a preference that is not theirs.
  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="">
        <SettingsStates />
      </AppShell>
    );
  }

  const read = await readDigestPreference();

  if (read.kind === "unavailable") {
    return (
      <AppShell name={displayName(session.user.email)} email={session.user.email}>
        <SettingsNav />

        <SettingsStates />
      </AppShell>
    );
  }

  const { delivery_time, timezone, include_personal_events } = read.preference;

  /**
   * **The schedule, as one value.**
   *
   * **Both halves or neither.** The endpoint requires the delivery time *and* the zone,
   * and it has no "change one field" mode — so a schedule that is missing either half
   * is a schedule the toggle cannot round-trip, and the toggle is told there is none.
   */
  const schedule =
    delivery_time !== null && timezone !== null ? { deliveryTime: delivery_time, timezone } : null;

  return (
    <AppShell name={displayName(session.user.email)} email={session.user.email}>
      <SettingsNav />

      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Pulse Digest</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          What&apos;s in your Pulse Digest.
        </p>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        <DigestPersonalEvents
          initialIncludePersonalEvents={include_personal_events}
          schedule={schedule}
        />
      </div>
    </AppShell>
  );
}

/**
 * A name for the sidenav's account row.
 *
 * **The email's local part is the best name the session carries** — the same rule the
 * digest home and the Timeline use.
 *
 * **This is a copy, and it is deliberately one.** The four existing settings routes each
 * carry their own; extracting a shared helper is a different change, and this intent is
 * not about that.
 */
function displayName(email: string): string {
  const local = email.split("@")[0] ?? email;
  const words = local.split(/[._-]+/).filter(Boolean);
  if (words.length === 0) return email;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}
