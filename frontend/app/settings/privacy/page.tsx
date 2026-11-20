import { redirect } from "next/navigation";

import { RankingFormula } from "@/components/settings/ranking-formula";
import { SettingsNav } from "@/components/settings/settings-nav";
import { SettingsStates } from "@/components/settings/settings-states";
import { AppShell } from "@/components/shell/app-shell";
import { displayName } from "@/lib/display-name";
import { readRankingTransparency } from "@/lib/ranking-transparency-read";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/settings/privacy` — **the published ranking formula** (FR-22).
 *
 * **This closes a promise the product had made and not kept.** FR-22 says the Confidence
 * Pulse's formula and weights are "published in the PRD and immutable post-launch", and
 * names its own testable consequence: *"Settings → Privacy → 'Ranking algorithm version'
 * shows the current weights and the last-amendment date."* Until this screen, nothing in
 * the frontend rendered a formula at all — so no user was shown a *wrong* formula, but
 * none was shown the right one either.
 *
 * ## Only the ranking section is built
 *
 * `EXPERIENCE.md` §2 row 9 also commits this route to a data inventory, export (FR-52),
 * deletion, a training opt-out, the Amendment A-14 geo-IP consent toggle, the A-13
 * amendment-history timeline and a read-only mirror of `Settings → Sources`. **None of
 * those is here.** Export already lives on `/settings/account`, so that part of the route
 * starts as a reconciliation rather than a build, and it is deliberately not folded into
 * the work item that only ever owned FR-22.
 *
 * The settings nav row therefore describes what is actually behind it. A row promising
 * "your data" over a page that only explains ranking would be the same kind of unkept
 * promise this screen exists to close.
 *
 * ## "Unavailable" is not "there is no formula"
 *
 * The two look alike and mean opposite things, and on *this* screen the difference is the
 * whole point: a transparency page rendering a blank table reads as a product with no
 * ranking, which is a worse answer than one that says it could not answer. So a failed
 * read renders the settings' own error state.
 *
 * ## It is not Pro-gated
 *
 * How a user's feed is ranked is not a feature; it is an explanation they are owed.
 */
export const dynamic = "force-dynamic";

export default async function SettingsPrivacyPage() {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="" avatarUrl="">
        <SettingsStates />
      </AppShell>
    );
  }

  const name = displayName(session.user);
  const read = await readRankingTransparency();

  if (read.kind === "unavailable") {
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

  return (
    <AppShell
        name={name}
        email={session.user.email}
        avatarUrl={session.user.avatar_url}
      >
      <SettingsNav />

      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Privacy</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          How your Pulse is ranked, in full. Nothing here is personalised guesswork we
          won&apos;t show you.
        </p>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        <RankingFormula ranking={read.ranking} />
      </div>
    </AppShell>
  );
}
