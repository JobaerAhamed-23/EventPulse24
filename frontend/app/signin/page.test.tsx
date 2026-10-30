import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SigninPage from "@/app/signin/page";

/**
 * The silent redirect.
 *
 * `EXPERIENCE.md`: `/signin` "returns the user to session if the cookie is still valid
 * (silent redirect to `/`)". `/signup`'s own test checks that it follows the same rule.
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
  onboarding: { completed: true, current_step: null },
};

beforeEach(() => {
  getSession.mockReset();
  redirect.mockReset();
});

describe("/signin", () => {
  it("sends a visitor whose session is still valid to the home", async () => {
    getSession.mockResolvedValue({ kind: "signed-in", user: USER });

    await SigninPage();

    expect(redirect).toHaveBeenCalledWith("/");
  });

  it("renders the form for an anonymous visitor", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    render(await SigninPage());

    expect(redirect).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("renders the form when the API cannot be reached, rather than redirecting", async () => {
    // Somebody trying to sign in during an outage should see the form, not a bounce.
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await SigninPage());

    expect(redirect).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("offers the cross-link to sign-up and the privacy line, as drawn", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    render(await SigninPage());

    expect(screen.getByRole("link", { name: "Sign up →" })).toHaveAttribute("href", "/signup");
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    expect(screen.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute(
      "href",
      "/privacy",
    );
  });

  it("is rendered per request, because it depends on the session", async () => {
    const page = await import("@/app/signin/page");

    expect(page.dynamic).toBe("force-dynamic");
  });
});
