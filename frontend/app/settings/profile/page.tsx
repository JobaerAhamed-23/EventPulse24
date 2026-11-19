import { redirect } from "next/navigation";

import { EmailChange } from "@/components/settings/email-change";
import { HomeCity } from "@/components/settings/home-city";
import { ProfileName } from "@/components/settings/profile-name";
import { SettingsNav } from "@/components/settings/settings-nav";
import { AppShell } from "@/components/shell/app-shell";
import { displayName } from "@/lib/display-name";
import { readHomeCity } from "@/lib/home-city-read";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/settings/profile` — **who you are, and where you are.**
 *
 * ## Why this screen exists
 *
 * **It was one field, and that is no longer true.** It shipped holding only the name,
 * on the stated grounds that the name was the only thing about an account a person could
 * change. The account has since grown a place, and it is growing a picture and a
 * movable address — so the claim that lived in this docstring has been removed rather
 * than left to mislead the next reader.
 *
 * ## The city is here because this is where a person looks for it
 *
 * **It was on `/settings/account`, and the zone is still on `/settings/general`.** That
 * split is the same failure `/settings/general` records about itself — *"the digest's
 * two settings lived on two different pages ... because each had arrived with its own
 * work item"*. "Where am I" is a fact about the person, not about billing, so the city
 * moved here and `/settings/account` links to where it went.
 *
 * **The zone did not move, and that is deliberate.** It is paired with the digest's
 * delivery time: together they answer *when the brief arrives*, and `HomeCity` itself
 * posts `deliveryTime` and `timezone` back unchanged because the endpoint requires the
 * three together. Moving the zone alone would split a pair to heal a different one. So
 * this screen **links** to it instead of holding it.
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
 * **Step 4's read is no longer absent, and the old reasoning is recorded because half
 * of it still holds.** The name needs no read — the session already carries it, and a
 * second call to the same endpoint microseconds later would answer one question twice.
 * **The city does need one**, so this route now reads like its siblings.
 *
 * **But a failed city read does not blank the screen.** The name is still there, and it
 * is still editable, so `SettingsStates`' *"Couldn't load your settings."* would be
 * false — it would send the visitor looking for a problem that did not happen to the
 * thing in front of them. The city section is simply absent, which is exactly what
 * `/settings/account` already does with the same read and for the same reason.
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

  // **The city, read the way `/settings/account` reads it** — the same helper, so there
  // is one implementation of "what city does this account have, and how did it get it".
  // A failure is not fatal here: the name above it is unaffected, so the section is
  // absent rather than the screen being replaced by an error.
  const homeCity = await readHomeCity();

  return (
    <AppShell name={displayName(session.user)} email={session.user.email}>
      <SettingsNav />

      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Profile</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          Your name, your address, and the city your Pulse Digest follows.
        </p>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        <ProfileName initialName={stored} email={session.user.email} />
      </div>

      {/*
        **The address, under the name.** It is the account's login rather than a
        preference, which is why it reads as its own block with its own explanation
        instead of sitting in the same list as the name.

        **It needs no read of its own**: `me` already carries the current address and any
        pending change, and the session has both in hand.
      */}
      <div className="mt-12 max-w-(--layout-container-reading)">
        <EmailChange
          email={session.user.email}
          initialPendingEmail={session.user.pending_email}
          initialPendingExpiresAt={session.user.pending_email_expires_at}
        />
      </div>

      {/*
        **Where you are, under who you are.** The order is the heading's order — the name
        first, the place second — because that is the order the heading promises.

        **An unavailable read renders nothing rather than an empty picker.** A select
        with no options would read as *"your city is not available"*, which is a
        statement about the user rather than about the request that failed. This is the
        rule `/settings/account` already applied to the same read.
      */}
      {homeCity.kind === "found" ? (
        <div className="mt-12 max-w-(--layout-container-reading)">
          <h2 className="text-ink-primary [font:var(--type-scale-headline-sm)]">City</h2>
          <div className="mt-6">
            <HomeCity
              initialCity={homeCity.city}
              initialCitySource={homeCity.citySource}
              choices={homeCity.choices}
              deliveryTime={homeCity.deliveryTime}
              timezone={homeCity.timezone}
            />
          </div>
          {/*
            **The zone is named here and edited elsewhere, and the line says so.** It is
            paired with the digest's delivery time on General — together they answer
            *when the brief arrives* — so this is a signpost, not a second control. A
            screen that silently omitted the zone would leave a reader hunting for it.

            **It names General; it does not link to it.** `tests/settings-routes.test.ts`
            forbids a hand-written link from one settings screen to another — *"one list,
            not a web of one-off links"* — and the sub-nav above already carries General
            on every settings screen. So the sentence says where to go and the sub-nav
            is how you get there, which is one destination list rather than two.
          */}
          <p
            data-city-zone-note
            className="mt-4 text-ink-secondary [font:var(--type-scale-meta-sm)]"
          >
            Your time zone decides when your Pulse Digest arrives. It sits with the
            delivery time under General.
          </p>
        </div>
      ) : null}
    </AppShell>
  );
}

