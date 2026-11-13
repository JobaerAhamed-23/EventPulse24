import { redirect } from "next/navigation";

import { ProfileName } from "@/components/settings/profile-name";
import { SettingsNav } from "@/components/settings/settings-nav";
import { AppShell } from "@/components/shell/app-shell";
import { displayName } from "@/lib/display-name";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/settings/profile` — **the one thing about your account you can change.**
 *
 * ## Why this screen exists
 *
 * **The name is the only editable field on an account.** The email is the login and the
 * key, and it is not changeable from here; the password is changed by the reset flow,
 * which ends the account's other sessions. So the profile surface is one field, and this
 * screen is one field.
 *
 * ## It is a settings route, and it follows the house pattern exactly
 *
 * All the other `/settings/*` routes do the same five things in the same order, and this
 * one does too:
 *
 * 1. `force-dynamic` — a settings screen is per-user and is never cached.
 * 2. `homeRoute(session)` redirects an anonymous visitor to `/preview` and a
 *    half-onboarded one to `/onboarding`. `redirect` throws, so it is called outside
 *    any try/catch.
 * 3. Not signed in → an empty `AppShell`.
 * 4. Otherwise the page itself, with a header and a reading-width content block.
 *
 * **Step 4's read is absent here, because this page reads nothing of its own.** Every
 * other settings route reads the data it shows, and that read can fail — which is why
 * they have an `unavailable` shell. **This screen's data is the name, and the session
 * already carries it**: `CurrentUserOut` gained a `name` field for exactly this. A
 * second read of the same endpoint, microseconds later, would answer the same question
 * twice and double the route's API traffic for nothing.
 *
 * **So the signed-out branch renders an empty shell rather than `SettingsStates`.**
 * That component's copy is *"Couldn't load your settings."*, and nothing failed to load
 * — there was nothing to load. A screen that reported a failure it did not have would
 * be sending the visitor to look for a problem that is not there.
 *
 * ## The name in the rail is not this screen's job
 *
 * The rail, the bottom bar and every other page derive their display name through one
 * shared helper — *the stored name when there is one, the email-derived name when there
 * is not*. This screen owns the **write**; it does not own where the name is rendered.
 *
 * **And the rail moves with the write.** The shell is rendered on the server, so the
 * name it was drawn with is fixed for the life of that render — which would leave the
 * rail showing the old name after a save. **A save that does not show up is a save that
 * did not happen**, so the island publishes the new display name to the shell once the
 * server has accepted it. The rail, the bottom bar and the account sheet all follow it.
 */
export const dynamic = "force-dynamic";

export default async function SettingsProfilePage() {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  // **A profile screen for somebody who is not signed in would be offering to change a
  // name that is not theirs.**
  //
  // **In practice `homeRoute` has already redirected this visitor** — an anonymous one
  // to `/preview` — so this branch is the belt to its braces. **It does run for one
  // case**: `getSession` answers `unavailable` when it could not ask the server at all,
  // and that is neither `anonymous` nor `signed-in`, so nothing was redirected and
  // there is no name here to edit.
  //
  // **It renders an empty shell rather than `SettingsStates`.** That component says
  // *"Couldn't load your settings."* — and nothing failed to load here; there was
  // nothing to load, and the visitor is not here for the settings. The other settings
  // routes use it because *their* read can fail. This one has no read.
  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="">
        {null}
      </AppShell>
    );
  }

  // **The name the account holds.**
  //
  // It is `""` when none is set — that is the backend's single "no name set" state, and
  // it is not `null` and not a 404.
  //
  // **The editor is handed the stored name exactly, and the shell is handed the
  // display name.** The editor shows what the account holds, so it shows `""` — an
  // empty field, which is what "no name set" looks like. The shell shows what to call
  // the person, which is the stored name when there is one and the email-derived name
  // when there is not. **Those are two different questions, and the shared helper
  // answers the second one.**
  const stored = session.user.name;

  return (
    <AppShell name={displayName(session.user)} email={session.user.email}>
      <SettingsNav />

      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Profile</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          Your name, and how we address you.
        </p>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        <ProfileName initialName={stored} email={session.user.email} />
      </div>
    </AppShell>
  );
}

