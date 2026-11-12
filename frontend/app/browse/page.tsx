import { redirect } from "next/navigation";

import { BrowseHero } from "@/components/browse/browse-hero";
import { BrowseSearch } from "@/components/browse/browse-search";
import { BrowseEmpty, BrowseError } from "@/components/browse/browse-states";
import { AppShell } from "@/components/shell/app-shell";
import { readBrowse } from "@/lib/browse-read";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/browse` — the Browse surface: the signed-in user's city, tonight and the next seven
 * days (FR-26, FR-48).
 *
 * **It renders inside the existing authed shell.** The sidenav, the brand-only topbar
 * and the sidenav footer are `AppShell`'s, and the shell is not forked or re-implemented
 * here — the same `AppShell` that `/`, `/timeline` and `/conflicts` use. Amendment A-12
 * is about what Browse puts *inside* that shell, not about replacing it.
 *
 * **The server states the fact; the page renders it.** The read returns one ranked pool,
 * already tiered and already carrying each card's save state. The page does not rank,
 * sort, re-tier or re-bucket (AD-10).
 *
 * **The route decision is the same one every authed route makes.** Anonymous →
 * `/preview`; signed in but not finished onboarding → `/onboarding`. Both are decided by
 * `homeRoute`, which is a pure function, and both are decided *here* rather than in
 * `proxy.ts` — the proxy has one job, and a second routing rule would run on every
 * request to every route.
 */
export const dynamic = "force-dynamic";

/** The server's page size. The soft cap and the chunk size are the same number. */
const PAGE_SIZE = 24;

/** The props Next passes the page: the route has no params, and the query string. */
type BrowsePageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/**
 * **The offset the reader asked for.**
 *
 * **The anchor's `href` is a real navigation, and the route honours it.** The chunk
 * loader intercepts the click so the chunk can arrive in place, but the `href` is
 * still `?offset=N` — and a link to a URL the page ignores is a link that lies. A
 * middle-click, a "copy link address", or a reader with JavaScript off must land on
 * the same chunk the anchor names.
 *
 * **A malformed offset is zero.** `?offset=abc` and `?offset=-5` are not numbers the
 * server can page with, and the first page is what the reader gets.
 */
async function requestedOffset(searchParams: BrowsePageProps["searchParams"]): Promise<number> {
  const params = await searchParams;
  const raw = params.offset;
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (typeof value !== "string") return 0;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) return 0;
  return parsed;
}

export default async function BrowsePage({ searchParams }: BrowsePageProps) {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  // **A Browse page for somebody who is not signed in would be showing a stranger's
  // city.** The read would be anonymous and would come back empty, which is a lie about
  // what the page is.
  if (session.kind !== "signed-in") {
    return (
      <AppShell name="" email="">
        <BrowseError />
      </AppShell>
    );
  }

  const offset = await requestedOffset(searchParams);
  const read = await readBrowse(offset);

  if (read.kind === "unavailable") {
    return (
      <AppShell name={displayName(session.user.email)} email={session.user.email}>
        <BrowseError />
      </AppShell>
    );
  }

  const browse = read.browse;
  const noCity = browse.city_missing;
  const noCards = browse.cards.length === 0;

  return (
    <AppShell name={displayName(session.user.email)} email={session.user.email}>
      {noCity || noCards ? (
        /*
         **A user with no city gets the same quiet empty state as a city with nothing
         on.** The surface shows one quiet state with "Change city" as the way out,
         rather than guessing a city the user never chose — a city they never picked
         would make "Change city" a correction of our guess instead of a setting of
         their preference.
        */
        <BrowseEmpty />
      ) : (
        /*
         **The 32px frame.** The shell's `<main>` carries `px-6` — 24px — and Browse's
         frame is 32px. The extra 8px is `px-2`, and it wraps the *whole* surface, so
         the hero and the grid share one left edge: a hero at 24px and a grid at 32px
         would be two surfaces pretending to be one.
         *
         **And it is not the city page's full-bleed 80px frame.** The city page bleeds
         to the viewport edge; Browse sits inside the authed shell's container, which is
         the whole difference between a public page and a signed-in one.
         */
        <div className="px-2">
          <BrowseHero browse={browse} />

          {/*
            **The search, the grid and the soft cap's way through, as one island.**
            *
            **Amendment A-11's search filters the loaded set**, and a filter that
            reached only part of the surface would be a filter that lied about how much
            it had narrowed — so the search owns the grid and the chunk loader, and the
            chunk's state lives inside it too. A chunk becomes part of the loaded set
            the moment it lands, so the query has to reach it.
            *
            **The anchor appears only when the server says there is more** — `has_more`
            * is the server's statement, not the client's arithmetic on `total`.
          */}
          <BrowseSearch
            cards={browse.cards}
            tierTwoStartsAt={browse.tier_2_starts_at}
            total={browse.total}
            hasMore={browse.has_more}
            quota={browse.quota}
            offset={offset}
            limit={PAGE_SIZE}
            city={browse.city}
            windowFrom={browse.window_from}
            timezone={browse.timezone}
          />
        </div>
      )}
    </AppShell>
  );
}

/**
 * A name for the sidenav's account row.
 *
 * **The email's local part is the best name the session carries** — the same rule the
 * digest home and the timeline use.
 */
function displayName(email: string): string {
  const local = email.split("@")[0] ?? email;
  const words = local.split(/[._-]+/).filter(Boolean);
  if (words.length === 0) return email;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}
