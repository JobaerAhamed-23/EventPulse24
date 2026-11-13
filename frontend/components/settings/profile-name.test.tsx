/**
 * The name editor.
 *
 * **Four things are worth proving here, and they are the ones a screenshot cannot
 * show.**
 *
 * 1. **The save is inline.** There is no Save button; the field the user typed in is the
 *    thing that saves — the same rule every other settings island follows.
 * 2. **The API's refusal is shown verbatim.** A name carrying a line break is refused by
 *    the backend with a message written for the person who typed it, and that message
 *    says what to change. A generic *"Couldn't save."* would throw it away.
 * 3. **The payload is the name and nothing else.** The endpoint takes one field, and a
 *    payload that sent more would be sending more than the server has agreed to store.
 * 4. **An emptied name IS saved.** Every other island refuses to send a half-finished
 *    value — a time with nothing in it is not a schedule. **A name with nothing in it is
 *    a name**: it means *"no name set"*, and the backend stores `""`.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProfileName } from "@/components/settings/profile-name";

const PUT = vi.fn();

/**
 * The account's address.
 *
 * **The island is handed it so it can publish the *display* name.** The rail shows what
 * to call the person, and when the name is cleared that is the address-derived
 * fallback — which only the address can produce.
 */
const EMAIL = "maya@example.test";

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

/** The server's answer, as the `PUT` sends it. */
function answer(name: string) {
  return {
    data: { id: "11111111-1111-1111-1111-111111111111", email: "maya@example.test", name },
    response: { status: 200 },
  };
}

/**
 * The API's refusal, as the server sends it.
 *
 * **This is the shape `backend/config/errors.py` writes.** A `DomainError` becomes
 * `{ code, message, details }` with the status the error's class maps to — and the
 * message is written for the user, which is the whole point of it being there.
 */
function refusal(code: string, message: string, status = 422) {
  return {
    data: undefined,
    error: { code, message },
    response: { status },
  };
}

beforeEach(() => {
  PUT.mockReset();
  PUT.mockResolvedValue(answer("Maya Ahmed"));
});

describe("the name editor", () => {
  it("shows the name the account holds", () => {
    render(<ProfileName initialName="Maya Ahmed" email={EMAIL} />);

    expect(screen.getByLabelText("Your name")).toHaveValue("Maya Ahmed");
  });

  it("shows an empty field when no name is set", () => {
    // **The backend's single "no name set" state is `""`, not `null`.** The field is
    // empty, and the product falls back to the email-derived name everywhere else.
    render(<ProfileName initialName="" email={EMAIL} />);

    expect(screen.getByLabelText("Your name")).toHaveValue("");
  });

  it("saves on change, with no Save button", async () => {
    render(<ProfileName initialName="Maya Ahmed" email={EMAIL} />);

    expect(screen.queryByRole("button", { name: /^save/i })).toBeNull();

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Maya A" } });

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(PUT.mock.calls[0]?.[0]).toBe("/api/auth/profile");
  });

  it("sends the name, and only the name", async () => {
    render(<ProfileName initialName="Maya Ahmed" email={EMAIL} />);

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Maya A" } });

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    const body = PUT.mock.calls[0]?.[1]?.body;
    expect(body).toEqual({ name: "Maya A" });
  });

  it("saves an emptied name, because an empty name is a name", async () => {
    // **Clearing your name is a thing a person does.** The backend stores `""` for it
    // and the product falls back to the email-derived name — so the client must not
    // hold the value back the way it holds back an emptied time.
    render(<ProfileName initialName="Maya Ahmed" email={EMAIL} />);

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "" } });

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(PUT.mock.calls[0]?.[1]?.body).toEqual({ name: "" });
  });

  it("says 'Saved.' quietly, and announces it", async () => {
    render(<ProfileName initialName="Maya Ahmed" email={EMAIL} />);

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Maya A" } });

    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());
    // **A `role="status"` region**, so a screen reader announces it without the focus
    // moving. No emoji, no celebration.
    const status = document.querySelector('[role="status"]');
    expect(status).not.toBeNull();
    expect(status?.textContent).toBe("Saved.");
  });

  it("shows the name the server stored, not the one that was typed", async () => {
    // **The server trims and collapses.** A name typed with spaces around it comes back
    // without them, and the field shows what the account now holds.
    PUT.mockResolvedValue(answer("Maya Ahmed"));

    render(<ProfileName initialName="" email={EMAIL} />);

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "  Maya Ahmed  " } });

    await waitFor(() => expect(screen.getByLabelText("Your name")).toHaveValue("Maya Ahmed"));
  });

  it("keeps the chosen name when the save fails", async () => {
    PUT.mockRejectedValue(new Error("offline"));

    render(<ProfileName initialName="Maya Ahmed" email={EMAIL} />);

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Maya A" } });

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
    // **The name is still theirs.** Reverting it would throw away their work over a
    // transient failure.
    expect(screen.getByLabelText("Your name")).toHaveValue("Maya A");
  });

  it("shows the server's refusal, verbatim", async () => {
    // **The API's own verdict.** The backend refuses a name carrying a line break, and
    // says why in a message written for the person who typed it.
    //
    // **The generic line would throw that away**, and the user would be left with
    // "Couldn't save." and no idea what to change — on a screen whose only control is one
    // field.
    PUT.mockResolvedValue(
      refusal("invalid_input", "A name can't contain line breaks or control characters."),
    );

    render(<ProfileName initialName="Maya Ahmed" email={EMAIL} />);

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Maya\nAhmed" } });

    await waitFor(() =>
      expect(
        screen.getByText("A name can't contain line breaks or control characters."),
      ).toBeInTheDocument(),
    );
    // **The generic line is not shown as well** — the API's verdict replaces it, rather
    // than joining it.
    expect(screen.queryByText("Couldn't save.")).toBeNull();
  });

  it("announces the failure, and marks it", async () => {
    PUT.mockRejectedValue(new Error("offline"));

    render(<ProfileName initialName="Maya Ahmed" email={EMAIL} />);

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Maya A" } });

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
    // **A `role="alert"`**, so a screen reader announces it immediately — the failure is
    // the thing the user most needs to know about.
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toBe("Couldn't save.");
    expect(alert.getAttribute("data-save-failed")).not.toBeNull();
  });

  it("falls back to the route's own line when the API says nothing", async () => {
    // **The request never reached the API**, so there is nothing to quote — and the
    // route's own line is the honest one, because nothing was refused.
    PUT.mockRejectedValue(new Error("offline"));

    render(<ProfileName initialName="Maya Ahmed" email={EMAIL} />);

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Maya A" } });

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
  });

  it("marks the field invalid when the API refuses it", async () => {
    // **The field has to say it too.** The failure line says what went wrong, but a
    // person tabbing back to the field has no reason to know it holds a value the
    // server will not take.
    PUT.mockResolvedValue(
      refusal("invalid_input", "A name can't contain line breaks or control characters."),
    );

    render(<ProfileName initialName="Maya Ahmed" email={EMAIL} />);

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Maya\nAhmed" } });

    await waitFor(() =>
      expect(screen.getByLabelText("Your name")).toHaveAttribute("aria-invalid", "true"),
    );
  });

  it("does not mark the field invalid when nothing was refused", async () => {
    // **An offline failure is not the field's fault.** Marking an empty field invalid
    // with no error on it would be a form demanding something.
    render(<ProfileName initialName="" email={EMAIL} />);

    expect(screen.getByLabelText("Your name")).not.toHaveAttribute("aria-invalid");
  });
});

describe("a superseded save", () => {
  it("ignores a slow response for a name the user has since replaced", async () => {
    // **A free-text field is typed a character at a time**, so a second save can be
    // started before the first comes back — and the first to *return* is not
    // necessarily the newest request.
    //
    // **Without a guard, the slow first response would win**: it would overwrite the
    // name the user has since typed and replace it with the server's answer to the
    // *older* name. The person would watch their typing disappear.
    const resolvers: ((value: unknown) => void)[] = [];
    PUT.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvers.push(resolve);
        }),
    );

    render(<ProfileName initialName="" email={EMAIL} />);

    // The first keystroke, and its save.
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "M" } });
    await waitFor(() => expect(resolvers).toHaveLength(1));

    // The second keystroke, and its save — started before the first came back.
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Ma" } });
    await waitFor(() => expect(resolvers).toHaveLength(2));

    // **The first response arrives last**, carrying the server's answer to "M".
    resolvers[1]?.(answer("Ma"));
    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());

    resolvers[0]?.(answer("M"));
    await waitFor(() => expect(screen.getByLabelText("Your name")).toHaveValue("Ma"));
  });

  it("does not show a failure for a save the user has already superseded", async () => {
    // **A failure line from a superseded save is noise.** The user has moved on — the
    // newest save is the one that decides what the screen says.
    const resolvers: ((value: unknown) => void)[] = [];
    PUT.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvers.push(resolve);
        }),
    );

    render(<ProfileName initialName="" email={EMAIL} />);

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "M" } });
    await waitFor(() => expect(resolvers).toHaveLength(1));
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Ma" } });
    await waitFor(() => expect(resolvers).toHaveLength(2));

    // The stale save fails.
    resolvers[0]?.(refusal("invalid_input", "A name can't contain line breaks."));
    await waitFor(() => expect(resolvers[0]).toBeDefined());

    // **The failure line is not shown** — that save said nothing about what is on
    // screen now.
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("the in-flight affordance", () => {
  it("shows a static dot, never a spinner", async () => {
    // **The product bans spinners.** `EXPERIENCE.md`: "No spinners, anywhere. A
    // spinner is a visual urgency badge." The architecture test plants `animate-spin`
    // as a must-fail fixture. So the in-flight state is the form the spec itself
    // specifies for reduced motion: a static dot.
    let resolvePut: (value: unknown) => void = () => {};
    PUT.mockReturnValue(
      new Promise((resolve) => {
        resolvePut = resolve;
      }),
    );

    render(<ProfileName initialName="Maya Ahmed" email={EMAIL} />);
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Maya A" } });

    await waitFor(() => expect(document.querySelector("[data-saving-dot]")).not.toBeNull());
    const dot = document.querySelector("[data-saving-dot]");
    expect(dot?.className).toContain("rounded-full");
    // **A static dot.** Nothing animates.
    expect(dot?.className).not.toContain("animate-");
    expect(dot?.getAttribute("aria-hidden")).toBe("true");

    resolvePut(answer("Maya A"));
    await waitFor(() => expect(document.querySelector("[data-saving-dot]")).toBeNull());
  });
});
