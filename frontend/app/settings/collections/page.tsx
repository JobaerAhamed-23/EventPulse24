import { redirect } from "next/navigation";

import { CollectionManager } from "@/components/collections/collection-manager";
import { SettingsStates } from "@/components/settings/settings-states";
import { AppShell } from "@/components/shell/app-shell";
import { UpgradePrompt } from "@/components/upgrade/upgrade-prompt";
import { readCollections } from "@/lib/collections-read";
import { readIsPro } from "@/lib/entitlement-read";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/settings/collections` — **FR-49's first screen**.
 *
 * TRACEABILITY.md: *"no screen shows creating, viewing, or managing a collection."* This is
 * that screen, and it is **the one surface in this intent with no approved design** —
 * EXPERIENCE.md claims `settings-desktop.html` covers FR-49 and the mockup contains no
 * collection content at all. It is therefore built from the design system's existing
 * vocabulary and invents nothing.
 *
 * **It lives under `/settings` because the navigation is closed.** DESIGN.md's rule forbids
 * adding routes to the nav, with Browse as its single named exception, so a top-level
 * `/collections` would be a route nothing could point at. The sidenav's Settings item
 * matches `pathname.startsWith("/settings/")`, so this is reachable with no nav change.
 *
 * **A Free user is shown what collections are and offered them — not hidden, not a modal.**
 * The create form is simply absent rather than present-and-refusing: letting somebody name
 * a collection and *then* telling them they cannot have one would be accurate and still a
 * trap.
 *
 * **A lapsed Pro user sees their collections and can read them.** Their rows are kept on
 * purpose — `saved-collections-api` gates only the two operations that add — so the list
 * renders rather than vanishing, which would look like the deletion the brief forbids.
 */
export const dynamic = "force-dynamic";

/**
 * The sentence a Free user is offered collections with.
 *
 * **The backend's `COLLECTIONS_UPGRADE_HINT`, spelled again — the same cost
 * `/settings/quiet-hours` records.** A Free user is never refused here, because they are
 * never given a control that could be refused, so no 409 ever arrives to carry the server's
 * copy. `page.test.tsx` pins the exact string against the backend constant.
 */
const COLLECTIONS_HINT = "Group your saves into collections with Pro.";

export default async function SettingsCollectionsPage() {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="">
        <SettingsStates />
      </AppShell>
    );
  }

  const name = displayName(session.user.email);
  const [read, isPro] = await Promise.all([readCollections(), readIsPro()]);

  // **"Unavailable" is not "you have none".** The two look identical on screen and mean
  // opposite things — a Pro user with three collections whose read blinked would be shown
  // an empty state that reads as data loss.
  if (read.kind === "unavailable") {
    return (
      <AppShell name={name} email={session.user.email}>
        <SettingsStates />
      </AppShell>
    );
  }

  const collections = read.collections;

  return (
    <AppShell name={name} email={session.user.email}>
      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Collections</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          Group your saved events however you like.
        </p>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        {isPro ? (
          <CollectionManager initial={collections} />
        ) : collections.length > 0 ? (
          <>
            {/*
              **A lapsed Pro user.** Their collections are still theirs and still readable;
              what stopped is the ability to make the set bigger. Showing the manager with
              no create form would be a lie about what they can do, so the list is rendered
              read-only beside the offer.
            */}
            <ul className="flex flex-col gap-3" data-lapsed-collections>
              {collections.map((collection) => (
                <li
                  key={collection.id}
                  data-collection-row={collection.id}
                  className="rounded-card border border-border-subtle px-4 py-3"
                >
                  <span className="text-ink-primary [font:var(--type-scale-body-md)]">
                    {collection.name}
                  </span>
                  <span className="ml-3 text-ink-muted [font:var(--type-scale-meta-sm)]">
                    {collection.item_count === 1 ? "1 event" : `${collection.item_count} events`}
                  </span>
                </li>
              ))}
            </ul>
            <UpgradePrompt hint={COLLECTIONS_HINT} className="mt-6" />
          </>
        ) : (
          <>
            <p className="text-ink-secondary [font:var(--type-scale-body-md)]">
              Collections let you group your saves into something like “Music this month” or “For
              the kids”.
            </p>
            <UpgradePrompt hint={COLLECTIONS_HINT} className="mt-6" />
          </>
        )}
      </div>
    </AppShell>
  );
}

/**
 * A name for the sidenav's account row — the email's local part, the same rule every other
 * authed surface uses.
 */
function displayName(email: string): string {
  const local = email.split("@")[0] ?? email;
  const words = local.split(/[._-]+/).filter(Boolean);
  if (words.length === 0) return email;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}
