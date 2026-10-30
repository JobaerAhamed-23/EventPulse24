import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SignupForm } from "@/components/auth/signup-form";

/**
 * Sign-up: the client-side checks, the API's own verdicts, and the two-call flow.
 *
 * The flow is the part worth pinning. `POST /api/auth/signup` establishes no session on
 * purpose (a `Set-Cookie` on one answer and not another is a confirmed-password oracle),
 * so this form signs in afterwards. If that second call were ever dropped, sign-up would
 * still *look* successful and the user would land on `/onboarding` with no session.
 */

const POST = vi.fn();
const replace = vi.fn();
const refresh = vi.fn();
const matchMedia = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

const EMAIL = "maya@example.test";
const PASSWORD = "calm-river-lantern-42";

beforeEach(() => {
  POST.mockReset();
  replace.mockReset();
  refresh.mockReset();
  matchMedia.mockReset();
  matchMedia.mockReturnValue({ matches: false });
  vi.stubGlobal("matchMedia", matchMedia);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function fillIn({ email = EMAIL, password = PASSWORD, confirm = PASSWORD } = {}) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: confirm } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
}

/** Both calls succeed: the account is created, then the session is established. */
function bothSucceed() {
  POST.mockResolvedValueOnce({ data: { status: "accepted" }, error: undefined });
  POST.mockResolvedValueOnce({ data: { status: "signed_in" }, error: undefined });
}

describe("SignupForm", () => {
  describe("the checks the browser can make itself", () => {
    it("rejects a malformed address, with the locked copy", async () => {
      render(<SignupForm />);

      fillIn({ email: "maya@example" });
      submit();

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "That doesn't look like a valid email address.",
      );
      expect(POST).not.toHaveBeenCalled();
    });

    it("rejects a short password, with the locked copy", async () => {
      render(<SignupForm />);

      fillIn({ password: "short", confirm: "short" });
      submit();

      expect(await screen.findByRole("alert")).toHaveTextContent("Use at least 8 characters.");
      expect(POST).not.toHaveBeenCalled();
    });

    it("reports a mismatch on Confirm, and keeps the password the user already typed", async () => {
      render(<SignupForm />);

      fillIn({ confirm: `${PASSWORD}-typo` });
      submit();

      const error = await screen.findByRole("alert");
      expect(error).toHaveTextContent("Passwords don't match.");
      expect(screen.getByLabelText("Confirm password")).toHaveAttribute("aria-invalid", "true");
      // The Password field is not the one at fault and is not cleared: the user typed it
      // correctly, and clearing it would be unkind.
      expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "false");
      expect(screen.getByLabelText("Password")).toHaveValue(PASSWORD);
    });

    it("reports a mismatch on Confirm's blur, before submit", async () => {
      render(<SignupForm />);

      fillIn({ confirm: `${PASSWORD}-typo` });
      fireEvent.blur(screen.getByLabelText("Confirm password"));

      expect(await screen.findByRole("alert")).toHaveTextContent("Passwords don't match.");
      expect(POST).not.toHaveBeenCalled();
    });
  });

  describe("the API's verdicts", () => {
    it("shows a field error from details, in the API's own words", async () => {
      POST.mockResolvedValueOnce({
        data: undefined,
        error: {
          code: "invalid_input",
          message: "That password doesn't meet our requirements.",
          details: { errors: [{ loc: ["password"], msg: "This password is too common." }] },
        },
      });
      render(<SignupForm />);

      fillIn({ password: "password1", confirm: "password1" });
      submit();

      expect(await screen.findByRole("alert")).toHaveTextContent("This password is too common.");
      expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
    });

    it("shows a throttle refusal at form level", async () => {
      POST.mockResolvedValueOnce({
        data: undefined,
        error: {
          code: "rate_limited",
          message: "That's a lot of requests. Try again in a little while.",
        },
      });
      render(<SignupForm />);

      fillIn();
      submit();

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "That's a lot of requests. Try again in a little while.",
      );
    });
  });

  describe("the two-call flow", () => {
    it("creates the account and then signs in, because sign-up establishes no session", async () => {
      bothSucceed();
      render(<SignupForm />);

      fillIn();
      submit();

      await screen.findByText("Account created. Taking you to onboarding…");
      expect(POST.mock.calls[0]).toEqual([
        "/api/auth/signup",
        { body: { email: EMAIL, password: PASSWORD } },
      ]);
      expect(POST.mock.calls[1]).toEqual([
        "/api/auth/signin",
        { body: { email: EMAIL, password: PASSWORD } },
      ]);
    });

    it("goes to /onboarding after the 1.5s hold, never straight to /", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      bothSucceed();
      render(<SignupForm />);

      fillIn();
      submit();

      await screen.findByText("Account created. Taking you to onboarding…");
      expect(replace).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(1500);

      expect(replace).toHaveBeenCalledWith("/onboarding");
      expect(refresh).toHaveBeenCalled();
    });

    it("redirects immediately when the user asked for reduced motion", async () => {
      // The hold is a timed transition. `prefers-reduced-motion` collapses it to 0ms.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      matchMedia.mockReturnValue({ matches: true });
      bothSucceed();
      render(<SignupForm />);

      fillIn();
      submit();

      await screen.findByText("Account created. Taking you to onboarding…");
      await vi.advanceTimersByTimeAsync(0);

      expect(replace).toHaveBeenCalledWith("/onboarding");
    });

    it("shows the API's message when the follow-up sign-in fails, and claims nothing about accounts", async () => {
      // What a taken address looks like from here: the sign-up answers 201 whatever the
      // address was, and the sign-in with the wrong password fails. The user is told what
      // the API says, and never that the address is taken.
      POST.mockResolvedValueOnce({ data: { status: "accepted" }, error: undefined });
      POST.mockResolvedValueOnce({
        data: undefined,
        error: { code: "invalid_credentials", message: "That email and password don't match." },
      });
      render(<SignupForm />);

      fillIn();
      submit();

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "That email and password don't match.",
      );
      expect(replace).not.toHaveBeenCalled();
      const text = (document.body.textContent ?? "").toLowerCase();
      for (const phrase of ["already exists", "is taken", "registered", "no account"]) {
        expect(text).not.toContain(phrase);
      }
    });
  });

  it("renders no OIDC provider buttons, because none of them can sign anybody in yet", () => {
    render(<SignupForm />);

    for (const provider of ["Google", "Apple", "Outlook", "Microsoft"]) {
      expect(screen.queryByRole("button", { name: new RegExp(provider, "i") })).toBeNull();
    }
  });

  it("offers the way to sign in instead", () => {
    render(<SignupForm />);

    expect(screen.getByRole("link", { name: "Sign in →" })).toHaveAttribute("href", "/signin");
  });

  it("marks itself busy while the round trip is in flight", async () => {
    let settle: (value: unknown) => void = () => {};
    POST.mockReturnValue(
      new Promise((resolve) => {
        settle = resolve;
      }),
    );
    render(<SignupForm />);

    fillIn();
    submit();

    const busy = await screen.findByRole("button", { name: "Creating account…" });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute("aria-busy", "true");

    settle({ data: undefined, error: { code: "x", message: "y" } });
  });
});
