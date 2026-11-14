import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DigestCardList } from "@/components/digest/digest-card-list";

const recordDismissal = vi.fn();
const setCategoryMute = vi.fn();

vi.mock("@/lib/dismissal-write", () => ({
  recordDismissal: (...args: unknown[]) => recordDismissal(...args),
}));

vi.mock("@/lib/taste-mute-write", () => ({
  setCategoryMute: (...args: unknown[]) => setCategoryMute(...args),
}));

/**
 * The digest's card list, and the "less of this" prompt (FR-25).
 *
 * **The server decides what a dismissal means.** These tests never assert that the
 * client counted anything — the client sends one event id and renders what comes back.
 * What they *do* assert is the wiring: the card disappears when the server confirms,
 * the prompt opens when the server says it is due, and accepting it writes a mute.
 */

const CARD_A = "11111111-1111-1111-1111-111111111111";
const CARD_B = "22222222-2222-2222-2222-222222222222";

function card(eventId: string, title: string) {
  return {
    event_id: eventId,
    slot: "nearby",
    event_kind: "public",
    title,
    canonical_url: null,
    start_time_utc: "2026-11-07T23:00:00Z",
    end_time_utc: null,
    start_time_tz: "America/New_York",
    venue_name: "BAM Howard Gilman Opera House",
    venue_city: "Brooklyn",
    location: null,
    tags: ["nearby", "tonight"],
    bucket: 4,
    source_badge: "official_site",
    tz_review_pending: false,
    catalog_event_missing: false,
    conflict: false,
    public_slug: null,
  };
}

const PROMPT = {
  title: "Less arts & culture in your next digest?",
  description: "You've swiped past 3 similar events.",
  category_key: "arts_culture",
};

beforeEach(() => {
  recordDismissal.mockReset();
  setCategoryMute.mockReset();
  recordDismissal.mockResolvedValue({ cluster_advanced: true, prompt_due: false, prompt: null });
  setCategoryMute.mockResolvedValue(true);
});

function renderList() {
  render(
    <DigestCardList
      cards={[
        card(CARD_A, "Brooklyn Symphony open rehearsal"),
        card(CARD_B, "Pianist Eri Yamamoto"),
      ]}
      origin="https://eventpulse24.test"
    />,
  );
}

describe("the card list", () => {
  it("renders the cards in the server's order", () => {
    // The composition service chose the order and persisted it (AD-10). A client that
    // re-sorted would be re-deciding a persisted fact at render.
    renderList();

    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["Brooklyn Symphony open rehearsal", "Pianist Eri Yamamoto"]);
  });

  it("announces the count once, in one status region", () => {
    renderList();

    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("2 events for today");
  });

  it("takes the card away when the server confirms the dismissal", async () => {
    // **The removal is local, and honestly local.** The server's composition is a record
    // of a past decision, and it does not change because the user swiped a card on this
    // page load — the *next* composition is what excludes it.
    renderList();

    fireEvent.click(screen.getAllByRole("button", { name: /Show me less of this/ })[0]);

    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { level: 3, name: "Brooklyn Symphony open rehearsal" }),
      ).toBeNull(),
    );
    expect(
      screen.getByRole("heading", { level: 3, name: "Pianist Eri Yamamoto" }),
    ).toBeInTheDocument();
  });

  it("leaves the card alone when the server refuses the dismissal", async () => {
    recordDismissal.mockResolvedValue(null);

    renderList();

    fireEvent.click(screen.getAllByRole("button", { name: /Show me less of this/ })[0]);

    await waitFor(() => expect(recordDismissal).toHaveBeenCalled());
    expect(
      screen.getByRole("heading", { level: 3, name: "Brooklyn Symphony open rehearsal" }),
    ).toBeInTheDocument();
  });
});

describe("the prompt", () => {
  it("does not open until the server says the cluster completed", async () => {
    renderList();

    fireEvent.click(screen.getAllByRole("button", { name: /Show me less of this/ })[0]);

    await waitFor(() => expect(recordDismissal).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens with the server's copy when the server says the cluster completed", async () => {
    recordDismissal.mockResolvedValue({
      cluster_advanced: true,
      prompt_due: true,
      prompt: PROMPT,
    });

    renderList();

    fireEvent.click(screen.getAllByRole("button", { name: /Show me less of this/ })[0]);

    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(PROMPT.title);
  });

  it("writes a mute when the user accepts", async () => {
    recordDismissal.mockResolvedValue({
      cluster_advanced: true,
      prompt_due: true,
      prompt: PROMPT,
    });

    renderList();

    fireEvent.click(screen.getAllByRole("button", { name: /Show me less of this/ })[0]);
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Show me less" }));

    await waitFor(() => expect(setCategoryMute).toHaveBeenCalledWith("arts_culture", 30));
  });

  it("writes no mute when the user declines", async () => {
    recordDismissal.mockResolvedValue({
      cluster_advanced: true,
      prompt_due: true,
      prompt: PROMPT,
    });

    renderList();

    fireEvent.click(screen.getAllByRole("button", { name: /Show me less of this/ })[0]);
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Not now" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(setCategoryMute).not.toHaveBeenCalled();
  });

  it("writes no mute for a generic prompt, because it has no category", async () => {
    // **The generic prompt is a prompt, never a mute's subject.** The server sends no
    // `category_key` when the cluster did not agree on one chip, and a mute on nothing
    // would be a mute on nothing.
    recordDismissal.mockResolvedValue({
      cluster_advanced: true,
      prompt_due: true,
      prompt: {
        title: "Less events like these in your next digest?",
        description: "You've swiped past 3 similar events.",
        category_key: null,
      },
    });

    renderList();

    fireEvent.click(screen.getAllByRole("button", { name: /Show me less of this/ })[0]);
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Show me less" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(setCategoryMute).not.toHaveBeenCalled();
  });

  it("says so when the mute did not save", async () => {
    // **A user who was told "yes" and got nothing is worse off than one who was never
    // asked.** So the failure is stated, with the way out.
    recordDismissal.mockResolvedValue({
      cluster_advanced: true,
      prompt_due: true,
      prompt: PROMPT,
    });
    setCategoryMute.mockResolvedValue(false);

    renderList();

    fireEvent.click(screen.getAllByRole("button", { name: /Show me less of this/ })[0]);
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Show me less" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent("Settings → Taste");
  });
});
