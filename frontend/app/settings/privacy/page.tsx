import { redirect } from "next/navigation";

import { DangerZone } from "@/components/settings/danger-zone";
import { DataInventory } from "@/components/settings/data-inventory";
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
 * amendment-history timeline and a read-only mirror of `Settings → Sources`.
 *
 * **The data inventory is now here** (2026-11-20) — PRD §10.2's *"Settings → Privacy →
 * 'What we store' displays the categories and current retention windows in plain
 * language"*, built from `RETENTION_ROWS` so it cannot drift from the registry the
 * database enforces. Deletion is here as the *danger zone* (Amendment A-16) rather than
 * as the route's own section, and export already lives on `/settings/account`.
 *
 * **Still missing:** the A-14 geo-IP consent toggle, the A-13 amendment-history timeline,
 * and the read-only mirror of `Settings → Sources`. Row 9 is not closed.
 *
 * The settings nav row therefore describes what is actually behind it. A row promising
 * "your data" over a page that only explains ranking would be the same kind of unkept
 * promise this screen exists to close.
 *
 * ## The danger zone lives here, and it lives in both branches
 *
 * Amendment A-16 puts the destructive control on this route, in a section of its own —
 * irreversibles are put away from the reversible ones, and away from the avatar upload
 * that sits next to them on `/settings/account`.
 *
 * **It renders in the `unavailable` branch too.** A failed ranking read must not
 * silently remove the one control on this page that destroys something: a danger zone
 * that vanishes when the page is unhealthy is the opposite of what a danger zone is for.
 * So the section is unconditional, and the `unavailable` branch carries it too.
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
      <AppShell name={name} email={session.user.email} avatarUrl={session.user.avatar_url}>
        <SettingsNav />

        <SettingsStates />

        {/*
          **The inventory renders here too, and for the same reason as the danger zone.**
          It depends on no API read — `RETENTION_ROWS` is a compiled-in mirror of the
          retention registry — so a failed *ranking* read is no reason to stop telling a
          user what is stored about them. A data inventory that vanishes when an
          unrelated endpoint blinks is one nobody can rely on.
        */}
        <div className="mt-8 max-w-(--layout-container-reading)">
          <DataInventory />
        </div>

        {/*
          **The danger zone renders even here.** A failed ranking read must not silently
          remove the one control on this page that destroys something — a danger zone
          that disappears when the page is unhealthy is the opposite of what a danger
          zone is for.
        */}
        <div className="mt-12 max-w-(--layout-container-reading)">
          <DangerZone
            deletionScheduledFor={session.user.deletion_scheduled_for}
            deletionRequestedAt={session.user.deletion_requested_at}
          />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell name={name} email={session.user.email} avatarUrl={session.user.avatar_url}>
      <SettingsNav />

      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Privacy</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          How your Pulse is ranked, in full. Nothing here is personalised guesswork we won&apos;t
          show you. Below that, everything we store about you and for how long. Then the danger
          zone — the one part of this page that can be undone only for the next thirty days.
        </p>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        <RankingFormula ranking={read.ranking} />
      </div>

      {/*
        **Readable things together, the irreversible one last.** The inventory explains
        what is kept; the danger zone destroys it. Putting the inventory between them is
        also the order a reader needs: what you hold, then the control that removes it.
      */}
      <div className="mt-12 max-w-(--layout-container-reading)">
        <DataInventory />
      </div>

      {/*
        **The danger zone is put away from the ranking formula.** It is the only
        destructive control on this page, and irreversible things do not sit beside
        readable ones.
      */}
      <div className="mt-12 max-w-(--layout-container-reading)">
        <DangerZone
          deletionScheduledFor={session.user.deletion_scheduled_for}
          deletionRequestedAt={session.user.deletion_requested_at}
        />
      </div>
    </AppShell>
  );
}
