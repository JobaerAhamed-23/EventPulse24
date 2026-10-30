import { redirect } from "next/navigation";

import { BrandTopbar } from "@/components/brand-topbar";
import { OnboardingFlow } from "@/components/onboarding/onboarding-flow";
import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { getSession, sessionHeaders } from "@/lib/session";

/**
 * `/onboarding` — the three-step first run (FR-1).
 *
 * **The state is read on the server, with the first paint.** The flow has to open on the
 * step the user is actually on: FR-1 says someone who leaves mid-step is resumed at the
 * same step within 7 days, and resuming is only true if the first thing they see is that
 * step. Fetching it in the browser instead would paint step 1 and then jump, which is the
 * same bug wearing a spinner.
 *
 * Three gates before the flow renders:
 *
 *   - anonymous → `/signin`. There is no onboarding without an account, and `/signup`
 *     sends people here *after* it signs them in.
 *   - already completed → `/`. The AC's rule, and the reason a finished user who keeps
 *     the URL in a tab is not asked to do it again.
 *   - the API unreachable → the calm error, not a redirect loop with `/`.
 */
export const dynamic = "force-dynamic";

type OnboardingState = components["schemas"]["OnboardingStateOut"];
type Chip = components["schemas"]["InterestChipOut"];
type Connection = components["schemas"]["CalendarConnectionOut"];

export default async function OnboardingPage() {
  const session = await getSession();
  // `redirect` throws to unwind the render, so both calls stay outside any try/catch.
  if (session.kind === "anonymous") redirect("/signin");
  if (session.kind === "signed-in" && session.user.onboarding.completed) redirect("/");

  if (session.kind !== "signed-in") return <OnboardingUnavailable />;

  const headers = await sessionHeaders();
  const [state, chips, connection] = await Promise.all([
    readState(headers),
    readChips(headers),
    readConnection(headers),
  ]);

  if (state === null) return <OnboardingUnavailable />;

  return (
    <div className="flex min-h-screen flex-col">
      <BrandTopbar href="/onboarding" />
      <main className="flex-1">
        <OnboardingFlow state={state} chips={chips} connection={connection} />
      </main>
    </div>
  );
}

async function readState(headers: { cookie: string }): Promise<OnboardingState | null> {
  try {
    const response = await api.GET("/api/personal/onboarding", { headers });
    return response.data ?? null;
  } catch {
    return null;
  }
}

/**
 * The ten chips. An empty list is survivable: step 2 says so and stays skippable, because
 * an optional step must not be able to block an optional flow.
 */
async function readChips(headers: { cookie: string }): Promise<Chip[]> {
  try {
    const response = await api.GET("/api/personal/onboarding/interest-chips", { headers });
    return response.data?.items ?? [];
  } catch {
    return [];
  }
}

/** The calendar the user has already connected, if they come back to step 1. */
async function readConnection(headers: { cookie: string }): Promise<Connection | null> {
  try {
    const response = await api.GET("/api/personal/calendars", { headers });
    return response.data?.items?.[0] ?? null;
  } catch {
    return null;
  }
}

function OnboardingUnavailable() {
  return (
    <div className="flex min-h-screen flex-col">
      <BrandTopbar href="/onboarding" />
      <main className="fade-in mx-auto w-full max-w-(--layout-container-form) flex-1 px-6 py-20">
        <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
          Couldn&apos;t reach Pulse. Try again.
        </h1>
        <p className="mt-4 [font:var(--type-scale-body-md)] text-ink-secondary">
          Nothing is lost — your account is there, and setting up takes a minute whenever you come
          back.
        </p>
      </main>
    </div>
  );
}
