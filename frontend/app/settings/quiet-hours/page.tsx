import Link from "next/link";
import { redirect } from "next/navigation";

import { DigestDeliveryTime } from "@/components/settings/digest-delivery-time";
import { QuietHoursWindow } from "@/components/settings/quiet-hours-window";
import { SettingsStates } from "@/components/settings/settings-states";
import { WeekdayQuietHours } from "@/components/settings/weekday-quiet-hours";
import { AppShell } from "@/components/shell/app-shell";
import { UpgradePrompt } from "@/components/upgrade/upgrade-prompt";
import { readIsPro } from "@/lib/entitlement-read";
import { DEFAULT_QUIET_HOURS } from "@/lib/notification-settings";
import { readNotificationSettings } from "@/lib/notification-settings-read";
import { getSession, homeRoute } from "@/lib/session";

/**
 * The sentence a Free user is offered the Pro variant with.
 *
 * **It is the backend's `QUIET_HOURS_PRO_UPGRADE_HINT`, spelled again here, and that is a
 * cost worth naming.** Everywhere else in this intent the upgrade sentence is the
 * server's, carried on a 409 and rendered verbatim — the rule that lets backend copy
 * change without a frontend release. A Free user on this screen is **never refused**,
 * because they are never given a control that could be refused, so no payload ever
 * arrives to carry the sentence.
 *
 * The alternatives were worse: inventing a second sentence here, or giving Free users the
 * editor and letting them fill in seven windows before the server says no. So the one
 * sentence is duplicated, and `page.test.tsx` pins the exact string against the backend
 * constant so the two cannot drift silently.
 */
const PRO_QUIET_HOURS_HINT = "Set a different window for each day with Pro.";

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
 * **Per-day-of-week windows are Pro's, and a Free user's screen is unchanged** (FR-51).
 * The Pro user gets the seven-row picker; the Free user gets the single window they
 * always had, plus one inline line offering the variant. A locked seven-row preview —
 * which `component.control.day-picker` specifies — is deliberately **not** built: a row
 * the user can neither use nor remove is worse than no row, DESIGN.md's own
 * Do's-and-Dont's row says *"Free stays single-window"*, and the two statements
 * contradict each other inside one amendment. Logged as a deviation.
 *
 * **A lapsed Pro user sees their week and cannot change it.** Their rows are kept on
 * purpose — `quiet-hours-pro-api` refuses the write, never the read — so the picker
 * renders read-only rather than vanishing, which would look as though the lapse had
 * deleted what they set.
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

  const isPro = await readIsPro();
  const overrides = settings.quiet_hours_overrides ?? [];
  // **Three states, not two.** Pro edits the week; a *lapsed* Pro user — not Pro, but
  // holding stored windows the API still returns — reads it; a Free user has no week to
  // show and is offered one instead.
  const weekday = isPro ? "editable" : overrides.length > 0 ? "read-only" : "none";

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

      {weekday === "none" ? (
        // **The Free user's whole per-day surface: one line.** Not a locked week, not a
        // disabled control — an offer, in the same inline prompt every other cap uses.
        <div className="mt-6 max-w-(--layout-container-reading)">
          <UpgradePrompt hint={PRO_QUIET_HOURS_HINT} />
        </div>
      ) : (
        <div className="mt-12 max-w-(--layout-container-reading)">
          <h2 className="text-ink-primary [font:var(--type-scale-headline-sm)]">Each day</h2>
          <div className="mt-6">
            <WeekdayQuietHours
              initialOverrides={overrides}
              baseStart={window.start}
              baseEnd={window.end}
              canEdit={weekday === "editable"}
            />
          </div>
          {weekday === "read-only" ? (
            // **The lapse, said plainly.** The windows are still theirs and still shown;
            // what stopped is their effect and the ability to change them.
            <div className="mt-6">
              <UpgradePrompt hint={PRO_QUIET_HOURS_HINT} />
            </div>
          ) : null}
        </div>
      )}

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
        {/*
          **The link to the digest's own screen.** `/settings/digest` is a separate
          route, and **there is no settings index and no settings sub-nav** — so without
          this link the route would be reachable and invisible.

          **It lives in the "Pulse Digest" section because that is where the digest's
          settings already are.** The delivery time is here; the opt-out is the other
          half of the same question ("when does it arrive" and "what is in it"), and a
          link under the heading that already says "Pulse Digest" is the one a user
          would follow.
        */}
        <div className="mt-6">
          <Link
            href="/settings/digest"
            className="inline-block text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-md)]"
          >
            What&apos;s in your Pulse Digest
          </Link>
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
