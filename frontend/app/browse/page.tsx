import { redirect } from "next/navigation";

import { CoverageRequestControl } from "@/components/browse/coverage-request-control";
import { BrowseHero } from "@/components/browse/browse-hero";
import { BrowseQuotaProvider } from "@/components/browse/browse-quota-provider";
import { BrowseSearch } from "@/components/browse/browse-search";
import {
  BrowseEmpty,
  BrowseError,
  BrowseCollecting,
  BrowseNoSources,
} from "@/components/browse/browse-states";
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

  /*
   **The four honest states.**
   *
   **A city with no events is not one thing.** It can be *collecting* — we registered
   **sources and are waiting for the first events — or *quiet* — covered, and simply
   **nothing on tonight — or it can have *no sources* — we never found anything to
   **collect from. Those are three different facts, and the order of the branches below
   **is the order they are checked in.
   *
   **The order is load-bearing.** `city_missing` comes first, because a user with no
   **city has no collection to report and must not be told collection is under way.
   **`collecting` comes next, because a collecting city has no cards *by definition* —
   **it has not published anything yet — and must not fall through to the quiet state.
   **That fall-through is the bug this state exists to fix.
   */
  const status = browse.city_collection_status;
  const isCollecting = status === "collecting";
  /*
   **The no-sources family: four statuses, one honest sentence.**
   *
   **They are four different facts** — no provider covers the city
   *(`no_providers`), provisioning itself failed (`failed`), every source gave nothing
   *(`yielded_nothing`), or somebody stopped it (`paused`) — **and from the reader's
   *side they are one sentence**: we have nothing to collect this city from, so there
   *are no events, and here is the way to ask for one.
   *
   **The distinction is not lost — it is in the payload**, and it is what the editorial
   *surface reads. The reader has no way to act on the difference between "we never
   *tried" and "we tried and got nothing", and a sentence that pretended to would be
   *inventing a distinction the reader cannot use.
   */
  const hasNoSources =
    status === "no_providers" ||
    status === "failed" ||
    status === "yielded_nothing" ||
    status === "paused";
  /*
   **A `live` city is the quiet state's city.**
   *
   **A covered city with nothing on tonight is not a special case — it is what a
   *working collection looks like on a Tuesday.** So `live` needs no *treatment* of its
   *own: the quiet state below is the answer for it, and the ordinary surface is the
   *answer for it when it has cards.
   *
   **The comparison is written out anyway.** A reader of this file should be able to see
   *that `live` is *handled* — by falling through — rather than infer it from its
   *absence, and the vocabulary test holds the two surfaces to the same set of statuses
   *they recognise. A status that is handled by omission is still a status the surface
   *knows about.
   *
   **And a `live` city with no cards is the quiet state.** The condition is
   **`noCards`** — a `live` city *with* cards has to reach the ordinary surface below,
   *so `isLive` cannot be part of it. It is used below, to say what the ordinary
   *surface is for.
   */
  const isLive = status === "live";

  /*
   **The coverage request, and where it is offered.**
   *
   **It is rendered once, at the page level, and the *condition* is what decides
   **whether the reader is offered it. **The control appears in the no-sources family
   **and nowhere else** — asking us to collect a city we are already collecting is
   **asking for what we are already doing, and a covered city that is simply quiet is
   **not broken.
   *
   **It is a client island in a server page**, and that is the seam the codebase
   **already uses**: the hero's cards are islands too, and `browse-save.tsx` **owns its
   **own write.**
   */
  const coverageRequest = hasNoSources ? <CoverageRequestControl city={browse.city} /> : null;

  return (
    <AppShell
      name={displayName(session.user)}
      email={session.user.email}
      avatarUrl={session.user.avatar_url}
    >
      {noCity ? (
        /*
         **A user with no city gets the quiet empty state.** The surface shows it with
         * "Change city" as the way out, rather than guessing a city the user never
         * chose — a city they never picked would make "Change city" a correction of
         * our guess instead of a setting of their preference.
         *
         **It is not the collecting state.** A user with no city has no collection to
         * report, and telling them we are collecting for them would be a claim about a
         * city they do not have.
         */
        <BrowseEmpty />
      ) : isCollecting ? (
        /*
         **The collecting state.** Our sources are registered and have not answered
         * yet. **This replaces the hero**, so it carries the `<h1>` itself.
         *
         **It says "check back soon" and nothing more**, because that is the whole of
         * what we know: we are collecting. A date we cannot keep is a lie, and so is a
         * count we have not got.
         */
        <BrowseCollecting city={browse.city} coverageRequest={coverageRequest} />
      ) : hasNoSources ? (
        /*
         **The no-sources state.** We have no sources for this city, so there are no
         * events — and this is the one empty state with a way out: ask us to cover it.
         *
         **It is not the quiet state.** A covered city that is simply quiet must not be
         * told its sources failed.
         *
         **The coverage request is offered here and only here.** The node is built once
         * above, guarded by `hasNoSources`, and this is where it is placed.
         */
        <BrowseNoSources city={browse.city} coverageRequest={coverageRequest} />
      ) : noCards ? (
        /*
         **The quiet state.** A covered city with nothing on tonight. The existing
         * `BrowseEmpty`, unchanged — its copy is the honest answer for exactly this
         * case, and a covered city must not be told its sources failed.
         *
         **This also covers a city that was never provisioned**
         * (`city_collection_status` is empty). We have no events for it and we are not
         * collecting for it yet, and the quiet state is the honest answer to that.
         *
         **A `live` city with no cards is here too** — that is what a working
         *collection looks like on a Tuesday. `isLive` is named above so the status is
         **recognised* in code and not merely handled by omission; the vocabulary test
         *holds both surfaces to the same set.
         */
        <BrowseEmpty />
      ) : (
        /*
         **The ordinary surface — a city that has events.**
         *
         **A `live` city with cards lands here**, and so does any city that has cards
         *and a status the frontend does not recognise. **The cards are the cards**: a
         *listing we have is a listing we show, whatever our collection is doing, and
         *degrading a city that has events because of a status the frontend has not
         *learned about would throw away real events.
         *
         **No frame of its own — the shell carries it.** Browse used to add `px-2` on
         top of `<main>`'s `px-6` to make a 32px frame. That was 8px more than every
         other authed surface, so a reader moving from Settings or the Timeline to
         Browse watched the heading step 8px to the right, and the two surfaces read as
         two different pages rather than one app.

         **The shell's frame is now responsive** (24/48/80px, from
         `--layout-page-padding-*`), so the thing Browse wanted — a wider frame on a
         wide screen — it now gets, along with everything else and on the same edge.
         *
         * **`isLive` is read here so the status is *recognised* in code**, not merely
         * handled by omission — and the vocabulary test holds this surface and the city
         * page's to the same set of statuses.
         */
        <div data-browse-live={isLive ? "true" : "false"}>
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
