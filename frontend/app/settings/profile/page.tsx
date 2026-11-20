import { redirect } from "next/navigation";

import { AvatarUpload } from "@/components/settings/avatar-upload";
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
 * ## What this screen holds now
 *
 * **It was one field, and that is no longer true.** It shipped holding only the name,
 * on the stated grounds that the name was the only thing about an account a person could
 * change. The account has since grown a picture, a movable address and a place — so the
 * claim that lived in this docstring has been removed rather than left to mislead the
 * next reader.
 *
 * **The four things on it are in the order the heading promises**, and that order is the
 * account sheet's order:
 *
 * | | What it is | How it saves |
 * |---|---|---|
 * | **The picture** | The face, drawn in three places | **On the choice** — the file is chosen, and that is the save |
 * | **The name** | What to call the person | **On change** |
 | **The address** | The account's login | **On a press** — the request has to be sent, and the link opened to confirm it |
 * | **The city** | Where the digest comes from | **On change** |
 *
 * **Three of the four save on change, and one does not — and the difference is real.**
 * The picture is chosen rather than typed, so there is no keystroke to hang a save on.
 * The address would mail `m@`, then `ma@`, then `may@` — to strangers, from an endpoint
 * that sends real mail — so it takes an explicit action. **A reader who notices that the
 * four controls do not behave alike is noticing something real, and this docstring
 * records it rather than leaving it to look like an inconsistency.**
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
 * this screen **names** it instead of holding it.
 *
 * ## The read question, answered
 *
 * **This screen has one read that can fail, and it is the city's.** The rest of what it
 * shows comes from the session, which was read before the page was rendered:
 *
 * | What it shows | Where it comes from | Can it fail? |
 * |---|---|---|
 * | The name | `session.user.name` | **No** — the session carries it, and a second `GET /api/auth/me` microseconds later would answer one question twice. |
 * | The picture | `session.user.avatar_url` | **No** — the same read, for the same reason. |
 * | The address and any pending change | `session.user.email`, `session.user.pending_email` | **No** — the same read. |
 * | **The city and its choices** | `readHomeCity()` | **Yes** — two requests, either of which can fail. |
 *
 * **So the failure is the city's, and not the screen's.** The name is still there, and
 * it is still editable, so `SettingsStates`' *"Couldn't load your settings."* would be
 * false — it would send the visitor looking for a problem that did not happen to the
 * thing in front of them. **The city section is simply absent**, which is exactly what
 * `/settings/account` already does with the same read and for the same reason.
 *
 * **An empty picker would be worse than no picker.** A `<select>` with no options reads
 * as *"your city is not available"*, which is a statement about the user rather than
 * about the request that failed. So an unavailable read renders **nothing at all**.
 *
 * ## It is a settings route, and it follows the house pattern exactly
 *
 * All the other `/settings/*` routes do the same four things in the same order, and this
 * one does too:
 *
 * 1. `force-dynamic` — a settings screen is per-user and is never cached.
 * 2. `homeRoute(session)` redirects an anonymous visitor to `/preview` and a
 *    half-onboarded one to `/onboarding`. `redirect` throws, so it is called outside
 *    any try/catch.
 * 3. Not signed in → an empty `AppShell`.
 * 4. Otherwise the page itself, with a header and a reading-width content block.
 *
 * **Step 3's empty shell is not `SettingsStates`, and the reason is worth stating
 * exactly.** It is not *"nothing failed to load, there was nothing to load"* — the screen
 * *does* have a read, and it can fail. **The reason is that there is no account to read
 * anything about.** `readHomeCity` needs a session, and this branch has none — so
 * there is no read to fail and nothing that could have loaded. It renders an empty
 * shell, and a visitor who is here for the settings was redirected away by `homeRoute`
 * in every case but this one: the session could not be read at all.
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
 *
 * ## The picture is here too, and it follows the same path
 *
 * **The picture is the other half of the face, and the face is drawn in three places** —
 * the sidenav, the bottom bar and the account sheet — so the screen that owns the
 * picture is this one, next to the name it sits beside.
 *
 * **The island publishes the picture the same way the name's island publishes the
 * name**: after the server accepts the write, and not before. **The server validates
 * the bytes, re-encodes them and may refuse the file outright** — so a URL published
 * early would name a picture that does not exist, and the rail would show a broken face
 * for an upload that was refused.
 *
 * **The picture is the control that does not save on change, and the reason is the
 * undo.** There is no undo on a file picker: a replaced picture is gone, and the old
 * object is removed from the store when the new one commits. So the screen says what
 * will happen *before* it happens rather than after.
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
  // *"Couldn't load your settings."* — and this is not that case. **The reason is that
  // there is no account to read anything about**, not that nothing failed: the screen's
  // one read that can fail is the city's, and `readHomeCity` needs a session, and this
  // branch has none. So there is no read to fail and nothing that could have loaded.
  //
  // **The city is not read here, and that is deliberate.** Reading it would be a request
  // with no session to read *with* — and the section is absent either way.
  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="" avatarUrl="">
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
  //
  // **This is the screen's one read that can fail, and the failure is the city's rather
  // than the screen's.** The name above it is unaffected, so the section is absent
  // rather than the screen being replaced by an error — a whole-screen error would be a
  // false statement about the field above it.
  const homeCity = await readHomeCity();

  return (
    <AppShell
      name={displayName(session.user)}
      email={session.user.email}
      avatarUrl={session.user.avatar_url}
    >
      <SettingsNav />

      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Profile</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          Your picture, your name, your address, and the city your Pulse Digest follows.
        </p>
      </header>

      {/*
        **The picture, first — because it is the first thing about you.**

        **It sits above the name, and that is the order the account sheet reads in**:
        face, then name, then address. The rail draws the disc beside the name in that
        order too, and the sheet opens with the pair — so the screen that edits them
        presents them in the order they are presented everywhere else.

        **The island is handed the seed and the display name.** The seed is the picture
        the account holds (`""` when it holds none), and the display name is the source
        of the initials — **the same name the rail shows**, so the fallback on this
        screen is the same letters the rail shows. The island publishes the new picture
        to the shell once the server accepts the write, so the rail, the bottom bar and
        the account sheet all follow it without a reload.

        **This is the one control here that does not save on change**, and the reason is
        the undo rather than the timing: a file is chosen, and there is no undo on a
        file picker — a replaced picture is gone. So the island says what will happen
        *before* it happens.
      */}
      <div className="mt-8 max-w-(--layout-container-reading)">
        <AvatarUpload initialAvatarUrl={session.user.avatar_url} name={displayName(session.user)} />
      </div>

      <div className="mt-12 max-w-(--layout-container-reading)">
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
            Your time zone decides when your Pulse Digest arrives. It sits with the delivery time
            under General.
          </p>
        </div>
      ) : null}
    </AppShell>
  );
}
