"use client";

/**
 * `Component.Sidenav.Footer` — the account row, and the sheet behind it.
 *
 * **The row is a control, not a route.** It was a `<Link href="/settings">`, and
 * `/settings` does not exist. The sidenav's own rule — "a link to a 404 is a lie about
 * where the label goes" — made every inert *route* a `<span>`, and the account row was
 * the one place in the rail that broke it. It is now a button onto a sheet, which is a
 * real surface: the same control-versus-route distinction `MoreMenu` already draws.
 *
 * **The sheet is where Sign out lives.** `SignOutButton` sat in the home's footer until
 * the Pulse Digest replaced that page; since then nothing rendered it, so the endpoint
 * worked and the control was unreachable. The button's own docstring named this footer as
 * where it belonged once the footer existed. It exists.
 *
 * **Two shapes, one panel.** The rail opens `AccountPanel` in a sheet. The mobile
 * overflow sheet renders the same panel *inline*, because a sheet opened from inside a
 * sheet is a second overlay level, and `Sheet` keeps there being exactly one.
 *
 * **The face is the shell's own disc, and it is live.** The row and the panel draw
 * `AvatarDisc` — **the same component**, not a copy — so the face in the rail, the face
 * in the sheet and the face on the profile screen cannot drift apart. And the URL is
 * read from the avatar store, so a picture saved on this page appears in the row
 * without a reload.
 */

import Link from "next/link";
import { useState } from "react";

import { SignOutButton } from "@/components/auth/sign-out-button";
import { Sheet } from "@/components/sheets/sheet";
import { AvatarDisc } from "@/components/shell/avatar-disc";
import { useLiveAvatar } from "@/lib/avatar-store";
import { useLiveName } from "@/lib/session-name";

export type AccountProps = {
  /**
   * The user's name, for the row and the panel.
   *
   * **It is the seed, not the truth.** The shell is rendered on the server, so this is
   * the name the page was drawn with — and a name saved *after* the render is newer.
   * `useLiveName` takes the published name when there is one and falls back to this,
   * which is how the rail follows a save that happened on this page.
   */
  name: string;
  /**
   * The user's email.
   *
   * **The session carries four things** — the id, the email, the name and the
   * onboarding status — and **the panel shows two of them**: the name and the email.
   *
   * **The panel does not invent fields the backend has no endpoint for.** The id is
   * the account's key rather than something to show, and the onboarding status is a
   * fact about a flow rather than about the person.
   */
  email: string;
  /**
   * The user's picture — `""` when the account has none.
   *
   * **It is the seed, not the truth**, for the same reason the name is: the shell was
   * rendered on the server, and a picture uploaded after that render is newer.
   * `useLiveAvatar` takes the published picture when there is one.
   */
  avatarUrl: string;
};

/**
 * Who you are, and the one thing you can do about it.
 *
 * This is the whole account surface today. **The name is the one thing that can be
 * changed** — it has an endpoint, and "Edit your name" goes to the screen that edits
 * it. Changing an email, changing a password while signed in and closing an account
 * have no endpoints yet, so the panel does not offer them: an affordance that cannot
 * work is the same lie as a link to a 404.
 *
 * **The password is changed by the reset flow, not from here** — and that flow ends the
 * account's other sessions, so it is not a thing a panel can quietly do on someone's
 * behalf.
 *
 * **One link, and it is a real route.** `/settings/profile` exists. The two links this
 * panel used to carry are gone: `/settings` because the rail already has a Settings row
 * that goes to the same index — two ways to one place, and the rail's is the one that is
 * always there — and `/pricing` because **the sheet is about the account, not about the
 * upsell.** The account's plan already has a home: `/settings/account` shows the plan,
 * the payment state and the data export.
 *
 * **The row stays a button**, and that is unchanged. The sheet is the only surface that
 * mounts Sign out at both breakpoints, and the rail's own Settings row already goes to
 * `/settings`.
 */
export function AccountPanel({ name, email, avatarUrl }: AccountProps) {
  // **The live name, not the rendered one.** The panel shows what to call the person,
  // and the name the account holds may have changed since the page was drawn.
  const live = useLiveName(name);
  // **The live picture, for the same reason.** The account sheet is where the picture is
  // read most carefully — it is the face the sheet opens with — so a picture saved
  // elsewhere on the page must be the one shown here.
  const picture = useLiveAvatar(avatarUrl);

  return (
    /*
      **The hook is what the ordering assertion finds the panel by.** Without it, the
      nearest `<div>` to the Sign out button is `SignOutButton`'s own wrapper — which
      has one child — and an assertion built on that is true whatever the panel's order
      is. The hook names the panel's *root*, so "Sign out is last" is a claim about the
      panel and not about the button.
    */
    <div className="flex flex-col gap-4" data-account-panel>
      <div className="flex items-center gap-3">
        <AvatarDisc avatarUrl={picture} name={live} />
        <span className="flex min-w-0 flex-col">
          <span className="text-ink-primary [font:var(--type-scale-body-md)]">{live}</span>
          <span className="truncate text-ink-muted [font:var(--type-scale-meta-sm)]">{email}</span>
        </span>
      </div>
      {/*
        **"Edit your name", not "Profile".** The section in the settings nav is
        "Profile"; the link says what it does. The rail's Settings row points at the
        index, and the index carries the Profile row — so the two labels are different on
        purpose, and the link here is the one that names the action.
      */}
      <Link
        href="/settings/profile"
        className="text-ink-secondary underline underline-offset-4 [font:var(--type-scale-body-sm)]"
      >
        Edit your name
      </Link>
      <SignOutButton />
    </div>
  );
}

/** The rail's account row: the button, and the sheet it opens. */
export function AccountMenu({ name, email, avatarUrl }: AccountProps) {
  const [open, setOpen] = useState(false);
  // **The live name, not the rendered one** — the row is the account's face, and it
  // must agree with the sheet it opens.
  const live = useLiveName(name);
  // **And the live picture, for the same reason** — the row and the sheet must show the
  // same face, and it must be the current one.
  const picture = useLiveAvatar(avatarUrl);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label={`Account: ${live}`}
        className="mt-1 flex w-full items-center gap-3 rounded-subtle px-2 py-2 text-left hover:bg-surface-subtle"
      >
        <AvatarDisc avatarUrl={picture} name={live} />
        <span className="flex min-w-0 flex-col">
          <span className="text-ink-primary [font:var(--type-scale-body-md)]">{live}</span>
          <span className="text-ink-muted [font:var(--type-scale-meta-sm)]">Account</span>
        </span>
        {/*
          The disclosure mark is decorative: `aria-haspopup="dialog"` is what tells a
          screen reader the row opens something, and a chevron read aloud is noise.
        */}
        <span
          aria-hidden="true"
          className="ml-auto text-ink-muted [font:var(--type-scale-meta-sm)]"
        >
          ›
        </span>
      </button>

      <Sheet open={open} onClose={() => setOpen(false)} label="Account">
        <div className="p-4">
          <AccountPanel name={name} email={email} avatarUrl={avatarUrl} />
        </div>
      </Sheet>
    </>
  );
}
