import { redirect } from "next/navigation";

import { SettingsNav } from "@/components/settings/settings-nav";
import { SettingsStates } from "@/components/settings/settings-states";
import { SourceList } from "@/components/settings/source-list";
import { SourceTrustLegend } from "@/components/settings/source-trust-legend";
import { AppShell } from "@/components/shell/app-shell";
import { displayName } from "@/lib/display-name";
import { readSources } from "@/lib/source-mutes-read";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/settings/sources` — **the source registry, with each source's trust and visibility
 * control** (FR-13, FR-16).
 *
 * **The screen's job is transparency.** Every source that informs the user's timeline is
 * listed here, including the ones they have muted. A muted source that vanished would be
 * a preference the user could not see or undo, on the very screen whose purpose is to
 * tell them what is shaping their brief.
 *
 * **It lives under `/settings` because the navigation is closed.** DESIGN.md forbids adding
 * nav rows, and the sidenav's Settings item matches `pathname.startsWith("/settings/")`,
 * so this route is reachable with no nav change — and the sub-nav renders
 * `SETTINGS_SECTIONS`, so it is reachable from every settings screen too.
 *
 * **"Unavailable" is not "you have no sources".** The two look identical and mean opposite
 * things: a user whose read blinked would be shown an empty registry, on the screen whose
 * whole job is to say what is informing their timeline. So the failed read renders the
 * settings' own error state, and the empty registry — a real answer, since the registry
 * genuinely has few sources today — renders its own quiet empty state inside
 * `SourceList`.
 *
 * **It is not Pro-gated.** Muting a source is a preference, not a feature.
 */
export const dynamic = "force-dynamic";

export default async function SettingsSourcesPage() {
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

  const name = displayName(session.user);
  const read = await readSources();

  if (read.kind === "unavailable") {
    return (
      <AppShell name={name} email={session.user.email}>
        <SettingsNav />

        <SettingsStates />
      </AppShell>
    );
  }

  return (
    <AppShell name={name} email={session.user.email}>
      <SettingsNav />

      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Sources</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          Where your events come from. Mute a source, show less of it, or leave it as it is.
        </p>
        {/*
          **The legend is in the head, where the reading is learned.** The mockup puts it
          there, and a dot row without one is a number the user cannot interpret.
        */}
        <div className="mt-3">
          <SourceTrustLegend />
        </div>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        <SourceList groups={read.groups} />
      </div>
    </AppShell>
  );
}
