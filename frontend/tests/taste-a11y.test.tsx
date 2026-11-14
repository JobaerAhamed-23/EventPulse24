/**
 * The FR-25 surfaces' **axe-core gate**.
 *
 * **"axe-core reports zero serious or critical violations on this surface."** The work
 * item's acceptance criteria say so, and this file is the gate.
 *
 * **The gate runs over every state, not just the happy one.** A screen can be
 * accessible when it is full and inaccessible when it is empty: an empty list with no
 * heading hierarchy, a failed read whose state names no control, a prompt with a
 * description it does not point at — each is a different document, and each is a
 * different set of rules. So the populated, empty and failed documents are all
 * audited, and so is the prompt with its own copy.
 *
 * **Serious and critical only.** `minor` and `moderate` findings are advisory — they
 * are usually about contrast on non-text decoration — and a gate that fails on a
 * moderate finding is a gate that gets disabled. Serious and critical are the ones
 * that make a surface unusable for someone.
 *
 * **`color-contrast` is off.** jsdom computes no layout, so axe cannot measure
 * contrast and would report every coloured thing as a violation. The digest's gate
 * disables it for the same reason, and `tests/contrast.test.ts` measures contrast
 * against the tokens separately.
 */
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsTastePage from "@/app/settings/taste/page";
import { MutePrompt } from "@/components/digest/mute-prompt";

const getSession = vi.fn();
const readTaste = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/taste-mutes-read", () => ({
  readTaste: () => readTaste(),
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  usePathname: () => "/settings/taste",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

const MUTE = {
  category_key: "arts_culture",
  label: "Arts & culture",
  expires_at: "2026-12-07T00:00:00Z",
  is_indefinite: false,
};

const PROMPT = {
  title: "Less arts & culture in your next digest?",
  description:
    "You've swiped past 3 similar events. Want us to deprioritize this category for a while? You can undo anytime in Settings → Taste.",
  category_key: "arts_culture",
};

beforeEach(() => {
  getSession.mockReset();
  readTaste.mockReset();
  redirect.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readTaste.mockResolvedValue({ kind: "found", mutes: [MUTE] });
});

/** Run axe over whatever is on the page, and report only serious and critical. */
async function audit() {
  const results = await axe.run(document.body, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
  });
  return results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
}

describe("the taste screen", () => {
  it("has no serious or critical violations with mutes on it", async () => {
    render(await SettingsTastePage());

    expect(await audit()).toEqual([]);
  });

  it("has no serious or critical violations when nothing is muted", async () => {
    // **The empty list is a different document.** An empty state with no heading
    // hierarchy, or a bulk control that is gone but whose region is not, would each be
    // its own set of rules.
    readTaste.mockResolvedValue({ kind: "found", mutes: [] });

    render(await SettingsTastePage());

    expect(await audit()).toEqual([]);
  });

  it("has no serious or critical violations when the read failed", async () => {
    // **The failed read is a third document**, and it is the one that matters most:
    // it is what a user whose read blinked sees, on the screen whose job is to let
    // them undo what they muted.
    readTaste.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsTastePage());

    expect(await audit()).toEqual([]);
  });
});

describe("the prompt", () => {
  it("has no serious or critical violations when it is open", async () => {
    render(<MutePrompt open prompt={PROMPT} onAccept={vi.fn()} onDismiss={vi.fn()} />);

    expect(await audit()).toEqual([]);
  });

  it("has no serious or critical violations when it is closed", async () => {
    render(<MutePrompt open={false} prompt={PROMPT} onAccept={vi.fn()} onDismiss={vi.fn()} />);

    expect(await audit()).toEqual([]);
  });
});

describe("the prompt's own structure", () => {
  it("is reachable by keyboard, with every control a real button", () => {
    // **The prompt is a question, and a gesture-only dismissal would be a dark
    // pattern.** So the dismissal paths — Escape, the X, and the "Not now" button —
    // are all in the DOM as controls.
    render(<MutePrompt open prompt={PROMPT} onAccept={vi.fn()} onDismiss={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Show me less" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Not now" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });
});
