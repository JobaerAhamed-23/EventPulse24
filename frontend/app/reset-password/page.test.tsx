import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ResetPasswordPage, { metadata } from "@/app/reset-password/page";

/**
 * `/reset-password` — one route, two forms, chosen by the token in the link.
 */

vi.mock("@/lib/backend-client", () => ({
  api: { POST: vi.fn() },
}));

/** The props Next passes a page: `searchParams` is a promise in this version. */
function props(search: Record<string, string | string[]>) {
  return { params: Promise.resolve({}), searchParams: Promise.resolve(search) } as Parameters<
    typeof ResetPasswordPage
  >[0];
}

describe("/reset-password", () => {
  it("asks for an address when there is no token", async () => {
    render(await ResetPasswordPage(props({})));

    expect(screen.getByRole("button", { name: "Send reset link" })).toBeInTheDocument();
    expect(screen.queryByLabelText("New password")).toBeNull();
  });

  it("sets a new password when the link carried a token", async () => {
    render(await ResetPasswordPage(props({ token: "from-the-email" })));

    expect(screen.getByLabelText("New password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set new password" })).toBeInTheDocument();
  });

  it("treats an empty token as no token", async () => {
    render(await ResetPasswordPage(props({ token: "" })));

    expect(screen.getByRole("button", { name: "Send reset link" })).toBeInTheDocument();
  });

  it("treats a repeated token parameter as no token, rather than guessing which is ours", async () => {
    render(await ResetPasswordPage(props({ token: ["one", "two"] })));

    expect(screen.getByRole("button", { name: "Send reset link" })).toBeInTheDocument();
  });

  it("sends no referrer, so the token cannot leak in a Referer header", () => {
    // The token is a 30-minute bearer credential for the account, and it is in the URL.
    expect(metadata.referrer).toBe("no-referrer");
  });
});
