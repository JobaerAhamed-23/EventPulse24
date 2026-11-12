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
 */

import Link from "next/link";
import { useState } from "react";

import { SignOutButton } from "@/components/auth/sign-out-button";
import { Sheet } from "@/components/sheets/sheet";

export type AccountProps = {
  /** The user's name, for the row and the panel. */
  name: string;
  /**
   * The user's email.
   *
   * It is the only account fact the session carries — `CurrentUserOut` sends the id, the
   * email and the onboarding status, and nothing else — so it is the only one shown. The
   * panel does not invent fields the backend has no endpoint for.
   */
  email: string;
};

/**
 * Who you are, and the one thing you can do about it.
 *
 * This is the whole account surface today. Changing an email, changing a password while
 * signed in and closing an account have no endpoints yet, so the panel does not offer
 * them: an affordance that cannot work is the same lie as a link to a 404.
 *
 * **Pricing is the one link in here**, and it is a real route — `/pricing` exists — so it
 * does not break the rule above. It is where a Free user reads what Pro adds, and where
 * a Pro user finds the portal. It is quiet, because the sheet is about the account, not
 * about the upsell: the plan is one line among the account's own facts.
 */
export function AccountPanel({ name, email }: AccountProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Avatar name={name} />
        <span className="flex min-w-0 flex-col">
          <span className="text-ink-primary [font:var(--type-scale-body-md)]">{name}</span>
          <span className="truncate text-ink-muted [font:var(--type-scale-meta-sm)]">{email}</span>
        </span>
      </div>
      <Link
        href="/pricing"
        className="text-ink-secondary underline underline-offset-4 [font:var(--type-scale-body-sm)]"
      >
        Pricing
      </Link>
      <SignOutButton />
    </div>
  );
}

/** The rail's account row: the button, and the sheet it opens. */
export function AccountMenu({ name, email }: AccountProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label={`Account: ${name}`}
        className="mt-1 flex w-full items-center gap-3 rounded-subtle px-2 py-2 text-left hover:bg-surface-subtle"
      >
        <Avatar name={name} />
        <span className="flex min-w-0 flex-col">
          <span className="text-ink-primary [font:var(--type-scale-body-md)]">{name}</span>
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
          <AccountPanel name={name} email={email} />
        </div>
      </Sheet>
    </>
  );
}

/**
 * The initials disc.
 *
 * It is `aria-hidden`: the name is beside it in text, and a screen reader announcing two
 * letters before the name it abbreviates is noise.
 */
function Avatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-inset text-ink-secondary [font:var(--type-scale-meta-sm)]"
    >
      {name.slice(0, 2).toUpperCase()}
    </span>
  );
}
