import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  PreviewBannerSlot,
  PreviewCardsSlot,
  PreviewProvider,
} from "@/components/preview/preview-section";
import { CHOICE_COOKIE } from "@/lib/preview-choice";

/**
 * The preview's state: the request, the three states, the consent banner and the soft
 * wall.
 */

const GET = vi.fn();
const push = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { GET: (...args: unknown[]) => GET(...args) },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
}));

function card(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    slug: `event-${id}`,
    title: `Event ${id}`,
    start_time_utc: "2026-11-07T23:00:00Z",
    start_time_tz: "America/New_York",
    venue_name: "A venue",
    city: "Brooklyn",
    score: 4,
    tags: ["tonight"],
    source_name: "A source",
    source_badge: "official_site",
    ...overrides,
  };
}

const PREVIEW = {
  city: "Brooklyn",
  city_source: "geo",
  items: [card("1"), card("2"), card("3")],
};

function answer(path: string, data: unknown) {
  return (requested: string) =>
    Promise.resolve(
      requested === path
        ? { data, error: undefined }
        : { data: { cities: ["Brooklyn", "Queens"] }, error: undefined },
    );
}

function renderPreview() {
  render(
    <PreviewProvider>
      <PreviewBannerSlot />
      <PreviewCardsSlot />
    </PreviewProvider>,
  );
}

beforeEach(() => {
  GET.mockReset();
  push.mockReset();
  GET.mockImplementation(answer("/api/public/preview", PREVIEW));
});

afterEach(() => {
  document.cookie = `${CHOICE_COOKIE}=; Path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
});

describe("the three states", () => {
  it("shows three skeletons while the request is in flight", () => {
    GET.mockReturnValue(new Promise(() => {}));
    renderPreview();

    expect(screen.getByRole("status", { name: "Loading the preview" })).toBeInTheDocument();
  });

  it("shows the cards once they arrive", async () => {
    renderPreview();

    expect(await screen.findByText("Event 1")).toBeInTheDocument();
    expect(screen.getByText("Event 3")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Next 3 days in Brooklyn");
  });

  it("names the city in the empty state", async () => {
    GET.mockImplementation(
      answer("/api/public/preview", { city: "Queens", city_source: "query", items: [] }),
    );
    renderPreview();

    expect(await screen.findByText("No preview available in Queens yet.")).toBeInTheDocument();
  });

  it("names the city the visitor asked for, not a fallback's", async () => {
    // An unsupported explicit city comes back empty carrying *that* city's name. Showing
    // another city's events under it would be a heading that lies.
    GET.mockImplementation(
      answer("/api/public/preview", { city: "Milton Keynes", city_source: "query", items: [] }),
    );
    renderPreview();

    expect(
      await screen.findByText("No preview available in Milton Keynes yet."),
    ).toBeInTheDocument();
    // The heading names it too, rather than silently showing another city's events.
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      "Next 3 days in Milton Keynes",
    );
  });

  it("shows the error copy when the API refuses", async () => {
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "rate_limited", message: "Too many requests." },
    });
    renderPreview();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't load the preview. Refresh.",
    );
  });

  it("shows the error copy when the request never reaches the API", async () => {
    GET.mockRejectedValue(new TypeError("Failed to fetch"));
    renderPreview();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't load the preview. Refresh.",
    );
  });
});

describe("the consent banner", () => {
  it("asks once, naming the resolved city", async () => {
    renderPreview();

    const banner = await screen.findByRole("region", { name: "Location consent" });
    expect(banner).toHaveTextContent("Showing events near Brooklyn. Use a different city?");
    for (const action of ["Use this", "Change", "Don't use my location"]) {
      expect(screen.getByRole("button", { name: action })).toBeInTheDocument();
    }
  });

  it("does not ask a visitor who has already chosen", async () => {
    document.cookie = `${CHOICE_COOKIE}=Queens; Path=/`;
    renderPreview();

    await screen.findByText("Event 1");
    expect(screen.queryByRole("region", { name: "Location consent" })).toBeNull();
  });

  it("asks for the city the visitor already chose", async () => {
    document.cookie = `${CHOICE_COOKIE}=Queens; Path=/`;
    renderPreview();

    await screen.findByText("Event 1");
    expect(GET).toHaveBeenCalledWith("/api/public/preview", {
      params: { query: { city: "Queens" } },
    });
  });

  it("remembers 'Use this' and closes, without asking again", async () => {
    renderPreview();
    await screen.findByRole("region", { name: "Location consent" });
    GET.mockClear();

    fireEvent.click(screen.getByRole("button", { name: "Use this" }));

    expect(screen.queryByRole("region", { name: "Location consent" })).toBeNull();
    expect(document.cookie).toContain(`${CHOICE_COOKIE}=Brooklyn`);
    // Nothing changed about what to show, so nothing is re-read.
    expect(GET).not.toHaveBeenCalled();
  });

  it("switches the location off on the opt-out, and re-reads without it", async () => {
    // Not just remembered: `use_geo=false` is what stops the backend consulting the
    // header at all, and the fallback city is what the visitor then sees.
    renderPreview();
    await screen.findByRole("region", { name: "Location consent" });
    GET.mockClear();
    GET.mockImplementation(
      answer("/api/public/preview", { city: "NYC", city_source: "fallback", items: [card("9")] }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Don't use my location" }));

    expect(GET).toHaveBeenCalledWith("/api/public/preview", {
      params: { query: { use_geo: false } },
    });
    expect(document.cookie).toContain(`${CHOICE_COOKIE}=off`);
    expect(await screen.findByRole("heading", { level: 2 })).toHaveTextContent("NYC");
    expect(screen.queryByRole("region", { name: "Location consent" })).toBeNull();
  });

  it("offers the supported cities on Change, and re-reads for the one picked", async () => {
    renderPreview();
    await screen.findByRole("region", { name: "Location consent" });

    fireEvent.click(screen.getByRole("button", { name: "Change" }));

    const queens = await screen.findByRole("button", { name: "Queens" });
    expect(GET).toHaveBeenCalledWith("/api/public/preview/cities");

    GET.mockClear();
    GET.mockImplementation(
      answer("/api/public/preview", { ...PREVIEW, city: "Queens", city_source: "query" }),
    );
    fireEvent.click(queens);

    expect(GET).toHaveBeenCalledWith("/api/public/preview", {
      params: { query: { city: "Queens" } },
    });
    expect(document.cookie).toContain(`${CHOICE_COOKIE}=Queens`);
  });

  it("says so plainly when the city list cannot be read", async () => {
    renderPreview();
    await screen.findByRole("region", { name: "Location consent" });
    GET.mockRejectedValue(new TypeError("Failed to fetch"));

    fireEvent.click(screen.getByRole("button", { name: "Change" }));

    expect(await screen.findByText(/couldn't load the city list/i)).toBeInTheDocument();
  });
});

describe("the soft wall", () => {
  async function saveButtons() {
    renderPreview();
    await screen.findByText("Event 1");
    return screen.getAllByRole("button", { name: "Save" });
  }

  it("records the first two saves on the page, and says they are only for this visit", async () => {
    const buttons = await saveButtons();

    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[1]);

    expect(screen.getAllByText("Saved for this visit. Sign up to keep it.")).toHaveLength(2);
    expect(push).not.toHaveBeenCalled();
  });

  it("asks for an account on the third save (FR-2)", async () => {
    const buttons = await saveButtons();

    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[1]);
    fireEvent.click(buttons[2]);

    expect(push).toHaveBeenCalledWith("/signup");
  });

  it("counts saves, not cards, so a repeated tap does not spend the allowance", async () => {
    const buttons = await saveButtons();

    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[1]);

    expect(push).not.toHaveBeenCalled();
  });
});
