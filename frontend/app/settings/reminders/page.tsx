import { redirect } from "next/navigation";

import { DefaultReminderSlots } from "@/components/settings/default-reminder-slots";
import { SettingsStates } from "@/components/settings/settings-states";
import { AppShell } from "@/components/shell/app-shell";
import { readNotificationSettings } from "@/lib/notification-settings-read";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/settings/reminders` — the **Default Reminder Plan** editor.
 *
 * **The first `/settings/*` route the product has had.** The sidenav's Settings entry
 * has said "Coming soon" since the shell was built, and the onboarding flow tells the
 * user *"You can change these later in Settings."* This route makes that true.
 *
 * **It sets a default, and it says so.** The server does not rewrite the plans that
 * already exist — `notification-preferences-api` proves that — but the user has to be
 * told, or the setting looks like it does something it does not. The sentence is above
 * the chips.
 *
 * **The chips are the per-event picker's chips.** `ReminderChip` is reused rather than
 * copied, so the ink-inversion treatment is the picker's by construction. There is no
 * target event here, so there are no delivery times and **no chip dims** — the dimming
 * belongs to a plan that knows when it will send.
 *
 * **The save is inline.** There is no Save button: the work item rules one out, and a
 * settings screen that asks for a confirmation of a control the user just pressed is a
 * screen that asks for something it does not need.
 *
 * **It is an authed surface.** `homeRoute` has already sent an anonymous visitor to
 * the preview and a half-onboarded one to `/onboarding`; what is left is a signed-in
 * user, or a session the API could not answer.
 */
export const dynamic = "force-dynamic";

export default async function SettingsRemindersPage() {
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

  return (
    <AppShell name={displayName(session.user.email)} email={session.user.email}>
      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Default reminders</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          What we suggest when you save an event.
        </p>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        <DefaultReminderSlots initialSlots={read.settings.default_reminder_slots} />
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
