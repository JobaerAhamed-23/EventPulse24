/**
 * The privacy screen's danger zone — **when a deletion is pending.**
 *
 * ## Why this file exists, and what it is not
 *
 * `components/settings/danger-zone-pending.test.tsx` holds the pending island on its own,
 * and `tests/privacy-danger-zone.test.tsx` holds the page with nothing pending. **Neither
 * of those is a claim about the product.** An island that renders but is never given the
 * server's two moments is a component; a page that never shows the pending state to a
 * person whose account is scheduled for destruction is a line of code.
 *
 * ## The claim that matters: the pending state reaches the page
 *
 * **The two moments ride `me`.** `CurrentUserOut` carries `deletion_scheduled_for` and
 * `deletion_requested_at`, and the page hands both to `<DangerZone>`. If the page did
 * not — if it passed the empty string, or omitted the prop — the island would render a
 * request row and a person whose account is scheduled for destruction would be told they
 * could delete it again. **That is the failure this file exists to catch**, and it is a
 * failure in the wiring between the page and the section, so it can only be seen from
 * the page.
 *
 * ## And it survives the page's own unhealthy branch
 *
 * `/settings/privacy` has two branches — the ranking formula, and `unavailable` when the
 * ranking read fails. **The pending state has to be in both.** A failed ranking read is
 * exactly the moment someone might go looking for how to stop their account's deletion.
 * A pending state that disappears when the page is unhealthy is the same mistake as a
 * danger zone that disappears, and it is worse here: the person is *already* in the
 * middle of a destructive action.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPrivacyPage from "@/app/settings/privacy/page";
import type { RankingTransparency } from "@/lib/ranking-transparency-read";

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

/** The server's two moments, for an account with a deletion pending. */
const SCHEDULED_FOR = "2026-12-20T00:00:00+00:00";
const REQUESTED_AT = "2026-11-20T00:00:00+00:00";

/** A signed-in visitor whose account is scheduled for destruction. */
const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "Maya Ahmed",
  avatar_url: "/api/auth/profile/avatar/ab12cd34",
  pending_email: "",
  pending_email_expires_at: "",
  deletion_scheduled_for: SCHEDULED_FOR,
  deletion_requested_at: REQUESTED_AT,
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

describe("the privacy screen, with a deletion pending", () => {
  it("shows the pending state, not the request row", async () => {
    /** **One instruction at a time.** A page offering a "Delete account →" row *and* a
     * "Keep my account" button is offering two contradictory instructions — and for an
     * account already scheduled for destruction, the second one is the true one. */
    render(await SettingsPrivacyPage());

    expect(screen.getByRole("button", { name: /keep my account/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete account/i })).not.toBeInTheDocument();
  });

  it("carries the server's destruction date onto the page", async () => {
    /** **The wiring.** The date the server computed has to survive the trip from `me`,
     * through the page, into the section. If the page passed the empty string, the
     * pending state would render with no date at all. */
    render(await SettingsPrivacyPage());

    expect(screen.getByText(/december 20, 2026/i)).toBeInTheDocument();
  });

  it("shows the pending state when the ranking read failed", async () => {
    /** **The branch that matters.**
     *
     * A failed ranking read renders the settings' error state, and the pending state
     * still has to be there — **a pending state that disappears when the page is
     * unhealthy is the same mistake as a danger zone that disappears**, and it is worse
     * here: the person is already in the middle of a destructive action. */
    readRankingTransparency.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsPrivacyPage());

    expect(screen.getByRole("button", { name: /keep my account/i })).toBeInTheDocument();
    expect(screen.getByText(/december 20, 2026/i)).toBeInTheDocument();
  });

  it("does not spend the destructive colour on the way back", async () => {
    /** **The pending state is the way back *from* a destructive action.** Spending the
     * destructive colour on a button whose job is to prevent destruction would spend the
     * accent on the opposite of what it means. */
    render(await SettingsPrivacyPage());

    const button = screen.getByRole("button", { name: /keep my account/i });
    expect(button.className).not.toContain("terracotta");
  });
});
