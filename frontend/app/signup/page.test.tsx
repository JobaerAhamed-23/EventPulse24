import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SignupPage from "@/app/signup/page";

/**
 * `/signup` follows `/signin`'s silent-redirect rule: someone who already has a session
 * has no account to create, and offering them the form invites a second one.
 */

const getSession = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", () => ({
  getSession: () => getSession(),
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

beforeEach(() => {
  getSession.mockReset();
  redirect.mockReset();
});

describe("/signup", () => {
  it("sends a signed-in visitor to the home", async () => {
    getSession.mockResolvedValue({ kind: "signed-in", user: USER });

    await SignupPage();

    expect(redirect).toHaveBeenCalledWith("/");
  });

  it("renders the form for an anonymous visitor", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    render(await SignupPage());

    expect(redirect).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { level: 1, name: "Create your account" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Confirm password")).toBeInTheDocument();
  });

  it("is rendered per request", async () => {
    const page = await import("@/app/signup/page");

    expect(page.dynamic).toBe("force-dynamic");
  });
});
