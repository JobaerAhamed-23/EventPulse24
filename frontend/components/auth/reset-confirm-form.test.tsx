import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ResetConfirmForm } from "@/components/auth/reset-confirm-form";

/**
 * Setting a new password from the emailed link.
 *
 * Two properties beyond the happy path: the **expired-or-used** state, which is the only
 * thing an exhausted token can produce, and keeping the token — a live bearer credential
 * — out of the address bar.
 */

const POST = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

const TOKEN = "reset-token-from-the-email";
const NEW_PASSWORD = "calm-river-lantern-43";

beforeEach(() => {
  POST.mockReset();
  window.history.replaceState(null, "", `/reset-password?token=${TOKEN}`);
});

function fillIn(password = NEW_PASSWORD, confirm = NEW_PASSWORD) {
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: confirm } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Set new password" }));
}

describe("ResetConfirmForm", () => {
  it("sets the new password and offers the way back to sign in", async () => {
    POST.mockResolvedValue({ data: { status: "password_reset" }, error: undefined });
    render(<ResetConfirmForm token={TOKEN} />);

    fillIn();
    submit();

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Your password is changed. Sign in with your new password.",
    );
    expect(POST).toHaveBeenCalledWith("/api/auth/password-reset/confirm", {
      body: { token: TOKEN, new_password: NEW_PASSWORD },
    });
    expect(screen.getByRole("link", { name: "Sign in →" })).toHaveAttribute("href", "/signin");
  });

  it("shows the expired-or-used state in the API's words, with a way to ask again", async () => {
    // Expired, already used and never-valid are one answer on purpose: distinguishing
    // them would let someone test guessed tokens.
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "invalid_reset_token",
        message: "That reset link isn't valid anymore. Ask for a new one.",
      },
    });
    render(<ResetConfirmForm token={TOKEN} />);

    fillIn();
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That reset link isn't valid anymore. Ask for a new one.",
    );
    expect(screen.getByRole("link", { name: "Ask for a new link →" })).toHaveAttribute(
      "href",
      "/reset-password",
    );
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("takes the token out of the address bar as soon as it has it", () => {
    render(<ResetConfirmForm token={TOKEN} />);

    expect(window.location.search).toBe("");
    expect(window.location.pathname).toBe("/reset-password");
  });

  it("still submits the token it was given after the URL is cleaned", async () => {
    POST.mockResolvedValue({ data: { status: "password_reset" }, error: undefined });
    render(<ResetConfirmForm token={TOKEN} />);

    fillIn();
    submit();

    await screen.findByRole("status");
    expect(POST).toHaveBeenCalledWith("/api/auth/password-reset/confirm", {
      body: { token: TOKEN, new_password: NEW_PASSWORD },
    });
  });

  it("recovers when the request never reaches the API, with the token unspent", async () => {
    POST.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<ResetConfirmForm token={TOKEN} />);

    fillIn();
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't reach Pulse. Try again.");
    expect(screen.getByRole("button", { name: "Set new password" })).toBeEnabled();
  });

  it("checks the password's length and the two fields' agreement first", async () => {
    render(<ResetConfirmForm token={TOKEN} />);

    fillIn("short", "short");
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent("Use at least 8 characters.");
    expect(POST).not.toHaveBeenCalled();

    fillIn(NEW_PASSWORD, `${NEW_PASSWORD}-typo`);
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords don't match.");
    expect(POST).not.toHaveBeenCalled();
  });

  it("shows a weak-password verdict from the API on the field", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "invalid_input",
        message: "That password doesn't meet our requirements.",
        details: { errors: [{ loc: ["new_password"], msg: "This password is too common." }] },
      },
    });
    render(<ResetConfirmForm token={TOKEN} />);

    fillIn("password1", "password1");
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent("This password is too common.");
    expect(screen.getByLabelText("New password")).toHaveAttribute("aria-invalid", "true");
  });
});
