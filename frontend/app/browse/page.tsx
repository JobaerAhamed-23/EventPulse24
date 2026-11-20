import { redirect } from "next/navigation";

import { BrowseHero } from "@/components/browse/browse-hero";
import { BrowseQuotaProvider } from "@/components/browse/browse-quota-provider";
import { BrowseSearch } from "@/components/browse/browse-search";
import { BrowseEmpty, BrowseError } from "@/components/browse/browse-states";
import { AppShell } from "@/components/shell/app-shell";
import { readBrowse } from "@/lib/browse-read";
import { displayName } from "@/lib/display-name";
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
      <AppShell name="" email="" avatarUrl="">
        <BrowseError />
      </AppShell>
    );
  }

  const offset = await requestedOffset(searchParams);
  const read = await readBrowse(offset);

  if (read.kind === "unavailable") {
    return (
      <AppShell
        name={displayName(session.user)}
        email={session.user.email}
        avatarUrl={session.user.avatar_url}
      >
        <BrowseError />
      </AppShell>
    );
  }

  const browse = read.browse;
  const noCity = browse.city_missing;
  const noCards = browse.cards.length === 0;

  return (
    <AppShell
        name={displayName(session.user)}
        email={session.user.email}
        avatarUrl={session.user.avatar_url}
      >
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
         **No frame of its own — the shell carries it.** Browse used to add `px-2` on
         top of `<main>`'s `px-6` to make a 32px frame. That was 8px more than every
         other authed surface, so a reader moving from Settings or the Timeline to
         Browse watched the heading step 8px to the right, and the two surfaces read as
         two different pages rather than one app.

         **The shell's frame is now responsive** (24/48/80px, from
         `--layout-page-padding-*`), so the thing Browse wanted — a wider frame on a
         wide screen — it now gets, along with everything else and on the same edge.
         */
        <div>
          {/*
            **The live allowance, held for the whole surface.**

            **The hero's note and the cards' buttons read the same number, and that
            number moves.** One save spends the Free allowance, so the note in the hero
            and the wall on every other card have to move with it — and the hero is a
            server component while the cards are a client island, so the shared number
            cannot be a prop. The provider holds the server's last answer and asks again
            after a save. See `browse-quota-provider.tsx`.
          */}
          <BrowseQuotaProvider quota={browse.quota}>
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
          </BrowseQuotaProvider>
        </div>
      )}
    </AppShell>
  );
}
