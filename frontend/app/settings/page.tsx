import Link from "next/link";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/shell/app-shell";
import { getSession, homeRoute } from "@/lib/session";
import { SETTINGS_SECTIONS } from "@/lib/settings-sections";

/**
 * `/settings` — **the settings index.**
 *
 * ## Why it exists
 *
 * It did not, and that was the bug. The six settings screens shipped one per work item,
 * each inheriting the convention *"there is no `/settings` index page and no settings
 * sub-navigation"*, and each made reachable by a hand-written link from whichever page
 * shipped before it. The nav pointed at `/settings/reminders`, which has no links out;
 * `/settings/quiet-hours` held the only links to two more; `/settings/collections` was
 * linked from nowhere. **Four of six working screens could not be reached by clicking.**
 * The account row in the rail had meanwhile been downgraded from a link to a button
 * precisely because `/settings` 404'd.
 *
 * So this is the route the rail and the bottom bar now point at, and
 * `SETTINGS_SECTIONS` is the list it and `SettingsNav` both render.
 *
 * ## It follows the house pattern, minus the step it has no use for
 *
 * The five steps every `/settings/*` route performs, in order:
 *
 * 1. `force-dynamic` — a settings screen is per-user and is never cached.
 * 2. `homeRoute(session)` redirects an anonymous visitor to `/preview` and a
 *    half-onboarded one to `/onboarding`. `redirect` throws, so it is called outside any
 *    try/catch.
 * 3. Not signed in → `SettingsStates` inside an empty `AppShell`.
 * 4. The read came back `unavailable` → `SettingsStates` inside a named `AppShell`.
 * 5. Otherwise the page itself, with a header and a reading-width content block.
 *
 * **Step 4 is absent, because this page reads nothing.** It renders a module constant,
 * so there is no call that can fail and no unavailable state to render — and a page that
 * imported `SettingsStates` to render a failure it cannot have would be claiming a
 * dependency it does not have. Steps 1, 2, 3 and 5 are all here.
 *
 * **Step 3 keeps `SettingsStates` out too, for the same reason**: the signed-out branch
 * exists to avoid offering to change settings that are not the caller's, and with no
 * read to fail the honest render is an empty shell. `homeRoute` has already redirected
 * this visitor in every case the product actually produces; the branch is the belt to
 * its braces.
 *
 * ## It does not render `SettingsNav`
 *
 * The sub-nav *is* this list, in a compact shape. Rendering both would put the same six
 * links on the screen twice, once with descriptions and once without. The index is the
 * long form; every other settings route gets the short one.
 */
export const dynamic = "force-dynamic";

export default async function SettingsIndexPage() {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  // **Settings are a signed-in surface.** A settings index for somebody who is not
  // signed in would be a table of contents for somebody else's account.
  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="">
        {null}
      </AppShell>
    );
  }

  return (
    <AppShell name={displayName(session.user.email)} email={session.user.email}>
      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Settings</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          How EventPulse24 works for you.
        </p>
      </header>

      {/*
        **A list, because it is a list.** Six rows in a `<ul>`, each one a whole-row
        link: the target is the row the user sees, not the label inside it — the same
        rule `SidenavItem` follows.
      */}
      <ul className="mt-8 flex max-w-(--layout-container-reading) flex-col gap-3">
        {SETTINGS_SECTIONS.map((section) => (
          <li key={section.href}>
            <Link
              href={section.href}
              className="flex items-center gap-4 rounded-subtle border border-border-subtle bg-surface-elevated px-4 py-4 hover:bg-surface-subtle"
            >
              <span className="flex min-w-0 flex-col gap-1">
                <span className="text-ink-primary [font:var(--type-scale-body-md)]">
                  {section.label}
                </span>
                <span className="text-ink-secondary [font:var(--type-scale-body-sm)]">
                  {section.description}
                </span>
              </span>
              {/*
                Decorative: the row is a link and announces itself as one, and a chevron
                read aloud after every label is noise. The same rule as the account
                row's disclosure mark.
              */}
              <span
                aria-hidden="true"
                className="ml-auto text-ink-muted [font:var(--type-scale-meta-sm)]"
              >
                ›
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </AppShell>
  );
}

/**
 * A name for the sidenav's account row.
 *
 * **The email's local part is the best name the session carries** — the same rule the
 * digest home, the Timeline and the other settings routes use.
 */
function displayName(email: string): string {
  const local = email.split("@")[0] ?? email;
  const words = local.split(/[._-]+/).filter(Boolean);
  if (words.length === 0) return email;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}
