import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SourceList } from "@/components/settings/source-list";

/**
 * `Settings → Sources` (FR-13, FR-16) — the registry, the three-state control, and the
 * bulk reset.
 *
 * **What these tests hold.**
 *
 * 1. **Every source is listed, including the muted ones.** The screen's job is
 *    transparency: the user is told what is informing their timeline *and* what they
 *    have turned off. A muted source that disappeared would be a preference they could
 *    not see or undo, on the very screen whose purpose is to show them that.
 * 2. **The three options show every choice.** Three buttons in a labelled group, with
 *    the selected one `aria-pressed` — a radio group would hide the two inactive options
 *    from a screen-reader user, and a `<select>` would hide them from everyone.
 * 3. **The state moves only when the server confirms.** A failed write leaves the
 *    control where it was, because the server did not record the change.
 * 4. **"Restore all defaults" confirms before it does.** The bulk reset is a destructive
 *    action, and the safeguard is that it is confirmed *before it completes* — so no
 *    request leaves on the first press.
 * 5. **The empty registry is an answer, not an error.** Nothing is fabricated to fill
 *    the screen.
 */
const PUT = vi.fn();
const POST = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    PUT: (...args: unknown[]) => PUT(...args),
    POST: (...args: unknown[]) => POST(...args),
  },
}));

type RegistrySource = {
  id: string;
  name: string;
  source_badge: string;
  city: string;
  trust: { band: number; score: string };
  mute_state: "mute" | "show_less" | "default";
  is_paused: boolean;
};

const OFFICIAL: RegistrySource = {
  id: "src-official",
  name: "Barbican Centre",
  source_badge: "official_site",
  city: "London",
  trust: { band: 4, score: "0.72" },
  mute_state: "default",
  is_paused: false,
};

const COMMUNITY: RegistrySource = {
  id: "src-community",
  name: "Crossrail Boards",
  source_badge: "community",
  city: "London",
  trust: { band: 3, score: "0.50" },
  mute_state: "mute",
  is_paused: false,
};

const PAUSED: RegistrySource = {
  id: "src-paused",
  name: "Old Venue Feed",
  source_badge: "aggregator",
  city: "",
  trust: { band: 1, score: "0.30" },
  mute_state: "default",
  is_paused: true,
};

function group(badge: string, label: string, sources: RegistrySource[]) {
  return { badge, label, sources };
}

const GROUPS = [
  group("official_site", "Official", [OFFICIAL]),
  group("community", "Community", [COMMUNITY]),
  group("aggregator", "Aggregator", [PAUSED]),
  group("crawled_html", "Crawled", []),
];

beforeEach(() => {
  PUT.mockReset();
  POST.mockReset();
  PUT.mockResolvedValue({ data: { source_id: "src-official", state: "mute", changed: true } });
  POST.mockResolvedValue({ data: { removed: 2 } });
});

describe("the registry", () => {
  it("lists every group, in order", () => {
    render(<SourceList groups={GROUPS} />);

    const headings = screen.getAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent?.split(" ")[0])).toEqual([
      "Official",
      "Community",
      "Aggregator",
      "Crawled",
    ]);
  });

  it("lists a muted source, because the screen is transparency", () => {
    render(<SourceList groups={GROUPS} />);

    expect(screen.getByText("Crossrail Boards")).toBeTruthy();
  });

  it("shows the state each source is in", () => {
    render(<SourceList groups={GROUPS} />);

    const group = screen.getByRole("group", { name: "Mute controls for Crossrail Boards" });
    const pressed = group.querySelectorAll('[aria-pressed="true"]');
    expect(pressed.length).toBe(1);
    expect(pressed[0]?.textContent).toBe("Mute");
  });

  it("shows the city's name under the source's name", () => {
    const { container } = render(<SourceList groups={GROUPS} />);

    // **Selected by its own attribute, not by its nesting.** This used to walk
    // `> div > span > span:nth-child(2)`, which meant the assertion about *what the row
    // says* broke the moment the row's layout changed — it was pinning the DOM shape as
    // a side effect of asking about text. The paused source has no city, so its line is
    // just "paused": a source with no city is not a local source, and the row says so
    // rather than showing a separator.
    const subLine = (id: string) =>
      container.querySelector(`[data-source="${id}"] [data-source-sub]`)?.textContent;

    expect(subLine("src-paused")).toBe("paused");
    expect(subLine("src-official")).toBe("London");
    // A paused *local* source says both things.
    expect(subLine("src-community")).toBe("London");
  });

  it("marks a paused source as paused", () => {
    const { container } = render(<SourceList groups={GROUPS} />);

    const paused = container.querySelector('[data-source="src-paused"]');
    expect(paused?.textContent).toContain("paused");
  });

  it("shows an empty group as an empty group, not as nothing", () => {
    render(<SourceList groups={GROUPS} />);

    expect(screen.getByText("None yet.")).toBeTruthy();
  });

  it("shows an empty registry as an answer, not an error", () => {
    render(<SourceList groups={[]} />);

    expect(screen.getByText(/No sources yet/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("the trust dots", () => {
  it("reads the band out in one sentence", () => {
    render(<SourceList groups={GROUPS} />);

    expect(screen.getByLabelText("4 of 5 reliability")).toBeTruthy();
  });

  it("does not read the dots out one by one", () => {
    const { container } = render(<SourceList groups={GROUPS} />);

    const dots = container.querySelector("[data-trust-dots]");
    expect(dots?.getAttribute("aria-hidden")).toBeNull();
    // The five dots themselves are decorative; the group's label carries the reading.
    expect(dots?.querySelector('[aria-hidden="true"]')).toBeTruthy();
  });
});

describe("the three-state control", () => {
  it("offers all three options, and names the group", () => {
    render(<SourceList groups={GROUPS} />);

    const group = screen.getByRole("group", { name: "Mute controls for Barbican Centre" });
    expect(group.textContent).toContain("Mute");
    expect(group.textContent).toContain("Show less");
    expect(group.textContent).toContain("Default");
  });

  it("sends the state the user chose, for the source it was chosen on", async () => {
    render(<SourceList groups={GROUPS} />);

    const group = screen.getByRole("group", { name: "Mute controls for Barbican Centre" });
    const mute = group.querySelector('[data-source-mute-option="mute"]');
    if (!mute) throw new Error("expected a Mute button");
    fireEvent.click(mute);

    await waitFor(() =>
      expect(PUT).toHaveBeenCalledWith("/api/settings/sources/{source_id}", {
        params: { path: { source_id: "src-official" } },
        body: { state: "mute" },
      }),
    );
  });

  it("does not send a request for the state the source is already in", async () => {
    render(<SourceList groups={GROUPS} />);

    const group = screen.getByRole("group", { name: "Mute controls for Crossrail Boards" });
    const mute = group.querySelector('[data-source-mute-option="mute"]');
    if (!mute) throw new Error("expected a Mute button");
    fireEvent.click(mute);

    await waitFor(() => expect(PUT).not.toHaveBeenCalled());
  });

  it("moves the control only when the server confirms", async () => {
    render(<SourceList groups={GROUPS} />);

    const group = screen.getByRole("group", { name: "Mute controls for Barbican Centre" });
    const mute = group.querySelector('[data-source-mute-option="mute"]');
    if (!mute) throw new Error("expected a Mute button");
    fireEvent.click(mute);

    await waitFor(() =>
      expect(
        group.querySelector('[data-source-mute-option="mute"]')?.getAttribute("aria-pressed"),
      ).toBe("true"),
    );
  });

  it("leaves the control where it was when the server refuses", async () => {
    PUT.mockResolvedValue({ error: { code: "server_error", message: "nope" } });
    render(<SourceList groups={GROUPS} />);

    const group = screen.getByRole("group", { name: "Mute controls for Barbican Centre" });
    const mute = group.querySelector('[data-source-mute-option="mute"]');
    if (!mute) throw new Error("expected a Mute button");
    fireEvent.click(mute);

    await waitFor(() => expect(screen.getAllByRole("alert").length).toBeGreaterThan(0));
    expect(
      group.querySelector('[data-source-mute-option="mute"]')?.getAttribute("aria-pressed"),
    ).toBe("false");
    expect(
      group.querySelector('[data-source-mute-option="default"]')?.getAttribute("aria-pressed"),
    ).toBe("true");
  });
});

describe("restore all defaults", () => {
  it("sends no request on the first press", () => {
    render(<SourceList groups={GROUPS} />);

    fireEvent.click(screen.getByRole("button", { name: /Restore default visibility/ }));

    expect(POST).not.toHaveBeenCalled();
  });

  it("asks before it does, in place", () => {
    render(<SourceList groups={GROUPS} />);

    fireEvent.click(screen.getByRole("button", { name: /Restore default visibility/ }));

    expect(screen.getByText(/Reset every source to its default visibility/)).toBeTruthy();
  });

  it("resets when the answer is yes", async () => {
    render(<SourceList groups={GROUPS} />);

    fireEvent.click(screen.getByRole("button", { name: /Restore default visibility/ }));
    fireEvent.click(screen.getByRole("button", { name: "Reset them" }));

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/settings/sources/restore-defaults"),
    );
  });

  it("resets nothing when the answer is no", () => {
    render(<SourceList groups={GROUPS} />);

    fireEvent.click(screen.getByRole("button", { name: /Restore default visibility/ }));
    fireEvent.click(screen.getByRole("button", { name: "Keep them" }));

    expect(POST).not.toHaveBeenCalled();
  });

  it("puts every row back to the default once the server confirms", async () => {
    render(<SourceList groups={GROUPS} />);

    fireEvent.click(screen.getByRole("button", { name: /Restore default visibility/ }));
    fireEvent.click(screen.getByRole("button", { name: "Reset them" }));

    await waitFor(() => {
      const group = screen.getByRole("group", { name: "Mute controls for Crossrail Boards" });
      expect(
        group.querySelector('[data-source-mute-option="default"]')?.getAttribute("aria-pressed"),
      ).toBe("true");
    });
  });

  it("puts a row the user had changed back to the default too", async () => {
    // **The reset must undo what the user did, not just what the server had.** A row the
    // user muted individually carries a local "just confirmed" state, and a reset that
    // only rewrote the prop would leave the control showing Mute while the server says
    // Default — the screen would be asserting a mute the server has just cleared.
    render(<SourceList groups={GROUPS} />);

    const group = screen.getByRole("group", { name: "Mute controls for Barbican Centre" });
    const mute = group.querySelector('[data-source-mute-option="mute"]');
    if (!mute) throw new Error("expected a Mute button");
    fireEvent.click(mute);

    await waitFor(() =>
      expect(
        group.querySelector('[data-source-mute-option="mute"]')?.getAttribute("aria-pressed"),
      ).toBe("true"),
    );

    fireEvent.click(screen.getByRole("button", { name: /Restore default visibility/ }));
    fireEvent.click(screen.getByRole("button", { name: "Reset them" }));

    await waitFor(() => {
      const after = screen.getByRole("group", { name: "Mute controls for Barbican Centre" });
      expect(
        after.querySelector('[data-source-mute-option="default"]')?.getAttribute("aria-pressed"),
      ).toBe("true");
      expect(
        after.querySelector('[data-source-mute-option="mute"]')?.getAttribute("aria-pressed"),
      ).toBe("false");
    });
  });

  it("offers no reset at all when there is nothing to reset", () => {
    render(<SourceList groups={[]} />);

    expect(screen.queryByRole("button", { name: /Restore default visibility/ })).toBeNull();
  });
});
