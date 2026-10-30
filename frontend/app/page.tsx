import Link from "next/link";
import { redirect } from "next/navigation";

import { SignOutButton } from "@/components/auth/sign-out-button";
import { PersonalEventsSection } from "@/components/personal-events-section";
import { BrandTopbar } from "@/components/brand-topbar";
import { SavedEventsSection } from "@/components/saved-events-section";
import { getSession, homeRoute } from "@/lib/session";

/**
 * `/` — the signed-in home, and the route decision that gets people to the right one.
 *
 * In the route map `/` is the **Pulse Digest**. That is the Pulse Digest intent's work,
 * so until then this is the calm placeholder the onboarding intent promised: no digest
 * cards, no invented scores, no fake data of any kind — just a true statement that the
 * Pulse is being prepared, and the two surfaces the user does have.
 *
 * **Three visitors, three answers** (`lib/session.ts` holds the rule, as a pure function
 * this page calls):
 *
 *   - anonymous → `/preview`, the public preview (AD-12);
 *   - signed in, onboarding unfinished → `/onboarding`, which resumes at their step;
 *   - signed in and onboarded → this page.
 *
 * A fourth case is not a redirect: when the API cannot be reached, the page says so.
 * Sending a signed-in user to the anonymous preview because one request failed would tell
 * them they are logged out when they are not.
 *
 * **The decision is made here, not in `proxy.ts`.** The proxy has one job — forward
 * `/api/*` to Django — and a redirect rule there would be a second one, running on every
 * request to every route. Here it is a function call on the route that needs it.
 *
 * The page is rendered **per request**, as it was before: it shows the signed-in user's
 * own events and now also their session, and neither can be baked into a build.
 */
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const session = await getSession();
  const destination = homeRoute(session);
  // `redirect` throws, so it is called outside any try/catch.
  if (destination !== null) redirect(destination);

  if (session.kind !== "signed-in") return <HomeUnavailable />;

  return (
    <div className="flex min-h-screen flex-col">
      <BrandTopbar href="/" />
      <main className="fade-in mx-auto w-full max-w-(--layout-container-reading) flex-1 px-6 py-12">
        <h1 className="text-ink-primary [font:var(--type-scale-display-md)]">
          Your Pulse is being prepared.
        </h1>
        <p className="mt-4 [font:var(--type-scale-body-lg)] text-ink-secondary">
          The Pulse Digest isn&apos;t ready yet. Until it is, your personal events and the events
          you&apos;ve saved are here.
        </p>

        {/*
          The personal-events section owns its own "Add event" affordance, inside the
          panel that knows the create → conflict → resolve round trip. The page does not
          add a second one: the nav-level Add button (`components/add-event-button.tsx`)
          mounts its own copy of that panel, so rendering both put two "Your personal
          events" lists on this page, one of them permanently empty. The button stays in
          the codebase for the sidenav that will carry it.
        */}
        <section className="mt-12" aria-label="Your personal events">
          <PersonalEventsSection />
        </section>

        <section className="mt-12" aria-label="Saved events">
          <SavedEventsSection />
        </section>
      </main>

      {/*
        Account affordances live in the footer, not the topbar (the topbar-quiet rule).
        The sidenav footer that will hold "Account" does not exist yet.
      */}
      <footer className="border-t border-border-subtle px-6 py-8">
        <div className="mx-auto flex max-w-(--layout-container-reading) flex-col gap-3">
          <p className="[font:var(--type-scale-body-sm)] text-ink-muted">
            Signed in as {session.user.email}
          </p>
          <SignOutButton />
        </div>
      </footer>
    </div>
  );
}

/**
 * The API could not be reached. The user keeps their session and their place; they are
 * told what happened, in the product's error voice (`EXPERIENCE.md` §6: honest, brief).
 */
function HomeUnavailable() {
  return (
    <div className="flex min-h-screen flex-col">
      <BrandTopbar href="/" />
      <main className="fade-in mx-auto w-full max-w-(--layout-container-reading) flex-1 px-6 py-20">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
          Couldn&apos;t reach Pulse. Try again.
        </h1>
        <p className="mt-4 [font:var(--type-scale-body-md)] text-ink-secondary">
          Your events are safe. This is on our side.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block [font:var(--type-scale-body-sm)] text-accent-terracotta underline underline-offset-4"
        >
          Try again →
        </Link>
      </main>
    </div>
  );
}
