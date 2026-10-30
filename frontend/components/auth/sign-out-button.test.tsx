import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SignOutButton } from "@/components/auth/sign-out-button";

const POST = vi.fn();
const replace = vi.fn();
const refresh = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

beforeEach(() => {
  POST.mockReset();
  replace.mockReset();
  refresh.mockReset();
});

describe("SignOutButton", () => {
  it("ends the session and goes to sign-in", async () => {
    POST.mockResolvedValue({ data: { status: "signed_out" }, error: undefined });
    render(<SignOutButton />);

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await vi.waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/signin");
    });
    expect(POST).toHaveBeenCalledWith("/api/auth/signout");
    // The server components re-run, so nothing of the old session stays on screen.
    expect(refresh).toHaveBeenCalled();
  });

  it("goes to /signin rather than /, which would bounce on to the public preview", async () => {
    POST.mockResolvedValue({ data: { status: "signed_out" }, error: undefined });
    render(<SignOutButton />);

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await vi.waitFor(() => {
      expect(replace).toHaveBeenCalled();
    });
    expect(replace).not.toHaveBeenCalledWith("/");
  });

  it("stays put and says why when the sign-out fails", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "csrf_failed",
        message: "Your session needs refreshing. Reload the page and try again.",
      },
    });
    render(<SignOutButton />);

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your session needs refreshing. Reload the page and try again.",
    );
    expect(replace).not.toHaveBeenCalled();
  });
});
