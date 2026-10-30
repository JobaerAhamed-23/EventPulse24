import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SigninForm } from "@/components/auth/signin-form";

/**
 * Sign-in, and the **account-enumeration rule** that shapes it.
 *
 * `EXPERIENCE.md` locks it: the error goes on the Password field whichever half actually
 * failed, because "we don't know that email" hands an attacker a way to enumerate
 * accounts. The API makes that easy — one 401 for both — and these tests make sure the
 * form does not undo it.
 */

const POST = vi.fn();
const replace = vi.fn();
const refresh = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

const INVALID_CREDENTIALS = {
  data: undefined,
  error: { code: "invalid_credentials", message: "That email and password don't match." },
};

beforeEach(() => {
  POST.mockReset();
  replace.mockReset();
  refresh.mockReset();
});

function fillIn(email = "maya@example.test", password = "calm-river-lantern-42") {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("SigninForm", () => {
  it("signs in and lands on the home", async () => {
    POST.mockResolvedValue({ data: { status: "signed_in" }, error: undefined });
    render(<SigninForm />);

    fillIn();
    submit();

    await vi.waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/");
    });
    expect(POST).toHaveBeenCalledWith("/api/auth/signin", {
      body: { email: "maya@example.test", password: "calm-river-lantern-42" },
    });
    // Without the refresh the server components keep their anonymous render.
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the API's message verbatim on the Password field", async () => {
    POST.mockResolvedValue(INVALID_CREDENTIALS);
    render(<SigninForm />);

    fillIn();
    submit();

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent("That email and password don't match.");
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Password")).toHaveAttribute(
      "aria-describedby",
      "signin-password-error",
    );
  });

  it("never marks the Email field invalid from a failed sign-in", async () => {
    // The enumeration rule: an error on Email would say "this address is the problem",
    // which is exactly what the API refuses to say.
    POST.mockResolvedValue(INVALID_CREDENTIALS);
    render(<SigninForm />);

    fillIn();
    submit();

    await screen.findByRole("alert");
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "false");
  });

  it("says nothing about whether an account exists", async () => {
    POST.mockResolvedValue(INVALID_CREDENTIALS);
    render(<SigninForm />);

    fillIn();
    submit();
    await screen.findByRole("alert");

    const text = (document.body.textContent ?? "").toLowerCase();
    for (const phrase of ["already exists", "don't see an account", "no account", "registered"]) {
      expect(text).not.toContain(phrase.toLowerCase());
    }
  });

  it("checks the email's shape on blur, before any round trip", async () => {
    render(<SigninForm />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "maya@example" } });
    fireEvent.blur(screen.getByLabelText("Email"));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That doesn't look like a valid email address.",
    );
    expect(POST).not.toHaveBeenCalled();
  });

  it("does not submit an address it can already see is malformed", async () => {
    render(<SigninForm />);

    fillIn("maya@example", "calm-river-lantern-42");
    submit();

    await screen.findByRole("alert");
    expect(POST).not.toHaveBeenCalled();
  });

  it("shows a throttle refusal at form level, not on a field", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "rate_limited",
        message: "That's a lot of requests. Try again in a little while.",
      },
    });
    render(<SigninForm />);

    fillIn();
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That's a lot of requests. Try again in a little while.",
    );
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "false");
  });

  it("shows the offline message when the request never reaches the API", async () => {
    // openapi-fetch **rethrows** a failed `fetch` rather than returning an error, so this
    // mock rejects. Mocking a returned error here would test a shape the client cannot
    // produce — and the form would hang on "Signing in…" in the case that really happens.
    POST.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<SigninForm />);

    fillIn();
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't reach Pulse. Try again.");
    // And the form is usable again, rather than stuck on its busy label.
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("marks itself busy while the request is in flight, so it cannot be submitted twice", async () => {
    let settle: (value: unknown) => void = () => {};
    POST.mockReturnValue(
      new Promise((resolve) => {
        settle = resolve;
      }),
    );
    render(<SigninForm />);

    fillIn();
    submit();

    const busy = await screen.findByRole("button", { name: "Signing in…" });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(screen.getByLabelText("Email")).toHaveAttribute("readonly");

    settle({ data: { status: "signed_in" }, error: undefined });
  });

  it("offers the way to a reset", () => {
    render(<SigninForm />);

    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute(
      "href",
      "/reset-password",
    );
  });

  it("reveals and hides the password, and the toggle names what it will do", () => {
    render(<SigninForm />);

    const toggle = screen.getByRole("button", { name: "Show password" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");

    fireEvent.click(toggle);

    const pressed = screen.getByRole("button", { name: "Hide password" });
    expect(pressed).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
  });
});
