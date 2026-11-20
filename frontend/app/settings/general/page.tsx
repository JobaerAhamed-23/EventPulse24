import { redirect } from "next/navigation";

import { DefaultReminderSlots } from "@/components/settings/default-reminder-slots";
import { DigestDeliveryTime } from "@/components/settings/digest-delivery-time";
import { DigestPersonalEvents } from "@/components/settings/digest-personal-events";
import { PulsePingSwitch } from "@/components/settings/pulse-ping-switch";
import { QuietHoursWindow } from "@/components/settings/quiet-hours-window";
import { SettingsNav } from "@/components/settings/settings-nav";
import { SettingsStates } from "@/components/settings/settings-states";
import { WeekdayQuietHours } from "@/components/settings/weekday-quiet-hours";
import { AppShell } from "@/components/shell/app-shell";
import { UpgradePrompt } from "@/components/upgrade/upgrade-prompt";
import { readDigestPreference } from "@/lib/digest-preference-read";
import { displayName } from "@/lib/display-name";
import { readIsPro } from "@/lib/entitlement-read";
import { DEFAULT_QUIET_HOURS } from "@/lib/notification-settings";
import { readNotificationSettings } from "@/lib/notification-settings-read";
import { getSession, homeRoute } from "@/lib/session";

/**
 * The sentence a Free user is offered the Pro variant with.
 *
 * **It is the backend's `QUIET_HOURS_PRO_UPGRADE_HINT`, spelled again here, and that is a
 * cost worth naming.** Everywhere else the upgrade sentence is the server's, carried on a
 * 409 and rendered verbatim — the rule that lets backend copy change without a frontend
 * release. A Free user on this screen is **never refused**, because they are never given a
 * control that could be refused, so no payload ever arrives to carry the sentence.
 *
 * The alternatives were worse: inventing a second sentence here, or giving Free users the
 * editor and letting them fill in seven windows before the server says no. So the one
 * sentence is duplicated, and `page.test.tsx` pins the exact string against the backend
 * constant so the two cannot drift silently.
 */
const PRO_QUIET_HOURS_HINT = "Set a different window for each day with Pro.";

/**
 * `/settings/general` — **the switches and the values, on one screen.**
 *
 * ## Why one screen
 *
 * Three routes used to hold the product's preferences: `/settings/reminders`,
 * `/settings/quiet-hours` and `/settings/digest`. Each was one or two controls, and each
 * cost a row in a sub-nav that every settings screen carries — so the nav grew by one
 * every time a switch was added, and the user had to know which of nine rows a given
 * switch had been filed under.
 *
 * **The split was already failing on its own terms.** The digest's two settings lived on
 * *two different pages*: the delivery time on Quiet hours, the personal-events opt-out on
 * Digest. Two pages, one feature, because each had arrived with its own work item. A user
 * looking for "my daily brief" had to find both.
 *
 * ## The zone is not here, and it was
 *
 * `DigestTimezone` opened this screen, on the grounds that *"everything under it is read
 * in that zone"* — and that was true of this page. It was not the question a reader
 * arrives with. **"Which zone am I in" is the same question as "which city am I in"**,
 * and the city was two screens away on `/settings/account`; a user correcting a wrong
 * zone after a move had to find two settings on two screens to describe one fact about
 * themselves. Both now sit together on `/settings/profile`.
 *
 * **What stayed is the delivery time**, which is a digest setting and reads as one. It
 * still sends the stored zone back unchanged, exactly as it always did — the endpoint
 * takes *"both or neither"*, and that was never a claim about which screen the zone is
 * edited on.
 *
 * So the preferences are one route now, and the nav rows that remain are **things** —
 * calendars, collections, sources, taste, the account, the profile — each a list the user
 * adds to or owns. **A new toggle belongs here**, under a new `<h2>`, and the navigation
 * does not change.
 *
 * ## The sections carry ids, because the old routes still work
 *
 * `/settings/reminders`, `/settings/quiet-hours` and `/settings/digest` redirect here,
 * each to its own anchor, so a bookmark or a link in an old email lands where it meant to
 * rather than at the top of a longer page.
 *
 * ## One failed read hides the whole screen, deliberately
 *
 * The page makes three reads — the notification settings, the digest preference and the
 * entitlement — and renders `SettingsStates` if either of the first two is unavailable.
 * Rendering the half that answered would mean a screen where some switches are live and
 * others are silently absent, with nothing saying which. **A settings screen that is
 * partly missing is worse than one that says it cannot be shown**, because the user
 * cannot tell a setting that is off from a setting that failed to load.
 *
 * `readIsPro` is the exception and does not gate anything: it already answers `false` when
 * it cannot reach the API, and "not Pro" is the safe reading — a Free screen, offered the
 * upgrade.
 *
 * ## It follows the house pattern
 *
 * 1. `force-dynamic` — a settings screen is per-user and is never cached.
 * 2. `homeRoute(session)` redirects an anonymous visitor to `/preview` and a
 *    half-onboarded one to `/onboarding`. `redirect` throws, so it is called outside any
 *    try/catch.
 * 3. Not signed in → `SettingsStates` inside an empty `AppShell`.
 * 4. A read came back `unavailable` → `SettingsStates` inside a named `AppShell`.
 * 5. Otherwise the page itself, with a header and reading-width content blocks.
 */
export const dynamic = "force-dynamic";

export default async function SettingsGeneralPage() {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  // **Settings are a signed-in surface.** A settings screen that renders for somebody
  // who is not signed in would offer to change preferences that are not theirs.
  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="" avatarUrl="">
        <SettingsStates />
      </AppShell>
    );
  }

  const name = displayName(session.user);
  const [notifications, digest] = await Promise.all([
    readNotificationSettings(),
    readDigestPreference(),
  ]);

  if (notifications.kind === "unavailable" || digest.kind === "unavailable") {
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

  const settings = notifications.settings;
  // **The window may be off.** `quiet_hours` is `null` when the user has turned quiet
  // hours off, and there is no window to edit then. The server's defaults are shown
  // instead — the window the user would get if they turned it back on.
  const window = settings.quiet_hours ?? DEFAULT_QUIET_HOURS;

  const isPro = await readIsPro();
  const overrides = settings.quiet_hours_overrides ?? [];
  // **Three states, not two.** Pro edits the week; a *lapsed* Pro user — not Pro, but
  // holding stored windows the API still returns — reads it; a Free user has no week to
  // show and is offered one instead.
  const weekday = isPro ? "editable" : overrides.length > 0 ? "read-only" : "none";

  const { delivery_time, timezone, include_personal_events } = digest.preference;
  /**
   * **The schedule, as one value.**
   *
   * **Both halves or neither.** The endpoint requires the delivery time *and* the zone,
   * and it has no "change one field" mode — so a schedule that is missing either half is
   * a schedule the toggle cannot round-trip, and the toggle is told there is none.
   */
  const schedule =
    delivery_time !== null && timezone !== null ? { deliveryTime: delivery_time, timezone } : null;

  return (
    <AppShell
        name={name}
        email={session.user.email}
        avatarUrl={session.user.avatar_url}
      >
      <SettingsNav />

      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">General</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          Reminders, quiet hours, and your daily brief.
        </p>
      </header>

      {/*
        **Each block is a `<section>` with an id and its own heading.** The id is what the
        redirected old routes target; the heading is what makes the long page navigable by
        a screen reader, which is the same job the sub-nav rows used to do.
      */}
      <section
        id="reminders"
        aria-labelledby="reminders-heading"
        className="mt-8 max-w-(--layout-container-reading) scroll-mt-8"
      >
        <h2
          id="reminders-heading"
          className="text-ink-primary [font:var(--type-scale-headline-sm)]"
        >
          Default reminders
        </h2>
        <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
          What we suggest when you save an event.
        </p>
        <div className="mt-6">
          <DefaultReminderSlots initialSlots={settings.default_reminder_slots} />
        </div>
      </section>

      <section
        id="quiet-hours"
        aria-labelledby="quiet-hours-heading"
        className="mt-12 max-w-(--layout-container-reading) scroll-mt-8"
      >
        <h2
          id="quiet-hours-heading"
          className="text-ink-primary [font:var(--type-scale-headline-sm)]"
        >
          Quiet hours
        </h2>
        <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
          When we stay quiet.
        </p>
        <div className="mt-6">
          <QuietHoursWindow initialStart={window.start} initialEnd={window.end} />
        </div>

        {weekday === "none" ? (
          // **The Free user's whole per-day surface: one line.** Not a locked week, not a
          // disabled control — an offer, in the same inline prompt every other cap uses.
          <div className="mt-6">
            <UpgradePrompt hint={PRO_QUIET_HOURS_HINT} />
          </div>
        ) : (
          <div className="mt-8">
            <h3 className="text-ink-primary [font:var(--type-scale-meta-md)]">Each day</h3>
            <div className="mt-4">
              <WeekdayQuietHours
                initialOverrides={overrides}
                baseStart={window.start}
                baseEnd={window.end}
                canEdit={weekday === "editable"}
              />
            </div>
            {weekday === "read-only" ? (
              // **The lapse, said plainly.** The windows are still theirs and still
              // shown; what stopped is their effect and the ability to change them.
              <div className="mt-6">
                <UpgradePrompt hint={PRO_QUIET_HOURS_HINT} />
              </div>
            ) : null}
          </div>
        )}
      </section>

      {/*
        **The digest's two settings, together at last.** The delivery time used to sit on
        the quiet-hours page and the opt-out on a page of its own, because each arrived
        with its own work item. They answer the two halves of one question — when the
        brief arrives, and what is in it — so they belong under one heading.
      */}
      <section
        id="digest"
        aria-labelledby="digest-heading"
        className="mt-12 max-w-(--layout-container-reading) scroll-mt-8"
      >
        <h2 id="digest-heading" className="text-ink-primary [font:var(--type-scale-headline-sm)]">
          Pulse Digest
        </h2>
        <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
          When your daily brief arrives, and what&apos;s in it.
        </p>
        {/*
          **Whether it arrives comes before when it arrives.** This switch turns the
          whole daily mail off (FR-10); the two rows under it configure a mail that is
          on. A reader who wants to stop the Ping should not have to scroll past the
          settings for one they are about to switch off.
        */}
        <div className="mt-6">
          <PulsePingSwitch initialPulsePing={settings.pulse_ping} />
        </div>
        <div className="mt-8">
          <DigestDeliveryTime
            initialDeliveryTime={settings.digest.delivery_time}
            initialTimezone={settings.digest.timezone}
          />
        </div>
        <div className="mt-8">
          <DigestPersonalEvents
            initialIncludePersonalEvents={include_personal_events}
            schedule={schedule}
          />
        </div>
      </section>
    </AppShell>
  );
}
