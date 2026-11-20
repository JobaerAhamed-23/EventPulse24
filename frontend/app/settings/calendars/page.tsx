import { redirect } from "next/navigation";

import { CalendarConnections } from "@/components/settings/calendar-connections";
import { SettingsNav } from "@/components/settings/settings-nav";
import { SettingsStates } from "@/components/settings/settings-states";
import { AppShell } from "@/components/shell/app-shell";
import { readCalendars } from "@/lib/calendars-read";
import { displayName } from "@/lib/display-name";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/settings/calendars` — the screen onboarding has been promising (FR-50).
 *
 * **Onboarding makes the promise twice.** *"Read-only access. You can disconnect anytime."*
 * (`onboarding-flow.tsx:76`) and *"read-only · disconnect any time in Settings"*
 * (`calendar-step.tsx:436`). Until this route there was no such screen, and
 * `DELETE /api/personal/calendars/{id}` had no caller at all — the product made a promise
 * it could not keep.
 *
 * **It lives under `/settings` because the navigation is closed.** DESIGN.md forbids adding
 * nav rows; the sidenav's Settings item matches `pathname.startsWith("/settings/")`, so
 * this is reachable with no nav change, and `/settings/quiet-hours` carries the one link
 * to it — the same way it already links to `/settings/digest`.
 *
 * **It is not Pro-gated.** FR-50 is "Calendar Provider Read-Only Sync (Free + Pro)", and
 * disconnecting is how a user withdraws access to their own calendar. Gating the exit from
 * a data-sharing arrangement would be the wrong thing on its own terms.
 *
 * **Connecting lives here as well as in onboarding.** `POST /api/personal/calendars` used
 * to have one caller — onboarding step 1 — so a user who skipped that step, or who wanted a
 * second calendar afterwards, had no way to add one: the only route to the feature ran
 * through a flow that cannot be re-entered. The tier cap (one calendar on Free, three on
 * Pro) stays the server's to enforce; this screen renders the refusal, it does not predict
 * it.
 */
export const dynamic = "force-dynamic";

export default async function SettingsCalendarsPage() {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="" avatarUrl="">
        <SettingsStates />
      </AppShell>
    );
  }

  const name = displayName(session.user);
  const read = await readCalendars();

  // **"Unavailable" is not "you have none".** On this screen the difference matters more
  // than most: an empty state here reads as the calendar having been disconnected.
  if (read.kind === "unavailable") {
    return (
      <AppShell
        name={name}
        email={session.user.email}
        avatarUrl={session.user.avatar_url}
      >
        <SettingsNav />

        <SettingsStates />
      </AppShell>
    );
  }

  return (
    <AppShell
        name={name}
        email={session.user.email}
        avatarUrl={session.user.avatar_url}
      >
      <SettingsNav />

      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Calendar sync</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          Connect a calendar, sync it on demand, or disconnect it. Access is read-only.
        </p>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        <CalendarConnections initial={read.connections} />
      </div>
    </AppShell>
  );
}
