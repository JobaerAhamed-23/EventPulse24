import { afterEach, describe, expect, it, vi } from "vitest";

import DevHealthPage from "@/app/dev/health/page";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

describe("DevHealthPage", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("doesn't exist in production builds", () => {
    vi.stubEnv("NODE_ENV", "production");

    expect(() => DevHealthPage()).toThrow("NEXT_NOT_FOUND");
  });

  it("renders the health panel in development", () => {
    vi.stubEnv("NODE_ENV", "development");

    expect(DevHealthPage()).toBeTruthy();
  });
});
