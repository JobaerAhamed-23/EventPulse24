import { render, screen, within } from "@testing-library/react";
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
  name: "",
  onboarding: { completed: true, current_step: null },
};

/** The route's props, with an optional `next`. */
function props(next?: string) {
  return { searchParams: Promise.resolve(next === undefined ? {} : { next }) };
}

beforeEach(() => {
  getSession.mockReset();
  redirect.mockReset();
});

describe("/signin", () => {
  it("sends a visitor whose session is still valid to the home", async () => {
    getSession.mockResolvedValue({ kind: "signed-in", user: USER });

    await SigninPage(props());

    expect(redirect).toHaveBeenCalledWith("/");
  });

  it("sends a visitor whose session is still valid to where they were going", async () => {
    getSession.mockResolvedValue({ kind: "signed-in", user: USER });

    await SigninPage(props("/pricing"));

    expect(redirect).toHaveBeenCalledWith("/pricing");
  });

  it("refuses to redirect to somewhere off this site", async () => {
    // **The open redirect, caught.** A visitor whose cookie is still valid would be sent
    // straight to the attacker's page — no sign-in at all.
    getSession.mockResolvedValue({ kind: "signed-in", user: USER });

    await SigninPage(props("https://attacker.example/steal"));

    expect(redirect).toHaveBeenCalledWith("/");
  });

  it("renders the form for an anonymous visitor", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    render(await SigninPage(props()));

    expect(redirect).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("renders the form when the API cannot be reached, rather than redirecting", async () => {
    // Somebody trying to sign in during an outage should see the form, not a bounce.
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await SigninPage(props()));

    expect(redirect).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("offers the cross-link to sign-up and the privacy line, as drawn", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    render(await SigninPage(props()));

    expect(screen.getByRole("link", { name: "Sign up →" })).toHaveAttribute("href", "/signup");

    // **Scoped to `main`, because the footer now carries these rows too.** `/terms` and
    // `/privacy` were built on 2026-11-20 and the pre-auth footer gained its spec'd
    // Terms row with them, so a page-wide `getByRole("link", { name: "Terms" })` finds
    // two. The line this test is about is the consent footnote under the form — "By
    // signing in, you agree to our Terms and Privacy Policy" — so the query belongs
    // inside `main`, where that sentence lives.
    //
    // **Both links 404'd until those routes shipped.** This assertion has always
    // checked the hrefs; nothing checked that anything served them.
    const form = within(screen.getByRole("main"));
    expect(form.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    expect(form.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute(
      "href",
      "/privacy",
    );
  });

  it("is rendered per request, because it depends on the session", async () => {
    const page = await import("@/app/signin/page");

    expect(page.dynamic).toBe("force-dynamic");
  });
});
