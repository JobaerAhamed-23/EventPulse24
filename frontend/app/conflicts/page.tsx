import { redirect } from "next/navigation";

import { ConflictsPanel } from "@/components/conflicts/conflicts-panel";
import { ConflictsError, NoOverlaps } from "@/components/conflicts/conflicts-states";
import { AppShell } from "@/components/shell/app-shell";
import { readConflicts } from "@/lib/conflict-list-read";
import { displayName } from "@/lib/display-name";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/conflicts` — the Conflict Review screen (FR-33, `Surface.Conflicts`).
 *
 * **A review surface, not a prompt.** The forced three-action sheet
 * (`Sheet.ConflictResolution`, FR-58) is where a conflict is caught — the moment the
 * user saves an event that clashes. This page is where a conflict is *reviewed*: every
 * pair the system has recorded, in two sections, with the decisions that were made
 * written down underneath.
 *
 * **The server states the fact; the page renders it.** `GET /api/personal/conflicts`
 * returns the pairs already split into `active` and `resolved`. The page does not
 * bucket, sort, decide which pairs are active, or compute a count — it renders the two
 * lists as they arrived (AD-10, applied to the review screen).
 *
 * **The counts are the server's too.** "Active (n)" and "Resolved (n)" are
 * `active.length` and `resolved.length` — the same lists the section renders, so the
 * count can never disagree with what is under it.
 *
 * **There is no auto-refresh.** The page re-reads once, after a successful write, when
 * `router.refresh()` re-runs this server component. A passive-pressure surface that
 * re-rendered under the user would move the button they were reaching for.
 */
export const dynamic = "force-dynamic";

export default async function ConflictsPage() {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  // **The Conflict Review is a signed-in surface.** `homeRoute` has already sent an
  // anonymous visitor to the preview and a half-onboarded one to `/onboarding`; what is
  // left is a signed-in user, or a session the API could not answer — and an unreadable
  // session is not a reason to show somebody else's conflicts.
  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="">
        <ConflictsError href="/conflicts" />
      </AppShell>
    );
  }

  const read = await readConflicts();

  if (read.kind === "unavailable") {
    return (
      <AppShell name={displayName(session.user)} email={session.user.email}>
        <ConflictsError href="/conflicts" />
      </AppShell>
    );
  }

  const active = read.pairs.active;
  const resolved = read.pairs.resolved;
  const quiet = active.length === 0 && resolved.length === 0;

  return (
    <AppShell name={displayName(session.user)} email={session.user.email}>
      <header className="flex flex-col gap-1">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
          These days overlap.
        </h1>
        <p className="max-w-(--layout-container-reading) text-ink-secondary [font:var(--type-scale-body-md)]">
          Every conflict pair the system has recorded. Active pairs need a decision; resolved pairs
          are immutable history.
        </p>
      </header>

      <div className="mt-8">
        {quiet ? <NoOverlaps /> : <ConflictsPanel active={active} resolved={resolved} />}
      </div>
    </AppShell>
  );
}

