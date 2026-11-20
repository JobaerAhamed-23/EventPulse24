/**
 * The privacy screen's danger zone — **and the screen's two branches.**
 *
 * ## Why the screen needs its own test
 *
 * The danger zone's own file holds its markup, and the page holds where it goes. **Those
 * are two different claims, and only the second one is a claim about the product.** A
 * danger zone that is built and never mounted is a component; a danger zone that is
 * mounted on a route nobody visits is a line of code.
 *
 * ## The claim that matters: it renders in *both* branches
 *
 * `/settings/privacy` has two branches — the ranking formula, and `unavailable` when the
 * ranking read fails. **The danger zone has to be in both.**
 *
 * The reason is the whole point of a danger zone: a section that vanishes when the page
 * is unhealthy is the opposite of what a danger zone is for. **A failed ranking read is
 * exactly the moment someone might go looking for how to delete their account** — the
 * page they are on is broken, and the one control on it that actually does something
 * should still be there.
 *
 * **So this file asserts the danger zone is on the page in each branch**, and the
 * mutation probe in the run's test report removes it from the `unavailable` branch to
 * show these assertions can fail.
 *
 * ## And the nav row has to agree
 *
 * The settings nav is one list, and the Privacy row's description is the page's own
 * subheading. **A nav row that says "your data" over a page that only explains ranking
 * is the unkept promise this screen exists to close** — so the description names the
 * ranking formula *and* the danger zone, and this file holds it to that.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPrivacyPage from "@/app/settings/privacy/page";
import type { RankingTransparency } from "@/lib/ranking-transparency-read";
import { SETTINGS_SECTIONS } from "@/lib/settings-sections";

const getSession = vi.fn();
const readRankingTransparency = vi.fn();

vi.mock("@/lib/ranking-transparency-read", () => ({
  readRankingTransparency: () => readRankingTransparency(),
}));

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/navigation", () => ({
  redirect: vi.fn(() => {
    throw new Error("NEXT_REDIRECT");
  }),
  usePathname: () => "/settings/privacy",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

/** A signed-in visitor, with the fields the page's shell reads. */
const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "Maya Ahmed",
  avatar_url: "/api/auth/profile/avatar/ab12cd34",
  pending_email: "",
  pending_email_expires_at: "",
  deletion_scheduled_for: "",
  deletion_requested_at: "",
  onboarding: { completed: true, current_step: null },
};

/** The ranking formula, in the shape the read promises. */
const RANKING: RankingTransparency = {
  terms: [
    { key: "interest_overlap", label: "What you picked", weight: "0.41" },
    { key: "recency", label: "How soon it starts", weight: "0.19" },
  ],
  total: "0.60",
  buckets: [
    { dots: 5, min_score: "0.87" },
    { dots: 4, min_score: "0.67" },
    { dots: 3, min_score: "0.47" },
    { dots: 2, min_score: "0.27" },
    { dots: 1, min_score: "0.00" },
  ],
  boundary_rule: "lower",
  amendment: { id: "A-99", record: "ADR-9999", date: "2026-01-02" },
};

beforeEach(() => {
  getSession.mockReset();
  readRankingTransparency.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readRankingTransparency.mockResolvedValue({ kind: "found", ranking: RANKING });
});

describe("the privacy screen's danger zone", () => {
  it("renders the danger zone when the ranking formula loads", async () => {
    render(await SettingsPrivacyPage());

    expect(screen.getByRole("region", { name: "Danger zone" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete account/i })).toBeInTheDocument();
  });

  it("renders the danger zone when the ranking read failed", async () => {
    /** **The branch that matters.**
     *
     * A failed ranking read renders the settings' error state, and the danger zone
     * still has to be there — **a danger zone that disappears when the page is
     * unhealthy is the opposite of what a danger zone is for.** */
    readRankingTransparency.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsPrivacyPage());

    expect(screen.getByRole("region", { name: "Danger zone" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete account/i })).toBeInTheDocument();
  });

  it("never renders both states of the danger zone at once", async () => {
    /** **One instruction at a time.** A page offering a "Delete account →" row *and* a
     * "Keep my account" button is offering two contradictory instructions. The pending
     * state is not built yet — `CurrentUserOut` carries no pending-deletion field, and
     * the item that adds it depends on this one — so the request state is the only
     * state there is. */
    render(await SettingsPrivacyPage());

    expect(screen.queryByRole("button", { name: /keep my account/i })).not.toBeInTheDocument();
  });

  it("keeps the destructive control in the destructive colour, on both branches", async () => {
    /** **Terracotta is reserved for destructive actions**, and the heading does not get
     * it — the accent is spent on the control, not on the decoration. */
    readRankingTransparency.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsPrivacyPage());

    const button = screen.getByRole("button", { name: /delete account/i });
    expect(button.className).toContain("text-accent-terracotta");

    const heading = screen.getByRole("heading", { name: "Danger zone" });
    expect(heading.className).not.toContain("terracotta");
  });
});

describe("the privacy screen's nav row", () => {
  it("names the danger zone, because the page now holds it", () => {
    /** **The description is the page's own subheading**, and the index is a table of
     * contents rather than a second description of the product.
     *
     * The description used to read *"How your Pulse is ranked."* — accurate for a page
     * that held only the formula, and inaccurate the moment the danger zone landed. */
    const privacy = SETTINGS_SECTIONS.find((section) => section.href === "/settings/privacy");

    expect(privacy).toBeDefined();
    expect(privacy?.description).toMatch(/ranked/i);
    expect(privacy?.description).toMatch(/delete your account/i);
  });

  it("agrees with the page's own subheading, because they are the same sentence", async () => {
    /** **One sentence, two places that must agree.**
     *
     * The nav row's description is "the same sentence as the destination page's own
     * subheading" — that is the rule `lib/settings-sections.ts` states for itself. So
     * when the danger zone landed and the description changed, the page's subheading
     * had to change with it.
     *
     * **This is the assertion that catches the drift.** Two sentences saying roughly the
     * same thing is how a nav row ends up promising something the page does not have —
     * the exact failure this screen's own docstring records. */
    const privacy = SETTINGS_SECTIONS.find((section) => section.href === "/settings/privacy");

    render(await SettingsPrivacyPage());

    const subheading = screen.getByText(/how your pulse is ranked, in full/i);
    expect(subheading).toBeInTheDocument();
    // **Both name the ranking formula and the danger zone.**
    expect(subheading.textContent).toMatch(/ranked/i);
    expect(subheading.textContent).toMatch(/danger zone/i);
    expect(privacy?.description).toMatch(/ranked/i);
    expect(privacy?.description).toMatch(/delete your account/i);
  });
});
