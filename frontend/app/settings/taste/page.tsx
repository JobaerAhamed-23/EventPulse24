import { redirect } from "next/navigation";

import { SettingsNav } from "@/components/settings/settings-nav";
import { SettingsStates } from "@/components/settings/settings-states";
import { TasteMuteList } from "@/components/settings/taste-mute-list";
import { AppShell } from "@/components/shell/app-shell";
import { displayName } from "@/lib/display-name";
import { getSession, homeRoute } from "@/lib/session";
import { readTaste } from "@/lib/taste-mutes-read";

/**
 * `/settings/taste` — **the muted categories, and the way back** (FR-25).
 *
 * **This is where the mockup's prompt sends the user.** The "less of this" sheet says
 * *"You can undo anytime in Settings → Taste"*, and this is that screen: every category
 * the user has muted, with the server's own label for each, and a one-tap way back.
 *
 * **It is a sibling of `Settings → Sources`, not the same screen.** The sources screen
 * mutes *sources* — where the events came from — and this one mutes *categories* — what
 * the events are about. Two different subjects, two different controls, two screens. The
 * mockup is explicit that the reversal lives here, and a control that could express both
 * subjects at once would be a control that expressed neither well.
 *
 * **"Unavailable" is not "you have nothing muted".** The two look identical and mean
 * opposite things: a user whose read blinked would be shown an empty list, on the very
 * screen whose job is to let them undo what they muted. So the failed read renders the
 * settings' own error state, and an empty list — a real answer — renders its own quiet
 * empty state inside `TasteMuteList`.
 *
 * **It is not Pro-gated.** Muting a category is a preference, not a feature.
 */
export const dynamic = "force-dynamic";

export default async function SettingsTastePage() {
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
  const read = await readTaste();

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
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Taste</h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          Categories you&apos;ve asked us to show less of. They come back on their own.
        </p>
      </header>

      <div className="mt-8 max-w-(--layout-container-reading)">
        <TasteMuteList mutes={read.mutes} />
      </div>
    </AppShell>
  );
}
