import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HealthPanel } from "@/app/dev/health/health-panel";
import { api } from "@/lib/backend-client";

vi.mock("@/lib/backend-client", () => ({ api: { GET: vi.fn() } }));

const GET = vi.mocked(api.GET);
const ok = { status: "ok" as const, reason: null };

function respond(result: unknown) {
  GET.mockResolvedValue(result as Awaited<ReturnType<typeof api.GET>>);
}

describe("HealthPanel", () => {
  beforeEach(() => {
    GET.mockReset();
  });

  it("shows Checking… while the request is in flight", () => {
    GET.mockReturnValue(new Promise(() => {}));

    render(<HealthPanel />);

    expect(screen.getByText("Checking…")).toBeInTheDocument();
    expect(GET).toHaveBeenCalledWith("/api/health");
  });

  it("lists every component as OK when the API is healthy", async () => {
    respond({ data: { status: "ok", components: { personal: ok, catalog: ok, redis: ok } } });

    render(<HealthPanel />);

    expect(await screen.findByText("Everything is responding.")).toBeInTheDocument();
    for (const label of ["Personal database", "Catalog database", "Redis"]) {
      expect(screen.getByText(label).closest("li")).toHaveTextContent("OK");
    }
  });

  it("names a down component in text, not just colour, from the 503 details", async () => {
    respond({
      error: {
        code: "service_unavailable",
        message: "Some services aren't responding right now.",
        details: {
          components: {
            personal: ok,
            catalog: ok,
            redis: { status: "down", reason: "unreachable" },
          },
        },
      },
    });

    render(<HealthPanel />);

    expect(
      await screen.findByText("Some services aren't responding right now."),
    ).toBeInTheDocument();
    expect(screen.getByText("Redis").closest("li")).toHaveTextContent("Down: not reachable");
    expect(screen.getByText("Catalog database").closest("li")).toHaveTextContent("OK");
  });

  it.each([
    ["the network fails", () => GET.mockRejectedValue(new TypeError("Failed to fetch"))],
    [
      "the proxy has no API address",
      () =>
        respond({
          error: { code: "api_not_configured", message: "The service isn't available right now." },
        }),
    ],
  ])("says the API isn't reachable when %s", async (_, arrange) => {
    arrange();

    render(<HealthPanel />);

    expect(
      await screen.findByText("The API isn't reachable. Is make dev running?"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});
