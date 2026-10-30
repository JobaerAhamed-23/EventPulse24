import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ResetRequestForm } from "@/components/auth/reset-request-form";

/**
 * The forgot-password request.
 *
 * The success sentence is locked copy, and it is **unconditional**: the API answers 202
 * for a known address and an unknown one alike, so a form that said anything different
 * for the two would be inventing information the API refuses to give.
 */

const POST = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

beforeEach(() => {
  POST.mockReset();
});

function request(email = "maya@example.test") {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
}

describe("ResetRequestForm", () => {
  it("asks for the link and shows the locked sentence, naming the address", async () => {
    POST.mockResolvedValue({ data: { status: "accepted" }, error: undefined });
    render(<ResetRequestForm />);

    request();

    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent("We've sent a reset link to maya@example.test.");
    expect(POST).toHaveBeenCalledWith("/api/auth/password-reset", {
      body: { email: "maya@example.test" },
    });
  });

  it("says the same thing whoever the address belongs to", async () => {
    // The API cannot tell the two apart on the wire, and neither can this.
    POST.mockResolvedValue({ data: { status: "accepted" }, error: undefined });
    render(<ResetRequestForm />);

    request("nobody-has-this@example.test");

    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent("We've sent a reset link to nobody-has-this@example.test.");
    const text = (document.body.textContent ?? "").toLowerCase();
    for (const phrase of ["no account", "don't see an account", "not registered"]) {
      expect(text).not.toContain(phrase);
    }
  });

  it("checks the address's shape before asking", async () => {
    render(<ResetRequestForm />);

    request("maya@example");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That doesn't look like a valid email address.",
    );
    expect(POST).not.toHaveBeenCalled();
  });

  it("shows the API's refusal rather than a false success", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "rate_limited",
        message: "That's a lot of requests. Try again in a little while.",
      },
    });
    render(<ResetRequestForm />);

    request();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That's a lot of requests. Try again in a little while.",
    );
    expect(screen.queryByRole("status")).toBeNull();
  });
});
