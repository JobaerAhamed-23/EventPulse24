import { redirect } from "next/navigation";

import { DigestDeliveryTime } from "@/components/settings/digest-delivery-time";
import { QuietHoursWindow } from "@/components/settings/quiet-hours-window";
import { SettingsStates } from "@/components/settings/settings-states";
import { AppShell } from "@/components/shell/app-shell";
import { DEFAULT_QUIET_HOURS } from "@/lib/notification-settings";
import { readNotificationSettings } from "@/lib/notification-settings-read";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/settings/quiet-hours` — the **Quiet Hours window** and the **digest delivery time**.
 *
 * **The window is two local wall clocks.** `22:00` means ten at night *where the user
 * is*, so the window crosses midnight and crosses the user's timezone with them. The
 * server owns the arithmetic; this page owns the two values.
 *
 * **The default is 22:00–08:00.** The server's `DEFAULT_QUIET_HOURS_START`/`END` are
 * `time(22, 0)` and `time(8, 0)`. The mockup drew `07:00` — a stale value — and the
 * work item locks the label *"10pm–8am. Nothing during this window."* The server and
 * the label win over the mockup.
 *
 * **The delivery time is here because onboarding is not the only place a person can
 * be.** It reuses the onboarding time control — extracted, not copied — and it sends
 * the zone it read, unchanged, because `DigestScheduleIn` says *"Both or neither. A
 * wall clock without its zone is not a schedule."*
 *
 * **Per-day-of-week windows are not in this markup at all.** FR-51 and Pro own them,
 * and the work item leaves them out entirely — a locked row for a feature that does
 * not exist on this tier would be a row the user can neither use nor remove.
 *
 * **It is an authed surface**, guarded the same way `/conflicts` is.
 */
export const dynamic = "force-dynamic";

export default async function SettingsQuietHoursPage() {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  // **Settings are a signed-in surface.** A settings screen that renders for somebody
  // who is not signed in would offer to change a plan that is not theirs.
  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="">
        <SettingsStates />
      </AppShell>
    );
  }

  const read = await readNotificationSettings();

  if (read.kind === "unavailable") {
    return (
      <AppShell name={displayName(session.user.email)} email={session.user.email}>
        <SettingsStates />
      </AppShell>
    );
  }

  const settings = read.settings;
  // **The window may be off.** `quiet_hours` is `null` when the user has turned quiet
  // hours off, and there is no window to edit then. The server's defaults are shown
  // instead — the window the user would get if they turned it back on.
  const window = settings.quiet_hours ?? DEFAULT_QUIET_HOURS;

  return (
    <AppShell name={displayName(session.user.email)} email={session.user.email}>
      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Quiet hours</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          When we stay quiet.
        </p>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        <QuietHoursWindow initialStart={window.start} initialEnd={window.end} />
      </div>

      {/*
        **The delivery time, in its own section.** It is a different setting from the
        window — one is when we are quiet, the other is when we speak — so it reads as
        its own block rather than as another row of the window's.
      */}
      <div className="mt-12 max-w-(--layout-container-reading)">
        <h2 className="text-ink-primary [font:var(--type-scale-headline-sm)]">Pulse Digest</h2>
        <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
          When your daily brief arrives.
        </p>
        <div className="mt-6">
          <DigestDeliveryTime
            initialDeliveryTime={settings.digest.delivery_time}
            initialTimezone={settings.digest.timezone}
          />
        </div>
      </div>
    </AppShell>
  );
}

/**
 * A name for the sidenav's account row.
 *
 * **The email's local part is the best name the session carries** — the same rule the
 * digest home and the Timeline use.
 */
function displayName(email: string): string {
  const local = email.split("@")[0] ?? email;
  const words = local.split(/[._-]+/).filter(Boolean);
  if (words.length === 0) return email;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}
