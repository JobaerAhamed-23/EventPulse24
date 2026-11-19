/**
 * `/confirm-email` — the page the link in the confirmation mail lands on.
 *
 * **The property tested hardest is that it works signed out.** `homeRoute(session)` sends
 * an anonymous visitor to `/preview`, and a confirmation link that gets redirected is a
 * link that does not work. The link is opened from a mailbox, in a browser that may never
 * have signed in to this product, so this route must never acquire that redirect.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ConfirmEmailPage, { metadata } from "@/app/confirm-email/page";

vi.mock("next/navigation", () => ({
  usePathname: () => "/confirm-email",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  redirect: vi.fn(() => {
    throw new Error("NEXT_REDIRECT");
  }),
}));

vi.mock("@/lib/backend-client", () => ({
  api: { POST: vi.fn() },
}));

describe("the confirmation route", () => {
  it("renders for a visitor with no session", async () => {
    /**
     * **The single most likely bug in this item.** If this page ever starts calling
     * `getSession`/`homeRoute`, an anonymous visitor is bounced to `/preview` and every
     * confirmation link in every mailbox stops working.
     */
    render(await ConfirmEmailPage({ params: Promise.resolve({}), searchParams: Promise.resolve({ token: "a-token" }) }));

    expect(screen.getByRole("button", { name: /confirm this address/i })).toBeInTheDocument();
  });

  it("asks for the link when there is no token, rather than accusing the visitor", async () => {
    render(await ConfirmEmailPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }));

    expect(screen.getByText(/open the link from the email/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /confirm this address/i })).not.toBeInTheDocument();
  });

  it("treats a repeated token parameter as no token rather than guessing", async () => {
    render(
      await ConfirmEmailPage({ params: Promise.resolve({}), searchParams: Promise.resolve({ token: ["a", "b"] }) }),
    );

    expect(screen.getByText(/open the link from the email/i)).toBeInTheDocument();
  });

  it("tells the browser not to leak the token in a Referer header", () => {
    /**
     * The token is a bearer credential and it is in the URL. Without this, any
     * cross-origin request from this page carries the whole URL — token included.
     * `/reset-password` carries the same attribute for the same reason.
     */
    expect(metadata.referrer).toBe("no-referrer");
  });

  it("is never prerendered, because the token comes from the request", async () => {
    const mod = await import("@/app/confirm-email/page");

    expect(mod.dynamic).toBe("force-dynamic");
  });
});
