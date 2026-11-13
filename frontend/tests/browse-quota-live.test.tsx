/**
 * The live save allowance — the number that moves while the reader is on the page.
 *
 * ## The bug this file exists for
 *
 * **The allowance is spent by a save, and the page has to show that.** The Free
 * allowance is one save a day; the reader presses Save on a card; the server spends the
 * slot. And from that moment the page's own copy of the allowance was a lie: the hero
 * still said "0 of 1 save used today", and **every other card's button still read "Save"
 * and was still pressable** — so the surface was offering a press it knew the server was
 * about to refuse. The server's gate was correct the whole time. What was missing was
 * the client asking the server again.
 *
 * **These tests are written so that removing the refresh makes them fail.** That is the
 * whole discipline here: a test that passes whether or not the fix is present proves
 * nothing about the fix. So each one names the *observable* — the note's text, the
 * button's label — and the assertions are on those, not on "a request was made".
 *
 * ## The rules the client obeys
 *
 * - **The client asks; it does not compute.** The number is the server's, taken from
 *   the same endpoint as the first paint. A client that added one to `used` would show
 *   a wall the server is not enforcing, and a client that counted its own presses would
 *   show one for a save the server *refused*.
 * - **A refused save moves nothing.** The server refused, so the allowance did not
 *   move, and the note must not claim it did.
 * - **A failed refresh leaves the last known number.** A request that fails is not a
 *   statement about the allowance.
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BrowseQuotaNote } from "@/components/browse/browse-quota-note";
import { BrowseQuotaProvider } from "@/components/browse/browse-quota-provider";
import { BrowseSave } from "@/components/browse/browse-save";
import type { BrowseQuota } from "@/lib/browse-read";

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiDelete = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    GET: (...args: unknown[]) => apiGet(...args),
    POST: (...args: unknown[]) => apiPost(...args),
    DELETE: (...args: unknown[]) => apiDelete(...args),
  },
}));

const EVENT_ID = "22222222-2222-2222-2222-222222222222";
const EVENT_NAME = "Brooklyn Symphony open rehearsal";
const SLUG = "brooklyn-symphony-open-rehearsal";

/**
 * **The fixtures are typed as the server's own type.**
 *
 * `BrowseQuota` is the generated `BrowseQuotaOut` — the shape the API actually sends —
 * so a fixture that does not fit it is a fixture that is not what the server would send.
 * **A Pro account's `cap` is `null`, and `null` is in the type**, so the Pro fixture
 * below needs no cast: a cast would say "the Pro shape is not expressible", which is
 * false, and a reader who believed it would not trust the Pro test.
 */
const FREE_QUOTA: BrowseQuota = {
  used: 0,
  cap: 1,
  is_pro: false,
  resets_in_seconds: 86400,
};

/** The Free allowance, spent. */
const SPENT_QUOTA: BrowseQuota = {
  used: 1,
  cap: 1,
  is_pro: false,
  resets_in_seconds: 86400,
};

/** A Pro account's allowance: no cap at all, and no limit to reach. */
const PRO_QUOTA: BrowseQuota = {
  used: 0,
  cap: null,
  is_pro: true,
  resets_in_seconds: 0,
};

/** A browse payload carrying a quota. */
function browsePayload(quota: BrowseQuota) {
  return { data: { quota }, response: { status: 200 }, error: undefined };
}

function ok() {
  return { data: { id: "saved-1" }, response: { status: 200 }, error: undefined };
}

/** The hero's note, inside the provider. */
function renderNote(quota: BrowseQuota) {
  return render(
    <BrowseQuotaProvider quota={quota}>
      <BrowseQuotaNote fallback={quota} />
    </BrowseQuotaProvider>,
  );
}

/** A Save button inside the provider, beside the note. */
function renderSaveWithNote(quota: BrowseQuota) {
  return render(
    <BrowseQuotaProvider quota={quota}>
      <BrowseQuotaNote fallback={quota} />
      <BrowseSave
        eventId={EVENT_ID}
        eventName={EVENT_NAME}
        slug={SLUG}
        saved={false}
        quota={quota}
      />
    </BrowseQuotaProvider>,
  );
}

/**
 * **Two cards, so the wall can be seen on the *other* one.**
 *
 * The card that was saved says "Saved ✓" — it is saved, and an already-saved event is
 * never walled (un-saving is not a new save). The wall belongs on the cards that were
 * *not* saved, and those are the ones the reader would otherwise press. So the wall is
 * asserted on the second card, which is where the reader's next press would land.
 */
function renderTwoCardsWithNote(quota: BrowseQuota) {
  return render(
    <BrowseQuotaProvider quota={quota}>
      <BrowseQuotaNote fallback={quota} />
      <BrowseSave
        eventId={EVENT_ID}
        eventName={EVENT_NAME}
        slug={SLUG}
        saved={false}
        quota={quota}
      />
      <BrowseSave
        eventId="33333333-3333-3333-3333-333333333333"
        eventName="Outdoor cinema in the park"
        slug="outdoor-cinema-in-the-park"
        saved={false}
        quota={quota}
      />
    </BrowseQuotaProvider>,
  );
}

function note(): HTMLElement {
  const found = document.querySelector<HTMLElement>("[data-browse-quota]");
  if (!found) throw new Error("no quota note");
  return found;
}

function button(): HTMLElement {
  const found = document.querySelector<HTMLElement>("[data-browse-save-button]");
  if (!found) throw new Error("no Save button");
  return found;
}

/** The buttons, in the order they were rendered. */
function buttons(): HTMLElement[] {
  const found = Array.from(document.querySelectorAll<HTMLElement>("[data-browse-save-button]"));
  if (found.length === 0) throw new Error("no Save button");
  return found;
}

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  apiDelete.mockReset();
  apiGet.mockResolvedValue(browsePayload(FREE_QUOTA));
  apiPost.mockResolvedValue(ok());
  apiDelete.mockResolvedValue({ data: undefined, response: { status: 204 }, error: undefined });
});

describe("the live allowance", () => {
  it("starts at the number the server stated", () => {
    renderNote(FREE_QUOTA);

    expect(note().textContent).toContain("0 of 1 save used today");
  });

  it("asks the server again after a save, and shows what it says", async () => {
    // **The server's answer after the save is the spent one.** This is the whole point:
    // the client must adopt the server's number, and the server's number is 1 of 1.
    apiGet.mockResolvedValue(browsePayload(SPENT_QUOTA));

    renderSaveWithNote(FREE_QUOTA);
    expect(note().textContent).toContain("0 of 1 save used today");

    await act(async () => {
      fireEvent.click(button());
    });

    // **The note moves without a reload.** A page that had to be reloaded to learn the
    // truth would be showing a lie for as long as the reader stayed on it.
    await waitFor(() => {
      expect(note().textContent).toContain("1 of 1 save used today");
    });
  });

  it("shows the wall on the other cards once the allowance is spent", async () => {
    apiGet.mockResolvedValue(browsePayload(SPENT_QUOTA));

    renderTwoCardsWithNote(FREE_QUOTA);
    expect(buttons()[1].textContent).toBe("Save");

    await act(async () => {
      fireEvent.click(buttons()[0]);
    });

    // **The *other* card becomes the wall.** The card that was saved says "Saved ✓" —
    // an already-saved event is never walled, because un-saving is not a new save —
    // and the card the reader would press next reads the allowance and refuses.
    await waitFor(() => {
      expect(buttons()[1].textContent).toBe("1 of 1 save used today");
    });
    expect(buttons()[1].hasAttribute("disabled")).toBe(true);
  });

  it("takes the number from the server, and never counts its own presses", async () => {
    // **The server says the allowance is NOT spent**, even though a save landed.
    apiGet.mockResolvedValue(browsePayload(FREE_QUOTA));

    renderSaveWithNote(FREE_QUOTA);

    await act(async () => {
      fireEvent.click(button());
    });

    await waitFor(() => {
      expect(apiGet).toHaveBeenCalled();
    });
    // **A client that added one to `used` would show "1 of 1" here.** The server said
    // "0 of 1", so the note says "0 of 1". The client's own arithmetic is not a source
    // of truth about the server's counter.
    await waitFor(() => {
      expect(note().textContent).toContain("0 of 1 save used today");
    });
  });

  it("does not move the allowance when the server refused the save", async () => {
    // **A refusal is not a save.** The server refused before anything was written, so
    // the allowance did not move.
    apiGet.mockResolvedValue(browsePayload(FREE_QUOTA));
    apiPost.mockResolvedValue({
      data: undefined,
      response: { status: 409 },
      error: {
        code: "save_cap_reached",
        message: "You've used your free save for today.",
        details: { cap: 1, upgrade_hint: "You saved one event today. Save more with Pro." },
      },
    });

    renderSaveWithNote(FREE_QUOTA);

    await act(async () => {
      fireEvent.click(button());
    });

    await waitFor(() => {
      expect(apiGet).not.toHaveBeenCalled();
    });
    expect(note().textContent).toContain("0 of 1 save used today");
  });

  it("keeps the last known number when the refresh fails", async () => {
    apiGet.mockRejectedValue(new Error("the API is down"));

    renderSaveWithNote(FREE_QUOTA);

    await act(async () => {
      fireEvent.click(button());
    });

    // **A failed request is not a statement about the allowance.** The note keeps the
    // number it had — a stale number, which costs the reader a refused press, rather
    // than a wrong one, which would be a claim the server never made.
    await waitFor(() => {
      expect(apiGet).toHaveBeenCalled();
    });
    expect(note().textContent).toContain("0 of 1 save used today");
  });

  it("does not spend a Pro account's allowance, and shows no wall", async () => {
    // **A Pro account has `cap: null`.** There is no ceiling to reach, so the note
    // says there is no limit and the button never shows the wall's label.
    apiGet.mockResolvedValue(browsePayload(PRO_QUOTA));

    renderTwoCardsWithNote(PRO_QUOTA);

    expect(note().textContent).toContain("no save limit");

    await act(async () => {
      fireEvent.click(buttons()[0]);
    });

    await waitFor(() => {
      expect(buttons()[0].textContent).toBe("Saved ✓");
    });
    // **The second card is not walled.** It still reads "Save" — the Pro allowance has
    // no ceiling to reach, so there is nothing for the wall to say. (The first card is
    // inside its 1500ms lockout, which holds the *press* back and is not the wall; the
    // wall is a different thing and it is absent here.)
    expect(buttons()[1].textContent).toBe("Save");
    expect(buttons()[1].hasAttribute("disabled")).toBe(false);
  });
});
