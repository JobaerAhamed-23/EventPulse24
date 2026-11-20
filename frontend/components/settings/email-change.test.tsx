/**
 * The email-change island: three states, and the one it must never reveal.
 *
 * **The hardest property here is a negative one.** The API answers a free address and one
 * another account already holds with the same 202, so this island must not become the
 * oracle the endpoint refuses to be. The success line is asserted to be the *same
 * sentence* in both cases, because a difference of a single word would give the game
 * away.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EmailChange } from "@/components/settings/email-change";

const post = vi.fn();
const del = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => post(...args),
    DELETE: (...args: unknown[]) => del(...args),
  },
}));

const OLD = "maya@example.test";
const NEW = "maya.new@example.test";
/** A pending link that is still good — the server sends the moment, not a duration. */
const IN_A_DAY = new Date(Date.now() + 24 * 3_600_000).toISOString();

beforeEach(() => {
  post.mockReset();
  del.mockReset();
  post.mockResolvedValue({ data: { status: "accepted" } });
  del.mockResolvedValue({ data: { status: "cancelled" } });
});

describe("with nothing pending", () => {
  it("shows the address the account signs in with", () => {
    render(<EmailChange email={OLD} initialPendingEmail="" initialPendingExpiresAt="" />);

    expect(screen.getByText(OLD)).toBeInTheDocument();
  });

  it("says what the button will do before it is pressed", () => {
    /** This control does not take effect on its own, and a person who expects it to
     * would be left thinking the change had happened. */
    render(<EmailChange email={OLD} initialPendingEmail="" initialPendingExpiresAt="" />);

    expect(screen.getByText(/nothing changes until you open the link/i)).toBeInTheDocument();
  });

  it("does not send on a keystroke", async () => {
    /** An address typed a character at a time would mail `m@`, `ma@`, `may@`. */
    render(<EmailChange email={OLD} initialPendingEmail="" initialPendingExpiresAt="" />);

    fireEvent.change(screen.getByLabelText(/new email address/i), { target: { value: NEW } });

    expect(post).not.toHaveBeenCalled();
  });

  it("sends when the explicit action is pressed", async () => {
    render(<EmailChange email={OLD} initialPendingEmail="" initialPendingExpiresAt="" />);

    fireEvent.change(screen.getByLabelText(/new email address/i), { target: { value: NEW } });
    fireEvent.click(screen.getByRole("button", { name: /send the link/i }));

    await waitFor(() => expect(post).toHaveBeenCalledOnce());
    expect(post.mock.calls[0][1]).toEqual({ body: { new_email: NEW } });
  });
});

describe("the taken-address silence", () => {
  it("builds the success line from the address alone, never from the answer", async () => {
    /**
     * **This test had to be rewritten, because the first version was vacuous.**
     *
     * The island cannot tell a free address from a taken one — the API answers both with
     * the same 202, which is the whole point — so rendering "the same thing twice" from
     * identical inputs proved nothing, and a mutation that branched the copy still
     * passed. The oracle risk lives at the API, and it is pinned there by
     * `test_a_taken_address_is_answered_identically`.
     *
     * What *this* layer can be held to is that the sentence is a template with the
     * address substituted and nothing else: no branch on the address, and no reading of
     * the response body. Two different addresses must give two lines that differ only
     * where the address sits.
     */
    const lines: string[] = [];
    for (const address of ["free@example.test", "taken@example.test"]) {
      const view = render(<EmailChange email={OLD} initialPendingEmail="" initialPendingExpiresAt="" />);
      fireEvent.change(screen.getByLabelText(/new email address/i), {
        target: { value: address },
      });
      fireEvent.click(screen.getByRole("button", { name: /send the link/i }));
      lines.push((await screen.findByText(/we've sent a link/i)).textContent ?? "");
      view.unmount();
    }

    const [free, taken] = lines;
    expect(free.replace("free@example.test", "X")).toBe(taken.replace("taken@example.test", "X"));
  });

  it("says nothing about the address being available or in use", async () => {
    render(<EmailChange email={OLD} initialPendingEmail="" initialPendingExpiresAt="" />);
    fireEvent.change(screen.getByLabelText(/new email address/i), {
      target: { value: NEW },
    });
    fireEvent.click(screen.getByRole("button", { name: /send the link/i }));

    const line = (await screen.findByText(/we've sent a link/i)).textContent ?? "";
    expect(line).not.toMatch(/already|in use|taken|available/i);
  });
});

describe("with a change pending", () => {
  it("names the address a link was sent to", () => {
    /** Somebody who mistyped it needs to see what they typed, or they wait a day for a
     * mail that will never arrive. */
    render(<EmailChange email={OLD} initialPendingEmail={NEW} initialPendingExpiresAt={IN_A_DAY} />);

    expect(screen.getByText(NEW)).toBeInTheDocument();
  });

  it("offers a resend, which posts the same address again", async () => {
    /** There is no resend endpoint: the token is never stored, so a resend has to mint a
     * new link, and the request endpoint already revokes the old one. */
    render(<EmailChange email={OLD} initialPendingEmail={NEW} initialPendingExpiresAt={IN_A_DAY} />);

    fireEvent.click(screen.getByRole("button", { name: /send the link again/i }));

    await waitFor(() => expect(post).toHaveBeenCalledOnce());
    expect(post.mock.calls[0][1]).toEqual({ body: { new_email: NEW } });
  });

  it("offers a cancel, which clears the pending state", async () => {
    render(<EmailChange email={OLD} initialPendingEmail={NEW} initialPendingExpiresAt={IN_A_DAY} />);

    fireEvent.click(screen.getByRole("button", { name: /cancel this change/i }));

    await waitFor(() => expect(del).toHaveBeenCalledOnce());
    expect(await screen.findByLabelText(/new email address/i)).toBeInTheDocument();
  });

  it("does not warn about being signed out elsewhere", () => {
    /** The design decided an email change ends no sessions. A screen that implied
     * otherwise would describe a product that does not exist. */
    render(<EmailChange email={OLD} initialPendingEmail={NEW} initialPendingExpiresAt={IN_A_DAY} />);

    expect(screen.queryByText(/signed out/i)).not.toBeInTheDocument();
  });
});

describe("when it fails", () => {
  it("shows the API's own refusal verbatim", async () => {
    post.mockResolvedValue({
      error: { code: "invalid_input", message: "That's already your email address." },
    });
    render(<EmailChange email={OLD} initialPendingEmail="" initialPendingExpiresAt="" />);

    fireEvent.change(screen.getByLabelText(/new email address/i), { target: { value: OLD } });
    fireEvent.click(screen.getByRole("button", { name: /send the link/i }));

    expect(await screen.findByText("That's already your email address.")).toBeInTheDocument();
  });

  it("shows the offline line when the request never reached the API", async () => {
    post.mockRejectedValue(new Error("offline"));
    render(<EmailChange email={OLD} initialPendingEmail="" initialPendingExpiresAt="" />);

    fireEvent.change(screen.getByLabelText(/new email address/i), { target: { value: NEW } });
    fireEvent.click(screen.getByRole("button", { name: /send the link/i }));

    expect(await screen.findByText("Couldn't save.")).toBeInTheDocument();
  });

  it("keeps the pending state when a cancel fails", async () => {
    /** A cancel that silently cleared the screen would tell the user the change was
     * stopped when it was not. */
    del.mockResolvedValue({ error: { code: "x", message: "Nope." } });
    render(<EmailChange email={OLD} initialPendingEmail={NEW} initialPendingExpiresAt={IN_A_DAY} />);

    fireEvent.click(screen.getByRole("button", { name: /cancel this change/i }));

    expect(await screen.findByText("Nope.")).toBeInTheDocument();
    expect(screen.getByText(NEW)).toBeInTheDocument();
  });
});

describe("the expiry on a pending change", () => {
  it("says roughly how long the link still works", async () => {
    /** Somebody waiting on a mail needs to know whether it is still worth waiting. */
    render(
      <EmailChange email={OLD} initialPendingEmail={NEW} initialPendingExpiresAt={IN_A_DAY} />,
    );

    expect(screen.getByText(/the link works for about 24 more hours/i)).toBeInTheDocument();
  });

  it("says a dead link is dead, rather than counting down past zero", async () => {
    const past = new Date(Date.now() - 60_000).toISOString();

    render(<EmailChange email={OLD} initialPendingEmail={NEW} initialPendingExpiresAt={past} />);

    expect(screen.getByText(/that link has expired/i)).toBeInTheDocument();
  });

  it("reads the clock once per render", async () => {
    /*
      **The guard and the value used to be computed from two separate `Date.now()`
      calls**, so one sentence was decided by two clocks. This asserts the defect
      directly rather than one of its symptoms: whatever the call site looks like, it
      reads the time once.
    */
    const now = vi.spyOn(Date, "now");

    render(
      <EmailChange email={OLD} initialPendingEmail={NEW} initialPendingExpiresAt={IN_A_DAY} />,
    );

    expect(now.mock.calls.length).toBeLessThanOrEqual(1);
    now.mockRestore();
  });

  it("does not let the guard and the sentence disagree", async () => {
    /*
      **The failure this replaces.** With two reads, the guard could see a live link and
      the paragraph could then render the dead one — the two halves of a single decision
      landing on opposite sides of the expiry.

      The clock here jumps two minutes between reads, and the link expires one minute
      from the first. A component that reads it once renders the live sentence. A
      component that reads it twice renders "that link has expired" underneath a guard
      that just decided it had not.
    */
    const base = Date.now();
    const expires = new Date(base + 60_000).toISOString();
    const now = vi
      .spyOn(Date, "now")
      .mockReturnValueOnce(base)
      .mockReturnValueOnce(base + 120_000)
      .mockReturnValue(base + 120_000);

    render(<EmailChange email={OLD} initialPendingEmail={NEW} initialPendingExpiresAt={expires} />);

    expect(screen.getByText(/the link works for about 1 more minute/i)).toBeInTheDocument();
    expect(screen.queryByText(/that link has expired/i)).toBeNull();
    now.mockRestore();
  });

  it("says nothing when the server sent no expiry", async () => {
    /** An absent or unparseable value is not a reason to invent a deadline. */
    const { container } = render(
      <EmailChange email={OLD} initialPendingEmail={NEW} initialPendingExpiresAt="" />,
    );

    expect(container.querySelector("[data-pending-expiry]")).toBeNull();
  });
});
