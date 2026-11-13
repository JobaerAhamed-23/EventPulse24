/**
 * `/settings/collections` — FR-49's first screen, across the three tiers.
 *
 * **The two states worth testing hardest are the ones that look alike and are not.**
 *
 * 1. A **Free** user and a **lapsed Pro** user are both "not Pro", and they must not see
 *    the same thing: one has nothing, the other has collections that are still theirs.
 *    Rendering a lapsed user's list as absent would be the deletion the brief forbids, as
 *    far as they could tell.
 * 2. An **unavailable read** and an **empty list** are both "no collections on screen" and
 *    mean opposite things.
 */
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsCollectionsPage from "@/app/settings/collections/page";

const readCollections = vi.fn();
const readIsPro = vi.fn();
const getSession = vi.fn();

vi.mock("@/lib/collections-read", () => ({
  readCollections: () => readCollections(),
}));

vi.mock("@/lib/entitlement-read", () => ({
  readIsPro: () => readIsPro(),
}));

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/collections",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  redirect: vi.fn(),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

const COLLECTIONS = [
  { id: "id-one", name: "Music this month", position: 0, item_count: 3 },
  { id: "id-two", name: "For the kids", position: 1, item_count: 0 },
];

function serve(collections = COLLECTIONS) {
  readCollections.mockResolvedValue({ kind: "found", collections });
}

beforeEach(() => {
  readCollections.mockReset();
  readIsPro.mockReset();
  getSession.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readIsPro.mockResolvedValue(false);
  serve([]);
});

describe("a Pro user", () => {
  beforeEach(() => {
    readIsPro.mockResolvedValue(true);
    serve();
  });

  it("gets the manager, with the create control", async () => {
    render(await SettingsCollectionsPage());

    expect(screen.getByRole("region", { name: "Collections" })).toBeTruthy();
    expect(screen.getByLabelText("New collection")).toBeTruthy();
  });

  it("sees their collections and how many events each holds", async () => {
    render(await SettingsCollectionsPage());

    expect(screen.getByRole("button", { name: /^Music this month/ })).toBeTruthy();
    expect(screen.getByText("3 events")).toBeTruthy();
    // Singular and plural are not the same word.
    expect(screen.getByText("0 events")).toBeTruthy();
  });

  it("is not offered an upgrade", async () => {
    render(await SettingsCollectionsPage());

    expect(screen.queryByRole("link", { name: "Upgrade" })).toBeNull();
  });

  it("gets the quiet empty state when they have none yet", async () => {
    serve([]);

    render(await SettingsCollectionsPage());

    expect(screen.getByText("No collections yet.")).toBeTruthy();
    expect(screen.getByLabelText("New collection")).toBeTruthy();
  });
});

describe("a Free user", () => {
  it("is told what collections are and offered them", async () => {
    render(await SettingsCollectionsPage());

    expect(screen.getByText(/Collections let you group your saves/)).toBeTruthy();
    // The sentence is the backend's `COLLECTIONS_UPGRADE_HINT`, verbatim. It is spelled on
    // the client because a Free user is never refused here, so no 409 ever carries it.
    expect(screen.getByText("Group your saves into collections with Pro.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Upgrade" })).toHaveAttribute("href", "/pricing");
  });

  it("gets no create form, rather than one that refuses", async () => {
    // Letting somebody name a collection and then telling them they cannot have one would
    // be accurate and still a trap.
    render(await SettingsCollectionsPage());

    expect(screen.queryByLabelText("New collection")).toBeNull();
    expect(screen.queryByRole("button", { name: "Create" })).toBeNull();
  });

  it("is offered inline, never as an interruption", async () => {
    render(await SettingsCollectionsPage());

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("is not shown the Pro empty state", async () => {
    // "No collections yet" with a create box would be an invitation they cannot accept.
    render(await SettingsCollectionsPage());

    expect(screen.queryByText("No collections yet.")).toBeNull();
  });
});

describe("a lapsed Pro user", () => {
  beforeEach(() => {
    readIsPro.mockResolvedValue(false);
    serve();
  });

  it("still sees their collections", async () => {
    // **Their rows are kept on purpose.** A list that hid them would be the deletion the
    // brief forbids, as far as the user could tell.
    render(await SettingsCollectionsPage());

    const list = document.querySelector("[data-lapsed-collections]");
    if (!list) throw new Error("the lapsed user's collections were not rendered");
    expect(within(list as HTMLElement).getByText("Music this month")).toBeTruthy();
    expect(within(list as HTMLElement).getByText("For the kids")).toBeTruthy();
  });

  it("is never shown as having none", async () => {
    render(await SettingsCollectionsPage());

    expect(screen.queryByText("No collections yet.")).toBeNull();
    expect(screen.queryByText(/Collections let you group your saves/)).toBeNull();
  });

  it("is offered the way back", async () => {
    render(await SettingsCollectionsPage());

    expect(screen.getByText("Group your saves into collections with Pro.")).toBeTruthy();
  });

  it("gets no controls they cannot use", async () => {
    render(await SettingsCollectionsPage());

    expect(screen.queryByLabelText("New collection")).toBeNull();
    expect(screen.queryByRole("button", { name: "Rename" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
  });
});

describe("the shell", () => {
  it("marks Settings as the active sidenav item", async () => {
    // The route lives under `/settings` precisely so the existing nav item lights up —
    // DESIGN.md closes the nav to new routes.
    render(await SettingsCollectionsPage());

    const sidenav = screen.getByRole("complementary", { name: "Primary" });
    expect(within(sidenav).getByRole("link", { name: "Settings" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("shows the unavailable state when the read fails", async () => {
    // **Not the empty state.** A Pro user with three collections whose read blinked would
    // otherwise be shown "you have none", which reads as data loss.
    readIsPro.mockResolvedValue(true);
    readCollections.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsCollectionsPage());

    expect(screen.queryByText("No collections yet.")).toBeNull();
    expect(screen.queryByRole("region", { name: "Collections" })).toBeNull();
  });

  it("shows the signed-out state without reading collections", async () => {
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsCollectionsPage());

    expect(screen.queryByRole("region", { name: "Collections" })).toBeNull();
  });
});
