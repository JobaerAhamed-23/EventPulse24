import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "@/app/page";

/**
 * `/` — the routing decision and the placeholder home.
 *
 * The three redirect branches are the heart of it: an anonymous visitor belongs on
 * `/preview`, a half-onboarded user on `/onboarding`, and an onboarded one here. The
 * fourth case — the API unreachable — must *not* redirect, or a blip would throw a
 * signed-in user out to the marketing page.
 */

const getSession = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  // `homeRoute` is the real one: it is the rule under test, and `lib/session.test.ts`
  // pins it directly. Stubbing it here would let the page and the rule drift apart.
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  // The page renders the real sign-out button, which is a client component with a router.
  // Its own behaviour is tested in `components/auth/sign-out-button.test.tsx`.
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

// The two server sections read through the API; the page's own test is about the page.
vi.mock("@/components/personal-events-section", () => ({
  PersonalEventsSection: () => <p>Personal events section</p>,
}));

vi.mock("@/components/saved-events-section", () => ({
  SavedEventsSection: () => <p>Saved events section</p>,
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  onboarding: { completed: true, current_step: null },
};

beforeEach(() => {
  getSession.mockReset();
  redirect.mockReset();
});

describe("the routing decision", () => {
  it("sends an anonymous visitor to the public preview", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    await HomePage();

    expect(redirect).toHaveBeenCalledWith("/preview");
  });

  it("sends a signed-in user who hasn't finished onboarding to /onboarding", async () => {
    getSession.mockResolvedValue({
      kind: "signed-in",
      user: { ...USER, onboarding: { completed: false, current_step: 1 } },
    });

    await HomePage();

    expect(redirect).toHaveBeenCalledWith("/onboarding");
  });

  it("keeps an onboarded user here", async () => {
    getSession.mockResolvedValue({ kind: "signed-in", user: USER });

    render(await HomePage());

    expect(redirect).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { level: 1, name: "Your Pulse is being prepared." }),
    ).toBeInTheDocument();
  });

  it("shows the calm error, and does not redirect, when the API can't be reached", async () => {
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await HomePage());

    expect(redirect).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Couldn't reach Pulse. Try again.",
    );
  });
});

describe("the placeholder home", () => {
  beforeEach(() => {
    getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  });

  it("hosts the personal and saved sections", async () => {
    // The work item: the home "links to personal and saved events". Neither has a route
    // of its own yet, so both are here rather than linked to a 404.
    render(await HomePage());

    expect(screen.getByText("Personal events section")).toBeInTheDocument();
    expect(screen.getByText("Saved events section")).toBeInTheDocument();
  });

  it("offers sign-out, and names who is signed in", async () => {
    render(await HomePage());

    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(screen.getByText("Signed in as maya@example.test")).toBeInTheDocument();
  });

  it("shows no digest content, because there is no digest yet", async () => {
    // The calm placeholder must not imply a Pulse Digest exists: no cards, no score, no
    // "Why this", no invented numbers.
    render(await HomePage());

    const text = (document.body.textContent ?? "").toLowerCase();
    for (const forbidden of ["why this", "relevance", "pulse score", "tonight's pulse"]) {
      expect(text).not.toContain(forbidden);
    }
  });

  it("renders exactly one personal-events surface", async () => {
    // The page used to render `AddEventButton` beside the section, and that button mounts
    // its own copy of the panel — so there were two "Your personal events" lists, one of
    // them always empty. The section owns the affordance now.
    const { container } = render(await HomePage());

    expect(container.querySelectorAll('[aria-label="Your personal events"]')).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Add personal event" })).toBeNull();
  });

  it("is rendered per request, so the build never reads the user's session or events", async () => {
    const page = await import("@/app/page");

    expect(page.dynamic).toBe("force-dynamic");
  });
});
