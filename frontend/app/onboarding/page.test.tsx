import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OnboardingPage from "@/app/onboarding/page";

/**
 * `/onboarding` — the gates, and the server-side read that makes resume real.
 */

const getSession = vi.fn();
const sessionHeaders = vi.fn();
const redirect = vi.fn();
const GET = vi.fn();

vi.mock("@/lib/session", () => ({
  getSession: () => getSession(),
  sessionHeaders: () => sessionHeaders(),
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/backend-client", () => ({
  api: {
    GET: (...args: unknown[]) => GET(...args),
    POST: vi.fn(),
    PUT: vi.fn(),
  },
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  onboarding: { completed: false, current_step: 2 },
};

const STATE = {
  completed: false,
  current_step: 2,
  step_name: "interests",
  interests: [],
  digest: { delivery_time: null, timezone: null },
  last_advanced_at: null,
  completed_at: null,
};

const CHIPS = { items: [{ key: "tech_meetups", label: "Tech & meetups" }] };

function answer(path: string) {
  if (path === "/api/personal/onboarding") return { data: STATE, error: undefined };
  if (path === "/api/personal/onboarding/interest-chips") return { data: CHIPS, error: undefined };
  if (path === "/api/personal/calendars") return { data: { items: [] }, error: undefined };
  return { data: undefined, error: { code: "not_found", message: "no" } };
}

beforeEach(() => {
  getSession.mockReset();
  sessionHeaders.mockReset();
  redirect.mockReset();
  GET.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  sessionHeaders.mockResolvedValue({ cookie: "sessionid=abc" });
  GET.mockImplementation((path: string) => Promise.resolve(answer(path)));
});

describe("the gates", () => {
  it("sends an anonymous visitor to sign in", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    await OnboardingPage();

    expect(redirect).toHaveBeenCalledWith("/signin");
  });

  it("sends a user who has already finished to the home", async () => {
    getSession.mockResolvedValue({
      kind: "signed-in",
      user: { ...USER, onboarding: { completed: true, current_step: null } },
    });

    await OnboardingPage();

    expect(redirect).toHaveBeenCalledWith("/");
  });

  it("shows the calm error when the API cannot be reached, rather than bouncing", async () => {
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await OnboardingPage());

    expect(redirect).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Couldn't reach Pulse. Try again.",
    );
  });

  it("shows the calm error when the state itself cannot be read", async () => {
    GET.mockImplementation((path: string) =>
      path === "/api/personal/onboarding"
        ? Promise.resolve({ data: undefined, error: { code: "x", message: "y" } })
        : Promise.resolve(answer(path)),
    );

    render(await OnboardingPage());

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Couldn't reach Pulse. Try again.",
    );
  });
});

describe("the server-side read", () => {
  it("carries the visitor's session on every read", async () => {
    await OnboardingPage();

    for (const path of [
      "/api/personal/onboarding",
      "/api/personal/onboarding/interest-chips",
      "/api/personal/calendars",
    ]) {
      expect(GET).toHaveBeenCalledWith(path, { headers: { cookie: "sessionid=abc" } });
    }
  });

  it("opens on the recorded step, so the first paint is the resume", async () => {
    render(await OnboardingPage());

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("What kinds of things?");
  });

  it("renders the chips the API gave", async () => {
    render(await OnboardingPage());

    expect(screen.getByRole("button", { name: /Tech & meetups/ })).toBeInTheDocument();
  });

  it("is rendered per request, because it depends on the session and the progress", async () => {
    const page = await import("@/app/onboarding/page");

    expect(page.dynamic).toBe("force-dynamic");
  });
});
