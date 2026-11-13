/**
 * **The stored name reaches the rail, and the fallback still works when it does not.**
 *
 * ## Why this file exists
 *
 * `lib/display-name.ts` pins *what the rule does*. `tests/display-name.test.ts` pins
 * *that every page goes through the helper*. **Neither of those proves the name
 * arrives.** The chain is four links long — the session carries it, the page reads it,
 * the page hands it to `AppShell`, and the shell hands it to the rail — and a link
 * anywhere in that chain can be dropped without either file noticing.
 *
 * **So this file renders a real page and asks the rail what it is showing.** That is
 * the only level at which "the user sees their name" is a fact at all: the helper
 * knows the rule, the page knows the call, and only the rendered rail knows the
 * outcome.
 *
 * ## The property
 *
 * Two cases, and they are the whole of the work item's promise:
 *
 * 1. **A user with a stored name sees that name.** Not the email's local part, not a
 *    capitalised version of it — *their* name.
 * 2. **A user with no stored name still sees the email-derived name.** The fallback
 *    is not "blank". A blank rail is a worse bug than a wrong one, because it reads as
 *    "this account has no name" rather than "this feature is broken".
 */
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "@/app/page";

const getSession = vi.fn();
const readDigest = vi.fn();
const readNotices = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  // `homeRoute` is the real one: it is the rule under test, and `lib/session.test.ts`
  // pins it directly. Stubbing it here would let the page and the rule drift apart.
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/digest-read", () => ({
  readDigest: () => readDigest(),
}));

vi.mock("@/lib/notice-read", () => ({
  readNotices: () => readNotices(),
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  usePathname: () => "/",
  // The page renders the real sign-out button, which is a client component with a router.
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

/**
 * A signed-in user whose only field of interest is the name.
 *
 * **The email is `maya.ahmed@example.test`, so the fallback would render
 * `"Maya Ahmed"`.** That matters: **the stored name in these tests is deliberately
 * *not* `"Maya Ahmed"`.** If it were, the two answers would be identical and the
 * test could not tell "the stored name was used" from "the fallback was used" — it
 * would pass either way, which is the same vacuity the mutation probe exists to
 * catch.
 *
 * **So the stored name is one the email cannot produce** — `"Ada Lovelace"`. The two
 * answers differ, and the assertions can tell them apart.
 */
const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya.ahmed@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

/** The name the fallback rule produces for `USER.email`. */
const FALLBACK_NAME = "Maya Ahmed";

/** A stored name the email cannot produce. */
const STORED_NAME = "Ada Lovelace";

beforeEach(() => {
  getSession.mockReset();
  readDigest.mockReset();
  readNotices.mockReset();
  redirect.mockReset();
  // **A composed digest with no cards.** The digest is not what this file is about —
  // the rail is — but the home page renders one, and it has to be a shape the header
  // can format. An empty card list is enough; the header only needs a local date and
  // a timezone.
  readDigest.mockResolvedValue({
    kind: "composed",
    digest: {
      status: "composed",
      cards: [],
      city: "Brooklyn",
      city_source: "user",
      local_date: "2026-11-07",
      timezone: "America/New_York",
    },
  });
  readNotices.mockResolvedValue({ kind: "notices", notices: [] });
});

/** Sign in as a user with the given stored name. */
function signIn(name: string) {
  getSession.mockResolvedValue({ kind: "signed-in", user: { ...USER, name } });
}

/** The home page's props — it reads the query string. */
function props(): PageProps<"/"> {
  return { params: Promise.resolve({}), searchParams: Promise.resolve({}) };
}

/**
 * The name the rail is showing.
 *
 * **The rail's account row is a button whose accessible name is `Account: <name>`.**
 * That is a stable hook, and it is the name the *user* would hear — so the assertion
 * is on what a person perceives rather than on an implementation detail.
 */
function railName(): string {
  const button = screen.getByRole("button", { name: /^Account: / });
  const label = button.getAttribute("aria-label") ?? "";
  return label.replace(/^Account: /, "");
}

describe("the rail", () => {
  it("shows a user with a stored name by that name", async () => {
    signIn(STORED_NAME);

    render(await HomePage(props()));

    expect(railName()).toBe(STORED_NAME);
  });

  it("does not fall back to the email-derived name when a name is stored", async () => {
    // **The failure this work item exists to prevent.** The rail would say
    // `"Maya Ahmed"` — the email's local part — if the stored name were ignored.
    //
    // **The two names differ on purpose** (see `USER` above), so this assertion can
    // tell "the stored name was used" from "the fallback was used".
    signIn(STORED_NAME);

    render(await HomePage(props()));

    expect(railName()).not.toBe(FALLBACK_NAME);
  });

  it("shows a user with no stored name the email-derived name", async () => {
    // **The fallback is not "blank".** This is the negative case worth checking by
    // hand: the name is `""`, and the rail must still say something.
    signIn("");

    render(await HomePage(props()));

    expect(railName()).toBe(FALLBACK_NAME);
  });

  it("shows the stored name in the account sheet too, not only in the rail", async () => {
    // **The rail's row and the sheet it opens are two renders of the same prop.**
    // The sheet is the one the person opens to *check* their name — so a sheet that
    // disagreed with the row would be the more confusing of the two.
    signIn(STORED_NAME);

    render(await HomePage(props()));

    // **The sheet is a native `<dialog>` with an `aria-label`.** It has no implicit
    // ARIA role, so it is queried by its element and its label rather than by role.
    //
    // **Scoped to the sheet.** The rail's row also carries the name, so an unscoped
    // `getByText` would find two and refuse to choose.
    const sheet = document.querySelector('dialog[aria-label="Account"]');
    expect(sheet).not.toBeNull();
    expect(within(sheet as HTMLElement).getByText(STORED_NAME)).toBeTruthy();
  });
});
